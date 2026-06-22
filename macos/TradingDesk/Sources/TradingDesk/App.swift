import AppKit
import SwiftUI

extension Notification.Name {
    /// Posted by the ⌘K menu command (or the menu-bar item) to open the palette.
    static let openSpotlight = Notification.Name("TradingDesk.openSpotlight")
    /// Posted by the menu-bar item to open Settings.
    static let openSettings = Notification.Name("TradingDesk.openSettings")
}

/// A SwiftPM executable defaults to a UI-less activation policy, so without this
/// the window never appears. Force regular-app behavior and bring it to front.
/// (This is dev-time glue; the Xcode app target at the packaging milestone gets
/// a real bundle Info.plist instead.)
@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        // Set the Dock / ⌘-Tab icon at runtime too: CFBundleIconFile already points
        // at the bundled AppIcon.icns, but an unsigned dev bundle can be served a
        // cached or generic icon by LaunchServices — this guarantees the brand mark.
        if let icon = Brand.appIcon { NSApp.applicationIconImage = icon }
        NSApp.activate(ignoringOtherApps: true)
        SettingsStore.shared.applyAppearance()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    private var didReplyToTerminate = false

    /// Stop the Docker backend before the app exits (start() launched it). Defer
    /// termination until stop() finishes so the container isn't orphaned — but a
    /// watchdog replies after a few seconds regardless, so a wedged Docker daemon
    /// can never trap quit.
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        Task { @MainActor in
            await DockerBackendController.shared.stop()
            replyToTerminateOnce()
        }
        Task { @MainActor in
            try? await Task.sleep(for: .seconds(6))
            replyToTerminateOnce()
        }
        return .terminateLater
    }

    /// Allow termination to proceed exactly once (stop() and the watchdog race).
    private func replyToTerminateOnce() {
        guard !didReplyToTerminate else { return }
        didReplyToTerminate = true
        NSApp.reply(toApplicationShouldTerminate: true)
    }
}

/// Bundled brand assets (TradingDesk "T-Burst"), copied into `Contents/Resources`
/// by `make-preview-app.sh` from `macos/branding/icon/`.
enum Brand {
    /// The full squircle app icon — for the Dock at runtime.
    static let appIcon = bundled("AppIcon", "icns")
    /// The monochrome burst as a menu-bar template image (macOS recolors it for
    /// the light/dark menu bar via the alpha channel).
    static let menuBar: NSImage? = {
        guard let image = bundled("TradingDesk-menubar", "png") else { return nil }
        image.size = NSSize(width: 18, height: 18)
        image.isTemplate = true
        return image
    }()

    private static func bundled(_ name: String, _ ext: String) -> NSImage? {
        Bundle.main.url(forResource: name, withExtension: ext).flatMap(NSImage.init(contentsOf:))
    }
}

@main
struct TradingDeskApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup("TradingDesk") {
            RootSplitView()
        }
        .defaultSize(width: 1040, height: 680)
        .windowResizability(.contentMinSize)
        .commands {
            CommandGroup(after: .textEditing) {
                Button("Search…") { NotificationCenter.default.post(name: .openSpotlight, object: nil) }
                    .keyboardShortcut("k", modifiers: .command)
            }
        }

        // Menu-bar item — quick actions reachable without raising the main window.
        MenuBarExtra {
            MenuBarContent()
        } label: {
            if let icon = Brand.menuBar {
                Image(nsImage: icon)
            } else {
                Image(systemName: "chart.line.uptrend.xyaxis")
            }
        }
    }
}

/// The menu-bar item's quick actions.
struct MenuBarContent: View {
    var body: some View {
        Button("Open TradingDesk") { Self.activate() }
        Button("New Search…") { Self.activate(then: .openSpotlight) }
        Button("Settings…") { Self.activate(then: .openSettings) }
        Divider()
        Button("Quit TradingDesk") { NSApp.terminate(nil) }
    }

    /// Bring the app + its main window forward, then optionally fire a UI action.
    static func activate(then action: Notification.Name? = nil) {
        NSApp.activate(ignoringOtherApps: true)
        for window in NSApp.windows where window.canBecomeMain {
            window.makeKeyAndOrderFront(nil)
            break
        }
        if let action { NotificationCenter.default.post(name: action, object: nil) }
    }
}

/// The three-pane workspace shell: Watchlist → Ticker Desk → Live Monitor.
/// Selection is the ticker *symbol* (a String). A command palette in the title
/// bar searches real tickers (add to watchlist) plus runs and decisions (jump).
struct RootSplitView: View {
    @State private var watch = WatchlistStore.shared
    @State private var selection: String?
    @State private var backend = DockerBackendController.shared
    @State private var showSettings = false
    @State private var runs = RunRegistry()
    @State private var deskStores = DeskStores()
    @State private var runningSymbols: Set<String> = []
    @State private var search = SearchModel()
    @State private var showSpotlight = false

