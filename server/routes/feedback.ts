import { Hono } from "hono"
import { computeSignalAccuracy, loadPostMortems } from "../lib/feedback.ts"
import { DatabaseFactory } from "../lib/db.ts"
import { priceCache, endOfToday } from "../lib/cache.ts"
import { dirname, join } from "node:path"
import { spawn } from "node:child_process"

export const feedbackRouter = new Hono()

/** GET /api/feedback — aggregated accuracy + post-mortems */
feedbackRouter.get("/", (c) => {
  const mortems = loadPostMortems()
  const accuracy = computeSignalAccuracy(mortems)
  return c.json({ accuracy, postMortems: mortems })
})

/** GET /api/feedback/post-mortems — all post-mortems */
feedbackRouter.get("/post-mortems", (c) => {
  const mortems = loadPostMortems()
  return c.json(mortems)
})

/** GET /api/feedback/accuracy — signal accuracy metrics */
feedbackRouter.get("/accuracy", (c) => {
  const mortems = loadPostMortems()
  const accuracy = computeSignalAccuracy(mortems)
  return c.json(accuracy)
})

// ── Signal × Position correlation (S06) ──────────────────────────────────────

interface DbSignal {
  id: number
  ticker: string
  platform: string
  date: string
  signal: string
  reasoning: string | null
  confidence: number | null
  created_at: string
}

interface DbPosition {
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

interface TickerCorrelation {
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
  signalOutcome: "buy_success" | "buy_failure" | "sell_success" | "sell_failure" | "hold" | "no_position"
  latestSignal: string
  outcomePct: number | null
}

function findProjectRoot(): string {
  if (process.env.TA_ROOT) return process.env.TA_ROOT
  const projectRoot = dirname(dirname(import.meta.dir))
  if (projectRoot.includes("TradingAgents")) return projectRoot
  return projectRoot
}

interface PriceResult { price: number | null; currency: string }

async function fetchPriceForTicker(ticker: string): Promise<PriceResult> {
  const now = Date.now()
  const cached = priceCache.get(ticker)
  if (cached && cached.expires > now && cached.price !== null) {
    return { price: cached.price, currency: "USD" }
  }

  return new Promise((resolve) => {
    const script = join(findProjectRoot(), "scripts", "get_price.py")
    const child = spawn("python3", [script, ticker], {
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
      timeout: 12_000,
    })
    let stdout = ""
    child.stdout.on("data", (d: Buffer) => { stdout += d.toString() })
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

/** GET /api/feedback/with-positions — signals correlated with position outcomes */
feedbackRouter.get("/with-positions", async (c) => {
  const db = DatabaseFactory.get()

  // Fetch all open positions and signals
  const positions = db.query(
    "SELECT id, ticker, platform, quantity, avg_cost, entry_date, thesis, status FROM positions WHERE status = 'open'",
  ).all() as DbPosition[]

  const signals = db.query(
    "SELECT id, ticker, platform, date, signal, reasoning, confidence, created_at FROM signals ORDER BY date DESC",
  ).all() as DbSignal[]

  if (signals.length === 0 && positions.length === 0) {
    return c.json({ correlations: [], summary: { total: 0, accurate: 0, accuracy: 0 } })
  }

  // Group signals by ticker (most recent first per ticker)
  const signalsByTicker = new Map<string, DbSignal[]>()
  for (const s of signals) {
    const list = signalsByTicker.get(s.ticker) ?? []
    list.push(s)
    signalsByTicker.set(s.ticker, list)
  }

  // FX rates for GBP conversion
  const fxPairs = ["GBPEUR=X", "GBPUSD=X"]
  const fxResults = await Promise.all(fxPairs.map(fetchPriceForTicker))
  const gbpeur = fxResults[0]?.price ?? 1.18
  const gbpUSD = fxResults[1]?.price ?? 1.27
  const gbpPerEur = 1 / gbpeur
  const gbpPerUsd = 1 / gbpUSD

  // All tickers needing price data
  const allTickers = [...new Set([...signalsByTicker.keys(), ...positions.map((p) => p.ticker)])]
  const priceData = new Map<string, PriceResult>()
  await Promise.all(
    allTickers.map(
      (t) =>
        fetchPriceForTicker(t).then((r) => {
          priceData.set(t, r)
        }),
    ),
  )

  const correlations: TickerCorrelation[] = []

  // Build correlations for tickers that have signals
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
    let costValueGbp: number = 0

    if (pos) {
      costValueGbp = pos.avg_cost * pos.quantity
      if (pos.platform === "degiero" || pos.exchange === "XETRA") {
        costValueGbp = (pos.avg_cost * pos.quantity) / gbpeur
      } else if (pos.platform === "ibkr" || pos.exchange === "US") {
        costValueGbp = (pos.avg_cost * pos.quantity) / gbpUSD
      }
      currentValueGbp = currentPriceGbp != null ? currentPriceGbp * pos.quantity : null
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
            current_price_gbp: currentPriceGbp != null ? Math.round(currentPriceGbp * 100) / 100 : null,
            current_value_gbp: currentValueGbp != null ? Math.round(currentValueGbp * 100) / 100 : null,
            pnl_gbp: pnlGbp != null ? Math.round(pnlGbp * 100) / 100 : null,
            pnl_pct: pnlPct != null ? Math.round(pnlPct * 100) / 100 : null,
          }
        : null,
      signalOutcome,
      latestSignal,
      outcomePct: pnlPct != null ? Math.round(pnlPct * 100) / 100 : null,
    })
  }

  // Compute accuracy: only tickers with positions and buy/sell signals
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

  return c.json({ correlations, summary })
})
