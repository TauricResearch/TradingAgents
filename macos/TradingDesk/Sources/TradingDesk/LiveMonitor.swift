import SwiftUI

/// Detail column: drives a run via RunCoordinator and renders it live as a
/// calm-but-alive **pipeline timeline** (stage progress, per-node timing, debate
/// rounds), a slim **cost/stats meter**, and a refined **Agent Theater** feed.
struct LiveMonitorView: View {
    let symbol: String
    var backend: DockerBackendController
    /// Shared from RootSplitView's RunRegistry (one per symbol) so a run survives
    /// ticker switches instead of being discarded with this view's state.
    let run: RunCoordinator
    var openSettings: () -> Void

    private var settings: SettingsStore { .shared }
    private var needsKey: Bool { !settings.providerReady }
    private var showHero: Bool { run.feed.isEmpty && !run.running }

    /// Pipeline grouped into glanceable stages (debates collapse their rounds).
    private struct Stage: Identifiable {
        let title: String
        let nodes: [String]
        let debate: Debate?
        var id: String { title }
        enum Debate { case investment, risk }
    }
    private let stages: [Stage] = [
        .init(title: "Market analyst", nodes: ["Market Analyst"], debate: nil),
        .init(title: "Sentiment analyst", nodes: ["Sentiment Analyst"], debate: nil),
        .init(title: "News analyst", nodes: ["News Analyst"], debate: nil),
        .init(title: "Fundamentals analyst", nodes: ["Fundamentals Analyst"], debate: nil),
        .init(title: "Bull vs bear debate", nodes: ["Bull Researcher", "Bear Researcher"], debate: .investment),
        .init(title: "Research manager", nodes: ["Research Manager"], debate: nil),
        .init(title: "Trader", nodes: ["Trader"], debate: nil),
        .init(title: "3-way risk debate", nodes: ["Aggressive Analyst", "Conservative Analyst", "Neutral Analyst"], debate: .risk),
        .init(title: "Portfolio manager", nodes: ["Portfolio Manager"], debate: nil),
    ]

    var body: some View {
        // One periodic tick drives the live timers (active-node + total elapsed).
        TimelineView(.periodic(from: .now, by: 1)) { context in
            content(now: context.date)
        }
    }

    private func content(now: Date) -> some View {
        VStack(alignment: .leading, spacing: Space.m) {
            header(now: now)
            configLine
            if showHero {
                Spacer(minLength: 0)
                hero
                Spacer(minLength: 0)
            } else {
                timeline(now: now)
                Rectangle().fill(Palette.separator).frame(height: 0.5)
                feedSection
            }
        }
        .padding(Space.l)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .safeAreaInset(edge: .bottom) {
            if !showHero {
                costMeter(now: now)
                    .padding(.horizontal, Space.l)
                    .padding(.bottom, Space.m)
            }
        }
    }

    // MARK: Header

    private func header(now: Date) -> some View {
        HStack(spacing: Space.s) {
            Text(symbol).font(.tickerTitle)
            Text(phaseText(now: now)).font(.caption).foregroundStyle(phaseColor).monospacedDigit()
            Spacer()
            if run.running {
                Button { run.cancel() } label: { Label("Stop", systemImage: "stop.fill") }
                    .buttonStyle(DestructiveButtonStyle())
            } else {
                Button { run.startRun(ticker: symbol) } label: { Label("Run analysis", systemImage: "play.fill") }
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(backend.state != .ready || needsKey)
            }
        }
    }

    private func phaseText(now: Date) -> String {
        guard run.running, let started = run.startedAt else { return run.phaseLabel }
        return "running · \(Self.mmss(now.timeIntervalSince(started)))"
    }

    private var phaseColor: Color {
        switch run.phase {
        case "running", "warming": return Palette.running
        case "done": return Palette.positive
        case "error": return Palette.negative
        default: return .secondary
        }
    }

    private var configLine: some View {
        HStack(spacing: Space.xs) {
            Image(systemName: "slider.horizontal.3").font(.caption2).foregroundStyle(.secondary)
            Text("\(settings.provider) · \(settings.deepModel) · \(settings.analysts.count) analysts · depth \(depthLabel)")
                .font(.caption).foregroundStyle(.secondary).lineLimit(1)
            Spacer()
        }
    }

    /// Round count for the config line — a single number when the debate and risk
    /// rounds match, else "debate/risk".
    private var depthLabel: String {
        settings.debateRounds == settings.riskRounds
            ? "\(settings.debateRounds)"
            : "\(settings.debateRounds)/\(settings.riskRounds)"
    }

