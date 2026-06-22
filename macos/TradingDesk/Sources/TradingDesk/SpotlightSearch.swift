import SwiftUI

/// The search trigger in the top bar: a magnifier + "Search something…" with
/// generous horizontal padding. Clicking it opens the command palette popover
/// right below (whose field keeps the fuller "Jump to ticker, run or decision"
/// placeholder).
struct SearchTrigger: View {
    @Binding var isPresented: Bool
    @Bindable var search: SearchModel
    var isTracked: (String) -> Bool
    var onOpen: () -> Void
    var onPickTicker: (String) -> Void
    var onAddTicker: (String) -> Void
    var onJumpRun: (ReportSummary) -> Void
    var onJumpDecision: (SearchDecision) -> Void

    var body: some View {
        Button(action: onOpen) {
            HStack(spacing: 6) {
                Image(systemName: "magnifyingglass")
                Text("Search something…")
            }
            .font(.system(size: 13))
            .foregroundStyle(.secondary)
            .padding(.vertical, 3)
            .frame(width: 360)
        }
        .buttonStyle(.plain)
        .popover(isPresented: $isPresented, arrowEdge: .bottom) {
            CommandPalette(
                search: search,
                isTracked: isTracked,
                onPickTicker: onPickTicker,
                onAddTicker: onAddTicker,
                onJumpRun: onJumpRun,
                onJumpDecision: onJumpDecision,
                onDismiss: { isPresented = false }
            )
        }
    }
}

/// The command palette shown right below the trigger: a search field plus live
/// results grouped into **Tickers** (real `/search` companies — hovering reveals
/// "add to watchlist"), **Runs**, and **Decisions** (click to jump).
struct CommandPalette: View {
    @Bindable var search: SearchModel
    var isTracked: (String) -> Bool
    var onPickTicker: (String) -> Void
    var onAddTicker: (String) -> Void
    var onJumpRun: (ReportSummary) -> Void
    var onJumpDecision: (SearchDecision) -> Void
    var onDismiss: () -> Void

    @FocusState private var focused: Bool
    @State private var hovered: String?

    private var isEmpty: Bool {
        search.results.isEmpty && search.runResults.isEmpty && search.decisionResults.isEmpty
    }

    var body: some View {
        VStack(spacing: 0) {
            field
            if search.isActive {
                Divider()
                resultsBody
            }
        }
        .frame(width: 460)
        .task { focused = true }
    }

    private var field: some View {
        HStack(spacing: 10) {
            Image(systemName: "magnifyingglass").font(.system(size: 15)).foregroundStyle(.secondary)
            TextField("Jump to ticker, run or decision", text: $search.query)
                .textFieldStyle(.plain)
                .font(.system(size: 16))
                .focused($focused)
                .onChange(of: search.query) { _, _ in search.search() }
                .onKeyPress(.escape) { onDismiss(); return .handled }
            if search.loading {
                ProgressView().controlSize(.small)
            } else if search.isActive {
                Button { search.query = "" } label: {
                    Image(systemName: "xmark.circle.fill").foregroundStyle(.tertiary)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
    }

    @ViewBuilder private var resultsBody: some View {
        if isEmpty {
            HStack {
                Text(search.loading ? "Searching…" : "No matches")
                    .font(.callout).foregroundStyle(.secondary)
                Spacer()
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
        } else {
            // A plain VStack (not a ScrollView, which reports ~0 intrinsic height
            // inside a popover and collapses the results) so the popover sizes to
            // its content. Tickers are capped to keep the panel a sensible height.
            VStack(alignment: .leading, spacing: 0) {
                if !search.results.isEmpty {
                    header("Tickers")
                    ForEach(Array(search.results.prefix(8))) { tickerRow($0) }
                }
                if !search.runResults.isEmpty {
                    header("Runs")
                    ForEach(search.runResults) { runRow($0) }
                }
                if !search.decisionResults.isEmpty {
                    header("Decisions")
                    ForEach(search.decisionResults) { decisionRow($0) }
                }
            }
            .padding(.vertical, 4)
        }
    }

    private func header(_ title: String) -> some View {
        Text(title.uppercased())
            .font(.caption2.weight(.semibold))
            .foregroundStyle(.tertiary)
            .padding(.horizontal, 14).padding(.top, 8).padding(.bottom, 2)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func tickerRow(_ r: TickerSearchResult) -> some View {
        let id = "T:" + r.symbol
        let tracked = isTracked(r.symbol)
        return rowShell(id: id, onTap: { onPickTicker(r.symbol) }) {
            Image(systemName: "chart.line.uptrend.xyaxis").foregroundStyle(.secondary).frame(width: 16)
            VStack(alignment: .leading, spacing: 1) {
                HStack(spacing: 6) {
                    Text(r.symbol).font(.system(size: 13, weight: .semibold))
                    if !r.exchange.isEmpty { Text(r.exchange).font(.caption2).foregroundStyle(.tertiary) }
                }
                if !r.name.isEmpty { Text(r.name).font(.caption).foregroundStyle(.secondary).lineLimit(1) }
            }
            Spacer(minLength: 8)
            if tracked {
                Label("in watchlist", systemImage: "checkmark")
                    .labelStyle(.iconOnly).font(.caption).foregroundStyle(Palette.positive)
            } else if hovered == id {
                Button { onAddTicker(r.symbol) } label: {
                    Label("Add to watchlist", systemImage: "plus").font(.caption.weight(.medium))
                }
                .buttonStyle(.borderless)
                .help("Add \(r.symbol) to your watchlist")
            }
        }
    }

    private func runRow(_ r: ReportSummary) -> some View {
        rowShell(id: "R:" + r.id, onTap: { onJumpRun(r) }) {
            Image(systemName: "doc.text").foregroundStyle(.secondary).frame(width: 16)
            VStack(alignment: .leading, spacing: 1) {
                Text("\(r.ticker) · \(r.date)").font(.system(size: 13, weight: .medium))
                Text("run document").font(.caption2).foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            if let rating = r.rating { RatingChip(rating: rating) }
            Image(systemName: "arrow.up.right").font(.caption2).foregroundStyle(.tertiary)
        }
    }

    private func decisionRow(_ r: SearchDecision) -> some View {
        rowShell(id: "D:" + r.id, onTap: { onJumpDecision(r) }) {
            Image(systemName: "book.closed").foregroundStyle(.secondary).frame(width: 16)
            VStack(alignment: .leading, spacing: 1) {
                Text("\(r.ticker) · \(r.date)").font(.system(size: 13, weight: .medium))
                Text("decision").font(.caption2).foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            if let rating = r.rating { RatingChip(rating: rating) }
            Image(systemName: "arrow.up.right").font(.caption2).foregroundStyle(.tertiary)
        }
    }

    @ViewBuilder
    private func rowShell<C: View>(id: String, onTap: @escaping () -> Void,
                                   @ViewBuilder content: () -> C) -> some View {
        HStack(spacing: 10, content: content)
            .padding(.horizontal, 14).padding(.vertical, 7)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(hovered == id ? Palette.accent.opacity(Tint.chipFill) : .clear)
            .contentShape(Rectangle())
            .onTapGesture(perform: onTap)
            .onHover { hovered = $0 ? id : (hovered == id ? nil : hovered) }
    }
}
