/** @jsxImportSource hono/jsx */

import { Hono } from "hono"
import { computePortfolioIntelligence, fetchPrices } from "../lib/portfolio-intel-data.ts"
import { PortfolioIntelView } from "../views/portfolio-intel.tsx"

export const intelligenceRouter = new Hono()

/** GET /api/portfolio/intelligence — JSON portfolio data */
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
      allocation_bar: data.allocation_bar,
      cash_breakdown: data.cash_breakdown,
      accounts: data.accounts,
      platforms: data.platforms,
      asset_classes: data.asset_classes,
      spreadbets: data.spreadbets,
      research_queue: data.research_queue,
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
    return c.html(<PortfolioIntelView data={data} />)
  } catch (e: unknown) {
    return c.html(
      <div class="error-card">
        <strong>Intelligence error</strong>
        <br />
        {(e as Error).message}
      </div>,
      500,
    )
  }
})

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
