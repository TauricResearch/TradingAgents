/**
 * Defuddle Extension — Fetch any webpage as clean Markdown.
 *
 * Uses the hosted defuddle.md API: GET https://defuddle.md/<url>
 * Strips ads, navigation, cookies — returns only article content.
 *
 * Features:
 *   - Domain blacklist (cookie walls, paywalls, JS-heavy sites)
 *   - Domain whitelist (known-good sites, user-configurable)
 *   - JSONL telemetry log per fetch (.pi/defuddle-log.jsonl)
 *   - /defuddle stats — summary of success rates by domain
 */

import * as fs from "node:fs"
import * as path from "node:path"
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent"
import { Type } from "typebox"

const DEFUDDLE_BASE = "https://defuddle.md"
const FETCH_TIMEOUT_MS = 15_000
const MAX_CONTENT_LEN = 100_000
const WHITELIST_FILE = path.join(".pi", "defuddle-whitelist.json")
const TELEMETRY_FILE = path.join(".pi", "defuddle-log.jsonl")

/**
 * Sites known to fail (cookie walls, heavy JS, paywalls).
 * Checked against the URL hostname (substring match).
 */
const DEFAULT_BLACKLIST = [
  "yahoo.com", // cookie wall
  "reuters.com", // heavy JS / cookie gate
  "ft.com", // paywall
  "bloomberg.com", // paywall
  "wsj.com", // paywall
  "marketwatch.com", // cookie wall
  "cnbc.com", // cookie gate on article pages
  "seekingalpha.com", // paywall / JS
  "barrons.com", // paywall
  "theguardian.com", // consent wall
  "investopedia.com", // heavy JS
  "google.com", // not article content
  "facebook.com", // login wall
  "twitter.com", // JS SPA (use FxTwitter instead)
  "x.com", // JS SPA
  "reddit.com", // login wall / JS
]

function ensureDir(cwd: string) {
  const dir = path.join(cwd, ".pi")
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true })
}

// ---- Whitelist ----

function loadWhitelist(cwd: string): string[] {
  try {
    const fullPath = path.join(cwd, WHITELIST_FILE)
    if (fs.existsSync(fullPath)) {
      const raw = fs.readFileSync(fullPath, "utf-8")
      return JSON.parse(raw) as string[]
    }
  } catch {
    /* ignore */
  }
  return []
}

function saveWhitelist(cwd: string, list: string[]) {
  ensureDir(cwd)
  const fullPath = path.join(cwd, WHITELIST_FILE)
  fs.writeFileSync(fullPath, `${JSON.stringify(list, null, 2)}\n`)
}

// ---- Telemetry (append-only JSONL) ----

interface TelemetryEntry {
  domain: string
  url: string
  ok: boolean
  words?: number
  reason?: string
  status?: number
  ts: number
}

function appendTelemetry(cwd: string, entry: TelemetryEntry) {
  ensureDir(cwd)
  const fullPath = path.join(cwd, TELEMETRY_FILE)
  fs.appendFileSync(fullPath, `${JSON.stringify(entry)}\n`)
}

function loadTelemetry(cwd: string): TelemetryEntry[] {
  const fullPath = path.join(cwd, TELEMETRY_FILE)
  if (!fs.existsSync(fullPath)) return []
  const lines = fs.readFileSync(fullPath, "utf-8").trim().split("\n").filter(Boolean)
  return lines
    .map((line) => {
      try {
        return JSON.parse(line) as TelemetryEntry
      } catch {
        return null
      }
    })
    .filter(Boolean) as TelemetryEntry[]
}

// ---- Domain helpers ----

function extractDomain(url: string): string {
  try {
    return new URL(url).hostname.toLowerCase()
  } catch {
    return url.toLowerCase()
  }
}

function isBlacklisted(url: string): string | null {
  const domain = extractDomain(url)
  for (const blocked of DEFAULT_BLACKLIST) {
    if (domain.endsWith(blocked)) return blocked
  }
  return null
}

function isWhitelisted(url: string, whitelist: string[]): boolean {
  const domain = extractDomain(url)
  return whitelist.some((allowed) => domain.endsWith(allowed))
}

// Block private/internal URLs to prevent SSRF
const BLOCKED_PATTERNS = [
  /^https?:\/\/(localhost|127\.|0\.0\.0\.0)/i,
  /^https?:\/\/10\./i,
  /^https?:\/\/192\.168\./i,
  /^https?:\/\/172\.(1[6-9]|2\d|3[01])\./i,
  /^https?:\/\/169\.254\./i,
  /^(file|ftp|gopher|data):/i,
]

