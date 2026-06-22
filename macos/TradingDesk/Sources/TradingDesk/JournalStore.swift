import Foundation
import Observation

/// Fetches a ticker's real Decisions Journal from the backend (/journal, parsed
/// from the engine's memory log). When a ticker has no runs yet, `entries` is
/// empty and the Ticker Desk shows an explicit "no decisions yet" state.
@MainActor
@Observable
final class JournalStore {
    let baseURL = DeskBackend.baseURL
    private(set) var entries: [JournalEntry] = []
    private(set) var loading = false
    private(set) var loadedTicker: String?

    func load(ticker: String) async {
        loading = true
        defer { loading = false }
        var comps = URLComponents(url: baseURL.appending(path: "journal"), resolvingAgainstBaseURL: false)!
        comps.queryItems = [URLQueryItem(name: "ticker", value: ticker)]
        guard let url = comps.url else { return }
        var req = URLRequest(url: url)
        req.timeoutInterval = 5
        // On failure keep any cached entries (so a silent refresh never flashes empty).
        defer { loadedTicker = ticker }
        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let raw = obj["entries"] as? [[String: Any]]
        else { return }
        entries = raw.compactMap(JournalEntry.from)
    }
}
