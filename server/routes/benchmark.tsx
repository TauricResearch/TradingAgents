/** @jsxImportSource hono/jsx */

import { Hono } from "hono"
import { cfg } from "../lib/settings.ts"
import {
  computePeriodReturns,
  fetchBenchmarkPrices,
  getLivePortfolioValue,
} from "../lib/benchmark-data.ts"
import { BenchmarkTable } from "../views/benchmark-view.tsx"

export const benchmarkRouter = new Hono()

/** GET /api/benchmark — portfolio vs. benchmark returns */
benchmarkRouter.get("/", async (c) => {
  try {
    const benchmark = c.req.query("ticker") || cfg.app.benchmarkTicker
    const { total: portfolioValue } = await getLivePortfolioValue()
    const prices = await fetchBenchmarkPrices(benchmark)
    const periodReturns = computePeriodReturns(prices, portfolioValue)

    return c.json({
      ticker: benchmark,
      currentValue: portfolioValue,
      benchmarkPrices: prices,
      periodReturns,
      source: "sqlite",
      baseCurrency: "GBP",
      note: "Portfolio value in GBP via live FX conversion. Benchmark prices in native ETF currency (EUR for VWCE.DE).",
    })
  } catch (e: unknown) {
    return c.json(
      {
        error: "Benchmark check failed",
        detail: (e as Error).message,
        hint: "Ensure yfinance is installed (uv pip install yfinance)",
      },
      500,
    )
  }
})

/** GET /api/benchmark/table — portfolio vs. benchmark as HTML for HTMX */
benchmarkRouter.get("/table", async (c) => {
  try {
    const benchmark = c.req.query("ticker") || cfg.app.benchmarkTicker
    const { total: portfolioValue } = await getLivePortfolioValue()
    const prices = await fetchBenchmarkPrices(benchmark)
    const periodReturns = computePeriodReturns(prices, portfolioValue)
    return c.html(<BenchmarkTable ticker={benchmark} currentValue={portfolioValue} periodReturns={periodReturns} />)
  } catch (e: unknown) {
    return c.html(
      <div class="error-card">
        <strong>Benchmark error</strong>
        <br />
        {(e as Error).message}
      </div>,
      500,
    )
  }
})
