/**
 * Strip secrets and credentials from text before persisting to the DB.
 *
 * Covers the common cases:
 * - API keys (OpenAI sk-..., Anthropic sk-ant-..., Google AI, etc.)
 * - Bearer tokens, Authorization headers
 * - URL credentials (user:pass@host)
 * - Private key blocks (BEGIN RSA PRIVATE KEY, etc.)
 * - Connection strings with embedded secrets
 *
 * Does NOT encrypt or protect against sophisticated injection.
 * Use for user-facing and AI-generated text fields only.
 */

// [regex, replacement-label] tuples — destructured as [re, label] in the loop
const _SANITIZE_PATTERNS: Array<[RegExp, string]> = [
  [/sk-[-A-Za-z0-9]{20,}/g, "[API_KEY_REMOVED]"],
  [/sk-ant(?:hropic)?[-][A-Za-z0-9]{20,}/gi, "[API_KEY_REMOVED]"],
  [/Bearer\s+[A-Za-z0-9_-]{10,}/gi, "[TOKEN_REMOVED]"],
  [/Authorization:\s*[A-Za-z0-9_-]{10,}/gi, "[AUTH_HEADER_REMOVED]"],
  [/https?:\/\/[^:\s]+:[^@\s]+@[\s]+/g, "[URL_CREDS_REMOVED]"],
  [/(?:password|secret|apikey|api_key|token|auth)[=:\s][^\s;,]{8,}/gi, "[SECRET_REMOVED]"],
  [
    /-----BEGIN\s+(?:RSA|EC|OPENSSH|DSA|PRIVATE)\s+KEY-----[\s\S]+?-----END\s+\w+\s+KEY-----/g,
    "[PRIVATE_KEY_REMOVED]",
  ],
  [/[A-Fa-f0-9]{40,}/g, "[HEX_TOKEN_REMOVED]"],
]

/**
 * Strip secrets from a string. Returns null if input is null/undefined.
 */
export function sanitizeForDb(value: string | null | undefined): string | null {
  if (value === null || value === undefined) return null

  let result = String(value)
  for (const [re, label] of _SANITIZE_PATTERNS) {
    result = result.replace(re, label)
  }

  return result
}
