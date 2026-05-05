import { spawn } from "node:child_process"
import { dirname, join } from "node:path"
import { Hono } from "hono"
import { priceCache } from "../lib/cache.ts"
import { DatabaseFactory } from "../lib/db.ts"
import { sanitizeForDb } from "../lib/sanitize.ts"

interface Signal {
  id?: number
  ticker: string
  platform: string
  date: string
  signal: string
  reasoning: string | null
  confidence: number | null
  [key: string]: unknown
}

export const signalsRouter = new Hono()

// ── HTML helpers ─────────────────────────────────────────────────────────────

function escSignals(s: string | null | undefined): string {
  if (s == null) return ""
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

function fmtDateSignals(d: string): string {
  if (!d) return "\u2014"
  const months = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ]
  const parts = d.split("-")
  if (parts.length !== 3) return d
  const [_year, month, day] = parts as [string, string, string]
  return `${parseInt(day, 10)}-${months[parseInt(month, 10) - 1] ?? ""}`
}

function signalClassSignals(signal: string): string {
  const s = (signal || "").toLowerCase()
  if (s.includes("buy") || s.includes("overweight")) return "status-buy"
  if (s.includes("sell") || s.includes("underweight")) return "status-sell"
  return "status-hold"
}

function norm(vals: number[]): number[] {
  if (!vals || vals.length === 0) return []
  const lo = Math.min(...vals)
  const hi = Math.max(...vals)
  const rng = hi - lo
  if (rng === 0) return vals.map(() => 50)
  return vals.map((v) => Math.round(((v - lo) / rng) * 100))
}

function sparkline(history: Array<{ close: number }> | null): string | null {
  if (!history || history.length === 0) return null
  const closes = history
    .slice(-20)
    .map((h) => h.close)
    .reverse()
  const n = norm(closes)
  return n.length > 0 ? `{l:${n.join(",")}}` : null
}

function buildTimelineHtml(
  ticker: string,
  signals: Signal[],
  priceData: Map<string, PriceWithHistory>,
): string {
  const tickerSignals = signals.filter((s) => s.ticker === ticker)
  if (tickerSignals.length === 0) return ""

  const priceHist = priceData.get(ticker)
  const priceSpark = sparkline(priceHist?.history ?? null)
  const firstCls = signalClassSignals(tickerSignals[0]?.signal ?? "")

  let html = '<div class="timeline-header">'
  if (priceSpark) {
    html += '<div class="timeline-section">'
    html += '<span class="muted" style="font-size:0.75em">Price (20d)</span>'
    html += `<div class="trend-cell ${firstCls}"><span class="trend-sparkline">${priceSpark}</span></div>`
    html += "</div>"
  }

  const confValues = tickerSignals.map((s) => Math.round((s.confidence ?? 0.5) * 100))
  const confSpark = `{l:${confValues.join(",")}}`
  html += '<div class="timeline-section">'
  html += '<span class="muted" style="font-size:0.75em">Confidence</span>'
  html += `<div class="sparkline ${firstCls}">${confSpark}</div>`
  html += "</div>"
  html += "</div>"

  html += '<div class="timeline-entries">'
  for (let i = 0; i < tickerSignals.length; i++) {
    const s = tickerSignals[i]!
    const cls = signalClassSignals(s.signal)
    const pct = Math.round((s.confidence ?? 0) * 100)
    const pie = `{p:${pct}}`
    html += `<div class="timeline-row ${cls}">`
    html += `<span class="timeline-signal">${s.signal}</span>`
    html += `<span class="timeline-date date-col">${fmtDateSignals(s.date)}</span>`
    html += `<span class="datatype-pie" title="${pct}% confidence">${pie}</span>`
    html += `<span class="timeline-confidence">${pct}%</span>`
    if (i === 0) html += '<span class="timeline-current">current</span>'
    html += "</div>"
  }
  html += "</div>"

  return html
}

