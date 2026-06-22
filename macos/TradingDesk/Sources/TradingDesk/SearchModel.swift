import Foundation
import Observation

/// One ticker hit in the command palette: a real, listed instrument returned by
/// the backend `/search` (Yahoo Finance) — symbol, company name, exchange.
struct TickerSearchResult: Identifiable, Equatable {
    var id: String { symbol }
    let symbol: String
    let name: String
    let exchange: String
}

/// One decision hit in the command palette (from the engine's journal).
struct SearchDecision: Identifiable, Equatable {
    var id: String { "\(ticker)-\(date)" }
    let ticker: String
    let date: String
    let rating: Rating?
}

/// Backs the command palette. Tickers come from a debounced live `/search`
/// lookup (real companies). Runs (`/reports`) and decisions (`/journal`) are
/// loaded once when the palette opens and filtered client-side, so one query
/// surfaces all three result kinds the user can jump to.
@MainActor
@Observable
final class SearchModel {
    let baseURL = DeskBackend.baseURL

    var query = ""
    private(set) var results: [TickerSearchResult] = []      // tickers (live /search)
    private(set) var loading = false

    private(set) var allRuns: [ReportSummary] = []           // corpus (loaded on open)
    private(set) var allDecisions: [SearchDecision] = []

    private var task: Task<Void, Never>?

    var trimmed: String { query.trimmingCharacters(in: .whitespacesAndNewlines) }
    var isActive: Bool { !trimmed.isEmpty }

    func reset() {
        task?.cancel()
        query = ""
        results = []
        loading = false
    }

    // MARK: Tickers — debounced live lookup

    /// Debounced live ticker search; call on every query change.
    func search() {
        task?.cancel()
        let q = trimmed
        guard !q.isEmpty else {
            results = []
            loading = false
            return
        }
        loading = true
        task = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(250))
            if Task.isCancelled { return }
            await self?.fetchTickers(q)
        }
    }

    private func fetchTickers(_ q: String) async {
        var comps = URLComponents(url: baseURL.appending(path: "search"), resolvingAgainstBaseURL: false)!
        comps.queryItems = [URLQueryItem(name: "q", value: q)]
        guard let url = comps.url else { return }
        var req = URLRequest(url: url)
        req.timeoutInterval = 8

        let data: Data
        let resp: URLResponse
        do {
            (data, resp) = try await URLSession.shared.data(for: req)
        } catch {
            if !Task.isCancelled { loading = false }
            return
        }
        if Task.isCancelled { return }
        loading = false
        guard (resp as? HTTPURLResponse)?.statusCode == 200,
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let arr = obj["results"] as? [[String: Any]]
        else {
            results = []
            return
        }
        results = arr.compactMap { r in
            guard let symbol = r["symbol"] as? String else { return nil }
            return TickerSearchResult(
                symbol: symbol,
                name: r["name"] as? String ?? "",
                exchange: r["exchange"] as? String ?? ""
            )
        }
    }

    // MARK: Runs + decisions — loaded once, filtered client-side

    /// Load the full run + decision corpus (cheap; small). Call when the palette
    /// opens so jumping to a run/decision needs no per-keystroke network.
    func loadCorpus() async {
        async let runs = fetchRuns()
        async let decisions = fetchDecisions()
        allRuns = await runs
        allDecisions = await decisions
    }

    var runResults: [ReportSummary] {
        guard isActive else { return [] }
        return allRuns.filter { matches($0.ticker, $0.date) }
    }

    var decisionResults: [SearchDecision] {
        guard isActive else { return [] }
        return allDecisions.filter { matches($0.ticker, $0.date) }
    }

    private func matches(_ ticker: String, _ date: String) -> Bool {
        ticker.localizedCaseInsensitiveContains(trimmed) || date.localizedCaseInsensitiveContains(trimmed)
    }

    private func fetchRuns() async -> [ReportSummary] {
        guard let (data, resp) = try? await URLSession.shared.data(from: baseURL.appending(path: "reports")),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let arr = obj["reports"] as? [[String: Any]]
        else { return [] }
        return arr.compactMap { r in
            guard let t = r["ticker"] as? String, let d = r["date"] as? String else { return nil }
            return ReportSummary(ticker: t, date: d, rating: Rating(rawValue: (r["rating"] as? String) ?? ""))
        }
    }

    private func fetchDecisions() async -> [SearchDecision] {
        guard let (data, resp) = try? await URLSession.shared.data(from: baseURL.appending(path: "journal")),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let arr = obj["entries"] as? [[String: Any]]
        else { return [] }
        return arr.compactMap { e in
            guard let t = e["ticker"] as? String, let d = e["date"] as? String else { return nil }
            return SearchDecision(ticker: t.uppercased(), date: d, rating: Rating(rawValue: (e["rating"] as? String) ?? ""))
        }
    }
}
