import SwiftUI

// MARK: - Button styles

/// The primary action (Run analysis): a soft accent-tinted fill with accent
/// label, with hover/press feedback. Matches the reference's calm "run" button.
struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        StyledButton(configuration: configuration)
    }

    private struct StyledButton: View {
        let configuration: ButtonStyleConfiguration
        @State private var hovering = false
        @Environment(\.isEnabled) private var enabled

        var body: some View {
            configuration.label
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(enabled ? Palette.accent : Palette.neutral)
                .padding(.horizontal, Space.m)
                .padding(.vertical, 5)
                .background(Palette.accent.opacity(fill), in: RoundedRectangle(cornerRadius: Radius.control))
                .scaleEffect(configuration.isPressed ? 0.97 : 1)
                .onHover { hovering = $0 }
                .animation(.easeOut(duration: 0.12), value: hovering)
                .animation(.easeOut(duration: 0.10), value: configuration.isPressed)
        }

        private var fill: Double {
            guard enabled else { return 0.07 }
            if configuration.isPressed { return 0.28 }
            return hovering ? 0.22 : 0.15
        }
    }
}

/// A destructive/secondary action (Stop): an outlined hairline button that fills
/// faintly red on hover.
struct DestructiveButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        StyledButton(configuration: configuration)
    }

    private struct StyledButton: View {
        let configuration: ButtonStyleConfiguration
        @State private var hovering = false

        var body: some View {
            configuration.label
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(Palette.negative)
                .padding(.horizontal, Space.m)
                .padding(.vertical, 5)
                .background(Palette.negative.opacity(hovering ? 0.10 : 0), in: RoundedRectangle(cornerRadius: Radius.control))
                .overlay(RoundedRectangle(cornerRadius: Radius.control)
                    .strokeBorder(Palette.negative.opacity(hovering ? 0.5 : 0.3), lineWidth: 1))
                .scaleEffect(configuration.isPressed ? 0.97 : 1)
                .onHover { hovering = $0 }
                .animation(.easeOut(duration: 0.12), value: hovering)
        }
    }
}

/// A borderless icon button (gear / refresh / +) that lifts on hover.
struct IconButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        StyledButton(configuration: configuration)
    }

    private struct StyledButton: View {
        let configuration: ButtonStyleConfiguration
        @State private var hovering = false

        var body: some View {
            configuration.label
                .foregroundStyle(hovering ? Color.primary : Color.secondary)
                .padding(5)
                .background(Color.primary.opacity(hovering ? Tint.hover : 0), in: RoundedRectangle(cornerRadius: 6))
                .scaleEffect(configuration.isPressed ? 0.92 : 1)
                .onHover { hovering = $0 }
                .animation(.easeOut(duration: 0.12), value: hovering)
        }
    }
}

// MARK: - Segmented tabs

/// A custom pill segmented control (e.g. Library / Journal): a raised white pill
/// slides over a sunken track via `matchedGeometryEffect`. Replaces the stock
/// `.segmented` Picker for a softer, more bespoke feel.
struct SegmentedTabs<T: Hashable & Identifiable>: View {
    let items: [T]
    let title: (T) -> String
    @Binding var selection: T
    @Namespace private var ns

    var body: some View {
        HStack(spacing: 2) {
            ForEach(items) { item in
                let isSelected = item == selection
                Text(title(item))
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(isSelected ? Color.primary : Color.secondary)
                    .padding(.horizontal, Space.m)
                    .padding(.vertical, 5)
                    .background {
                        if isSelected {
                            RoundedRectangle(cornerRadius: 7)
                                .fill(Palette.surfaceRaised)
                                .shadow(color: .black.opacity(0.12), radius: 2, y: 1)
                                .matchedGeometryEffect(id: "segpill", in: ns)
                        }
                    }
                    .contentShape(Rectangle())
                    .onTapGesture { withAnimation(.snappy(duration: 0.22)) { selection = item } }
            }
        }
        .padding(3)
        .background(Palette.surfaceSunken, in: RoundedRectangle(cornerRadius: 9))
        .fixedSize()
    }
}

// MARK: - Premium empty state

/// A premium empty/placeholder state — a soft-tinted icon medallion, a title,
/// an optional message, and an optional CTA. Replaces stock `ContentUnavailableView`.
struct PremiumEmptyState: View {
    let icon: String
    let title: String
    var message: String?
    var tint: Color = Palette.accent
    var actionTitle: String?
    var action: (() -> Void)?

    var body: some View {
        VStack(spacing: Space.m) {
            ZStack {
                Circle().fill(tint.opacity(0.12)).frame(width: 60, height: 60)
                Image(systemName: icon)
                    .font(.system(size: 24, weight: .regular))
                    .foregroundStyle(tint)
            }
            VStack(spacing: Space.xs) {
                Text(title).font(.system(size: 15, weight: .semibold))
                if let message {
                    Text(message)
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 300)
                }
            }
            if let actionTitle, let action {
                Button(actionTitle, action: action).buttonStyle(PrimaryButtonStyle())
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, Space.xl)
    }
}

// MARK: - Sparkline

/// A tiny trend line (watchlist rows). Token-colored by the caller.
struct Sparkline: View {
    let points: [Double]
    var color: Color = Palette.neutral

    var body: some View {
        GeometryReader { geo in
            if points.count > 1 {
                let minV = points.min() ?? 0
                let maxV = points.max() ?? 1
                let range = max(maxV - minV, 0.0001)
                Path { path in
                    for (i, v) in points.enumerated() {
                        let x = geo.size.width * CGFloat(i) / CGFloat(points.count - 1)
                        let y = geo.size.height * (1 - CGFloat((v - minV) / range))
                        let pt = CGPoint(x: x, y: y)
                        if i == 0 { path.move(to: pt) } else { path.addLine(to: pt) }
                    }
                }
                .stroke(color, style: StrokeStyle(lineWidth: 1.5, lineCap: .round, lineJoin: .round))
            }
        }
    }
}
