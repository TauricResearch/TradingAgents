/**
 * Route: /api/trade-plan/:ticker
 *
 * GET /api/trade-plan/:ticker           → JSON TradePlan
 * GET /api/trade-plan/:ticker/html    → HTML bracket order view
 */

import { Hono } from "hono"
import { DatabaseFactory } from "../../lib/db.ts"
import { calculateTradePlan, type PriceBar } from "../../lib/trade-calculator.ts"
import { TradePlanView } from "../views/trade-plan.tsx"

const router = new Hono()

function fetchPriceHistory(ticker: string): PriceBar[] {
  const db = DatabaseFactory.get()
  const rows = db.query(
    `SELECT date, open, high, low, close, volume
     FROM prices
     WHERE ticker = ?
     ORDER BY date ASC`,
  ).all(ticker) as Array<{
    date: string
    open: number | string
    high: number | string
    low: number | string
    close: number | string
    volume: number | string
  }>

  return rows.map((r) => ({
    date: r.date,
    open: parseFloat(String(r.open)),
    high: parseFloat(String(r.high)),
    low: parseFloat(String(r.low)),
    close: parseFloat(String(r.close)),
    volume: parseInt(String(r.volume), 10),
  }))
}

function getSettings() {
  return {
    accountBalance: parseFloat(process.env.DEFAULT_ACCOUNT_BALANCE ?? "50000"),
    riskPerTrade: parseFloat(process.env.DEFAULT_RISK_PER_TRADE ?? "0.02"),
  }
}

// JSON API
router.get("/:ticker", async (c) => {
  const ticker = c.req.param("ticker")
  const { accountBalance, riskPerTrade } = getSettings()

  const history = fetchPriceHistory(ticker)
  if (history.length === 0) {
    return c.json({ error: "No price history", hint: "Run: just sync-prices" }, 404)
  }

  const plan = calculateTradePlan({
    ticker,
    priceHistory: history,
    accountBalance,
    riskPerTrade,
  })

  return c.json(plan)
})

// HTML view
router.get("/:ticker/html", async (c) => {
  const ticker = c.req.param("ticker")
  const { accountBalance, riskPerTrade } = getSettings()

  const history = fetchPriceHistory(ticker)
  if (history.length === 0) {
    return c.html(
      <div class="panel">No price history for {ticker}. Run <code>just sync-prices</code>.</div>,
      404,
    )
  }

  const plan = calculateTradePlan({
    ticker,
    priceHistory: history,
    accountBalance,
    riskPerTrade,
  })

  const view = <TradePlanView plan={plan} />
  return c.html(view)
})

export { router as tradePlanRouter }
