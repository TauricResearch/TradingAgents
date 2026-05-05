/**
 * GET /api/portfolio/intelligence — unified portfolio view
 *
 * Fuses:
 *   - hledger cash balances (authoritative per-platform cash)
 *   - SQLite positions with live market prices + P&L
 *   - Governance rules (violations + rebalance suggestions)
 *
 * Returns:
 *   - total portfolio value (live prices)
 *   - cash by platform
 *   - positions by platform with live P&L
 *   - allocation breakdown (by platform, by asset class)
 *   - governance violations
 *   - cash % of portfolio
 */

import { spawn } from "node:child_process"
import { dirname, join } from "node:path"
import { Hono } from "hono"
import { endOfToday, priceCache } from "../lib/cache.ts"
import { DatabaseFactory } from "../lib/db.ts"
import { checkRules, loadRules, suggestRebalance } from "../lib/governance.ts"
import { getHoldings } from "../lib/hledger.ts"
import type { PriceResult } from "../lib/types.ts"

export const intelligenceRouter = new Hono()

function findProjectRoot(): string {
  if (process.env.TA_ROOT) return process.env.TA_ROOT
  const projectRoot = dirname(dirname(import.meta.dir))
  if (projectRoot.includes("TradingAgents")) return projectRoot
  return projectRoot
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
}

interface PositionWithValue {
  id: number
  ticker: string
  exchange: string
  platform: string
  quantity: number
  avg_cost: number
  entry_date: string
  thesis: string | null
  current_price_gbp: number | null
  current_value_gbp: number | null
  cost_value_gbp: number
  pnl_gbp: number | null
  pnl_pct: number | null
  currency: string
}

