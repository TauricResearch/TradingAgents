import SwiftUI

/// Run configuration, shown as a centered sheet over the main window. Edits are
/// held as a draft and only persisted when the user presses Save.
struct SettingsView: View {
    @Environment(\.dismiss) private var dismiss
    @Bindable private var store = SettingsStore.shared
    private var caps: CapabilitiesStore { .shared }

    @State private var provider: String
    @State private var deepModel: String
    @State private var quickModel: String
    @State private var analysts: [String]
    @State private var debateRounds: Int
    @State private var riskRounds: Int
    @State private var tradeDate: Date
    @State private var language: String
    @State private var apiKey = ""
    @State private var fredKey = ""

    init() {
        let s = SettingsStore.shared
        _provider = State(initialValue: s.provider)
        _deepModel = State(initialValue: s.deepModel)
        _quickModel = State(initialValue: s.quickModel)
        _analysts = State(initialValue: s.analysts)
        _debateRounds = State(initialValue: s.debateRounds)
        _riskRounds = State(initialValue: s.riskRounds)
        _tradeDate = State(initialValue: s.tradeDate)
        _language = State(initialValue: s.outputLanguage)
    }

    private var providerInfo: ProviderInfo? { caps.provider(provider) }
    private var deepOptions: [ModelOption] { provider == "openrouter" ? caps.openRouterModels : (providerInfo?.deepModels ?? []) }
    private var quickOptions: [ModelOption] { provider == "openrouter" ? caps.openRouterModels : (providerInfo?.quickModels ?? []) }

    /// Drives the Shallow/Medium/Deep preset. Reads as the matching preset (1/3/5)
    /// only when both round counts agree, else "Custom" (0); selecting a preset
    /// sets both rounds, while tapping "Custom" is a no-op.
    private var depthPreset: Binding<Int> {
        Binding(
            get: {
                guard debateRounds == riskRounds, [1, 3, 5].contains(debateRounds) else { return 0 }
                return debateRounds
            },
            set: { newValue in
                guard newValue != 0 else { return }
                debateRounds = newValue
                riskRounds = newValue
            }
        )
    }

    var body: some View {
        VStack(spacing: 0) {
            Text("Settings").font(.headline).padding(.top, 14).padding(.bottom, 4)

            Form {
                Section("Appearance") {
                    Picker("Theme", selection: $store.appearance) {
                        ForEach(AppearanceMode.allCases) { Text($0.label).tag($0) }
                    }
                    .pickerStyle(.segmented)
                }

                Section("Provider & models") {
                    Picker("Provider", selection: $provider) {
                        ForEach(caps.providers) { Text($0.name).tag($0.name) }
                    }
                    ModelField(title: "Deep model", options: deepOptions, value: $deepModel)
                    ModelField(title: "Quick model", options: quickOptions, value: $quickModel)
                    if let url = providerInfo?.baseURL {
                        Text(url).font(.caption2).foregroundStyle(.secondary)
                    }
                }

                Section("API keys") {
                    if let env = providerInfo?.apiKeyEnv {
                        keyRow(label: env, text: $apiKey) {
                            await caps.testModel(provider: provider, model: deepModel,
                                                 baseURL: providerInfo?.baseURL, keys: [env: apiKey])
                        }
                    } else {
                        Text("This provider needs no API key.").font(.callout).foregroundStyle(.secondary)
                    }
                    keyRow(label: "FRED_API_KEY", text: $fredKey) {
                        await caps.testFred(key: fredKey)
                    }
                }

                Section("Analysts") {
                    ForEach(SettingsStore.analystOptions, id: \.key) { option in
                        Toggle(option.label, isOn: Binding(
                            get: { analysts.contains(option.key) },
                            set: { isOn in
                                if isOn {
                                    if !analysts.contains(option.key) { analysts.append(option.key) }
                                } else {
                                    analysts.removeAll { $0 == option.key }
                                }
                            }
                        ))
                    }
                }

                Section("Research depth") {
                    Picker("Preset", selection: depthPreset) {
                        Text("Shallow").tag(1)
                        Text("Medium").tag(3)
                        Text("Deep").tag(5)
                        Text("Custom").tag(0)
                    }
                    .pickerStyle(.segmented)
                    Stepper(value: $debateRounds, in: 1...20) {
                        Text("Debate rounds: \(debateRounds)")
                    }
                    Stepper(value: $riskRounds, in: 1...20) {
                        Text("Risk rounds: \(riskRounds)")
                    }
                }

                Section("Run") {
                    DatePicker("Trade date", selection: $tradeDate, in: ...Date(), displayedComponents: .date)
                    Picker("Output language", selection: $language) {
                        ForEach(caps.languages.isEmpty ? ["English"] : caps.languages, id: \.self) { Text($0).tag($0) }
                    }
                }
            }
            .formStyle(.grouped)

            Divider()
            HStack {
                Button("Cancel") { dismiss() }
                Spacer()
                Button("Save") { save() }
                    .keyboardShortcut(.defaultAction)
                    .buttonStyle(PrimaryButtonStyle())
            }
            .padding(12)
        }
        .frame(width: 520, height: 660)
        .task {
            if !caps.loaded { await caps.load() }
            if provider == "openrouter" { await caps.loadOpenRouterModels() }
            loadKeys()
            normalizeModels()
        }
        .onChange(of: provider) { _, _ in
            loadKeys()
            Task {
                if provider == "openrouter" { await caps.loadOpenRouterModels() }
                normalizeModels()
            }
        }
    }

