/** Governance data layer — extracted from route for reuse. */
import {
  checkRules,
  type GovernanceRule,
  loadRules,
  loadRulesForPlatform,
  type RebalanceSuggestion,
  type RuleViolation,
  suggestRebalance,
} from "./governance.ts"
import { getHoldings } from "./hledger.ts"

export interface GovernanceCheckResult {
  rules: GovernanceRule[]
  portfolioValue: number
  cashPct: number
  violations: RuleViolation[]
  suggestions: RebalanceSuggestion[]
  note?: string
}

export async function checkGovernance(platform?: string): Promise<GovernanceCheckResult> {
  const { holdings, cash } = await getHoldings()
  const rules = platform && platform !== "default" ? loadRulesForPlatform(platform) : loadRules()

  if (holdings.length === 0) {
    return {
      rules,
      portfolioValue: 0,
      cashPct: 0,
      violations: [],
      suggestions: [],
      note: "No holdings loaded",
    }
  }

  const platformHoldings =
    platform && platform !== "default" ? holdings.filter((h) => h.platform === platform) : holdings
  const platformCash =
    platform && platform !== "default" ? cash.filter((c) => c.platform === platform) : cash

  const totalCost = platformHoldings.reduce((s, h) => s + h.costBasis, 0)
  const cashTotal = platformCash.reduce((s, c) => s + c.amount, 0)
  const portfolioValue = totalCost + cashTotal

  const allocations = platformHoldings.map((h) => ({
    ticker: h.ticker,
    value: h.costBasis,
    weight: portfolioValue > 0 ? (h.costBasis / portfolioValue) * 100 : 0,
  }))

  const cashPct = portfolioValue > 0 ? (cashTotal / portfolioValue) * 100 : 0

  const violations = checkRules(allocations, cashPct, portfolioValue, portfolioValue, rules)
  const suggestions = suggestRebalance(allocations, cashPct, rules)

  return {
    rules,
    portfolioValue,
    cashPct,
    violations,
    suggestions,
  }
}

export {
  type GovernanceRule,
  getConfigPath,
  loadRules,
  loadRulesForPlatform,
  type RebalanceSuggestion,
  type RuleViolation,
} from "./governance.ts"
