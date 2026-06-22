import SwiftUI

/// The engine's 5-tier portfolio rating (parsed server-side from the Portfolio
/// Manager decision). Drives chips and sparkline coloring across the app.
enum Rating: String, CaseIterable, Identifiable {
    case buy = "Buy"
    case overweight = "Overweight"
    case hold = "Hold"
    case underweight = "Underweight"
    case sell = "Sell"

    var id: String { rawValue }

    /// Compact label for narrow chips.
    var short: String {
        switch self {
        case .overweight: return "Ovwt"
        case .underweight: return "Undwt"
        default: return rawValue
        }
    }

    /// Harmonized, appearance-adaptive tier color (from the design palette):
    /// a bullish→bearish ramp of green · green-teal · neutral · amber · red.
    var tint: Color {
        switch self {
        case .buy: return Palette.positive
        case .overweight: return Color(light: Color(red: 0.16, green: 0.58, blue: 0.49),
                                       dark: Color(red: 0.36, green: 0.80, blue: 0.69))
        case .hold: return Palette.neutral
        case .underweight: return Palette.warning
        case .sell: return Palette.negative
        }
    }
}

/// A small pill showing a rating, tinted by tier — a pastel fill of the tier hue
/// with same-hue text. Reads cleanly on any surface (selection is now a soft
/// card, so no special on-accent treatment is needed) and adapts to dark/light.
struct RatingChip: View {
    let rating: Rating

    var body: some View {
        Text(rating.short)
            .font(.caption2.weight(.semibold))
            .monospacedDigit()
            .padding(.horizontal, 7)
            .padding(.vertical, 2)
            .background(rating.tint.opacity(Tint.chipFill), in: Capsule())
            .foregroundStyle(rating.tint)
    }
}

extension View {
    /// Liquid Glass chrome, gated to macOS 26. Passthrough today so the app
    /// builds on the SwiftPM deployment target; wired to `.glassEffect` when the
    /// chrome pass lands (chrome surfaces only — never reading surfaces).
    @ViewBuilder
    func glassChrome() -> some View {
        self
    }
}
