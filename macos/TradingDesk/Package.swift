// swift-tools-version: 6.0
import PackageDescription

// TradingDesk — the native macOS app for TradingAgents.
//
// Started as a SwiftPM executable so it builds headlessly (`swift build`) and
// launches for live preview (`swift run`) without hand-authoring an .xcodeproj.
// An Xcode app target + bundle/entitlements/signing is added at the packaging
// milestone; the sources here move into it unchanged.
let package = Package(
    name: "TradingDesk",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "TradingDesk",
            path: "Sources/TradingDesk"
        )
    ]
)