    // MARK: Idle / gated hero

    @ViewBuilder private var hero: some View {
        if needsKey {
            PremiumEmptyState(icon: "key.fill", title: "Set your API key",
                              message: "Add your \(settings.provider) key in Settings to run an analysis.",
                              tint: Palette.warning, actionTitle: "Open Settings", action: openSettings)
        } else if backend.state != .ready {
            PremiumEmptyState(icon: "hourglass", title: "Waiting for the backend",
                              message: "The engine is starting up — this takes a few seconds on first launch.",
                              tint: Palette.neutral)
        } else {
            PremiumEmptyState(icon: "sparkles", title: "Ready to run \(symbol)",
                              message: "Press Run analysis to watch the agents research and debate live.",
                              tint: Palette.accent, actionTitle: "Run analysis",
                              action: { run.startRun(ticker: symbol) })
        }
    }

    // MARK: Pipeline timeline

    private func timeline(now: Date) -> some View {
        // The connecting spine is a BACKGROUND of the node stack so it's bounded to
        // the nodes' height (first dot → last dot). As a flexible-height rectangle
        // inside a ZStack it instead stretched the timeline to fill leftover space,
        // trailing a line well past the last node once a run finished.
        VStack(alignment: .leading, spacing: Space.s) {
            ForEach(stages) { stage in stageRow(stage, now: now) }
            if let term = terminalInfo { terminalRow(term) }
        }
        .background(alignment: .topLeading) {
            Rectangle().fill(Palette.separator)
                .frame(width: 1.5)
                .padding(.leading, 7)
                .padding(.vertical, 11)
        }
    }

    /// The terminal status of a finished run, surfaced as the last node on the
    /// timeline: "Done" (green), "Cancelled" (muted), or "Failed" (red). Nil while
    /// the run is still going.
    private var terminalInfo: (icon: String, label: String, color: Color, trailing: String)? {
        guard !run.running else { return nil }
        switch run.phase {
        case "done":
            return ("checkmark.circle.fill", "Done", Palette.positive, run.rating)
        case "cancelled", "stopped":
            return ("stop.circle.fill", "Cancelled", Palette.neutral, "")
        case "error":
            return ("exclamationmark.octagon.fill", "Failed", Palette.negative, "")
        default:
            return nil
        }
    }

    /// A surface-filled circle that masks the timeline spine behind a node dot.
    private var spineMask: some View { Circle().fill(Palette.surface).frame(width: 14, height: 14) }

    private func terminalRow(_ term: (icon: String, label: String, color: Color, trailing: String)) -> some View {
        HStack(spacing: Space.s) {
            ZStack {
                spineMask
                Image(systemName: term.icon).font(.system(size: 13)).foregroundStyle(term.color)
            }
            .frame(width: 16)
            Text(term.label).font(.system(size: 13, weight: .semibold)).foregroundStyle(term.color)
            Spacer(minLength: Space.s)
            if !term.trailing.isEmpty {
                Text(term.trailing).font(.caption.weight(.medium)).foregroundStyle(.secondary)
            }
        }
    }

    private func stageRow(_ stage: Stage, now: Date) -> some View {
        let state = stageState(stage)
        return HStack(spacing: Space.s) {
            dot(state).frame(width: 16)
            Text(stage.title)
                .font(.system(size: 13, weight: state == .active ? .medium : .regular))
                .foregroundStyle(state == .pending ? Color.secondary.opacity(0.7) : .primary)
            Spacer(minLength: Space.s)
            Text(rightValue(stage, state: state, now: now))
                .font(.caption).monospacedDigit()
                .foregroundStyle(state == .active && run.running ? Palette.accent : .secondary)
        }
    }

    @ViewBuilder private func dot(_ state: StageState) -> some View {
        ZStack {
            spineMask
            switch state {
            case .completed:
                Image(systemName: "circle.fill").font(.system(size: 9)).foregroundStyle(Palette.positive)
            case .active:
                if run.running {
                    Image(systemName: "circle.fill").font(.system(size: 10)).foregroundStyle(Palette.accent)
                        .symbolEffect(.pulse, options: .repeating)
                } else {
                    // The run ended while this node was active — static, muted, no pulse.
                    Image(systemName: "circle.fill").font(.system(size: 9)).foregroundStyle(Palette.neutral)
                }
            case .pending:
                Image(systemName: "circle").font(.system(size: 9)).foregroundStyle(Palette.neutral.opacity(0.5))
            }
        }
    }

