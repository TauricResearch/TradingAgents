/**
 * Feedback loop — post-mortems and signal accuracy tracking.
 *
 * Two distinct concerns in one file (post-mortem files + live database signals):
 *   - Post-mortem file operations: save/load/parse post-mortems, compute accuracy
 *   - Live signal-to-position correlation: compute from SQLite signals + positions
 *
 * Both computations are independent and serve different audiences (offline review
 * vs. real-time dashboard). Keeping them in one file avoids the pair split while
 * making the distinction explicit via section headers.
 */

import { spawn } from "node:child_process"
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { DatabaseFactory } from "../../lib/db.ts"
import type { PriceResult } from "../../lib/types.ts"
import { endOfToday, priceCache } from "./cache.ts"
import { findProjectRoot } from "./utils.ts"

const POST_MORTEMS_DIR =
  process.env.POST_MORTEMS_DIR ?? join(process.env.HOME ?? "/tmp", ".tradingagents", "post-mortems")

const DECISIONS_DIR =
  process.env.DECISIONS_DIR ?? join(process.env.HOME ?? "/tmp", ".tradingagents", "decisions")

// ── Post-mortem types ─────────────────────────────────────────────────────────

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

// ── Live correlation types (moved from feedback-data.ts) ─────────────────────

export interface DbSignal {
  id: number
  ticker: string
  platform: string
  date: string
  signal: string
  reasoning: string | null
  confidence: number | null
  created_at: string
}

export interface DbPosition {
  id: number
  ticker: string
  exchange: string
  platform: string
  quantity: number
  avg_cost: number
  entry_date: string
  thesis: string | null
  status: string
}

export interface TickerCorrelation {
  ticker: string
  signals: Array<{
    id: number
    date: string
    signal: string
    reasoning: string | null
    confidence: number | null
    platform: string
  }>
  position: {
    platform: string
    quantity: number
    entry_date: string
    thesis: string | null
    avg_cost: number
    current_price_gbp: number | null
    current_value_gbp: number | null
    pnl_gbp: number | null
    pnl_pct: number | null
  } | null
  signalOutcome:
    | "buy_success"
    | "buy_failure"
    | "sell_success"
    | "sell_failure"
    | "hold"
    | "no_position"
  latestSignal: string
  outcomePct: number | null
}

// ── Post-mortem file operations ───────────────────────────────────────────────

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

// ── Live correlation operations ───────────────────────────────────────────────

export async function fetchPriceForTicker(ticker: string): Promise<PriceResult> {
  const now = Date.now()
  const cached = priceCache.get(ticker)
  if (cached && cached.expires > now && cached.price !== null) {
    return { price: cached.price, currency: "USD" }
  }

  return new Promise((resolve) => {
    const script = join(findProjectRoot(), "scripts", "py", "get_price.py")
    const child = spawn("python3", [script, ticker], {
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
      timeout: 12_000,
    })
    let stdout = ""
    child.stdout.on("data", (d: Buffer) => {
      stdout += d.toString()
    })
    child.on("close", () => {
      try {
        const data = JSON.parse(stdout.trim())
        if (data.price != null) {
          priceCache.set(ticker, { price: data.price, expires: endOfToday() })
        }
        resolve({ price: data.price ?? null, currency: data.currency ?? "USD" })
      } catch {
        resolve({ price: null, currency: "USD" })
      }
    })
    child.on("error", () => resolve({ price: null, currency: "USD" }))
  })
}

export interface CorrelationResult {
  correlations: TickerCorrelation[]
  summary: { totalSignalsWithPositions: number; total: number; accurate: number; accuracy: number }
}

