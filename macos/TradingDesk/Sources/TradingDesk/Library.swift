import SwiftUI

struct ReportSummary: Identifiable {
    var id: String { "\(ticker)-\(date)" }
    let ticker: String
    let date: String
    let rating: Rating?
}

struct ReportSection: Identifiable {
    let id = UUID()
    let title: String
    let body: String
}

/// Lists and loads saved run documents from the backend (/reports), which reads
/// the per-run full_states_log JSON the engine writes on completion.
@MainActor
@Observable
final class ReportStore {
    let baseURL = DeskBackend.baseURL
    private(set) var docs: [ReportSummary] = []
    private(set) var loadedTicker: String?

    func loadList(ticker: String) async {
        defer { loadedTicker = ticker }
        guard let url = query(["ticker": ticker]) else { return }
        // On failure keep any cached docs (so a silent refresh never flashes empty).
        guard let (data, resp) = try? await URLSession.shared.data(from: url),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let arr = obj["reports"] as? [[String: Any]]
        else { return }
        docs = arr.compactMap { r in
            guard let t = r["ticker"] as? String, let d = r["date"] as? String else { return nil }
            return ReportSummary(ticker: t, date: d, rating: Rating(rawValue: (r["rating"] as? String) ?? ""))
        }
    }

    func loadDoc(ticker: String, date: String) async -> [ReportSection] {
        guard let url = query(["ticker": ticker, "date": date]) else { return [] }
        guard let (data, resp) = try? await URLSession.shared.data(from: url),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              let d = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return [] }
        return Self.sections(from: d)
    }

    private func query(_ items: [String: String]) -> URL? {
        var comps = URLComponents(url: baseURL.appending(path: "reports"), resolvingAgainstBaseURL: false)
        comps?.queryItems = items.map { URLQueryItem(name: $0.key, value: $0.value) }
        return comps?.url
    }

    static func sections(from d: [String: Any]) -> [ReportSection] {
        func s(_ key: String) -> String { (d[key] as? String) ?? "" }
        func nested(_ key: String, _ field: String) -> String {
            ((d[key] as? [String: Any])?[field] as? String) ?? ""
        }
        let candidates: [(String, String)] = [
            ("Final decision", s("final_trade_decision")),
            ("Market analysis", s("market_report")),
            ("Sentiment analysis", s("sentiment_report")),
            ("News analysis", s("news_report")),
            ("Fundamentals analysis", s("fundamentals_report")),
            ("Research plan", s("investment_plan")),
            ("Bull case", nested("investment_debate_state", "bull_history")),
            ("Bear case", nested("investment_debate_state", "bear_history")),
            ("Trader plan", s("trader_investment_decision")),
            ("Risk · aggressive", nested("risk_debate_state", "aggressive_history")),
            ("Risk · conservative", nested("risk_debate_state", "conservative_history")),
            ("Risk · neutral", nested("risk_debate_state", "neutral_history")),
        ]
        return candidates
            .filter { !$0.1.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
            .map { ReportSection(title: $0.0, body: $0.1) }
    }
}

/// Library tab: the selected ticker's saved run documents. Docs are preloaded
/// by TickerDeskView (alongside the journal) so switching tabs never refetches
/// or flashes the empty state.
struct LibraryView: View {
    let docs: [ReportSummary]
    /// Set by a command-palette "jump to run": the date to auto-open. Consumed
    /// (reset to nil) once the matching document is presented.
    @Binding var openDate: String?
    @State private var openDoc: ReportSummary?

    var body: some View {
        Group {
            if docs.isEmpty {
                PremiumEmptyState(
                    icon: "doc.text",
                    title: "No saved runs",
                    message: "Run an analysis — its full report is saved here as a re-openable document.",
                    tint: Palette.neutral
                )
            } else {
                ScrollView {
                    LazyVStack(spacing: Space.s) {
                        ForEach(docs) { doc in
                            Button { openDoc = doc } label: { docRow(doc) }
                                .buttonStyle(.plain)
                        }
                    }
                    .padding(.vertical, Space.s)
                }
            }
        }
        .sheet(item: $openDoc) { RunDocumentView(summary: $0) }
        // Auto-open a palette-requested run, retrying once the docs arrive.
        .onAppear { openRequested() }
        .onChange(of: openDate) { _, _ in openRequested() }
        .onChange(of: docs.count) { _, _ in openRequested() }
    }

    private func docRow(_ doc: ReportSummary) -> some View {
        HStack(spacing: Space.s) {
            Image(systemName: "doc.text").foregroundStyle(.secondary).frame(width: 18)
            VStack(alignment: .leading, spacing: 1) {
                Text(DeskFormat.shortDate(doc.date)).font(.system(size: 14, weight: .semibold))
                Text("full report").font(.caption2).foregroundStyle(.secondary)
            }
            Spacer()
            if let rating = doc.rating { RatingChip(rating: rating) }
            Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.tertiary)
        }
        .card()
        .contentShape(RoundedRectangle(cornerRadius: Radius.card))
    }

    private func openRequested() {
        guard let date = openDate, let doc = docs.first(where: { $0.date == date }) else { return }
        openDoc = doc
        openDate = nil
    }
}

/// Reads one saved run as a long-form document: a pinned rating header and the
/// report sections + debate transcripts rendered as markdown.
struct RunDocumentView: View {
    let summary: ReportSummary
    @State private var store = ReportStore()
    @State private var sections: [ReportSection] = []
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("\(summary.ticker) · \(DeskFormat.shortDate(summary.date))").font(.tickerTitle)
                    Text("Run document").font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if let rating = summary.rating { RatingChip(rating: rating) }
                Button("Done") { dismiss() }.buttonStyle(PrimaryButtonStyle())
            }
            .padding(Space.l)
            Rectangle().fill(Palette.separator).frame(height: 0.5)
            if sections.isEmpty {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: Space.xl) {
                        ForEach(sections) { section in
                            VStack(alignment: .leading, spacing: Space.s) {
                                Text(section.title)
                                    .font(.system(size: 15, weight: .semibold))
                                    .foregroundStyle(Palette.accent)
                                Text(Self.markdown(section.body))
                                    .font(.system(size: 13))
                                    .lineSpacing(2)
                                    .textSelection(.enabled)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                        }
                    }
                    .padding(Space.xl)
                    .frame(maxWidth: 680, alignment: .leading)
                    .frame(maxWidth: .infinity)
                }
            }
        }
        .frame(minWidth: 560, minHeight: 560)
        .task { sections = await store.loadDoc(ticker: summary.ticker, date: summary.date) }
    }

    private static func markdown(_ s: String) -> AttributedString {
        let options = AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        return (try? AttributedString(markdown: s, options: options)) ?? AttributedString(s)
    }
}
