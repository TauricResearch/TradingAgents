import AppKit
import SwiftUI

// MARK: - Dynamic color

extension Color {
    /// A color that resolves per the view's effective appearance (light/dark).
    /// The app forces appearance via `NSApp.appearance`, and AppKit re-resolves
    /// the dynamic provider whenever that changes, so tokens adapt everywhere.
    init(light: Color, dark: Color) {
        self = Color(nsColor: NSColor(name: nil) { appearance in
            let isDark = appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
            return NSColor(isDark ? dark : light)
        })
    }
}

// MARK: - Palette (the single source of truth for color)

/// Semantic color tokens for the "calm native pro" look. Warm, layered neutral
/// surfaces; one swappable accent; harmonized status + rating hues. Every color
/// in the app should come from here (no raw `.blue`/`.green`/opacity literals).
enum Palette {
    // Surfaces — warm off-white in light, graphite in dark.
    static let surface       = Color(light: Color(white: 0.97), dark: Color(white: 0.13))
    static let surfaceRaised = Color(light: .white, dark: Color(white: 0.17))
    static let surfaceSunken = Color(light: Color(white: 0.925), dark: Color(white: 0.10))
    static let selection     = Color(light: Color(white: 0.90), dark: Color(white: 0.25))
    static let separator     = Color(light: .black.opacity(0.08), dark: .white.opacity(0.11))

    // Accent — SINGLE source of truth. Swap these two values to rebrand the app.
    static let accent = Color(light: Color(red: 0.17, green: 0.42, blue: 0.90),
                              dark: Color(red: 0.42, green: 0.62, blue: 0.99))

    // Status — harmonized; used for P&L, node states, provenance, phases.
    static let positive = Color(light: Color(red: 0.13, green: 0.60, blue: 0.35),
                                dark: Color(red: 0.31, green: 0.80, blue: 0.52))
    static let negative = Color(light: Color(red: 0.80, green: 0.27, blue: 0.24),
                                dark: Color(red: 0.97, green: 0.45, blue: 0.42))
    static let warning  = Color(light: Color(red: 0.78, green: 0.53, blue: 0.11),
                                dark: Color(red: 0.93, green: 0.67, blue: 0.26))
    /// The starred / pinned gold — the SAME warm gold in light and dark (the
    /// dark-mode gold), so a starred ticker reads identically in either
    /// appearance. Kept separate from the mode-adaptive `warning` token, which
    /// stays darker in light mode for genuine warnings (e.g. the stale badge).
    static let star     = Color(red: 0.93, green: 0.67, blue: 0.26)
    static let running  = accent
    static let neutral  = Color(light: Color(white: 0.52), dark: Color(white: 0.62))

    /// Green for a non-negative value, red otherwise (P&L / alpha).
    static func gain(_ value: Double) -> Color { value >= 0 ? positive : negative }
}

// MARK: - Opacity / elevation scale (replaces the ad-hoc magic numbers)

enum Tint {
    static let chipFill: Double = 0.16   // pastel chip backgrounds
    static let cardFill: Double = 0.06   // tinted card/feed-row backgrounds
    static let hover: Double = 0.08      // row hover wash
}

// MARK: - Spacing & radius scales (4/8 grid)

enum Space {
    static let xs: CGFloat = 4
    static let s: CGFloat = 8
    static let m: CGFloat = 12
    static let l: CGFloat = 16
    static let xl: CGFloat = 24
}

enum Radius {
    static let card: CGFloat = 10
    static let control: CGFloat = 8
}

// MARK: - Typography ramp

extension Font {
    /// Big ticker / date headers.
    static let tickerTitle = Font.system(size: 20, weight: .semibold)
    /// Card / row titles.
    static let cardTitle = Font.system(size: 13, weight: .semibold)
    /// Small uppercase section labels.
    static let sectionLabel = Font.system(size: 11, weight: .semibold)
}

// MARK: - Surface modifiers

extension View {
    /// A raised card surface (hairline border, soft radius). The standard
    /// container for list rows, panels, and stats.
    func card(radius: CGFloat = Radius.card, padding: CGFloat = Space.m) -> some View {
        self
            .padding(padding)
            .background(Palette.surfaceRaised, in: RoundedRectangle(cornerRadius: radius))
            .overlay(RoundedRectangle(cornerRadius: radius).strokeBorder(Palette.separator, lineWidth: 0.5))
    }

    /// A tinted card (e.g. an agent-theater feed row) — a soft wash of `color`.
    func tintedCard(_ color: Color, radius: CGFloat = Radius.card, padding: CGFloat = Space.s) -> some View {
        self
            .padding(padding)
            .background(color.opacity(Tint.cardFill), in: RoundedRectangle(cornerRadius: radius))
    }
}
