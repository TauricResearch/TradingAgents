import AppKit
import Foundation
import Observation
import SwiftUI

/// App appearance preference (overrides or follows the system).
enum AppearanceMode: String, CaseIterable, Identifiable {
    case system, light, dark
    var id: String { rawValue }
    var label: String {
        switch self {
        case .system: return "System"
        case .light: return "Light"
        case .dark: return "Dark"
        }
    }
    var colorScheme: ColorScheme? {
        switch self {
        case .system: return nil
        case .light: return .light
        case .dark: return .dark
        }
    }
}

/// The active run configuration (a single "profile" for v1), persisted to
/// UserDefaults. Secrets are NOT here — they live in the Keychain. Singleton so
/// the Settings scene and the main window's Run button share one instance.
@MainActor
@Observable
final class SettingsStore {
    static let shared = SettingsStore()
    private let defaults = UserDefaults.standard

    var provider: String { didSet { defaults.set(provider, forKey: "cfg.provider") } }
    var deepModel: String { didSet { defaults.set(deepModel, forKey: "cfg.deepModel") } }
    var quickModel: String { didSet { defaults.set(quickModel, forKey: "cfg.quickModel") } }
    var analysts: [String] { didSet { defaults.set(analysts, forKey: "cfg.analysts") } }
    /// Investment debate rounds (Bull vs Bear → Research Manager); engine
    /// `max_debate_rounds`. One round = a bull turn + a bear turn.
    var debateRounds: Int { didSet { defaults.set(debateRounds, forKey: "cfg.debateRounds") } }
    /// Risk debate rounds (Aggressive / Conservative / Neutral); engine
    /// `max_risk_discuss_rounds`. One round = all three analysts speak once.
    var riskRounds: Int { didSet { defaults.set(riskRounds, forKey: "cfg.riskRounds") } }
    var outputLanguage: String { didSet { defaults.set(outputLanguage, forKey: "cfg.language") } }
    var tradeDate: Date { didSet { defaults.set(tradeDate, forKey: "cfg.tradeDate") } }
    /// Applied immediately (display preference, not part of the run draft).
    var appearance: AppearanceMode {
        didSet {
            defaults.set(appearance.rawValue, forKey: "cfg.appearance")
            applyAppearance()
        }
    }

    /// Force the app-wide appearance via NSApp so every window AND sheet update
    /// uniformly (preferredColorScheme deep in a hierarchy + sheets can update
    /// only part of the window). nil = follow the system.
    func applyAppearance() {
        switch appearance {
        case .system: NSApp.appearance = nil
        case .light: NSApp.appearance = NSAppearance(named: .aqua)
        case .dark: NSApp.appearance = NSAppearance(named: .darkAqua)
        }
    }

    /// True when the selected provider has its API key (or needs none). Observable
    /// so the Run gate reacts; refreshed at launch and after saving Settings.
    private(set) var providerReady = true

    func refreshKeyStatus() {
        let info = CapabilitiesStore.shared.provider(provider)
        guard let env = info?.apiKeyEnv, !(info?.keyOptional ?? false) else {
            providerReady = true
            return
        }
        providerReady = KeychainStore.has(account: env)
    }

    private init() {
        provider = defaults.string(forKey: "cfg.provider") ?? "openrouter"
        deepModel = defaults.string(forKey: "cfg.deepModel") ?? "openai/gpt-4o-mini"
        quickModel = defaults.string(forKey: "cfg.quickModel") ?? "openai/gpt-4o-mini"
        analysts = (defaults.array(forKey: "cfg.analysts") as? [String]) ?? ["market", "news"]
        // Migrate the old single "research depth" (which drove both) into the two
        // round controls; fresh installs default to 1.
        let legacyDepth = defaults.object(forKey: "cfg.depth") as? Int
        debateRounds = defaults.object(forKey: "cfg.debateRounds") as? Int ?? legacyDepth ?? 1
        riskRounds = defaults.object(forKey: "cfg.riskRounds") as? Int ?? legacyDepth ?? 1
        outputLanguage = defaults.string(forKey: "cfg.language") ?? "English"
        tradeDate = (defaults.object(forKey: "cfg.tradeDate") as? Date) ?? Date()
        appearance = AppearanceMode(rawValue: defaults.string(forKey: "cfg.appearance") ?? "") ?? .system
    }

    /// Engine analyst keys in canonical order (matches AnalystType wire values).
    static let analystOptions: [(key: String, label: String)] = [
        ("market", "Market"),
        ("social", "Sentiment"),
        ("news", "News"),
        ("fundamentals", "Fundamentals"),
    ]

    var tradeDateString: String { DeskFormat.isoString(tradeDate) }
}
