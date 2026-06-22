import Combine
import SwiftUI

/// The center column: a selected ticker's run Library + Decisions Journal, both
/// fed live from the engine (`/journal`, `/reports`). Reloads on ticker switch
/// and whenever a run for this ticker completes (RunCoordinator broadcasts).
struct TickerDeskView: View {
    let symbol: String
    /// Which tab to show — bound to RootSplitView so a command-palette jump can
    /// deep-link to Library (a run) or Journal (a decision).
    @Binding var tab: DeskTab
    /// A run date to auto-open in the Library (consumed once by LibraryView).
    @Binding var openRunDate: String?
    /// Cached per-symbol stores (from DeskStores) so switching back to a ticker
    /// shows its journal/library instantly instead of flashing the empty state.
    let journalStore: JournalStore
    let reportStore: ReportStore

    enum DeskTab: String, CaseIterable, Identifiable {
        case library = "Library"
        case journal = "Journal"
        var id: String { rawValue }
    }

    private var name: String { Instruments.name(symbol) }
    private var benchmark: String { Instruments.benchmark(symbol) }
    private var entries: [JournalEntry] { journalStore.entries }

    private var hitRate: String {
        let resolved = entries.filter { !$0.pending }
        guard !resolved.isEmpty else { return "—" }
        let wins = resolved.filter { ($0.alpha ?? 0) > 0 }.count
        return "\(wins)/\(resolved.count)"
    }

    private var cumulativeAlpha: Double {
        entries.compactMap(\.alpha).reduce(0, +)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Space.m) {
            header
            SegmentedTabs(items: DeskTab.allCases, title: { $0.rawValue }, selection: $tab)

            if !entries.isEmpty {
                Text("hit rate \(hitRate) · cumulative α \(DeskFormat.signedPercent(cumulativeAlpha)) · low n")
                    .font(.caption).foregroundStyle(.secondary).monospacedDigit()
            }

            switch tab {
            case .journal:
                if journalStore.loadedTicker == nil {
                    loadingPane
                } else if entries.isEmpty {
                    PremiumEmptyState(
                        icon: "book.closed",
                        title: "No decisions yet",
                        message: "Run \(symbol) in the Live Monitor to record its first decision.",
                        tint: Palette.neutral
                    )
                } else {
                    JournalList(entries: entries, symbol: symbol)
                }
            case .library:
                if reportStore.loadedTicker == nil {
                    loadingPane
                } else {
                    LibraryView(docs: reportStore.docs, openDate: $openRunDate)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(Space.l)
        .task(id: symbol) { await refresh() }
        .onReceive(NotificationCenter.default.publisher(for: .runCompleted)) { note in
            if (note.userInfo?["ticker"] as? String)?.uppercased() == symbol.uppercased() {
                Task { await refresh() }
            }
        }
    }

    private var header: some View {
        HStack(alignment: .firstTextBaseline, spacing: Space.s) {
            Text(symbol).font(.tickerTitle)
            Text("\(name) · α vs \(benchmark)")
                .font(.caption).foregroundStyle(.secondary)
            Spacer()
            if journalStore.loading { ProgressView().controlSize(.small) }
            Button { Task { await refresh() } } label: { Image(systemName: "arrow.clockwise") }
                .buttonStyle(IconButtonStyle())
                .help("Refresh from the engine's decision log")
        }
    }

    private var loadingPane: some View {
        ProgressView().controlSize(.small).frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func refresh() async {
        await journalStore.load(ticker: symbol)
        await reportStore.loadList(ticker: symbol)
    }
}

/// The Decisions Journal: each call as a clean row — big date, rating chip, and
/// realized α / raw / holding (or a pending note).
struct JournalList: View {
    let entries: [JournalEntry]
    let symbol: String

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: Space.l) {
                ForEach(entries) { entry in
                    JournalEntryRow(entry: entry, symbol: symbol)
                }
            }
            .padding(.vertical, Space.s)
        }
    }
}

private struct JournalEntryRow: View {
    let entry: JournalEntry
    let symbol: String

    var body: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            HStack {
                Text(DeskFormat.shortDate(entry.date))
                    .font(.system(size: 15, weight: .semibold))
                Spacer()
                RatingChip(rating: entry.rating)
            }
            if entry.pending {
                Text("pending — resolves on next \(symbol) run")
                    .font(.caption).italic().foregroundStyle(.tertiary)
            } else {
                HStack(spacing: Space.xs) {
                    Text(DeskFormat.signedPercent(entry.alpha ?? 0))
                        .font(.callout.weight(.semibold)).monospacedDigit()
                        .foregroundStyle(Palette.gain(entry.alpha ?? 0))
                    Text("α · raw \(DeskFormat.signedPercent(entry.raw ?? 0)) · \(entry.holdingDays ?? 0)d")
                        .font(.caption).foregroundStyle(.secondary).monospacedDigit()
                }
            }
        }
    }
}

/// Small formatting helpers shared by the desk surfaces.
enum DeskFormat {
    /// 0.031 -> "+3.1%", -0.004 -> "-0.4%".
    static func signedPercent(_ value: Double) -> String {
        let n = (value * 100).formatted(.number.precision(.fractionLength(1)))
        return (value >= 0 ? "+" : "") + n + "%"
    }

    /// "2025-06-13" -> "Jun 13"; passes through anything non-ISO unchanged.
    static func shortDate(_ s: String) -> String {
        guard let date = iso.date(from: s) else { return s }
        return short.string(from: date)
    }

    /// Parse / format the engine's ISO day format ("yyyy-MM-dd").
    static func parseISO(_ s: String) -> Date? { iso.date(from: s) }
    static func isoString(_ date: Date) -> String { iso.string(from: date) }

    private static let iso: DateFormatter = {
        let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"; return f
    }()
    private static let short: DateFormatter = {
        let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "MMM d"; return f
    }()
}

// LiveMonitorView lives in LiveMonitor.swift; LibraryView in Library.swift.

/// Live backend status (sidebar footer): one compact, non-truncating line —
/// a state dot plus the full status, including the host:port when ready.
struct BackendStatusView: View {
    var backend: DockerBackendController

    private var color: Color {
        switch backend.state {
        case .ready: return Palette.positive
        case .failed, .dockerMissing: return Palette.negative
        default: return Palette.warning
        }
    }

    private var text: String {
        switch backend.state {
        case .idle: return "Backend idle"
        case .checkingDocker: return "Checking Docker…"
        case .dockerMissing: return backend.detail.isEmpty ? "Docker not available" : backend.detail
        case .preparingImage: return backend.detail.isEmpty ? "Preparing engine image…" : backend.detail
        case .starting: return "Starting backend…"
        case .ready: return "Backend ready · \(host)"
        case .failed(let message): return "Backend failed — \(message)"
        case .stopped: return "Backend stopped"
        }
    }

    private var host: String {
        guard let h = backend.baseURL.host else { return backend.baseURL.absoluteString }
        return backend.baseURL.port.map { "\(h):\($0)" } ?? h
    }

    var body: some View {
        HStack(alignment: .top, spacing: Space.s) {
            Circle().fill(color).frame(width: 8, height: 8).padding(.top, 4)
            Text(text)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
    }
}
