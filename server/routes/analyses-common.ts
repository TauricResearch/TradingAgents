/** Shared helpers for analyses routes — filesystem and DB operations both use these. */
import { existsSync, readdirSync, readFileSync } from "node:fs"
import { join } from "node:path"
import { cfg } from "../lib/settings.ts"

/** Default results directory: ~/.tradingagents/logs */
export function resultsDir(): string {
  return cfg.paths.resultsDir
}

export function extractSignal(text: string): string {
  const lower = text.toLowerCase()
  if (lower.includes("overweight") || lower.includes("buy")) return "Overweight"
  if (lower.includes("underweight") || lower.includes("sell")) return "Underweight"
  return "Hold"
}

export function extractConfidence(text: string): number | null {
  const confMatch = text.match(/[Cc]onfidence[:\s]*([0-9.]+)/)
  return confMatch?.[1] ? parseFloat(confMatch[1]) : null
}

export function estimateConfidence(text: string, signal: string): number {
  const lower = text.toLowerCase()
  if (lower.includes("strong") || lower.includes("high conviction")) return 0.8
  if (lower.includes("cautious") || lower.includes("conditional")) return 0.5
  if (lower.includes("reduce") || lower.includes("trim")) return 0.4
  if (signal === "Overweight") return 0.7
  if (signal === "Underweight") return 0.6
  return 0.5
}

export function extractActions(text: string): Array<{ label: string; text: string }> {
  const items: Array<{ label: string; text: string }> = []
  const summaryMatch = text.match(/\*\*Executive Summary\*\*[:\s]*([\s\S]*?)(?=\n\*\*|$)/)
  if (!summaryMatch?.[1]) return items
  const body = summaryMatch[1].trim()

  const sizeMatch = body.match(/(\d+\.?\d*x\s*(?:to|–|-)\s*\d+\.?\d*x\s*benchmark)/i)
  if (sizeMatch?.[1]) items.push({ label: "Position size", text: sizeMatch[1] })

  const entryMatch = body.match(/(build[^,]+in tranches[^,.]*[,.])/i)
  if (entryMatch?.[1])
    items.push({ label: "Entry", text: entryMatch[1].replace(/[,.]$/, "").trim() })
  const pullbackMatch = body.match(/(prioritizing[^,.]+[,.])/i)
  if (pullbackMatch?.[1])
    items.push({ label: "Strategy", text: pullbackMatch[1].replace(/[,.]$/, "").trim() })

  const riskMatch = body.match(/(tighten risk[^,.]+[,.]|(?:stop|invalidation)[^,.]*[,.])/i)
  if (riskMatch?.[1])
    items.push({ label: "Risk control", text: riskMatch[1].replace(/[,.]$/, "").trim() })

  const horizonMatch = body.match(
    /((?:\d+[-–]?\d+\s*(?:month|week|day|year)[^,.]*)|(?:short|medium|long)[- ]?term[^,.]*[,.])/i,
  )
  if (horizonMatch?.[1])
    items.push({ label: "Horizon", text: horizonMatch[1].replace(/[,.]$/, "").trim() })

  const watchMatch = body.match(/(reassess if[^,.]+[,.]|monitor[^,.]+[,.]|watch for[^,.]+[,.])/i)
  if (watchMatch?.[1])
    items.push({ label: "Watch for", text: watchMatch[1].replace(/[,.]$/, "").trim() })

  if (items.length === 0) {
    const parts = body.split(/[;,.]/).filter((s) => s.trim().length > 20)
    for (const p of parts.slice(0, 4)) {
      items.push({ label: "", text: p.trim() })
    }
  }
  return items.slice(0, 6)
}

export function buildConfidenceSparkline(ticker: string, current: string): number[] {
  const root = resultsDir()
  const logDir = join(root, ticker, "TradingAgentsStrategy_logs")
  if (!existsSync(logDir)) return []

  const values: Array<{ date: string; conf: number }> = []
  for (const file of readdirSync(logDir)) {
    const m = file.match(/^full_states_log_(.+)\.json$/)
    if (!m?.[1]) continue
    const date = m[1]
    if (date > current) continue
    try {
      const raw = readFileSync(join(logDir, file), "utf-8")
      const state = JSON.parse(raw) as Record<string, unknown>
      const decision = String(state.final_trade_decision ?? "")
      const conf =
        extractConfidence(decision) ?? estimateConfidence(decision, extractSignal(decision))
      values.push({ date, conf })
    } catch {
      /* skip */
    }
  }
  values.sort((a, b) => a.date.localeCompare(b.date))
  return values.map((v) => Math.round(v.conf * 100))
}

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
}

export function signalClass(signal: string): string {
  const s = signal.toLowerCase()
  if (s.includes("buy") || s.includes("overweight")) return "status-buy"
  if (s.includes("sell") || s.includes("underweight")) return "status-sell"
  return "status-hold"
}
