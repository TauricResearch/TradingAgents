import Foundation
import Security

/// Minimal Keychain wrapper for API keys, stored as generic passwords keyed by
/// the provider's env-var name (e.g. "OPENROUTER_API_KEY"). Keys never touch
/// disk in plaintext; they are passed to the backend in-memory at run time.
enum KeychainStore {
    static let service = "ai.tauric.tradingdesk"

    static func set(_ value: String, account: String) {
        let base: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(base as CFDictionary)
        guard !value.isEmpty else { return }
        var add = base
        add[kSecValueData as String] = Data(value.utf8)
        add[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        SecItemAdd(add as CFDictionary, nil)
    }

    static func get(account: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data,
              let value = String(data: data, encoding: .utf8)
        else { return nil }
        return value
    }

    /// Existence check only — deliberately does NOT request the secret data
    /// (`kSecReturnData`) and suppresses the auth UI, so launch-time key-status
    /// refreshes never trigger a Keychain prompt or block the main thread. The
    /// actual value is read (which may prompt once) only when a run starts.
    /// `errSecInteractionNotAllowed` means the item exists but is gated — still
    /// "present" for gating purposes.
    static func has(account: String) -> Bool {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecMatchLimit as String: kSecMatchLimitOne,
            kSecUseAuthenticationUI as String: kSecUseAuthenticationUIFail,
        ]
        let status = SecItemCopyMatching(query as CFDictionary, nil)
        return status == errSecSuccess || status == errSecInteractionNotAllowed
    }
}
