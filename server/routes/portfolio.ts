import { spawn } from "node:child_process"
import { dirname, join } from "node:path"
import { type Context, Hono } from "hono"
import { endOfToday, priceCache } from "../lib/cache.ts"
import { DatabaseFactory } from "../lib/db.ts"
import { sanitizeForDb } from "../lib/sanitize.ts"

export const portfolioRouter = new Hono()

function findProjectRoot(): string {
  if (process.env.TA_ROOT) return process.env.TA_ROOT
  const projectRoot = dirname(dirname(import.meta.dir))
  if (projectRoot.includes("TradingAgents")) return projectRoot
  return projectRoot
}

// ── HTML helpers ───────────────────────────────────────────────────────────────

function escPortfolio(s: string | null | undefined): string {
  if (s == null) return ""
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

function fmtPortfolio(n: number | null | undefined, dec = 2): string {
  if (n == null || Number.isNaN(n)) return "\u2014"
  return n.toFixed(dec)
}

function clsPortfolio(pnl: number | null | undefined): string {
  if (pnl == null) return ""
  if (pnl > 0) return "positive"
  if (pnl < 0) return "negative"
  return ""
}

function fmtPnlPortfolio(pnl: number | null | undefined): string {
  if (pnl == null) return "\u2014"
  const sign = pnl >= 0 ? "+" : ""
  return `${sign}${fmtPortfolio(pnl, 2)}`
}

function buildPortfolioHtml(summary: PortfolioSummary): string {
  const totals = summary.totals
  const pnl = totals.total_pnl_gbp
  const pnlCls = clsPortfolio(pnl)

  let html = '<section class="panel" id="pnl-panel">'
  html += '<h3><span id="pnl-title">Portfolio Summary</span></h3>'
  html += '<div id="pnl-summary">'
  html += '<div class="pnl-totals" style="display:flex;gap:2rem;margin-bottom:1rem;flex-wrap:wrap">'
  html += '<div><div class="muted" style="font-size:0.75em">Portfolio Value</div>'
  html += `<div id="pnl-total-value" style="font-size:1.4em;font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">\u00a3${fmtPortfolio(totals.portfolio_value_gbp)}</div></div>`
  html += '<div><div class="muted" style="font-size:0.75em">Total Cost</div>'
  html += `<div id="pnl-total-cost" style="font-size:1.4em;font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">\u00a3${fmtPortfolio(totals.total_cost_gbp)}</div></div>`
  html += '<div><div class="muted" style="font-size:0.75em">Unrealised P&amp;L</div>'
  html += `<div id="pnl-total-pnl" style="font-size:1.4em;font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1" class="pnl-cell ${pnlCls}">\u00a3${fmtPnlPortfolio(pnl)}${totals.total_pnl_pct != null ? ` (${pnl != null && pnl >= 0 ? "+" : ""}${fmtPortfolio(totals.total_pnl_pct)}%)` : " \u2014"}</div></div>`
  html += "</div>"
  html +=
    '<p class="muted" style="font-size:0.75em;margin:0">Prices in GBP via live FX conversion (GBPEUR, GBPUSD). Sorted by P&amp;L descending (worst positions first).</p>'
  html += "</div></section>"

  html += '<section class="panel"><h3>Positions</h3>'
  html += '<div style="overflow-x:auto">'
  html += '<table id="positions-table" class="positions-table">'
  html +=
    '<thead><tr><th>Platform</th><th>Ticker</th><th>Qty</th><th>Avg Cost</th><th>Current</th><th>Value (GBP)</th><th>P&amp;L</th><th class="date-col">Entry</th><th>Thesis</th><th></th></tr></thead>'
  html += '<tbody id="positions-tbody">'

  if (!summary.positions || summary.positions.length === 0) {
    html += '<tr><td colspan="10" class="muted">No open positions</td></tr>'
  } else {
    for (const p of summary.positions) {
      const pnlCls = clsPortfolio(p.pnl_gbp)
      const pnlStr =
        p.pnl_gbp != null
          ? `${fmtPnlPortfolio(p.pnl_gbp)}${p.pnl_pct != null ? ` (${p.pnl_pct >= 0 ? "+" : ""}${fmtPortfolio(p.pnl_pct)}%)` : ""}`
          : "\u2014"
      const curPrice =
        p.current_price_gbp != null ? `\u00a3${fmtPortfolio(p.current_price_gbp)}` : "\u2014"
      const curVal =
        p.current_value_gbp != null ? `\u00a3${fmtPortfolio(p.current_value_gbp)}` : "\u2014"

      html += "<tr>"
      html += `<td><span class="platform-tag">${escPortfolio(p.platform)}</span></td>`
      html += `<td class="ticker">${escPortfolio(p.ticker)}</td>`
      html += `<td>${fmtPortfolio(p.quantity)}</td>`
      html += `<td>\u00a3${fmtPortfolio(p.avg_cost)}</td>`
      html += `<td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">${curPrice}</td>`
      html += `<td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">${curVal}</td>`
      html += `<td class="pnl-cell ${pnlCls}" style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">${pnlStr}</td>`
      html += `<td class="date-col">${p.entry_date}</td>`
      html += `<td>${escPortfolio(p.thesis) || "\u2014"}</td>`
      html += `<td><button class="btn-sm" hx-delete="/api/positions/${p.id}" hx-target="#portfolio-wrapper" hx-swap="innerHTML" hx-confirm="Close this position?">Close</button></td>`
      html += "</tr>"
    }
  }
  html += "</tbody></table></div></section>"

  return html
}

// ── Positions CRUD ────────────────────────────────────────────────────────────

/** GET /api/positions — list all open positions, optionally filter by platform */
portfolioRouter.get("/", (c) => {
  const db = DatabaseFactory.get()
  const platform = c.req.query("platform")
  if (platform) {
    const rows = db
      .query("SELECT * FROM positions WHERE status = 'open' AND platform = ? ORDER BY ticker")
      .all(platform)
    return c.json(rows)
  }
  const rows = db.query("SELECT * FROM positions WHERE status = 'open' ORDER BY ticker").all()
  return c.json(rows)
})

/** POST /api/positions — add a new position */
portfolioRouter.post("/", async (c) => {
  const db = DatabaseFactory.get()
  const body = await c.req.json()
  const { ticker, exchange, platform, quantity, avg_cost, entry_date, thesis, notes } = body
  if (!ticker || quantity == null || avg_cost == null) {
    return c.json({ error: "ticker, quantity, avg_cost required" }, 400)
  }
  const stmt = db.prepare(
    `INSERT INTO positions (ticker, exchange, platform, quantity, avg_cost, entry_date, thesis, notes)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
  )
  stmt.run(
    ticker,
    exchange ?? "US",
    platform ?? "unknown",
    quantity,
    avg_cost,
    entry_date ?? new Date().toISOString().slice(0, 10),
    sanitizeForDb(thesis) ?? null,
    sanitizeForDb(notes) ?? null,
  )

  // Return updated portfolio HTML for HTMX
  const summary = await computePortfolioSummary()
  return c.html(buildPortfolioHtml(summary))
})

/** DELETE /api/positions/:id — close a position */
portfolioRouter.delete("/:id", async (c) => {
  const db = DatabaseFactory.get()
  const id = c.req.param("id")
  const stmt = db.prepare("UPDATE positions SET status = 'closed' WHERE id = ?")
  const result = stmt.run(id)
  if (result.changes === 0) {
    return c.html('<div class="error-card"><strong>Position not found</strong></div>', 404)
  }

  // Return updated portfolio HTML for HTMX
  const summary = await computePortfolioSummary()
  return c.html(buildPortfolioHtml(summary))
})

// ── Portfolio P&L summary ─────────────────────────────────────────────────────

interface PriceData {
  price: number | null
  currency: string
  history: { date: string; close: number }[]
}

interface PositionEnriched {
  id: number
  ticker: string
  exchange: string
  platform: string
  quantity: number
  avg_cost: number
  entry_date: string
  thesis: string | null
  // enriched fields
  current_price_gbp: number | null
  current_value_gbp: number | null
  cost_value_gbp: number | null
  pnl_gbp: number | null
  pnl_pct: number | null
  currency: string
  price_history: { date: string; close: number }[] | null
}

interface PortfolioSummary {
  positions: PositionEnriched[]
  totals: {
    portfolio_value_gbp: number | null
    total_cost_gbp: number | null
    total_pnl_gbp: number | null
    total_pnl_pct: number | null
    positions_count: number
  }
  fx_rates: Record<string, number> // e.g. { GBPEUR: 1.18, GBPUSD: 1.27 }
}

async function computePortfolioSummary(): Promise<PortfolioSummary> {
  const db = DatabaseFactory.get()
  const rows = db
    .query("SELECT * FROM positions WHERE status = 'open' ORDER BY ticker")
    .all() as Array<{
    id: number
    ticker: string
    exchange: string
    platform: string
    quantity: number
    avg_cost: number
    entry_date: string
    thesis: string | null
  }>

  if (rows.length === 0) {
    return {
      positions: [],
      totals: {
        portfolio_value_gbp: 0,
        total_cost_gbp: 0,
        total_pnl_gbp: 0,
        total_pnl_pct: null,
        positions_count: 0,
      },
      fx_rates: {},
    }
  }

  const tickers = [...new Set(rows.map((r) => r.ticker))]
  const fxPairs = ["GBPEUR=X", "GBPUSD=X", "GBPEUR", "GBPUSD"]
  const allTickers = [...tickers, ...fxPairs]
  const priceResults = await batchFetchPrices(allTickers)

  const fxRates: Record<string, number> = {}
  for (const fx of fxPairs) {
    const data = priceResults.get(fx)
    if (data?.price != null) {
      const key = fx.replace("=X", "").replace("=", "")
      fxRates[key] = data.price
    }
  }

  if (!fxRates.GBPEUR) fxRates.GBPEUR = 1.18
  if (!fxRates.GBPUSD) fxRates.GBPUSD = 1.27

  const gbpPerEur = 1 / fxRates.GBPEUR
  const gbpPerUsd = 1 / fxRates.GBPUSD

  let totalValue = 0
  let totalCost = 0

  const enriched: PositionEnriched[] = rows.map((p) => {
    const priceData = priceResults.get(p.ticker) ?? null
    let currentPriceGbp: number | null = null

    if (priceData?.price != null) {
      const rawPrice = priceData.price
      if (priceData.currency === "EUR") {
        currentPriceGbp = rawPrice * gbpPerEur
      } else if (priceData.currency === "USD") {
        currentPriceGbp = rawPrice * gbpPerUsd
      } else {
        currentPriceGbp = rawPrice
      }
    }

    const quantity = p.quantity
    let costValueGbp = p.avg_cost * quantity
    if (p.exchange === "US" && fxRates.GBPUSD) {
      costValueGbp = (p.avg_cost * quantity) / fxRates.GBPUSD
    } else if ((p.exchange === "XETRA" || p.exchange === "EUR") && fxRates.GBPEUR) {
      costValueGbp = (p.avg_cost * quantity) / fxRates.GBPEUR
    }

    const currentValueGbp = currentPriceGbp != null ? currentPriceGbp * quantity : null
    const pnlGbp = currentValueGbp != null ? currentValueGbp - costValueGbp : null
    const pnlPct = costValueGbp > 0 && pnlGbp != null ? (pnlGbp / costValueGbp) * 100 : null

    if (currentValueGbp != null) totalValue += currentValueGbp
    totalCost += costValueGbp

    return {
      ...p,
      current_price_gbp: currentPriceGbp != null ? Math.round(currentPriceGbp * 100) / 100 : null,
      current_value_gbp: currentValueGbp != null ? Math.round(currentValueGbp * 100) / 100 : null,
      cost_value_gbp: Math.round(costValueGbp * 100) / 100,
      pnl_gbp: pnlGbp != null ? Math.round(pnlGbp * 100) / 100 : null,
      pnl_pct: pnlPct != null ? Math.round(pnlPct * 100) / 100 : null,
      currency: priceData?.currency ?? "GBP",
      price_history: priceData?.history ?? null,
    }
  })

  enriched.sort((a, b) => {
    if (a.pnl_gbp == null && b.pnl_gbp == null) return 0
    if (a.pnl_gbp == null) return 1
    if (b.pnl_gbp == null) return -1
    return a.pnl_gbp - b.pnl_gbp
  })

  const totalPnlGbp = totalValue - totalCost
  const totalPnlPct = totalCost > 0 ? (totalPnlGbp / totalCost) * 100 : null

  return {
    positions: enriched,
    totals: {
      portfolio_value_gbp: Math.round(totalValue * 100) / 100,
      total_cost_gbp: Math.round(totalCost * 100) / 100,
      total_pnl_gbp: Math.round(totalPnlGbp * 100) / 100,
      total_pnl_pct: totalPnlPct != null ? Math.round(totalPnlPct * 100) / 100 : null,
      positions_count: rows.length,
    },
    fx_rates: fxRates,
  }
}

/**
 * Standalone portfolio summary handler — mounted at GET /api/portfolio/summary in index.tsx.
 * Separated from portfolioRouter (which is mounted at /api/positions) to keep URLs clean.
 */
export async function handlePortfolioSummary(c: Context): Promise<Response> {
  const summary = await computePortfolioSummary()
  return c.json(summary)
}

/** GET /api/portfolio/summary/html — portfolio summary + positions table as HTML for HTMX */
export async function handlePortfolioSummaryHtml(c: Context): Promise<Response> {
  try {
    const summary = await computePortfolioSummary()
    return c.html(buildPortfolioHtml(summary))
  } catch (e: unknown) {
    return c.html(
      `<div class="error-card"><strong>Portfolio error</strong><br>${(e as Error).message}</div>`,
      500,
    )
  }
}

// ── Batch price helper (inline to avoid circular imports) ─────────────────────

async function batchFetchPrices(tickers: string[]): Promise<Map<string, PriceData>> {
  const results = new Map<string, PriceData>()
  const root = findProjectRoot()
  const script = join(root, "scripts", "py", "get_price.py")

  // Fetch in parallel, one at a time (yfinance is the bottleneck)
  const fetches = tickers.map(
    (ticker) =>
      new Promise<[string, PriceData]>((resolve) => {
        // Check cache first
        const cached = priceCache.get(ticker)
        const now = Date.now()
        if (cached && cached.expires > now) {
          resolve([ticker, { price: cached.price, currency: "USD", history: [] }])
          return
        }

        const child = spawn("python3", [script, ticker], {
          env: { ...process.env, PYTHONUNBUFFERED: "1" },
          timeout: 12_000,
        })

        let stdout = ""
        child.stdout.on("data", (d: Buffer) => {
          stdout += d.toString()
        })
        child.on("close", (_code) => {
          try {
            const data = JSON.parse(stdout.trim())
            const price = data.price ?? null
            const currency = data.currency ?? "USD"
            if (price != null) {
              priceCache.set(ticker, { price, expires: endOfToday() })
            }
            const history: { date: string; close: number }[] = (data.history ?? []).slice(-20)
            resolve([ticker, { price, currency, history }])
          } catch {
            resolve([ticker, { price: null, currency: "USD", history: [] }])
          }
        })
        child.on("error", () => resolve([ticker, { price: null, currency: "USD", history: [] }]))
      }),
  )

  const settled = await Promise.all(fetches)
  for (const [ticker, data] of settled) {
    results.set(ticker, data)
  }
  return results
}
