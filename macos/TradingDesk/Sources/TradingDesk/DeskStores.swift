import Foundation
import Observation

/// Caches one `JournalStore` + `ReportStore` per ticker symbol, owned ABOVE the
/// Ticker Desk. Switching back to a previously-viewed ticker then reuses its
/// already-loaded stores, so the desk shows its journal/library instantly
/// instead of tearing down to a fresh empty store and flashing the empty state
/// (the glitch seen when switching between two tickers that both have entries).
@MainActor
@Observable
final class DeskStores {
    // Ignored by Observation: lazily creating a store while the desk is built
    // must not invalidate the view mid-update; reactivity comes from each store.
    @ObservationIgnored private var journals: [String: JournalStore] = [:]
    @ObservationIgnored private var reports: [String: ReportStore] = [:]

    func journal(for symbol: String) -> JournalStore {
        let key = symbol.uppercased()
        if let existing = journals[key] { return existing }
        let made = JournalStore()
        journals[key] = made
        return made
    }

    func reports(for symbol: String) -> ReportStore {
        let key = symbol.uppercased()
        if let existing = reports[key] { return existing }
        let made = ReportStore()
        reports[key] = made
        return made
    }
}
