import Foundation
import Observation

/// Keeps one `RunCoordinator` per ticker symbol, owned ABOVE the detail pane.
/// A run therefore keeps streaming when the user switches to another ticker and
/// is still there — live or finished — when they switch back.
///
/// Without this, `LiveMonitorView` held the coordinator in per-view `@State` and
/// the detail pane is recreated `.id(symbol)` on every ticker switch, so the
/// running analysis was discarded (orphaned) the moment the user clicked away.
@MainActor
@Observable
final class RunRegistry {
    // Ignored by Observation: lazily inserting a coordinator while the detail
    // pane is being built must not invalidate the view mid-update. Reactivity to
    // a run's progress comes from each RunCoordinator's own @Observable state.
    @ObservationIgnored private var bySymbol: [String: RunCoordinator] = [:]

    func coordinator(for symbol: String) -> RunCoordinator {
        let key = symbol.uppercased()
        if let existing = bySymbol[key] { return existing }
        let made = RunCoordinator()
        bySymbol[key] = made
        return made
    }
}
