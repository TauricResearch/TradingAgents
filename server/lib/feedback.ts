/**
 * Feedback loop — post-mortems and signal accuracy tracking.
 *
 * Post-mortems are stored as markdown files in ~/.tradingagents/post-mortems/.
 * Signal accuracy is computed by comparing signal history (SQLite) against
 * exit outcomes (post-mortem files).
 */

import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"

const POST_MORTEMS_DIR =
  process.env.POST_MORTEMS_DIR ?? join(process.env.HOME ?? "/tmp", ".tradingagents", "post-mortems")

const DECISIONS_DIR =
  process.env.DECISIONS_DIR ?? join(process.env.HOME ?? "/tmp", ".tradingagents", "decisions")

export interface PostMortem {
  ticker: string
  exitDate: string
  exitPrice: number
  entryPrice: number
  thesis: string
  thesisPlayedOut: boolean
  aiSignalCorrect: boolean
  exitTrigger: "stop" | "target" | "time-stop" | "manual"
  lesson: string
}

export interface SignalAccuracy {
  totalSignals: number
  correctSignals: number
  accuracyPct: number
  bySignalType: Record<string, { total: number; correct: number; pct: number }>
}

/**
 * Save a post-mortem for an exited position.
 */
export function savePostMortem(pm: PostMortem): string {
  const dir = POST_MORTEMS_DIR
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })

  const date = pm.exitDate.replace(/-/g, "")
  const file = join(dir, `${date}-${pm.ticker}.md`)

  const content = `# Post-Mortem: ${pm.ticker}

**Exit Date:** ${pm.exitDate}
**Entry Price:** €${pm.entryPrice.toFixed(2)}
**Exit Price:** €${pm.exitPrice.toFixed(2)}
**Return:** ${(((pm.exitPrice - pm.entryPrice) / pm.entryPrice) * 100).toFixed(1)}%

## Thesis
${pm.thesis}

## Outcome
- Thesis played out: ${pm.thesisPlayedOut ? "✅ Yes" : "❌ No"}
- AI signal correct: ${pm.aiSignalCorrect ? "✅ Yes" : "❌ No"}
- Exit trigger: ${pm.exitTrigger}

## Lesson
${pm.lesson}
`

  writeFileSync(file, content, "utf-8")
  return file
}

/**
 * Load all post-mortems.
 */
export function loadPostMortems(): PostMortem[] {
  if (!existsSync(POST_MORTEMS_DIR)) return []

  const mortems: PostMortem[] = []
  for (const file of readdirSync(POST_MORTEMS_DIR)) {
    if (!file.endsWith(".md")) continue
    try {
      const content = readFileSync(join(POST_MORTEMS_DIR, file), "utf-8")
      const pm = parsePostMortem(content)
      if (pm) mortems.push(pm)
    } catch {
      // Skip malformed files
    }
  }
  return mortems
}

/**
 * Parse a post-mortem markdown file into a structured object.
 */
function parsePostMortem(content: string): PostMortem | null {
  const extract = (key: string): string => {
    const m = content.match(new RegExp(`\\*\\*${key}:\\*\\*\\s*(.+)`))
    return m?.[1]?.trim() ?? ""
  }

  const tickerMatch = content.match(/# Post-Mortem:\s*(\S+)/)
  if (!tickerMatch) return null
  const ticker = tickerMatch[1]
  if (!ticker) return null

  const thesisPlayedOut = content.includes("Thesis played out: ✅")
  const aiSignalCorrect = content.includes("AI signal correct: ✅")

  let exitTrigger: PostMortem["exitTrigger"] = "manual"
  const triggerMatch = content.match(/Exit trigger:\s*(stop|target|time-stop|manual)/)
  if (triggerMatch) exitTrigger = triggerMatch[1] as PostMortem["exitTrigger"]

  return {
    ticker: ticker,
    exitDate: extract("Exit Date"),
    exitPrice: parseFloat(extract("Exit Price").replace(/[€,\s]/g, "")) || 0,
    entryPrice: parseFloat(extract("Entry Price").replace(/[€,\s]/g, "")) || 0,
    thesis: extract("Thesis"),
    thesisPlayedOut,
    aiSignalCorrect,
    exitTrigger,
    lesson: content.split("## Lesson")[1]?.trim() ?? "",
  }
}

/**
 * Compute signal accuracy from post-mortems.
 */
export function computeSignalAccuracy(mortems: PostMortem[]): SignalAccuracy {
  const byType: Record<string, { total: number; correct: number }> = {}
  let total = 0
  let correct = 0

  for (const pm of mortems) {
    total++
    if (pm.aiSignalCorrect) correct++

    // Group by exit trigger as a proxy for signal type
    const type = pm.exitTrigger
    if (!byType[type]) byType[type] = { total: 0, correct: 0 }
    byType[type].total++
    if (pm.aiSignalCorrect) byType[type].correct++
  }

  const bySignalType: Record<string, { total: number; correct: number; pct: number }> = {}
  for (const [type, data] of Object.entries(byType)) {
    bySignalType[type] = {
      total: data.total,
      correct: data.correct,
      pct: data.total > 0 ? Math.round((data.correct / data.total) * 100) : 0,
    }
  }

  return {
    totalSignals: total,
    correctSignals: correct,
    accuracyPct: total > 0 ? Math.round((correct / total) * 100) : 0,
    bySignalType,
  }
}

/**
 * Log a decision (append-only).
 */
export function logDecision(ticker: string, decision: string, reason: string): string {
  const dir = DECISIONS_DIR
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })

  const date = new Date().toISOString().slice(0, 10)
  const file = join(dir, `${date}-${ticker}.md`)

  const content = `# Decision: ${ticker} — ${date}

**Action:** ${decision}
**Reason:** ${reason}

`

  // Append if file exists, otherwise create
  if (existsSync(file)) {
    writeFileSync(file, readFileSync(file, "utf-8") + content, "utf-8")
  } else {
    writeFileSync(file, content, "utf-8")
  }
  return file
}
