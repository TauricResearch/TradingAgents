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
  type GovernanceRule,
  getConfigPath,
  loadRules,
  loadRulesForPlatform,
  type RebalanceSuggestion,
  type RuleViolation,
  suggestRebalance,
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

    return c.json({
      rules,
      portfolioValue,
      cashPct,
      violations,
      suggestions,
      platforms: result.platforms,
      note: "hledger values are in native currencies (EUR/USD). Use /api/portfolio/intelligence for GBP-consistent totals.",
      baseCurrency: "mixed (EUR+USD)",
    })
  } catch (e: unknown) {
    return c.json({ error: "Governance check failed", detail: (e as Error).message }, 500)
  }
})

function buildRulesHtml(rules: GovernanceRule[]): string {
  let html = '<table class="data-table"><thead><tr>'
  html += "<th>Rule</th><th>Limit</th><th>Description</th>"
  html += "</tr></thead><tbody>"
  for (const r of rules) {
    html += "<tr>"
    html += `<td>${r.name}</td>`
    html += `<td>${r.limit}${r.unit === "%" ? "%" : r.unit === "count" ? "" : r.unit}</td>`
    html += `<td class="muted">${r.description}</td>`
    html += "</tr>"
  }
  html += "</tbody></table>"
  return html
}

function buildViolationsHtml(
  portfolioValue: number,
  cashPct: number,
  violations: RuleViolation[],
  suggestions: RebalanceSuggestion[],
  note?: string,
): string {
  if (note) return `<div class="muted">${note}</div>`

  let html = '<div class="governance-summary">'
  html += `<div>Portfolio: \u00a3${portfolioValue.toFixed(2)} <span class="muted">(base: GBP)</span></div>`
  html += `<div>Cash: ${cashPct.toFixed(1)}%</div>`
  html += "</div>"

  if (violations.length > 0) {
    html += "<h4>\u26a0\ufe0f Violations</h4>"
    for (const v of violations) {
      const cls = v.severity === "breach" ? "violation-breach" : "violation-warn"
      html += `<div class="${cls}">`
      html += `<strong>${v.rule.name}</strong>: ${v.detail}`
      html += "</div>"
    }
  } else {
    html += '<div class="ok">\u2705 All rules satisfied</div>'
  }

  if (suggestions.length > 0) {
    html += '<h4 style="margin-top:1rem">Rebalance Suggestions</h4>'
    html += '<table class="data-table" style="font-size:0.85em"><thead><tr>'
    html += "<th>Ticker</th><th>Action</th><th>Current</th><th>Target</th><th>Drift</th>"
    html += "</tr></thead><tbody>"
    for (const s of suggestions) {
      html += "<tr>"
      html += `<td class="ticker">${s.ticker}</td>`
      html += `<td class="${s.action === "trim" ? "negative" : "positive"}">${s.action.toUpperCase()}</td>`
      html += `<td>${s.currentWeight.toFixed(1)}%</td>`
      html += `<td>${s.targetWeight.toFixed(1)}%</td>`
      html += `<td>${s.delta.toFixed(1)}pp</td>`
      html += "</tr>"
    }
    html += "</tbody></table>"
  }

  return html
}

/** GET /api/governance/rules/html — rules table as HTML for HTMX */
governanceRouter.get("/rules/html", (c) => {
  const platform = c.req.query("platform") || "default"
  const rules = platform === "default" ? loadRules() : loadRulesForPlatform(platform)
  return c.html(buildRulesHtml(rules))
})

/** GET /api/governance/violations/html — violations + suggestions as HTML for HTMX */
governanceRouter.get("/violations/html", async (c) => {
  try {
    const { holdings, cash } = await getHoldings()
    const rules = loadRules()

    if (holdings.length === 0) {
      return c.html(buildViolationsHtml(0, 0, [], [], "No holdings loaded"))
    }

    const totalCost = holdings.reduce((s, h) => s + h.costBasis, 0)
    const cashTotal = cash.reduce((s, ca) => s + ca.amount, 0)
    const portfolioValue = totalCost + cashTotal

    const allocations = holdings.map((h) => ({
      ticker: h.ticker,
      value: h.costBasis,
      weight: portfolioValue > 0 ? (h.costBasis / portfolioValue) * 100 : 0,
    }))

    const cashPct = portfolioValue > 0 ? (cashTotal / portfolioValue) * 100 : 0
    const violations = checkRules(allocations, cashPct, portfolioValue, portfolioValue, rules)
    const suggestions = suggestRebalance(allocations, cashPct, rules)

    return c.html(buildViolationsHtml(portfolioValue, cashPct, violations, suggestions))
  } catch (e: unknown) {
    return c.html(
      `<div class="error-card"><strong>Governance error</strong><br>${(e as Error).message}</div>`,
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
    const { holdings, cash } = await getHoldings()

    // Filter holdings by platform if specified
    const platformHoldings =
      platform === "default" ? holdings : holdings.filter((h) => h.platform === platform)

    const platformCash = platform === "default" ? cash : cash.filter((c) => c.platform === platform)

    if (platformHoldings.length === 0) {
      const rules = platform === "default" ? loadRules() : loadRulesForPlatform(platform)
      return c.json({
        violations: [],
        suggestions: [],
        note: `No holdings for platform: ${platform}`,
        rules,
      })
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

    return c.json({
      platform,
      portfolioValue,
      cashPct,
      violations,
      suggestions,
      rules,
      note: "hledger values are in native currencies (EUR/USD). Use /api/portfolio/intelligence for GBP-consistent totals.",
      baseCurrency: "mixed (EUR+USD)",
    })
  } catch (e: unknown) {
    return c.json({ error: "Governance check failed", detail: (e as Error).message }, 500)
  }
})
