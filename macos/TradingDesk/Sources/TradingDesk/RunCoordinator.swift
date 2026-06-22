import Foundation
import Observation

extension Notification.Name {
    /// Posted (userInfo["ticker"]) when a run finishes, so the Watchlist and
    /// Ticker Desk can re-pull the now-updated decision log without polling.
    static let runCompleted = Notification.Name("TradingDesk.runCompleted")
    /// Posted (userInfo["ticker", "running"]) when a ticker's run starts/ends,
    /// so the Watchlist can show a "running" indicator on that row.
    static let runStateChanged = Notification.Name("TradingDesk.runStateChanged")
}

/// Drives one analysis run against the backend: POST /runs, then consume the
/// SSE event stream and project it into observable state the Live Monitor and
/// Agent Theater render. Events are exactly the desk_adapter/desk_server schema.
@MainActor
@Observable
final class RunCoordinator {
    struct FeedItem: Identifiable {
        enum Kind { case agent, tool, toolNoData, debate, system }
        let id = UUID()
        let icon: String
        let title: String
        let subtitle: String
        let kind: Kind
    }

    struct Stats {
        var llmCalls = 0
        var tokensIn = 0
        var tokensOut = 0
        var elapsed = 0.0
    }

    let baseURL = DeskBackend.baseURL

    private(set) var running = false
    private(set) var phase = "idle"
    private(set) var nodeStates: [String: String] = [:]
    private(set) var feed: [FeedItem] = []
    private(set) var stats = Stats()
    private(set) var rating = ""
    private(set) var errorMessage: String?

    // Live-monitor timeline state.
    private(set) var startedAt: Date?
    /// When the run reached a terminal state (done/cancelled/error/stopped). Used
    /// to freeze the active node's elapsed so it stops counting after the run ends.
    private(set) var terminalAt: Date?
    private(set) var nodeStart: [String: Date] = [:]
    private(set) var nodeEnd: [String: Date] = [:]
    private(set) var investmentRound = 0
    private(set) var riskRound = 0
    private(set) var maxDebateRounds = 0
    private(set) var maxRiskRounds = 0

    private var runID: String?
    private var ticker = ""

    /// Per-node elapsed (live for the active node, fixed once completed, and
    /// frozen at `terminalAt` once the run ends so a never-finished node stops
    /// counting instead of ticking forever).
    func elapsed(for node: String, now: Date) -> TimeInterval? {
        guard let start = nodeStart[node] else { return nil }
        let end = nodeEnd[node] ?? (running ? now : (terminalAt ?? now))
        return end.timeIntervalSince(start)
    }

    var phaseLabel: String {
        switch phase {
        case "idle": return "idle"
        case "warming": return "warming up…"
        case "running": return "running"
        case "done": return rating.isEmpty ? "done" : "done · \(rating)"
        case "error": return "error"
        case "cancelled": return "cancelled"
        case "stopped": return "stopped"
        default: return phase
        }
    }

    func startRun(ticker: String) {
        guard !running else { return }
        self.ticker = ticker
        nodeStates = [:]; feed = []; stats = Stats(); rating = ""; errorMessage = nil; runID = nil
        nodeStart = [:]; nodeEnd = [:]; investmentRound = 0; riskRound = 0
        maxDebateRounds = 0; maxRiskRounds = 0; startedAt = Date(); terminalAt = nil
        running = true
        phase = "warming"
        NotificationCenter.default.post(name: .runStateChanged, object: nil,
                                        userInfo: ["ticker": ticker, "running": true])
        let body = Self.buildBody(ticker: ticker)
        Task { await execute(body: body) }
    }