    /// Keep the selected models valid for the current provider's catalog,
    /// preferring gpt-4o-mini when present, else the first option.
    private func normalizeModels() {
        deepModel = Self.normalized(deepModel, in: deepOptions)
        quickModel = Self.normalized(quickModel, in: quickOptions)
    }

    /// Keep `model` valid for `options`, preferring gpt-4o-mini, else the first.
    private static func normalized(_ model: String, in options: [ModelOption]) -> String {
        guard !options.isEmpty, !options.contains(where: { $0.modelID == model }) else { return model }
        return options.first(where: { $0.modelID == "openai/gpt-4o-mini" })?.modelID ?? options[0].modelID
    }

    /// A native, borderless key row: leading label, left-aligned secure field,
    /// and a per-row connectivity test button — all vertically centered.
    private func keyRow(label: String, text: Binding<String>,
                        test: @escaping () async -> (ok: Bool, error: String?)) -> some View {
        HStack(spacing: 10) {
            Text(label)
                .font(.callout)
                .foregroundStyle(.secondary)
                .frame(width: 168, alignment: .leading)
            SecureField("", text: text)
                .textFieldStyle(.plain)
                .multilineTextAlignment(.leading)
            ConnectivityButton(input: text.wrappedValue, test: test)
        }
    }

    private func loadKeys() {
        // Pre-fill with the saved key so it shows as masked dots (a normal saved
        // password field) and the user never re-enters it. Save only writes when the
        // field is non-empty (see save()), so a stored key is never wiped by accident.
        apiKey = providerInfo?.apiKeyEnv.flatMap { KeychainStore.get(account: $0) } ?? ""
        fredKey = KeychainStore.get(account: "FRED_API_KEY") ?? ""
    }

    private func save() {
        let s = SettingsStore.shared
        s.provider = provider
        s.deepModel = deepModel
        s.quickModel = quickModel
        s.analysts = analysts
        s.debateRounds = debateRounds
        s.riskRounds = riskRounds
        s.tradeDate = tradeDate
        s.outputLanguage = language
        // Only write when the user actually typed a key — a blank field means "keep
        // the saved one", so reopening Settings and saving never wipes it.
        if let env = providerInfo?.apiKeyEnv, !apiKey.isEmpty { KeychainStore.set(apiKey, account: env) }
        if !fredKey.isEmpty { KeychainStore.set(fredKey, account: "FRED_API_KEY") }
        s.refreshKeyStatus()
        dismiss()
    }
}

/// A per-row connectivity test button whose icon reflects status: idle →
/// testing (spinner) → connected (green) / failed (red, with the error in its
/// tooltip). Resets to idle when the field value changes.
struct ConnectivityButton: View {
    let input: String
    let test: () async -> (ok: Bool, error: String?)

    @State private var state: ConnState = .idle

    enum ConnState: Equatable {
        case idle, testing, ok, failed(String)
    }

    var body: some View {
        Button {
            Task {
                state = .testing
                let result = await test()
                state = result.ok ? .ok : .failed(result.error ?? "failed")
            }
        } label: {
            switch state {
            case .idle:
                Image(systemName: "bolt.horizontal.circle")
                    .foregroundStyle(input.isEmpty ? AnyShapeStyle(.tertiary) : AnyShapeStyle(.secondary))
            case .testing:
                ProgressView().controlSize(.small)
            case .ok:
                Image(systemName: "checkmark.circle.fill").foregroundStyle(Palette.positive)
            case .failed:
                Image(systemName: "xmark.circle.fill").foregroundStyle(Palette.negative)
            }
        }
        .buttonStyle(.borderless)
        .disabled(input.isEmpty || state == .testing)
        .help(helpText)
        .onChange(of: input) { _, _ in state = .idle }
    }

    private var helpText: String {
        switch state {
        case .idle: return "Test connectivity"
        case .testing: return "Testing…"
        case .ok: return "Connected"
        case .failed(let message): return message
        }
    }
}

/// A model selector: a Picker over a catalog, or a free-text field when the
/// provider only accepts a custom model id (or the catalog hasn't loaded).
struct ModelField: View {
    let title: String
    let options: [ModelOption]
    @Binding var value: String

    private var customOnly: Bool { options.isEmpty || options.allSatisfy { $0.modelID == "custom" } }

    var body: some View {
        if customOnly {
            LabeledContent(title) {
                TextField("model id", text: $value).multilineTextAlignment(.trailing)
            }
        } else {
            Picker(title, selection: $value) {
                ForEach(options) { Text($0.label).tag($0.modelID) }
            }
        }
    }
}
