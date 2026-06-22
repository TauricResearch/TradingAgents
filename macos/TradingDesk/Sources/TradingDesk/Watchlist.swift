import SwiftUI

/// The Watchlist sidebar — every tracked name with its latest rating, a price
/// sparkline, a running indicator, and a stale badge. A `List` (for native swipe
/// actions) with custom rows that draw their own soft-card selection (no system
/// blue highlight). Swipe a row left to ★ star (pin to top) or delete it; "+"
/// and ⌘K open the command palette to add tickers.
struct WatchlistSidebar: View {
    let tickers: [WatchlistTicker]
    @Binding var selection: String?
    var backend: DockerBackendController
    var runningSymbols: Set<String>
    var onRemove: (String) -> Void
    var onTogglePin: (String) -> Void
    var onOpenSettings: () -> Void

    var body: some View {
        List {
            Section {
                ForEach(tickers, id: \.rowIdentity) { ticker in
                    WatchlistRow(ticker: ticker,
                                 isSelected: selection == ticker.symbol,
                                 isRunning: runningSymbols.contains(ticker.symbol))
                        // Zero horizontal list insets so the swipe buttons span the
                        // full row width (flush-right, no gap); the row's own
                        // padding gives the card its side margins.
                        .listRowInsets(EdgeInsets(top: 2, leading: 0, bottom: 2, trailing: 0))
                        .listRowSeparator(.hidden)
                        .listRowBackground(Color.clear)
                        .contentShape(Rectangle())
                        .onTapGesture { selection = ticker.symbol }
                        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                            Button(role: .destructive) { onRemove(ticker.symbol) } label: {
                                Label("Delete", systemImage: "trash").labelStyle(.iconOnly)
                            }
                            Button {
                                // Toggling pin changes the row's `rowIdentity`, so the
                                // List rebuilds a fresh cell (zero swipe offset) at the
                                // new pinned-first position instead of moving the
                                // offset-stuck cell. No transaction-deferral needed.
                                onTogglePin(ticker.symbol)
                            } label: {
                                Label(ticker.pinned ? "Unstar" : "Star",
                                      systemImage: ticker.pinned ? "star.slash.fill" : "star.fill")
                                    .labelStyle(.iconOnly)
                            }
                            .tint(Palette.star)
                        }
                        .contextMenu {
                            Button(ticker.pinned ? "Unstar \(ticker.symbol)" : "Star \(ticker.symbol)") {
                                onTogglePin(ticker.symbol)
                            }
                            Button("Remove \(ticker.symbol)", role: .destructive) { onRemove(ticker.symbol) }
                        }
                }
            } header: {
                HStack {
                    Text("Watchlist").font(.sectionLabel).foregroundStyle(.secondary)
                    Spacer()
                    Button { NotificationCenter.default.post(name: .openSpotlight, object: nil) } label: {
                        Image(systemName: "plus")
                    }
                    .buttonStyle(IconButtonStyle())
                    .help("Add a ticker (⌘K)")
                }
            }
        }
        .listStyle(.sidebar)
        .scrollContentBackground(.hidden)
        .safeAreaInset(edge: .bottom, spacing: 0) { footer }
    }

    private var footer: some View {
        VStack(spacing: 0) {
            Rectangle().fill(Palette.separator).frame(height: 0.5)
            HStack(spacing: Space.s) {
                BackendStatusView(backend: backend)
                Button(action: onOpenSettings) { Image(systemName: "gearshape") }
                    .buttonStyle(IconButtonStyle())
                    .keyboardShortcut(",", modifiers: .command)
                    .help("Settings")
            }
            .padding(.horizontal, Space.m)
            .padding(.vertical, Space.s)
        }
    }
}

struct WatchlistRow: View {
    let ticker: WatchlistTicker
    var isSelected: Bool = false
    var isRunning: Bool = false
    @State private var hovering = false

    private var latest: JournalEntry? { ticker.latest }

    var body: some View {
        VStack(alignment: .leading, spacing: Space.s) {
            HStack(spacing: Space.s) {
                Text(ticker.symbol).font(.system(size: 15, weight: .semibold))
                if ticker.pinned {
                    Image(systemName: "star.fill").font(.system(size: 9)).foregroundStyle(Palette.star)
                }
                if let days = staleDays { staleBadge(days) }
                Spacer(minLength: Space.s)
                if isRunning {
                    runningBadge
                } else if let rating = latest?.rating {
                    RatingChip(rating: rating)
                }
            }
            secondary
        }
        .padding(.horizontal, Space.m)
        .padding(.vertical, Space.s + 1)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(rowBackground, in: RoundedRectangle(cornerRadius: Radius.card))
        .contentShape(RoundedRectangle(cornerRadius: Radius.card))
        .onHover { hovering = $0 }
        .animation(.easeOut(duration: 0.12), value: hovering)
        .padding(.horizontal, Space.xs)  // slim card side margins (list insets are 0)
    }

    private var rowBackground: Color {
        if isSelected { return Palette.selection }
        return hovering ? Palette.selection.opacity(0.5) : .clear
    }

    private var runningBadge: some View {
        HStack(spacing: 4) {
            Image(systemName: "circle.fill").font(.system(size: 6))
                .foregroundStyle(Palette.running)
                .symbolEffect(.pulse, options: .repeating)
            Text("running").font(.caption2).foregroundStyle(Palette.running)
        }
    }

    /// A sparkline when we have a price series; otherwise a compact status line.
    @ViewBuilder private var secondary: some View {
        if ticker.series.count > 1 {
            Sparkline(points: ticker.series, color: trendColor).frame(height: 22)
        } else if let latest {
            HStack(spacing: Space.xs) {
                if let raw = latest.raw {
                    Text(raw, format: .percent.precision(.fractionLength(1)))
                        .font(.caption.weight(.medium)).monospacedDigit()
                        .foregroundStyle(Palette.gain(raw))
                    Text("since \(DeskFormat.shortDate(latest.date))").font(.caption2).foregroundStyle(.secondary)
                } else {
                    Text("pending · \(DeskFormat.shortDate(latest.date))").font(.caption2).foregroundStyle(.secondary)
                }
            }
        } else {
            Text("no runs yet").font(.caption2).foregroundStyle(.tertiary)
        }
    }

    private var trendColor: Color {
        guard ticker.series.count > 1, let first = ticker.series.first, let last = ticker.series.last
        else { return Palette.neutral }
        return last >= first ? Palette.positive : Palette.negative
    }

    /// Days since the latest decision, if older than two weeks (stale).
    private var staleDays: Int? {
        guard let dateStr = latest?.date, let date = DeskFormat.parseISO(dateStr) else { return nil }
        let days = Int(Date().timeIntervalSince(date) / 86_400)
        return days > 14 ? days : nil
    }

    private func staleBadge(_ days: Int) -> some View {
        HStack(spacing: 2) {
            Image(systemName: "clock").font(.system(size: 9))
            Text("\(days)d").font(.caption2).monospacedDigit()
        }
        .foregroundStyle(Palette.warning)
        .help("Last decision is \(days) days old — consider re-running")
    }

}