    /// Build the run-config POST body from the active settings + Keychain keys.
    static func buildBody(ticker: String) -> [String: Any] {
        let settings = SettingsStore.shared
        let info = CapabilitiesStore.shared.provider(settings.provider)

        var keys: [String: String] = [:]
        if let env = info?.apiKeyEnv, let value = KeychainStore.get(account: env), !value.isEmpty {
            keys[env] = value
        }
        if let fred = KeychainStore.get(account: "FRED_API_KEY"), !fred.isEmpty {
            keys["FRED_API_KEY"] = fred
        }

        var body: [String: Any] = [
            "ticker": ticker,
            "trade_date": settings.tradeDateString,
            "asset_type": Instruments.isCrypto(ticker) ? "crypto" : "stock",
            "analysts": settings.analysts.isEmpty ? ["market"] : settings.analysts,
            "profile_name": settings.provider,
            "llm_provider": settings.provider,
            "deep_think_llm": settings.deepModel,
            "quick_think_llm": settings.quickModel,
            "max_debate_rounds": settings.debateRounds,
            "max_risk_discuss_rounds": settings.riskRounds,
            "output_language": settings.outputLanguage,
            "keys": keys,
        ]
        if let url = info?.baseURL { body["backend_url"] = url }
        return body
    }

    func cancel() {
        guard let id = runID else { return }
        Task {
            var req = URLRequest(url: baseURL.appending(path: "runs/\(id)/cancel"))
            req.httpMethod = "POST"
            _ = try? await URLSession.shared.data(for: req)
        }
    }

    private func execute(body: [String: Any]) async {
        do {
            var post = URLRequest(url: baseURL.appending(path: "runs"))
            post.httpMethod = "POST"
            post.setValue("application/json", forHTTPHeaderField: "Content-Type")
            post.httpBody = try JSONSerialization.data(withJSONObject: body)
            let (data, resp) = try await URLSession.shared.data(for: post)
            guard (resp as? HTTPURLResponse)?.statusCode == 200,
                  let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let id = obj["run_id"] as? String
            else {
                throw RunError.message("could not start run: \(String(data: data, encoding: .utf8)?.prefix(160) ?? "")")
            }
            runID = id
            try await consumeEvents(runID: id)
        } catch {
            errorMessage = (error as? RunError)?.text ?? error.localizedDescription
            if phase != "done" { phase = "error" }
        }
        running = false
        if !["done", "error", "cancelled"].contains(phase) { phase = "stopped" }
        terminalAt = Date()  // freeze the active node's timer at the end of the run
        NotificationCenter.default.post(name: .runStateChanged, object: nil,
                                        userInfo: ["ticker": ticker, "running": false])
    }

    /// Consume the run's SSE stream, resuming via `Last-Event-ID` across transient
    /// transport drops. The run keeps executing on the backend even if the stream
    /// drops, so a blip must not be mistaken for a failed run — we resume from the
    /// last seq and only give up after repeated reconnects make no progress.
    private func consumeEvents(runID id: String) async throws {
        func isTerminal() -> Bool { ["done", "error", "cancelled"].contains(phase) }
        var lastSeq = 0
        var stalledReconnects = 0
        while true {
            let before = lastSeq
            do {
                var stream = URLRequest(url: baseURL.appending(path: "runs/\(id)/events"))
                stream.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                if lastSeq > 0 { stream.setValue(String(lastSeq), forHTTPHeaderField: "Last-Event-ID") }
                stream.timeoutInterval = 900
                let (bytes, sresp) = try await URLSession.shared.bytes(for: stream)
                guard (sresp as? HTTPURLResponse)?.statusCode == 200 else { throw RunError.message("event stream failed") }
                for try await line in bytes.lines {
                    guard line.hasPrefix("data: ") else { continue }
                    let payload = String(line.dropFirst(6))
                    if let d = payload.data(using: .utf8),
                       let ev = try? JSONSerialization.jsonObject(with: d) as? [String: Any] {
                        if let seq = ev["seq"] as? Int { lastSeq = max(lastSeq, seq) }
                        apply(ev)
                    }
                }
            } catch {
                // Transport drop — the run is still alive server-side; fall through
                // to the terminal/resume check below rather than failing the run.
            }
            if isTerminal() { return }
            // Clean end with no terminal event, or a drop: resume from lastSeq.
            // Reset the budget whenever a connection actually delivered new events.
            stalledReconnects = lastSeq > before ? 0 : stalledReconnects + 1
            if stalledReconnects > 6 { throw RunError.message("lost the connection to the run") }
            try? await Task.sleep(for: .seconds(min(Double(stalledReconnects), 5)))
        }
    }