function isPrivate(url: string): boolean {
  return BLOCKED_PATTERNS.some((p) => p.test(url))
}

// ---- Core fetch ----

async function fetchDefuddle(
  url: string,
  whitelist: string[],
  signal?: AbortSignal,
): Promise<{
  ok: boolean
  text?: string
  wordCount?: number
  truncated?: boolean
  error?: string
  status?: number
  reason?: string
}> {
  if (!url || (!url.startsWith("http://") && !url.startsWith("https://"))) {
    return {
      ok: false,
      error: `Invalid URL: ${url}. Must start with http:// or https://`,
      reason: "invalid_url",
    }
  }

  if (isPrivate(url)) {
    return { ok: false, error: `Blocked: ${url} is a private/internal URL.`, reason: "private_url" }
  }

  const blockedBy = isBlacklisted(url)
  if (blockedBy && !isWhitelisted(url, whitelist)) {
    return {
      ok: false,
      error: `Blocked: ${url} matches blacklisted domain "${blockedBy}". Use /defuddle allow <domain> to override.`,
      reason: "blacklisted",
    }
  }

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)
  signal?.addEventListener("abort", () => controller.abort())

  try {
    const resp = await fetch(`${DEFUDDLE_BASE}/${url}`, {
      signal: controller.signal,
      headers: { Accept: "text/plain" },
    })

    if (!resp.ok) {
      return { ok: false, error: `HTTP ${resp.status}`, status: resp.status, reason: "http_error" }
    }

    let text = await resp.text()
    const truncated = text.length > MAX_CONTENT_LEN
    if (truncated) text = `${text.slice(0, MAX_CONTENT_LEN)}\n\n[Content truncated]`

    if (text.trim().length < 50) {
      return {
        ok: false,
        error: "Minimal content returned — page may be JS-rendered or not an article.",
        reason: "minimal_content",
      }
    }

    return { ok: true, text, wordCount: text.split(/\s+/).length, truncated }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    return { ok: false, error: `Fetch failed: ${message}`, reason: "fetch_failed" }
  } finally {
    clearTimeout(timeout)
  }
}