interface CashBalance {
  platform: string
  currency: string
  amount: number
  amount_gbp: number
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

async function fetchPrices(tickers: string[]): Promise<Map<string, PriceResult>> {
  const results = new Map<string, PriceResult>()
  if (tickers.length === 0) return results

  const settled = await Promise.all(
    tickers.map(
      (t) =>
        new Promise<[string, PriceResult]>((resolve) => {
          fetchPriceForTicker(t).then((r) => resolve([t, r]))
        }),
    ),
  )
  for (const [ticker, data] of settled) results.set(ticker, data)
  return results
}

interface PortfolioIntel {
  total_value_gbp: number
  cash_gbp: number
  cash_pct: number
  cash_pct_raw: number
  cash_negative: boolean
  position_value_gbp: number
  positions_count: number
  fx_rates: { GBPEUR: number; GBPUSD: number }
  platforms: Array<{
    platform: string
    positions: PositionWithValue[]
    cash_gbp: number
    position_value_gbp: number
    total_value_gbp: number
    weight_pct: number
    cash_pct: number
  }>
  asset_classes: Array<{ assetClass: string; value_gbp: number; weight_pct: number }>
  governance: {
    violations: import("../lib/governance.ts").RuleViolation[]
    suggestions: import("../lib/governance.ts").RebalanceSuggestion[]
  }
}

async function computePortfolioIntelligence(): Promise<PortfolioIntel> {
  const { cash: hlCash } = await getHoldings()

  const db = DatabaseFactory.get()
  const dbPositions = db
    .query(
      "SELECT id, ticker, exchange, platform, quantity, avg_cost, entry_date, thesis FROM positions WHERE status = 'open'",
    )
    .all() as DbPosition[]

  const tickers = [...new Set(dbPositions.map((p) => p.ticker))]
  const fxPairs = ["GBPEUR=X", "GBPUSD=X"]
  const allNeeded = [...tickers, ...fxPairs]
  const prices = await fetchPrices(allNeeded)

  const gbpeur = prices.get("GBPEUR=X")?.price ?? 1.18
  const gbpUSD = prices.get("GBPUSD=X")?.price ?? 1.27
  const gbpPerEur = 1 / gbpeur
  const gbpPerUsd = 1 / gbpUSD

  const cashByPlatform: Map<string, CashBalance[]> = new Map()
  for (const c of hlCash) {
    const list = cashByPlatform.get(c.platform) ?? []
    let amountGbp = c.amount
    if (c.currency === "EUR") amountGbp = c.amount * gbpPerEur
    else if (c.currency === "USD") amountGbp = c.amount * gbpPerUsd
    list.push({
      platform: c.platform,
      currency: c.currency,
      amount: c.amount,
      amount_gbp: amountGbp,
    })
    cashByPlatform.set(c.platform, list)
  }

  const totalCashGbp = [...cashByPlatform.values()].flat().reduce((s, c) => s + c.amount_gbp, 0)

  const positionsWithValue: PositionWithValue[] = dbPositions.map((p) => {
    const pd = prices.get(p.ticker)
    let currentPriceGbp: number | null = null
    if (pd?.price != null) {
      if (pd.currency === "EUR") currentPriceGbp = pd.price * gbpPerEur
      else if (pd.currency === "USD") currentPriceGbp = pd.price * gbpPerUsd
      else currentPriceGbp = pd.price
    }

    let costValueGbp = p.avg_cost * p.quantity
    if (p.exchange === "US") costValueGbp = (p.avg_cost * p.quantity) / gbpUSD
    else if (p.exchange === "XETRA" || p.exchange === "EUR")
      costValueGbp = (p.avg_cost * p.quantity) / gbpeur

    const currentValueGbp = currentPriceGbp != null ? currentPriceGbp * p.quantity : null
    const pnlGbp = currentValueGbp != null ? currentValueGbp - costValueGbp : null
    const pnlPct = costValueGbp > 0 && pnlGbp != null ? (pnlGbp / costValueGbp) * 100 : null

    return {
      ...p,
      current_price_gbp: currentPriceGbp != null ? Math.round(currentPriceGbp * 100) / 100 : null,
      current_value_gbp: currentValueGbp != null ? Math.round(currentValueGbp * 100) / 100 : null,
      cost_value_gbp: Math.round(costValueGbp * 100) / 100,
      pnl_gbp: pnlGbp != null ? Math.round(pnlGbp * 100) / 100 : null,
      pnl_pct: pnlPct != null ? Math.round(pnlPct * 100) / 100 : null,
      currency: pd?.currency ?? "GBP",
    }
  })

  const totalPositionsValueGbp = positionsWithValue.reduce(
    (s, p) => s + (p.current_value_gbp ?? p.cost_value_gbp),
    0,
  )
  const totalPortfolioGbp = totalPositionsValueGbp + totalCashGbp
  const cashPctRaw = totalPortfolioGbp !== 0 ? (totalCashGbp / totalPortfolioGbp) * 100 : 0
  const cashPct = cashPctRaw
  const absPortfolioGbp = Math.abs(totalPortfolioGbp)

  const positionsByPlatform = new Map<string, PositionWithValue[]>()
  for (const p of positionsWithValue) {
    const list = positionsByPlatform.get(p.platform) ?? []
    list.push(p)
    positionsByPlatform.set(p.platform, list)
  }

  const cashByPlatformGbp = new Map<string, number>()
  for (const [platform, balances] of cashByPlatform) {
    cashByPlatformGbp.set(
      platform,
      balances.reduce((s, c) => s + c.amount_gbp, 0),
    )
  }

  const allPlatforms = [...new Set([...positionsByPlatform.keys(), ...cashByPlatformGbp.keys()])]

  const platformAllocations = allPlatforms.map((platform) => {
    const pos = positionsByPlatform.get(platform) ?? []
    const cashGbp = cashByPlatformGbp.get(platform) ?? 0
    const posValueGbp = pos.reduce((s, p) => s + (p.current_value_gbp ?? p.cost_value_gbp), 0)
    const totalGbp = posValueGbp + cashGbp
    return {
      platform,
      positions: pos,
      cash_gbp: Math.round(cashGbp * 100) / 100,
      position_value_gbp: Math.round(posValueGbp * 100) / 100,
      total_value_gbp: Math.round(totalGbp * 100) / 100,
      weight_pct: absPortfolioGbp > 0 ? Math.round((totalGbp / absPortfolioGbp) * 10000) / 100 : 0,
      cash_pct: totalGbp > 0 ? Math.round((cashGbp / totalGbp) * 10000) / 100 : 0,
    }
  })

  const etfValueGbp = positionsWithValue
    .filter((p) => classifyTicker(p.ticker, p.exchange) === "etf")
    .reduce((s, p) => s + (p.current_value_gbp ?? p.cost_value_gbp), 0)
  const equityValueGbp = positionsWithValue
    .filter((p) => classifyTicker(p.ticker, p.exchange) === "equity")
    .reduce((s, p) => s + (p.current_value_gbp ?? p.cost_value_gbp), 0)
  const cryptoValueGbp = positionsWithValue
    .filter((p) => classifyTicker(p.ticker, p.exchange) === "crypto")
    .reduce((s, p) => s + (p.current_value_gbp ?? p.cost_value_gbp), 0)

  const assetClassAllocation = [
    {
      assetClass: "cash",
      value_gbp: Math.round(Math.abs(totalCashGbp) * 100) / 100,
      weight_pct: Math.abs(cashPct),
    },
    {
      assetClass: "equity",
      value_gbp: Math.round(equityValueGbp * 100) / 100,
      weight_pct:
        absPortfolioGbp > 0 ? Math.round((equityValueGbp / absPortfolioGbp) * 10000) / 100 : 0,
    },
    {
      assetClass: "etf",
      value_gbp: Math.round(etfValueGbp * 100) / 100,
      weight_pct:
        absPortfolioGbp > 0 ? Math.round((etfValueGbp / absPortfolioGbp) * 10000) / 100 : 0,
    },
    {
      assetClass: "crypto",
      value_gbp: Math.round(cryptoValueGbp * 100) / 100,
      weight_pct:
        absPortfolioGbp > 0 ? Math.round((cryptoValueGbp / absPortfolioGbp) * 10000) / 100 : 0,
    },
  ].filter((a) => a.value_gbp > 0)

  const rules = loadRules()
  const overallAllocations = positionsWithValue.map((p) => ({
    ticker: p.ticker,
    value: p.current_value_gbp ?? p.cost_value_gbp,
    weight:
      absPortfolioGbp > 0 ? ((p.current_value_gbp ?? p.cost_value_gbp) / absPortfolioGbp) * 100 : 0,
  }))
  const overallViolations = checkRules(
    overallAllocations,
    cashPct,
    totalPortfolioGbp,
    totalPortfolioGbp,
    rules,
  )
  const overallSuggestions = suggestRebalance(overallAllocations, cashPct, rules)

  return {
    total_value_gbp: Math.round(totalPortfolioGbp * 100) / 100,
    cash_gbp: Math.round(totalCashGbp * 100) / 100,
    cash_pct: Math.round(cashPct * 100) / 100,
    cash_pct_raw: Math.round(cashPctRaw * 100) / 100,
    cash_negative: totalCashGbp < 0,
    position_value_gbp: Math.round(totalPositionsValueGbp * 100) / 100,
    positions_count: positionsWithValue.length,
    fx_rates: {
      GBPEUR: Math.round(gbpeur * 10000) / 10000,
      GBPUSD: Math.round(gbpUSD * 10000) / 10000,
    },
    platforms: platformAllocations.sort((a, b) => b.total_value_gbp - a.total_value_gbp),
    asset_classes: assetClassAllocation,
    governance: { violations: overallViolations, suggestions: overallSuggestions },
  }
}

// ── Asset classification helpers ─────────────────────────────────────────────

function classifyTicker(ticker: string, exchange: string): string {
  const t = ticker.toUpperCase()
  // ETFs
  if (t === "VWCE.DE" || t === "IWDA.L" || t === "CSPX.L" || t === "TERA.SW") return "etf"
  // Crypto
  if (exchange === "CRYPTO" || ["BTC", "ETH", "SOL", "XRP"].includes(t)) return "crypto"
  // Default: equity
  return "equity"
}

function _escIntel(s: string | null | undefined): string {
  if (s == null) return ""
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

function _fmtIntel(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—"
  const s = n.toFixed(2)
  return s.replace(/\B(?=(\d{3})+(?!\d))/g, ",")
}

function buildIntelHeroHtml(data: PortfolioIntel): string {
  let html = ""
  if (data.cash_negative) {
    html += '<div class="banner" style="margin-bottom:1rem">'
    html +=
      "\u26a0\ufe0f hledger cash is negative \u2014 more sells recorded than buys in journal. Total and % figures may be misleading until hledger cash is corrected."
    html += "</div>"
  }

  html += '<div class="intel-hero">'
  html += `<div class="intel-stat"><div class="intel-label">Total Portfolio</div><div class="intel-value">\u00a3${_fmtIntel(data.total_value_gbp)}</div></div>`
  html += `<div class="intel-stat"><div class="intel-label">Cash</div><div class="intel-value${data.cash_negative ? " negative" : ""}">\u00a3${_fmtIntel(data.cash_gbp)}<span class="intel-pct"> (${_fmtIntel(data.cash_pct_raw)}%)</span></div></div>`
  html += `<div class="intel-stat"><div class="intel-label">Positions</div><div class="intel-value">${data.positions_count}</div></div>`
  html += `<div class="intel-stat"><div class="intel-label">Live Value</div><div class="intel-value">\u00a3${_fmtIntel(data.position_value_gbp)}</div></div>`
  html += "</div>"

  html += '<div class="intel-fx">'
  if (data.fx_rates.GBPEUR) html += `<span>GBPEUR: ${data.fx_rates.GBPEUR.toFixed(4)}</span>`
  if (data.fx_rates.GBPUSD) html += `<span>GBPUSD: ${data.fx_rates.GBPUSD.toFixed(4)}</span>`
  html += "</div>"

  return html
}

function buildAssetClassHtml(data: PortfolioIntel): string {
  if (!data.asset_classes || data.asset_classes.length === 0) {
    return '<div class="muted">No allocation data</div>'
  }
  const total = data.total_value_gbp || 1
  const colors: Record<string, string> = {
    cash: "#3b82f6",
    equity: "#22c55e",
    etf: "#eab308",
    crypto: "#ef4444",
  }

  let bars = ""
  let legend = ""
  for (const ac of data.asset_classes) {
    const w = Math.round((ac.value_gbp / total) * 100)
    const color = colors[ac.assetClass] ?? "#71717a"
    bars += `<div style="display:inline-block;height:16px;width:${w}%;background:${color};margin-right:2px" title="${ac.assetClass}: ${w}% (${ac.value_gbp.toFixed(0)} GBP)"></div>`
    legend += `<span style="margin-right:12px"><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${color};vertical-align:middle;margin-right:4px"></span>${ac.assetClass} ${w}% (${ac.value_gbp.toFixed(0)})</span>`
  }

  return `<div class="allocation-bar">${bars}<div style="margin-top:4px;font-size:0.75em;color:var(--text-dim)">${legend}</div></div>`
}

function buildPlatformsHtml(data: PortfolioIntel): string {
  if (!data.platforms || data.platforms.length === 0) {
    return '<div class="muted">No platform data</div>'
  }

  const _total = data.total_value_gbp || 1
  let html = '<table class="data-table"><thead><tr>'
  html += "<th>Platform</th><th>Total Value</th><th>Weight</th><th>Cash</th><th>Positions</th>"
  html += "</tr></thead><tbody>"

  for (const p of data.platforms) {
    const posList = p.positions || []
    html += "<tr>"
    html += `<td><span class="platform-tag">${_escIntel(p.platform)}</span></td>`
    html += `<td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">\u00a3${_fmtIntel(p.total_value_gbp)}</td>`
    html += `<td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">${_fmtIntel(p.weight_pct)}%</td>`
    html += `<td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">\u00a3${_fmtIntel(p.cash_gbp)} <span class="muted">(${_fmtIntel(p.cash_pct)}%)</span></td>`
    html += "<td>"
    for (const pos of posList) {
      const pnl = pos.pnl_pct
      const pnlCls = pnl != null ? (pnl >= 0 ? "positive" : "negative") : ""
      const pnlStr = pnl != null ? `${(pnl >= 0 ? "+" : "") + _fmtIntel(pnl)}%` : ""
      html += `<span class="position-pill">${_escIntel(pos.ticker)} <span class="${pnlCls}">${pnlStr}</span></span>`
    }
    html += "</td>"
    html += "</tr>"
  }
  html += "</tbody></table>"
  return html
}

function buildGovernanceHtml(data: PortfolioIntel): string {
  const gov = data.governance
  let html = ""

  if (gov.violations && gov.violations.length > 0) {
    html += "<h4>\u26a0\ufe0f Violations</h4>"
    for (const v of gov.violations) {
      const cls = v.severity === "breach" ? "violation-breach" : "violation-warn"
      html += `<div class="${cls}"><strong>${v.rule.name}</strong>: ${v.detail}</div>`
    }
  } else {
    html += '<div class="ok">\u2705 All rules satisfied</div>'
  }

  if (gov.suggestions && gov.suggestions.length > 0) {
    html += '<h4 style="margin-top:1rem">Rebalance Suggestions</h4>'
    html += '<table class="data-table" style="font-size:0.85em"><thead><tr>'
    html += "<th>Ticker</th><th>Action</th><th>Current</th><th>Target</th><th>Drift</th>"
    html += "</tr></thead><tbody>"
    for (const s of gov.suggestions) {
      html += "<tr>"
      html += `<td class="ticker">${s.ticker}</td>`
      html += `<td class="${s.action === "trim" ? "negative" : "positive"}">${s.action.toUpperCase()}</td>`
      html += `<td>${_fmtIntel(s.currentWeight)}%</td>`
      html += `<td>${_fmtIntel(s.targetWeight)}%</td>`
      html += `<td>${_fmtIntel(s.delta)}pp</td>`
      html += "</tr>"
    }
    html += "</tbody></table>"
  }

  return html
}

function buildIntelHtml(data: PortfolioIntel): string {
  return (
    buildIntelHeroHtml(data) +
    buildAssetClassHtml(data) +
    buildPlatformsHtml(data) +
    buildGovernanceHtml(data)
  )
}

// ── Main endpoint ────────────────────────────────────────────────────────────

intelligenceRouter.get("/", async (c) => {
  try {
    const data = await computePortfolioIntelligence()
    return c.json({
      portfolio: {
        total_value_gbp: data.total_value_gbp,
        cash_gbp: data.cash_gbp,
        cash_pct: data.cash_pct,
        cash_pct_raw: data.cash_pct_raw,
        cash_negative: data.cash_negative,
        position_value_gbp: data.position_value_gbp,
        positions_count: data.positions_count,
      },
      fx_rates: data.fx_rates,
      platforms: data.platforms,
      asset_classes: data.asset_classes,
      governance: data.governance,
    })
  } catch (e: unknown) {
    return c.json({ error: "Portfolio intelligence failed", detail: (e as Error).message }, 500)
  }
})

/** GET /api/portfolio/intelligence/html — full intelligence page as HTML for HTMX */
intelligenceRouter.get("/html", async (c) => {
  try {
    const data = await computePortfolioIntelligence()
    return c.html(buildIntelHtml(data))
  } catch (e: unknown) {
    return c.html(
      `<div class="error-card"><strong>Intelligence error</strong><br>${(e as Error).message}</div>`,
      500,
    )
  }
})

// ── FX rates only ────────────────────────────────────────────────────────────

/** GET /api/portfolio/fx-rates — current GBP exchange rates (lightweight) */
intelligenceRouter.get("/fx-rates", async (c) => {
  try {
    const prices = await fetchPrices(["GBPEUR=X", "GBPUSD=X"])
    const gbpeur = prices.get("GBPEUR=X")?.price ?? 1.18
    const gbpUSD = prices.get("GBPUSD=X")?.price ?? 1.27
    return c.json({
      GBPEUR: Math.round(gbpeur * 10000) / 10000,
      GBPUSD: Math.round(gbpUSD * 10000) / 10000,
      fetched_at: new Date().toISOString(),
    })
  } catch (e: unknown) {
    return c.json({ error: "Failed to fetch FX rates", detail: (e as Error).message }, 500)
  }
})