export async function computeCorrelations(): Promise<CorrelationResult> {
  const db = DatabaseFactory.get()

  const positions = db
    .query(
      "SELECT id, ticker, platform, quantity, avg_cost, entry_date, thesis, status FROM positions WHERE status = 'open'",
    )
    .all() as DbPosition[]

  const signals = db
    .query(
      "SELECT id, ticker, platform, date, signal, reasoning, confidence, created_at FROM signals ORDER BY date DESC",
    )
    .all() as DbSignal[]

  if (signals.length === 0 && positions.length === 0) {
    return {
      correlations: [],
      summary: { totalSignalsWithPositions: 0, total: 0, accurate: 0, accuracy: 0 },
    }
  }

  const signalsByTicker = new Map<string, DbSignal[]>()
  for (const s of signals) {
    const list = signalsByTicker.get(s.ticker) ?? []
    list.push(s)
    signalsByTicker.set(s.ticker, list)
  }

  const fxResults = await Promise.all([
    fetchPriceForTicker("GBPEUR=X"),
    fetchPriceForTicker("GBPUSD=X"),
  ])
  const gbpeur = fxResults[0]?.price ?? 1.18
  const gbpUSD = fxResults[1]?.price ?? 1.27
  const gbpPerEur = 1 / gbpeur
  const gbpPerUsd = 1 / gbpUSD

  const allTickers = [...new Set([...signalsByTicker.keys(), ...positions.map((p) => p.ticker)])]
  const priceData = new Map<string, PriceResult>()
  await Promise.all(
    allTickers.map((t) =>
      fetchPriceForTicker(t).then((r) => {
        priceData.set(t, r)
      }),
    ),
  )

  const correlations: TickerCorrelation[] = []
  for (const [ticker, tickerSignals] of signalsByTicker) {
    const pos = positions.find((p) => p.ticker === ticker) ?? null
    const pd = priceData.get(ticker)

    let currentPriceGbp: number | null = null
    if (pd?.price != null) {
      if (pd.currency === "EUR") currentPriceGbp = pd.price * gbpPerEur
      else if (pd.currency === "USD") currentPriceGbp = pd.price * gbpPerUsd
      else currentPriceGbp = pd.price
    }

    let currentValueGbp: number | null = null
    let pnlGbp: number | null = null
    let pnlPct: number | null = null
    let costValueGbp = 0

    if (pos) {
      const avgCostNum = parseFloat(String(pos.avg_cost))
      const quantityNum = parseFloat(String(pos.quantity))
      costValueGbp = avgCostNum * quantityNum
      if (pos.platform === "degiero" || pos.exchange === "XETRA") {
        costValueGbp = (avgCostNum * quantityNum) / gbpeur
      } else if (pos.platform === "ibkr" || pos.exchange === "US") {
        costValueGbp = (avgCostNum * quantityNum) / gbpUSD
      }
      currentValueGbp = currentPriceGbp != null ? currentPriceGbp * quantityNum : null
      pnlGbp = currentValueGbp != null ? currentValueGbp - costValueGbp : null
      pnlPct = costValueGbp > 0 && pnlGbp != null ? (pnlGbp / costValueGbp) * 100 : null
    }

    const latestSignal = tickerSignals[0]?.signal ?? "unknown"
    const isBuy = latestSignal === "buy" || latestSignal === "overweight"
    const isSell = latestSignal === "sell" || latestSignal === "underweight"

    let signalOutcome: TickerCorrelation["signalOutcome"] = "no_position"
    if (pos && pnlPct != null) {
      if (isBuy) signalOutcome = pnlPct >= 0 ? "buy_success" : "buy_failure"
      else if (isSell) signalOutcome = pnlPct < 0 ? "sell_success" : "sell_failure"
      else signalOutcome = "hold"
    }

    correlations.push({
      ticker,
      signals: tickerSignals.map((s) => ({
        id: s.id,
        date: s.date,
        signal: s.signal,
        reasoning: s.reasoning,
        confidence: s.confidence,
        platform: s.platform,
      })),
      position: pos
        ? {
            platform: pos.platform,
            quantity: pos.quantity,
            entry_date: pos.entry_date,
            thesis: pos.thesis,
            avg_cost: pos.avg_cost,
            current_price_gbp:
              currentPriceGbp != null ? Math.round(currentPriceGbp * 100) / 100 : null,
            current_value_gbp:
              currentValueGbp != null ? Math.round(currentValueGbp * 100) / 100 : null,
            pnl_gbp: pnlGbp != null ? Math.round(pnlGbp * 100) / 100 : null,
            pnl_pct: pnlPct != null ? Math.round(pnlPct * 100) / 100 : null,
          }
        : null,
      signalOutcome,
      latestSignal,
      outcomePct: pnlPct != null ? Math.round(pnlPct * 100) / 100 : null,
    })
  }

  let accurate = 0
  let total = 0
  for (const c of correlations) {
    if (!c.position || c.signalOutcome === "hold" || c.signalOutcome === "no_position") continue
    total++
    if (c.signalOutcome === "buy_success" || c.signalOutcome === "sell_success") accurate++
  }

  const summary = {
    totalSignalsWithPositions: correlations.filter((c) => c.position).length,
    total,
    accurate,
    accuracy: total > 0 ? Math.round((accurate / total) * 100) : 0,
  }

  return { correlations, summary }
}

// ── Decision logging ──────────────────────────────────────────────────────────

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