export default function (pi: ExtensionAPI) {
  // ---------- Tool ----------

  pi.registerTool({
    name: "defuddle",
    label: "Defuddle",
    description:
      "Fetch a webpage URL and return its main content as clean Markdown. Strips ads, navigation, and sidebar clutter. Respects domain black/whitelist.",
    parameters: Type.Object({
      url: Type.String({
        description: "Full HTTP(S) URL of the webpage to fetch and convert to Markdown",
      }),
    }),
    promptSnippet: "Fetch webpage content as clean Markdown",
    promptGuidelines: [
      "Use defuddle to read full article content from URLs found in search results, news feeds, or documentation pages.",
      "Prefer defuddle over read or web_fetch when you need cleaned article content rather than raw HTML.",
      "If defuddle is blocked for a domain, ask the user to run /defuddle allow <domain> first.",
    ],

    async execute(_toolCallId, params, signal) {
      const cwd = pi.cwd ?? process.cwd()
      const whitelist = loadWhitelist(cwd)
      const result = await fetchDefuddle(params.url, whitelist, signal)

      // Telemetry — record every tool call
      appendTelemetry(cwd, {
        domain: extractDomain(params.url),
        url: params.url,
        ok: result.ok,
        words: result.wordCount,
        reason: result.reason,
        status: result.status,
        ts: Date.now(),
      })

      if (!result.ok) {
        return {
          content: [{ type: "text", text: result.error ?? "Unknown error" }],
          details: { error: result.error, reason: result.reason },
          isError: true,
        }
      }

      return {
        content: [{ type: "text", text: result.text ?? "" }],
        details: { url: params.url, wordCount: result.wordCount, truncated: result.truncated },
      }
    },
  })

  // ---------- Command ----------

  pi.registerCommand("defuddle", {
    description: "Fetch a webpage as Markdown; manage domain lists; view stats",
    getArgumentCompletions(prefix: string) {
      const items = [
        { value: "allow", label: "allow <domain> — whitelist a domain" },
        { value: "block", label: "block <domain> — add to blacklist" },
        { value: "list", label: "list — show black/white lists" },
        { value: "stats", label: "stats — fetch success rates by domain" },
      ]
      if (!prefix) return items
      return items.filter((i) => i.value.startsWith(prefix))
    },
    handler: async (args, ctx) => {
      const input = args?.trim()
      if (!input) {
        ctx.ui.notify("Usage: /defuddle <url>  |  allow|block|list|stats [args]", "error")
        return
      }

      const whitelist = loadWhitelist(ctx.cwd)

      // Subcommands

      if (input === "stats") {
        const entries = loadTelemetry(ctx.cwd)
        if (entries.length === 0) {
          ctx.ui.notify(
            "No fetch history yet. Use /defuddle <url> or the defuddle tool to start.",
            "info",
          )
          return
        }

        // Aggregate by domain
        const byDomain = new Map<
          string,
          { ok: number; fail: number; totalWords: number; reasons: string[] }
        >()
        for (const e of entries) {
          const d = byDomain.get(e.domain) ?? { ok: 0, fail: 0, totalWords: 0, reasons: [] }
          if (e.ok) {
            d.ok++
            d.totalWords += e.words ?? 0
          } else {
            d.fail++
            if (e.reason && !d.reasons.includes(e.reason)) d.reasons.push(e.reason)
          }
          byDomain.set(e.domain, d)
        }

        const lines: string[] = []
        lines.push(`Fetch log: ${entries.length} attempts across ${byDomain.size} domains\n`)

        // Sort: lowest success rate first (problems on top)
        const sorted = [...byDomain.entries()].sort((a, b) => {
          const rateA = a[1].ok / (a[1].ok + a[1].fail)
          const rateB = b[1].ok / (b[1].ok + b[1].fail)
          return rateA - rateB
        })

        for (const [domain, stats] of sorted) {
          const total = stats.ok + stats.fail
          const rate = total > 0 ? Math.round((stats.ok / total) * 100) : 0
          const avgWords = stats.ok > 0 ? Math.round(stats.totalWords / stats.ok) : 0
          const icon = rate >= 80 ? "✓" : rate >= 50 ? "⚠" : "✗"
          let line = `${icon} ${domain}: ${stats.ok}/${total} ok (${rate}%)`
          if (avgWords > 0) line += `, avg ${avgWords}w`
          if (stats.reasons.length > 0) line += ` — failures: ${stats.reasons.join(", ")}`
          lines.push(line)
        }

        ctx.ui.notify(lines.join("\n"), "info")
        return
      }

      if (input === "list") {
        const lines: string[] = []
        lines.push("Blacklisted domains (blocked unless whitelisted):")
        for (const d of DEFAULT_BLACKLIST) lines.push(`  ✗ ${d}`)
        lines.push("")
        lines.push(`Whitelisted domains (override blacklist):`)
        if (whitelist.length === 0) {
          lines.push("  (none)")
        } else {
          for (const d of whitelist) lines.push(`  ✓ ${d}`)
        }
        ctx.ui.notify(lines.join("\n"), "info")
        return
      }

      if (input.startsWith("allow ")) {
        const domain = input.slice(6).trim().toLowerCase()
        if (!domain) {
          ctx.ui.notify("Usage: /defuddle allow <domain>", "error")
          return
        }
        if (!whitelist.includes(domain)) {
          whitelist.push(domain)
          saveWhitelist(ctx.cwd, whitelist)
        }
        ctx.ui.notify(`Whitelisted: ${domain}`, "success")
        return
      }

      if (input.startsWith("block ")) {
        const domain = input.slice(6).trim().toLowerCase()
        if (!domain) {
          ctx.ui.notify("Usage: /defuddle block <domain>", "error")
          return
        }
        if (!DEFAULT_BLACKLIST.includes(domain)) DEFAULT_BLACKLIST.push(domain)
        ctx.ui.notify(`Blocked: ${domain} (session-only)`, "success")
        return
      }

      // Otherwise: treat as a URL
      ctx.ui.setStatus("defuddle", "Fetching…")
      const result = await fetchDefuddle(input, whitelist)
      ctx.ui.setStatus("defuddle", undefined)

      // Telemetry — record every command fetch
      appendTelemetry(ctx.cwd, {
        domain: extractDomain(input),
        url: input,
        ok: result.ok,
        words: result.wordCount,
        reason: result.reason,
        status: result.status,
        ts: Date.now(),
      })

      if (!result.ok) {
        ctx.ui.notify(`Defuddle failed: ${result.error}`, "error")
        return
      }

      const summary = `${result.wordCount} words${result.truncated ? " (truncated)" : ""}`
      ctx.ui.notify(`defuddle ${input} — ${summary}`, "success")

      pi.sendUserMessage(`Here is the content of ${input}:\n\n${result.text}`, {
        deliverAs: "followUp",
      })
    },
  })
}
