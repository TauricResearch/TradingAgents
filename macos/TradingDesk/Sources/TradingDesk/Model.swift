import Foundation

/// The local desk backend (Dockerized FastAPI) — the single source of truth for
/// its loopback host:port, shared by every store/controller that talks to it.
enum DeskBackend {
    static let baseURL = URL(string: "http://127.0.0.1:8765")!
}

/// One row in a ticker's Decisions Journal — a call plus its realized outcome.
/// `alpha`/`raw`/`holdingDays` are nil until the engine resolves the outcome on
/// a later run (the UI shows "resolves on next run").
struct JournalEntry: Identifiable {
    let id = UUID()
    let date: String
    let rating: Rating
    let raw: Double?
    let alpha: Double?
    let holdingDays: Int?

    var pending: Bool { alpha == nil }
}

extension JournalEntry {
    /// Parse one `/journal` entry dict (engine memory-log shape) into a JournalEntry.
    /// Shared by JournalStore (full journal) and WatchlistStore (latest per symbol).
    static func from(_ e: [String: Any]) -> JournalEntry? {
        guard let date = e["date"] as? String else { return nil }
        let rating = Rating(rawValue: (e["rating"] as? String) ?? "") ?? .hold
        let pending = (e["pending"] as? Bool) ?? false
        return JournalEntry(
            date: date,
            rating: rating,
            raw: pending ? nil : pct(e["raw"]),
            alpha: pending ? nil : pct(e["alpha"]),
            holdingDays: days(e["holding"])
        )
    }

    /// "+3.1%" / "-0.4%" -> 0.031 / -0.004 ; nil otherwise.
    private static func pct(_ value: Any?) -> Double? {
        guard let s = value as? String else { return nil }
        let cleaned = s.replacingOccurrences(of: "%", with: "").trimmingCharacters(in: .whitespaces)
        guard let v = Double(cleaned) else { return nil }
        return v / 100
    }

    /// "5d" -> 5 ; nil otherwise.
    private static func days(_ value: Any?) -> Int? {
        guard let s = value as? String else { return nil }
        return Int(s.replacingOccurrences(of: "d", with: "").trimmingCharacters(in: .whitespaces))
    }
}

/// Lightweight, client-side instrument helpers (display name + benchmark + asset
/// type). The seed watchlist symbols; names fall back to the symbol for tickers
/// the user adds. The engine resolves the real identity at run time.
enum Instruments {
    static let defaultSymbols = ["NVDA", "AAPL", "MSFT", "BTC-USD", "TSLA"]

    private static let names: [String: String] = [
        "NVDA": "Nvidia", "AAPL": "Apple", "MSFT": "Microsoft",
        "BTC-USD": "Bitcoin", "TSLA": "Tesla", "ETH-USD": "Ethereum",
        "GOOGL": "Alphabet", "AMZN": "Amazon", "META": "Meta", "SPY": "S&P 500",
    ]

    static func name(_ symbol: String) -> String { names[symbol.uppercased()] ?? symbol }
    static func isCrypto(_ symbol: String) -> Bool { symbol.uppercased().hasSuffix("-USD") }
    static func benchmark(_ symbol: String) -> String { isCrypto(symbol) ? "BTC" : "SPY" }
    static func normalize(_ input: String) -> String {
        input.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
    }
}