    // Desk navigation, owned here so a palette jump can deep-link the desk even
    // when the target ticker is already selected.
    @State private var deskTab: TickerDeskView.DeskTab = .journal
    @State private var pendingRunDate: String?

    private var tickers: [WatchlistTicker] { watch.tickers }

    /// The symbol to show: the explicit selection, else the first tracked name.
    private var selectedSymbol: String? {
        if let selection, watch.contains(selection) { return selection }
        return tickers.first?.symbol
    }

    var body: some View {
        NavigationSplitView {
            WatchlistSidebar(
                tickers: tickers, selection: $selection, backend: backend,
                runningSymbols: runningSymbols,
                onRemove: { sym in
                    watch.remove(sym)
                    if selection == sym { selection = nil }
                },
                // Animate the pin reorder. Folding `pinned` into the row identity
                // makes a toggle a remove+insert (fresh cell, zero swipe offset);
                // `.snappy` cross-fades that reinsert so it reads as a quick move
                // rather than a hard pop. Covers both the swipe and context-menu stars.
                onTogglePin: { sym in withAnimation(.snappy) { watch.togglePin(sym) } },
                onOpenSettings: { showSettings = true }
            )
            .navigationSplitViewColumnWidth(min: 200, ideal: 220, max: 320)
            .navigationTitle("TradingDesk")
        } content: {
            Group {
                if let sym = selectedSymbol {
                    TickerDeskView(symbol: sym, tab: $deskTab, openRunDate: $pendingRunDate,
                                   journalStore: deskStores.journal(for: sym),
                                   reportStore: deskStores.reports(for: sym)).id(sym)
                } else {
                    ContentUnavailableView(
                        "No tickers",
                        systemImage: "list.bullet.rectangle",
                        description: Text("Search from the title bar to add a ticker to your watchlist.")
                    )
                }
            }
            .navigationSplitViewColumnWidth(min: 280, ideal: 340)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    SearchTrigger(
                        isPresented: $showSpotlight,
                        search: search,
                        isTracked: { watch.contains($0) },
                        onOpen: openSpotlight,
                        onPickTicker: handlePickTicker,
                        onAddTicker: { _ = watch.add($0) },
                        onJumpRun: handleJumpRun,
                        onJumpDecision: handleJumpDecision
                    )
                }
            }
        } detail: {
            Group {
                if let sym = selectedSymbol {
                    LiveMonitorView(symbol: sym, backend: backend,
                                    run: runs.coordinator(for: sym),
                                    openSettings: { showSettings = true })
                        .id(sym)
                } else {
                    Text("No run").foregroundStyle(.secondary)
                }
            }
            .navigationSplitViewColumnWidth(min: 380, ideal: 480)
        }
        .sheet(isPresented: $showSettings) { SettingsView() }
        .onChange(of: showSpotlight) { _, open in if !open { search.reset() } }
        .onReceive(NotificationCenter.default.publisher(for: .openSpotlight)) { _ in openSpotlight() }
        .onReceive(NotificationCenter.default.publisher(for: .openSettings)) { _ in showSettings = true }
        .onReceive(NotificationCenter.default.publisher(for: .runStateChanged)) { note in
            guard let ticker = (note.userInfo?["ticker"] as? String)?.uppercased(),
                  let running = note.userInfo?["running"] as? Bool else { return }
            if running { runningSymbols.insert(ticker) } else { runningSymbols.remove(ticker) }
        }
        .task {
            await backend.start()
            // Don't fire empty loads at a backend that failed to start — let the
            // .failed state be the single clear signal instead of an empty UI.
            guard backend.state == .ready else { return }
            await watch.load()                       // live watchlist — no Keychain dependency
            await CapabilitiesStore.shared.load()    // feeds provider → key-env mapping
            SettingsStore.shared.refreshKeyStatus()  // existence-only, never prompts
        }
        .onAppear { if selection == nil { selection = tickers.first?.symbol } }
    }

    // MARK: Palette actions

    private func openSpotlight() {
        search.reset()
        showSpotlight = true
        Task { await search.loadCorpus() }
    }

    /// A ticker result: track it (if new), select it, show its Journal, close.
    private func handlePickTicker(_ symbol: String) {
        selection = watch.add(symbol)
        deskTab = .journal
        pendingRunDate = nil
        showSpotlight = false
    }

    /// A run result: open that run's document in the Library.
    private func handleJumpRun(_ run: ReportSummary) {
        selection = watch.add(run.ticker)
        pendingRunDate = run.date
        deskTab = .library
        showSpotlight = false
    }

    /// A decision result: jump to that ticker's Journal.
    private func handleJumpDecision(_ decision: SearchDecision) {
        selection = watch.add(decision.ticker)
        pendingRunDate = nil
        deskTab = .journal
        showSpotlight = false
    }
}