    private enum StageState { case pending, active, completed }

    private func stageState(_ stage: Stage) -> StageState {
        let states = stage.nodes.map { run.nodeStates[$0] }
        if !states.isEmpty, states.allSatisfy({ $0 == "completed" }) { return .completed }
        if states.contains("in_progress") || states.contains("completed") { return .active }
        return .pending
    }

    private func rightValue(_ stage: Stage, state: StageState, now: Date) -> String {
        switch state {
        case .pending:
            return "—"
        case .completed:
            let secs = stage.nodes.compactMap { run.elapsed(for: $0, now: now) }.reduce(0, +)
            return Self.mmss(secs)
        case .active:
            if let debate = stage.debate {
                let (cur, total) = debate == .risk
                    ? (run.riskRound, run.maxRiskRounds) : (run.investmentRound, run.maxDebateRounds)
                if total > 0 { return "round \(max(cur, 1))/\(total)" }
            }
            if let secs = stage.nodes.compactMap({ run.elapsed(for: $0, now: now) }).max() {
                return Self.mmss(secs)
            }
            return ""
        }
    }

    // MARK: Cost / stats meter

    private func costMeter(now: Date) -> some View {
        VStack(alignment: .leading, spacing: Space.s) {
            HStack {
                Text("\(run.stats.llmCalls) llm calls · \(tokenLabel) tokens")
                    .font(.caption).foregroundStyle(.secondary).monospacedDigit()
                Spacer()
                Text(Self.mmss(elapsedSeconds(now: now)))
                    .font(.callout.weight(.medium)).monospacedDigit().foregroundStyle(.secondary)
            }
        }
        .card()
    }

    private var tokenLabel: String {
        let total = run.stats.tokensIn + run.stats.tokensOut
        return total >= 1000 ? "\(total / 1000)k" : "\(total)"
    }

    private func elapsedSeconds(now: Date) -> TimeInterval {
        guard let started = run.startedAt else { return run.stats.elapsed }
        return run.running ? now.timeIntervalSince(started) : run.stats.elapsed
    }

    // MARK: Agent theater feed

    private var feedSection: some View {
        VStack(alignment: .leading, spacing: Space.s) {
            Text("AGENT THEATER").font(.sectionLabel).foregroundStyle(.tertiary)
            if run.feed.isEmpty {
                Text(run.running ? "warming up…" : "")
                    .font(.caption).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: Space.s) {
                            ForEach(Array(run.feed.enumerated()), id: \.element.id) { idx, item in
                                FeedRow(item: item, isLatest: idx == run.feed.count - 1)
                                    .id(item.id)
                                    .transition(.move(edge: .bottom).combined(with: .opacity))
                            }
                        }
                        .animation(.easeOut(duration: 0.25), value: run.feed.count)
                    }
                    .onChange(of: run.feed.count) { _, _ in
                        if let last = run.feed.last {
                            withAnimation(.easeOut(duration: 0.25)) { proxy.scrollTo(last.id, anchor: .bottom) }
                        }
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }

    private static func mmss(_ secs: TimeInterval) -> String {
        let s = max(0, Int(secs))
        return String(format: "%d:%02d", s / 60, s % 60)
    }
}

/// One streamed event as an action card in the Agent Theater — tinted by kind,
/// with a highlighted border on the most recent (active) card.
struct FeedRow: View {
    let item: RunCoordinator.FeedItem
    var isLatest = false

    private var tint: Color {
        switch item.kind {
        case .agent: return Palette.accent
        case .tool: return Palette.neutral
        case .toolNoData: return Palette.warning
        case .debate: return Color(light: Color(red: 0.16, green: 0.58, blue: 0.49),
                                   dark: Color(red: 0.36, green: 0.80, blue: 0.69))
        case .system: return Palette.positive
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: Space.s) {
            Image(systemName: item.icon).foregroundStyle(tint).frame(width: 18)
            VStack(alignment: .leading, spacing: 2) {
                Text(item.title).font(.cardTitle)
                if !item.subtitle.isEmpty {
                    Text(item.subtitle).font(.caption2).foregroundStyle(.secondary).lineLimit(2)
                }
            }
            Spacer(minLength: 0)
        }
        .tintedCard(tint)
        .overlay {
            if isLatest {
                RoundedRectangle(cornerRadius: Radius.card).strokeBorder(tint.opacity(0.45), lineWidth: 1)
            }
        }
    }
}
