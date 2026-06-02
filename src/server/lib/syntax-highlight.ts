/**
 * Server-side syntax highlighting via highlight.js.
 * Renders code blocks as HTML with language-specific token classes.
 */

import hljs from "highlight.js"

/**
 * Highlight source code. Returns HTML string with hljs CSS classes.
 * The result is safe for dangerouslySetInnerHTML.
 */
export function highlightCode(source: string, language?: string): string {
  if (!language || language === "text") {
    return escapeHtml(source)
  }

  const lang = hljs.getLanguage(language)
  if (!lang) {
    return escapeHtml(source)
  }

  try {
    const result = hljs.highlight(source, { language })
    return result.value
  } catch {
    return escapeHtml(source)
  }
}

/** Escape HTML entities for plain text code blocks. */
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
}

/**
 * Map file extension to highlight.js language identifier.
 */
export function highlightLanguage(path: string): string | null {
  const ext = path.split(".").pop()?.toLowerCase() ?? ""
  switch (ext) {
    case "ts":
    case "tsx":
      return "typescript"
    case "js":
    case "jsx":
      return "javascript"
    case "py":
      return "python"
    case "json":
      return "json"
    case "yaml":
    case "yml":
      return "yaml"
    case "toml":
      return "ini" // highlight.js doesn't have TOML; ini is closest
    case "sql":
      return "sql"
    case "css":
      return "css"
    case "html":
      return "xml"
    case "md":
      return "markdown"
    case "sh":
    case "bash":
      return "bash"
    case "xml":
    case "svg":
      return "xml"
    default:
      return null
  }
}

/**
 * Render a pretty-printed JSON string (safe for HTML).
 */
export function prettyPrintJson(raw: string): string {
  try {
    const parsed = JSON.parse(raw)
    const formatted = JSON.stringify(parsed, null, 2)
    return highlightCode(formatted, "json")
  } catch {
    return escapeHtml(raw)
  }
}