function buildSignalsViewHtml(
  signals: Signal[],
  priceData: Map<string, PriceWithHistory>,
  allPlatforms: string[],
  allTickers: string[],
  selectedPlatform: string,
  selectedTicker: string,
): string {
  let html =
    '<div class="form-row" style="margin-bottom:0.5rem" hx-get="/api/signals/view/html" hx-target="#signals-wrapper" hx-trigger="change" hx-include="this">'
  html += `<select name="platform" id="signals-platform" style="max-width:150px">`
  html += '<option value="">All platforms</option>'
  for (const p of allPlatforms) {
    html += `<option value="${escSignals(p)}"${p === selectedPlatform ? " selected" : ""}>${escSignals(p)}</option>`
  }
  html += "</select>"
  html += `<select name="ticker" id="signals-ticker" style="max-width:150px">`
  html += '<option value="">All tickers</option>'
  for (const t of allTickers) {
    html += `<option value="${escSignals(t)}"${t === selectedTicker ? " selected" : ""}>${escSignals(t)}</option>`
  }
  html += "</select>"
  html += "</div>"

  html += '<table id="signals-table">'
  html +=
    "<thead><tr><th>Platform</th><th>Date</th><th>Ticker</th><th>Signal</th><th>Trend</th><th>Confidence</th><th>Reasoning</th></tr></thead>"
  html += '<tbody id="signals-body">'

  if (signals.length === 0) {
    html += '<tr><td colspan="7" class="muted">No signals recorded</td></tr>'
  } else {
    for (const s of signals) {
      const cls = signalClassSignals(s.signal)
      const plat = s.platform || "unknown"
      const conf = s.confidence != null ? `${Math.round(s.confidence * 100)}%` : "\u2014"
      const reasoning = (s.reasoning || "").substring(0, 100)
      const priceHist = priceData.get(s.ticker)
      const spark = sparkline(priceHist?.history ?? null)
      const trendCell = spark
        ? `<span class="trend-sparkline">${spark}</span>`
        : '<span class="muted">\u2014</span>'

      html += `<tr>`
      html += `<td><span class="platform-tag">${escSignals(plat)}</span></td>`
      html += `<td class="date-col">${fmtDateSignals(s.date)}</td>`
      html += `<td class="ticker">${escSignals(s.ticker)}</td>`
      html += `<td class="${cls}">${s.signal}</td>`
      html += `<td class="trend-cell ${cls}">${trendCell}</td>`
      html += `<td>${conf}</td>`
      html += `<td class="muted" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escSignals(s.reasoning ?? "")}">${escSignals(reasoning)}</td>`
      html += "</tr>"
    }
  }
  html += "</tbody></table>"

  // Timeline panel
  if (selectedTicker && signals.some((s) => s.ticker === selectedTicker)) {
    const _tickerSignals = signals.filter((s) => s.ticker === selectedTicker)
    html += '<section class="panel" id="timeline-panel">'
    html += `<h4>Timeline: ${escSignals(selectedTicker)}</h4>`
    html += `<div id="signal-timeline">${buildTimelineHtml(selectedTicker, signals, priceData)}</div>`
    html += "</section>"
  }

  return html
}

// ── Signals CRUD ──────────────────────────────────────────────────────────────

async function fetchSignalsWithHistory(
  ticker: string | undefined,
  platform: string | undefined,
): Promise<{ signals: Signal[]; priceData: Map<string, PriceWithHistory> }> {
  const db = DatabaseFactory.get()

  let rows: unknown[]
  if (ticker && platform) {
    rows = db
      .query("SELECT * FROM signals WHERE ticker = ? AND platform = ? ORDER BY date DESC, id DESC")
      .all(ticker, platform)
  } else if (ticker) {
    rows = db
      .query("SELECT * FROM signals WHERE ticker = ? ORDER BY date DESC, id DESC")
      .all(ticker)
  } else if (platform) {
    rows = db
      .query("SELECT * FROM signals WHERE platform = ? ORDER BY date DESC, id DESC")
      .all(platform)
  } else {
    rows = db.query("SELECT * FROM signals ORDER BY date DESC, id DESC").all()
  }

  const signals = rows as Signal[]
  const tickers = [...new Set(signals.map((r) => r.ticker))]
  const priceData = await batchFetchPricesWithHistory(tickers)
  return { signals, priceData }
}

/** GET /api/signals — list all signals, optionally filter by ticker or platform */
signalsRouter.get("/", (c) => {
  const db = DatabaseFactory.get()
  const ticker = c.req.query("ticker")
  const platform = c.req.query("platform")

  if (ticker && platform) {
    const rows = db
      .query("SELECT * FROM signals WHERE ticker = ? AND platform = ? ORDER BY date DESC, id DESC")
      .all(ticker, platform)
    return c.json(rows)
  }
  if (ticker) {
    const rows = db
      .query("SELECT * FROM signals WHERE ticker = ? ORDER BY date DESC, id DESC")
      .all(ticker)
    return c.json(rows)
  }
  if (platform) {
    const rows = db
      .query("SELECT * FROM signals WHERE platform = ? ORDER BY date DESC, id DESC")
      .all(platform)
    return c.json(rows)
  }

  const rows = db.query("SELECT * FROM signals ORDER BY date DESC, id DESC").all()
  return c.json(rows)
})

/** GET /api/signals/table — signals with price history for sparklines */
signalsRouter.get("/table", async (c) => {
  const { signals, priceData } = await fetchSignalsWithHistory(
    c.req.query("ticker"),
    c.req.query("platform"),
  )
  const enriched = signals.map((s) => ({
    ...s,
    price_history: priceData.get(s.ticker) ?? null,
  }))
  return c.json(enriched)
})

