/**
 * GET /api/governance — aggregated rules + violations, platform-aware
 * GET /api/governance/rules — list all governance rules
 * GET /api/governance/check?platform= — evaluate holdings against rules for a platform
 *
 * NOTE: hledger stores holdings in native currencies (EUR, USD).
 * portfolioValue and costBasis are summed without FX conversion.
 * For GBP-consistent values, use /api/portfolio/intelligence instead.
 * This endpoint is kept for per-rule evaluation (weights in %) which
 * are currency-independent.
 */
import { Hono } from "hono"
import {
  checkRules,
  suggestRebalance,
  loadRules,
  loadRulesForPlatform,
  getConfigPath,
  DEFAULT_RULES,
} from "../lib/governance.ts"
import { getHoldings } from "../lib/hledger.ts"

export const governanceRouter = new Hono()

/** GET /api/governance — aggregated violations across all platforms */
governanceRouter.get("/", async (c) => {
  try {
    const result = await getHoldings()
    const { holdings, cash } = result
    const rules = loadRules()

    if (holdings.length === 0) {
      return c.json({ rules, violations: [], suggestions: [], note: "No holdings loaded" })
    }

    const totalCost = holdings.reduce((s, h) => s + h.costBasis, 0)
    const cashTotal = cash.reduce((s, c) => s + c.amount, 0)
    const portfolioValue = totalCost + cashTotal

    const allocations = holdings.map((h) => ({
      ticker: h.ticker,
      value: h.costBasis,
      weight: portfolioValue > 0 ? (h.costBasis / portfolioValue) * 100 : 0,
    }))

    const cashPct = portfolioValue > 0 ? (cashTotal / portfolioValue) * 100 : 0

    const violations = checkRules(allocations, cashPct, portfolioValue, portfolioValue, rules)
    const suggestions = suggestRebalance(allocations, cashPct, rules)

    return c.json({ rules, portfolioValue, cashPct, violations, suggestions, platforms: result.platforms, note: "hledger values are in native currencies (EUR/USD). Use /api/portfolio/intelligence for GBP-consistent totals.", baseCurrency: "mixed (EUR+USD)" })
  } catch (e: unknown) {
    return c.json({ error: "Governance check failed", detail: (e as Error).message }, 500)
  }
})

/** GET /api/governance/rules?platform= — list rules (global or platform-specific) */
governanceRouter.get("/rules", (c) => {
  const platform = c.req.query("platform") || "default"
  const rules = platform === "default" ? loadRules() : loadRulesForPlatform(platform)
  return c.json({ platform, rules, configPath: getConfigPath() })
})

/** GET /api/governance/check?platform= — evaluate holdings against rules for a platform */
governanceRouter.get("/check", async (c) => {
  const platform = c.req.query("platform") || "default"
  try {
    const { holdings, cash } = await getHoldings()

    // Filter holdings by platform if specified
    const platformHoldings = platform === "default"
      ? holdings
      : holdings.filter((h) => h.platform === platform)

    const platformCash = platform === "default"
      ? cash
      : cash.filter((c) => c.platform === platform)

    if (platformHoldings.length === 0) {
      const rules = platform === "default" ? loadRules() : loadRulesForPlatform(platform)
      return c.json({ violations: [], suggestions: [], note: `No holdings for platform: ${platform}`, rules })
    }

    const totalCost = platformHoldings.reduce((s, h) => s + h.costBasis, 0)
    const cashTotal = platformCash.reduce((s, c) => s + c.amount, 0)
    const portfolioValue = totalCost + cashTotal

    const allocations = platformHoldings.map((h) => ({
      ticker: h.ticker,
      value: h.costBasis,
      weight: portfolioValue > 0 ? (h.costBasis / portfolioValue) * 100 : 0,
    }))

    const cashPct = portfolioValue > 0 ? (cashTotal / portfolioValue) * 100 : 0
    const rules = platform === "default" ? loadRules() : loadRulesForPlatform(platform)

    const violations = checkRules(allocations, cashPct, portfolioValue, portfolioValue, rules)
    const suggestions = suggestRebalance(allocations, cashPct, rules)

    return c.json({ platform, portfolioValue, cashPct, violations, suggestions, rules, note: "hledger values are in native currencies (EUR/USD). Use /api/portfolio/intelligence for GBP-consistent totals.", baseCurrency: "mixed (EUR+USD)" })
  } catch (e: unknown) {
    return c.json({ error: "Governance check failed", detail: (e as Error).message }, 500)
  }
})