    private func apply(_ ev: [String: Any]) {
        guard let type = ev["type"] as? String else { return }
        switch type {
        case "warming": phase = "warming"
        case "started":
            phase = "running"
            maxDebateRounds = ev["max_debate_rounds"] as? Int ?? 0
            maxRiskRounds = ev["max_risk_discuss_rounds"] as? Int ?? 0
        case "node_status":
            if let node = ev["node"] as? String, let state = ev["state"] as? String {
                nodeStates[node] = state
                if state == "in_progress", nodeStart[node] == nil { nodeStart[node] = Date() }
                if state == "completed" {
                    if nodeStart[node] == nil { nodeStart[node] = Date() }
                    nodeEnd[node] = Date()
                }
            }
        case "agent_step":
            if let text = ev["text"] as? String {
                let node = (ev["node"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? "Agent"
                feed.append(.init(icon: "brain", title: node, subtitle: snippet(text), kind: .agent))
            }
        case "tool_call":
            let name = ev["name"] as? String ?? "tool"
            let args = (ev["args"] as? [String: Any]).map(compactArgs) ?? ""
            feed.append(.init(icon: "wrench", title: "called \(name)", subtitle: args, kind: .tool))
        case "tool_result":
            let name = ev["name"] as? String ?? "tool"
            let noData = (ev["data_status"] as? String) == "no_data"
            feed.append(.init(
                icon: noData ? "exclamationmark.triangle" : "tray.full",
                title: noData ? "\(name): no data available" : "\(name) → result",
                subtitle: snippet((ev["preview"] as? String) ?? ""),
                kind: noData ? .toolNoData : .tool))
        case "debate_turn":
            let round = ev["round"] as? Int ?? 0
            if (ev["debate"] as? String) == "risk" { riskRound = max(riskRound, round) }
            else { investmentRound = max(investmentRound, round) }
            if let speaker = ev["speaker"] as? String, let text = ev["text"] as? String {
                feed.append(.init(icon: "bubble.left.and.bubble.right", title: speaker, subtitle: snippet(text), kind: .debate))
            }
        case "stats":
            stats.llmCalls = ev["llm_calls"] as? Int ?? stats.llmCalls
            stats.tokensIn = ev["tokens_in"] as? Int ?? stats.tokensIn
            stats.tokensOut = ev["tokens_out"] as? Int ?? stats.tokensOut
            stats.elapsed = ev["elapsed_s"] as? Double ?? stats.elapsed
        case "done":
            phase = "done"
            rating = ev["rating"] as? String ?? ""
            feed.append(.init(icon: "checkmark.seal", title: "Done — \(rating)", subtitle: "", kind: .system))
            // The engine has already written the decision log by the time `done`
            // arrives — refresh the watchlist and notify the desk to re-pull.
            let finished = ticker
            Task { await WatchlistStore.shared.load() }
            NotificationCenter.default.post(name: .runCompleted, object: nil, userInfo: ["ticker": finished])
        case "error":
            phase = "error"
            errorMessage = ev["message"] as? String
            feed.append(.init(icon: "xmark.octagon", title: "Error", subtitle: errorMessage ?? "", kind: .system))
        case "cancelled":
            phase = "cancelled"
            feed.append(.init(icon: "stop.circle", title: "Cancelled", subtitle: "", kind: .system))
        default:
            break
        }
    }

    private func snippet(_ s: String, _ limit: Int = 160) -> String {
        let flat = s.replacingOccurrences(of: "\n", with: " ").trimmingCharacters(in: .whitespaces)
        return flat.count > limit ? String(flat.prefix(limit)) + "…" : flat
    }

    private func compactArgs(_ args: [String: Any]) -> String {
        args.map { "\($0.key)=\($0.value)" }.sorted().joined(separator: ", ")
    }

    private enum RunError: Error {
        case message(String)
        var text: String {
            switch self {
            case .message(let s): return s
            }
        }
    }
}
