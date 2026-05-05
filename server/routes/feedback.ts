import { spawn } from "node:child_process"
import { dirname, join } from "node:path"
import { Hono } from "hono"
import { endOfToday, priceCache } from "../lib/cache.ts"
import { DatabaseFactory } from "../lib/db.ts"
import {
  computeSignalAccuracy,
  loadPostMortems,
  type PostMortem,
  type SignalAccuracy,
} from "../lib/feedback.ts"
import type { PriceResult } from "../lib/types.ts"

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

function findProjectRoot(): string {
  if (process.env.TA_ROOT) return process.env.TA_ROOT
  const projectRoot = dirname(dirname(import.meta.dir))
  if (projectRoot.includes("TradingAgents")) return projectRoot
  return projectRoot
}

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

async function computeCorrelations(): Promise<{
  correlations: TickerCorrelation[]
  summary: { totalSignalsWithPositions: number; total: number; accurate: number; accuracy: number }
}> {
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

  const fxPairs = ["GBPEUR=X", "GBPUSD=X"]
  const fxResults = await Promise.all(fxPairs.map(fetchPriceForTicker))
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

function buildAccuracyHtml(acc: SignalAccuracy): string {
  if (!acc || acc.totalSignals === 0) {
    return '<div class="muted">No post-mortems yet. Exit a position to generate one.</div>'
  }

  let html = '<div class="accuracy-summary">'
  html += `<div class="accuracy-score ${acc.accuracyPct >= 60 ? "positive" : "negative"}">${acc.accuracyPct}% accuracy (${acc.correctSignals}/${acc.totalSignals})</div>`
  html += "</div>"

  if (acc.bySignalType && Object.keys(acc.bySignalType).length > 0) {
    html += '<table class="data-table"><thead><tr>'
    html += "<th>Exit Trigger</th><th>Signals</th><th>Correct</th><th>Accuracy</th>"
    html += "</tr></thead><tbody>"
    for (const [type, d] of Object.entries(acc.bySignalType)) {
      html += "<tr>"
      html += `<td>${type}</td>`
      html += `<td>${d.total}</td>`
      html += `<td>${d.correct}</td>`
      html += `<td class="${d.pct >= 60 ? "positive" : "negative"}">${d.pct}%</td>`
      html += "</tr>"
    }
    html += "</tbody></table>"
  }
  return html
}

function buildPostMortemsHtml(mortems: PostMortem[]): string {
  if (!mortems || mortems.length === 0) {
    return '<div class="muted">No post-mortems yet.</div>'
  }

  let html = ""
  for (const pm of mortems) {
    const signalClass = pm.aiSignalCorrect ? "positive" : "negative"
    const signalIcon = pm.aiSignalCorrect ? "\u2705" : "\u274c"
    html += '<div class="post-mortem-card">'
    html += '<div class="pm-header">'
    html += `<span class="ticker">${pm.ticker}</span>`
    html += `<span class="pm-date">${pm.exitDate}</span>`
    html += "</div>"
    html += `<div class="pm-thesis">${pm.thesis.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")}</div>`
    html += '<div class="pm-outcome">'
    html += `<span>Thesis: ${pm.thesisPlayedOut ? "\u2705" : "\u274c"}</span>`
    html += `<span>AI signal: <span class="${signalClass}">${signalIcon}</span></span>`
    html += `<span>Exit: ${pm.exitTrigger}</span>`
    html += "</div>"
    if (pm.lesson) {
      html += `<div class="pm-lesson">${pm.lesson.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")}</div>`
    }
    html += "</div>"
  }
  return html
}

function buildCorrelationsHtml(data: {
  correlations: TickerCorrelation[]
  summary: { total: number; accurate: number; accuracy: number }
}): string {
  if (!data.correlations || data.correlations.length === 0) {
    return '<div class="muted">No signals recorded yet.</div>'
  }

  const summary = data.summary
  const accCls = summary.accuracy >= 60 ? "positive" : "negative"
  let html = '<div class="accuracy-summary" style="margin-bottom:1rem">'
  html += "<span>Signal accuracy: </span>"
  html += `<span class="accuracy-score ${accCls}">${summary.accuracy}%</span>`
  html += `<span class="muted"> (${summary.accurate}/${summary.total} buy/sell signals with positions)</span>`
  html += "</div>"

  html += '<table class="data-table" style="font-size:0.85em"><thead><tr>'
  html +=
    "<th>Ticker</th><th>Latest Signal</th><th>Platform</th><th>Position</th><th>Entry</th><th>P&amp;L</th><th>Signal Outcome</th>"
  html += "</tr></thead><tbody>"

  for (const c of data.correlations) {
    const plat = c.signals[0]?.platform ?? "unknown"
    const sCls = c.signalOutcome.includes("success")
      ? "positive"
      : c.signalOutcome.includes("failure")
        ? "negative"
        : c.signalOutcome === "hold"
          ? "status-hold"
          : "muted"
    const pnlCls = c.outcomePct != null ? (c.outcomePct >= 0 ? "positive" : "negative") : "muted"
    const pnlStr =
      c.outcomePct != null
        ? `${(c.outcomePct >= 0 ? "+" : "") + c.outcomePct.toFixed(1)}%`
        : "\u2014"

    html += "<tr>"
    html += `<td class="ticker">${c.ticker}</td>`
    html += `<td class="status-${c.latestSignal.includes("buy") ? "buy" : c.latestSignal.includes("sell") ? "sell" : "hold"}">${c.latestSignal}</td>`
    html += `<td><span class="platform-tag">${plat}</span></td>`
    if (c.position) {
      html += `<td>${c.position.quantity} shares @ \u00a3${c.position.avg_cost.toFixed(2)} <span class="muted">(GBP)</span></td>`
      html += `<td>${c.position.entry_date}</td>`
      html += `<td class="pnl-cell ${pnlCls}" style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">${pnlStr}</td>`
    } else {
      html +=
        '<td class="muted">\u2014</td><td class="muted">\u2014</td><td class="muted">\u2014</td>'
    }
    html += `<td class="${sCls}">${c.signalOutcome}</td>`
    html += "</tr>"
  }
  html += "</tbody></table>"
  return html
}

/** GET /api/feedback/with-positions — signals correlated with position outcomes */
feedbackRouter.get("/with-positions", async (c) => {
  const data = await computeCorrelations()
  return c.json(data)
})

/** GET /api/feedback/accuracy/html — accuracy as HTML for HTMX */
feedbackRouter.get("/accuracy/html", (c) => {
  const mortems = loadPostMortems()
  const accuracy = computeSignalAccuracy(mortems)
  return c.html(buildAccuracyHtml(accuracy))
})

/** GET /api/feedback/post-mortems/html — post-mortems as HTML for HTMX */
feedbackRouter.get("/post-mortems/html", (c) => {
  const mortems = loadPostMortems()
  return c.html(buildPostMortemsHtml(mortems))
})

/** GET /api/feedback/with-positions/html — correlations as HTML for HTMX */
feedbackRouter.get("/with-positions/html", async (c) => {
  try {
    const data = await computeCorrelations()
    return c.html(buildCorrelationsHtml(data))
  } catch (e: unknown) {
    return c.html(
      `<div class="error-card"><strong>Feedback error</strong><br>${(e as Error).message}</div>`,
      500,
    )
  }
})
