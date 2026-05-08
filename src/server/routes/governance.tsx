/** @jsxImportSource hono/jsx */

import { Hono } from "hono"
import {
  checkGovernance,
  getConfigPath,
  loadRules,
  loadRulesForPlatform,
} from "../lib/governance-data.ts"
import { RulesTable, ViolationsPanel } from "../views/governance-view.tsx"

export const governanceRouter = new Hono()

/** GET /api/governance — aggregated violations across all platforms */
governanceRouter.get("/", async (c) => {
  try {
    const result = await checkGovernance()
    return c.json({
      rules: result.rules,
      portfolioValue: result.portfolioValue,
      cashPct: result.cashPct,
      violations: result.violations,
      suggestions: result.suggestions,
      note: result.note ??
        "hledger values are in native currencies (EUR/USD). Use /api/portfolio/intelligence for GBP-consistent totals.",
      baseCurrency: "mixed (EUR+USD)",
    })
  } catch (e: unknown) {
    return c.json({ error: "Governance check failed", detail: (e as Error).message }, 500)
  }
})

/** GET /api/governance/rules/html — rules table as HTML for HTMX */
governanceRouter.get("/rules/html", (c) => {
  const platform = c.req.query("platform") || "default"
  const rules = platform === "default" ? loadRules() : loadRulesForPlatform(platform)
  return c.html(<RulesTable rules={rules} />)
})

/** GET /api/governance/violations/html — violations + suggestions as HTML for HTMX */
governanceRouter.get("/violations/html", async (c) => {
  try {
    const result = await checkGovernance()
    if (result.note) {
      return c.html(<ViolationsPanel portfolioValue={0} cashPct={0} violations={[]} suggestions={[]} note={result.note} />)
    }
    return c.html(
      <ViolationsPanel
        portfolioValue={result.portfolioValue}
        cashPct={result.cashPct}
        violations={result.violations}
        suggestions={result.suggestions}
      />,
    )
  } catch (e: unknown) {
    return c.html(
      <div class="error-card">
        <strong>Governance error</strong>
        <br />
        {(e as Error).message}
      </div>,
      500,
    )
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
    const result = await checkGovernance(platform)
    return c.json({
      platform,
      portfolioValue: result.portfolioValue,
      cashPct: result.cashPct,
      violations: result.violations,
      suggestions: result.suggestions,
      rules: result.rules,
      note: result.note ??
        "hledger values are in native currencies (EUR/USD). Use /api/portfolio/intelligence for GBP-consistent totals.",
      baseCurrency: "mixed (EUR+USD)",
    })
  } catch (e: unknown) {
    return c.json({ error: "Governance check failed", detail: (e as Error).message }, 500)
  }
})
