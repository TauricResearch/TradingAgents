import Foundation
import Observation

struct ModelOption: Identifiable, Hashable {
    var id: String { modelID }
    let label: String
    let modelID: String
}

struct ProviderInfo: Identifiable {
    var id: String { name }
    let name: String
    let apiKeyEnv: String?
    let baseURL: String?
    let keyOptional: Bool
    let quickModels: [ModelOption]
    let deepModels: [ModelOption]
}

/// Provider/model/language metadata sourced from the engine (`/capabilities`),
/// so the Settings UI never hard-codes or drifts from the backend. Singleton so
/// the main window and the Settings scene share one instance.
@MainActor
@Observable
final class CapabilitiesStore {
    static let shared = CapabilitiesStore()
    let baseURL = DeskBackend.baseURL

    private(set) var providers: [ProviderInfo] = []
    private(set) var languages: [String] = []
    private(set) var openRouterModels: [ModelOption] = []
    private(set) var loaded = false

    func load() async {
        guard let (data, resp) = try? await URLSession.shared.data(from: baseURL.appending(path: "capabilities")),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return }

        if let provs = obj["providers"] as? [[String: Any]] {
            providers = provs.map { p in
                ProviderInfo(
                    name: p["name"] as? String ?? "",
                    apiKeyEnv: p["api_key_env"] as? String,
                    baseURL: p["base_url"] as? String,
                    keyOptional: p["key_optional"] as? Bool ?? false,
                    quickModels: Self.parseModels(p["quick_models"]),
                    deepModels: Self.parseModels(p["deep_models"])
                )
            }
        }
        languages = (obj["output_languages"] as? [String]) ?? []
        loaded = true
    }

    func provider(_ name: String) -> ProviderInfo? { providers.first { $0.name == name } }

    /// Map a backend `[{label, model_id}]` array into `[ModelOption]`.
    private static func parseModels(_ raw: Any?) -> [ModelOption] {
        (raw as? [[String: Any]] ?? []).compactMap { m in
            guard let label = m["label"] as? String, let id = m["model_id"] as? String else { return nil }
            return ModelOption(label: label, modelID: id)
        }
    }

    func loadOpenRouterModels() async {
        guard openRouterModels.isEmpty else { return }
        guard let (data, resp) = try? await URLSession.shared.data(from: baseURL.appending(path: "openrouter/models")),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let arr = obj["models"] as? [[String: Any]]
        else { return }
        openRouterModels = Self.parseModels(arr)
    }

    /// Quick availability check via the backend (/test): builds the client and pings.
    func testModel(provider: String, model: String, baseURL urlOverride: String?, keys: [String: String]) async -> (ok: Bool, error: String?) {
        var req = URLRequest(url: baseURL.appending(path: "test"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 60
        var body: [String: Any] = ["llm_provider": provider, "model": model, "keys": keys]
        if let urlOverride { body["backend_url"] = urlOverride }
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return (false, "request failed") }
        return ((obj["ok"] as? Bool) ?? false, obj["error"] as? String)
    }

    func testFred(key: String) async -> (ok: Bool, error: String?) {
        var req = URLRequest(url: baseURL.appending(path: "test_fred"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 30
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["key": key])
        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return (false, "request failed") }
        return ((obj["ok"] as? Bool) ?? false, obj["error"] as? String)
    }
}
