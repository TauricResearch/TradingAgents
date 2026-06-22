import Foundation
import Observation

/// One Watchlist row: a tracked symbol, its latest journal decision (live from
/// /journal), and a recent price series for the row's sparkline. `latest` is nil
/// until the symbol has a recorded run; `series` is empty until /prices answers.
struct WatchlistTicker: Identifiable {
    var id: String { symbol }
    /// Identity for the sidebar `ForEach`. Folds `pinned` in so that toggling a
    /// star CHANGES the row's List-cell identity — forcing the framework to tear
    /// down the old cell and insert a fresh one whose native `.swipeActions`
    /// offset starts at zero, instead of MOVING the reused cell (and inheriting
    /// its stuck swipe-shrunk width) to its new pinned-first position. `id`
    /// stays `symbol`; selection is keyed by symbol separately, so this is safe.
    var rowIdentity: String { "\(symbol)#\(pinned ? 1 : 0)" }
    let symbol: String
    let latest: JournalEntry?
    let series: [Double]
    let pinned: Bool
}

/// Source of truth for the Watchlist: a persisted set of tracked symbols joined
/// with a live snapshot of the latest decision per symbol (`/journal`) and a
/// recent price series per symbol (`/prices`). Seeded with a default basket on
/// first launch. Only the symbol list is persisted (UserDefaults) — decisions and
/// prices always come from the engine, so the watchlist can't drift from reality.
@MainActor
@Observable
final class WatchlistStore {
    static let shared = WatchlistStore()

    let baseURL = DeskBackend.baseURL
    private let defaultsKey = "watchlist.symbols"
    private let pinnedKey = "watchlist.pinned"

    private(set) var symbols: [String]
    private(set) var pinned: Set<String>
    private(set) var latest: [String: JournalEntry] = [:]
    private(set) var series: [String: [Double]] = [:]

    private init() {
        let saved = UserDefaults.standard.array(forKey: defaultsKey) as? [String]
        symbols = (saved?.isEmpty == false ? saved : nil) ?? Instruments.defaultSymbols
        pinned = Set(UserDefaults.standard.array(forKey: pinnedKey) as? [String] ?? [])
    }

    /// The rows the sidebar renders: pinned symbols first (preserving their
    /// relative order), then the rest — each joined with its latest decision and
    /// price series.
    var tickers: [WatchlistTicker] {
        let ordered = symbols.filter { pinned.contains($0) } + symbols.filter { !pinned.contains($0) }
        return ordered.map { sym in
            WatchlistTicker(symbol: sym,
                            latest: latest[sym], series: series[sym] ?? [],
                            pinned: pinned.contains(sym))
        }
    }

    func load() async {
        await loadJournal()
        await loadSeries()
    }

    /// Fetch the whole journal once and keep the newest entry per ticker. The
    /// server returns entries newest-first, so the first hit per symbol is its
    /// latest decision. Leaves existing data intact on failure.
    private func loadJournal() async {
        var req = URLRequest(url: baseURL.appending(path: "journal"))
        req.timeoutInterval = 5
        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let raw = obj["entries"] as? [[String: Any]]
        else { return }

        var map: [String: JournalEntry] = [:]
        for entry in raw {
            guard let sym = (entry["ticker"] as? String)?.uppercased(), map[sym] == nil,
                  let parsed = JournalEntry.from(entry) else { continue }
            map[sym] = parsed
        }
        latest = map
    }

    /// Fetch a recent daily-close series per tracked symbol (concurrently) for
    /// the row sparklines. Best-effort: a symbol with no data just has no line.
    private func loadSeries() async {
        let base = baseURL
        let syms = symbols
        let fetched = await withTaskGroup(of: (String, [Double]).self) { group -> [String: [Double]] in
            for sym in syms {
                group.addTask { (sym, await Self.fetchSeries(base: base, symbol: sym)) }
            }
            var map: [String: [Double]] = [:]
            for await (sym, points) in group { map[sym] = points }
            return map
        }
        series = fetched
    }

    private nonisolated static func fetchSeries(base: URL, symbol: String) async -> [Double] {
        var comps = URLComponents(url: base.appending(path: "prices"), resolvingAgainstBaseURL: false)!
        comps.queryItems = [URLQueryItem(name: "ticker", value: symbol),
                            URLQueryItem(name: "days", value: "30")]
        guard let url = comps.url else { return [] }
        var req = URLRequest(url: url)
        req.timeoutInterval = 8
        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let raw = obj["points"] as? [Any]
        else { return [] }
        return raw.compactMap { ($0 as? NSNumber)?.doubleValue }
    }

    func contains(_ symbol: String) -> Bool {
        symbols.contains(Instruments.normalize(symbol))
    }

    /// Track a new symbol (normalized, deduped) and persist. Returns the
    /// normalized symbol so the caller can select it.
    @discardableResult
    func add(_ input: String) -> String {
        let sym = Instruments.normalize(input)
        guard !sym.isEmpty else { return sym }
        if !symbols.contains(sym) {
            symbols.append(sym)
            persist()
        }
        return sym
    }

    func remove(_ symbol: String) {
        let sym = Instruments.normalize(symbol)
        symbols.removeAll { $0 == sym }
        pinned.remove(sym)
        persist()
    }

    func isPinned(_ symbol: String) -> Bool { pinned.contains(Instruments.normalize(symbol)) }

    /// Toggle "starred" — pinned symbols float to the top of the watchlist and
    /// stay there regardless of newly added tickers.
    func togglePin(_ symbol: String) {
        let sym = Instruments.normalize(symbol)
        if pinned.contains(sym) { pinned.remove(sym) } else { pinned.insert(sym) }
        persist()
    }

    private func persist() {
        UserDefaults.standard.set(symbols, forKey: defaultsKey)
        UserDefaults.standard.set(Array(pinned), forKey: pinnedKey)
    }
}