/** GET /api/signals/view/html — full signals view as HTML for HTMX */
signalsRouter.get("/view/html", async (c) => {
  try {
    const platform = c.req.query("platform") || ""
    const ticker = c.req.query("ticker") || ""
    const { signals, priceData } = await fetchSignalsWithHistory(
      ticker || undefined,
      platform || undefined,
    )

    const db = DatabaseFactory.get()
    const allPlatforms = (
      db.query("SELECT DISTINCT platform FROM signals ORDER BY platform").all() as Array<{
        platform: string
      }>
    ).map((r) => r.platform)
    const allTickers = (
      db.query("SELECT DISTINCT ticker FROM signals ORDER BY ticker").all() as Array<{
        ticker: string
      }>
    ).map((r) => r.ticker)

    return c.html(
      buildSignalsViewHtml(signals, priceData, allPlatforms, allTickers, platform, ticker),
    )
  } catch (e: unknown) {
    return c.html(
      `<div class="error-card"><strong>Signals error</strong><br>${(e as Error).message}</div>`,
      500,
    )
  }
})

/** GET /api/signals/:ticker — signal timeline for a specific ticker */
signalsRouter.get("/:ticker", (c) => {
  const db = DatabaseFactory.get()
  const ticker = c.req.param("ticker")
  const rows = db
    .query("SELECT * FROM signals WHERE ticker = ? ORDER BY date DESC, id DESC")
    .all(ticker)
  return c.json(rows)
})

/** POST /api/signals — record a new signal */
signalsRouter.post("/", async (c) => {
  const db = DatabaseFactory.get()
  const body = await c.req.json()
  const { ticker, date, signal, reasoning, confidence, platform } = body

  if (!ticker || !signal) {
    return c.json({ error: "ticker and signal are required" }, 400)
  }

  const VALID_SIGNALS = ["buy", "overweight", "hold", "underweight", "sell"]
  const normalised = String(signal).toLowerCase()
  if (!VALID_SIGNALS.includes(normalised)) {
    return c.json({ error: `signal must be one of: ${VALID_SIGNALS.join(", ")}` }, 400)
  }

  const stmt = db.prepare(
    `INSERT INTO signals (ticker, platform, date, signal, reasoning, confidence)
     VALUES (?, ?, ?, ?, ?, ?)`,
  )
  const result = stmt.run(
    ticker,
    platform ?? "unknown",
    date ?? new Date().toISOString().slice(0, 10),
    normalised,
    sanitizeForDb(reasoning) ?? null,
    confidence != null ? Number(confidence) : null,
  )

  return c.json(
    {
      id: result.lastInsertRowid,
      ticker,
      platform: platform ?? "unknown",
      date: date ?? new Date().toISOString().slice(0, 10),
      signal: normalised,
    },
    201,
  )
})

// ── Batch price fetch with history (for sparklines) ───────────────────────────

interface PriceWithHistory {
  price: number | null
  currency: string
  history: { date: string; close: number }[]
}

function findProjectRoot(): string {
  if (process.env.TA_ROOT) return process.env.TA_ROOT
  const projectRoot = dirname(dirname(import.meta.dir))
  if (projectRoot.includes("TradingAgents")) return projectRoot
  return projectRoot
}

async function batchFetchPricesWithHistory(
  tickers: string[],
): Promise<Map<string, PriceWithHistory>> {
  const results = new Map<string, PriceWithHistory>()
  if (tickers.length === 0) return results

  const root = findProjectRoot()
  const script = join(root, "scripts", "get_price.py")

  // Fetch in parallel batches of 4 (yfinance is the bottleneck)
  const BATCH_SIZE = 4
  for (let i = 0; i < tickers.length; i += BATCH_SIZE) {
    const batch = tickers.slice(i, i + BATCH_SIZE)
    const batchResults = await Promise.all(
      batch.map(
        (ticker) =>
          new Promise<[string, PriceWithHistory]>((resolve) => {
            const cached = priceCache.get(ticker)
            const now = Date.now()
            // Check if we have cached full price data
            if (cached && cached.expires > now && cached.price !== null) {
              // We only cached price, not history — need to fetch anyway for history
              // But use cache to avoid duplicate spawns within same request
            }

            const child = spawn("python3", [script, ticker], {
              env: { ...process.env, PYTHONUNBUFFERED: "1" },
              timeout: 12_000,
            })
            let stdout = ""
            child.stdout.on("data", (d: Buffer) => {
              stdout += d.toString()
            })
            child.on("close", (code) => {
              if (code !== 0) {
                resolve([ticker, { price: null, currency: "USD", history: [] }])
                return
              }
              try {
                const data = JSON.parse(stdout.trim())
                const history: { date: string; close: number }[] = (data.history ?? []).slice(-20)
                resolve([
                  ticker,
                  {
                    price: data.price ?? null,
                    currency: data.currency ?? "USD",
                    history,
                  },
                ])
              } catch {
                resolve([ticker, { price: null, currency: "USD", history: [] }])
              }
            })
            child.on("error", () =>
              resolve([ticker, { price: null, currency: "USD", history: [] }]),
            )
          }),
      ),
    )
    for (const [ticker, data] of batchResults) {
      results.set(ticker, data)
    }
  }

  return results
}
