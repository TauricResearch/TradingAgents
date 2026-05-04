/**
 * Portfolio governance — risk rules and rebalancing checks.
 *
 * Rules are loaded from ~/.tradingagents/governance.yaml (YAML config).
 * Falls back to DEFAULT_RULES if the config file is missing or invalid.
 *
 * YAML structure:
 *   rules:                          # global defaults
 *     - id: max-position
 *       limit: 15
 *       unit: "%"
 *       description: No single holding > 15% of portfolio
 *   platforms:                      # optional per-platform overrides
 *     pension:nn:
 *       max-position: { limit: 10 } # stricter for pension
 *     trading:
 *       max-position: { limit: 20 } # looser for trading
 */

import { existsSync, readFileSync } from "node:fs"
import { join, dirname } from "node:path"
import { homedir } from "node:os"
import { load as parseYaml } from "js-yaml"

export interface GovernanceRule {
  id: string
  name: string
  limit: number
  unit: "%" | "EUR" | "count"
  description: string
}

export interface RuleViolation {
  rule: GovernanceRule
  current: number
  severity: "warn" | "breach"
  detail: string
}

export interface AllocationItem {
  ticker: string
  value: number
  weight: number
}

export interface RebalanceSuggestion {
  ticker: string
  action: "trim" | "add"
  currentWeight: number
  targetWeight: number
  delta: number
}

export const DEFAULT_RULES: GovernanceRule[] = [
  { id: "max-position",   name: "Max single position",       limit: 15,  unit: "%",    description: "No single holding > 15% of portfolio" },
  { id: "max-sector",     name: "Max sector concentration",  limit: 30,  unit: "%",    description: "No sector > 30% of portfolio" },
  { id: "cash-floor",     name: "Cash floor",               limit: 10,  unit: "%",    description: "Minimum 10% cash reserve" },
  { id: "max-drawdown",   name: "Max portfolio drawdown",   limit: 15,  unit: "%",    description: "If portfolio drops 15%, reduce to 50% cash" },
  { id: "max-holdings",   name: "Max number of holdings",   limit: 24,  unit: "count", description: "Keep portfolio manageable (< 24 positions)" },
]

// ── Config loading ────────────────────────────────────────────────────────────

interface PlatformOverride {
  [ruleId: string]: Partial<Pick<GovernanceRule, "limit" | "description">>
}

interface GovernanceConfig {
  rules?: GovernanceRule[]
  platforms?: { [platform: string]: PlatformOverride }
}

function configPath(): string {
  return join(homedir(), ".tradingagents", "governance.yaml")
}

/**
 * Load rules from ~/.tradingagents/governance.yaml.
 * Falls back to DEFAULT_RULES if the file is absent or unparseable.
 */
export function loadRules(): GovernanceRule[] {
  const path = configPath()
  if (!existsSync(path)) return DEFAULT_RULES

  try {
    const raw = readFileSync(path, "utf8")
    const config = parseYaml(raw) as GovernanceConfig

    if (config.rules && Array.isArray(config.rules) && config.rules.length > 0) {
      return config.rules
    }
    return DEFAULT_RULES
  } catch (err) {
    console.error("[governance] Failed to load config:", err)
    return DEFAULT_RULES
  }
}

/**
 * Load rules for a specific platform, applying per-platform overrides on top
 * of the global defaults.
 */
export function loadRulesForPlatform(platform: string): GovernanceRule[] {
  const globalRules = loadRules()
  const path = configPath()

  if (!existsSync(path)) return globalRules

  try {
    const raw = readFileSync(path, "utf8")
    const config = parseYaml(raw) as GovernanceConfig

    const platformOverrides = config.platforms?.[platform]
    if (!platformOverrides) return globalRules

    return globalRules.map((rule) => {
      const override = platformOverrides[rule.id]
      if (!override) return rule
      return {
        ...rule,
        limit: override.limit ?? rule.limit,
        description: override.description ?? rule.description,
      }
    })
  } catch {
    return globalRules
  }
}

// ── Rule evaluation ───────────────────────────────────────────────────────────

function findRule(rules: GovernanceRule[], id: string): GovernanceRule {
  const rule = rules.find((r) => r.id === id)
  if (!rule) throw new Error(`Governance rule not found: ${id}`)
  return rule
}

export function checkRules(
  allocations: AllocationItem[],
  cashPct: number,
  peakValue: number,
  currentValue: number,
  rules: GovernanceRule[] = loadRules(),
): RuleViolation[] {
  const violations: RuleViolation[] = []

  // Max single position
  const maxPosRule = findRule(rules, "max-position")
  for (const a of allocations) {
    if (a.weight > maxPosRule.limit) {
      violations.push({
        rule: maxPosRule,
        current: a.weight,
        severity: a.weight > maxPosRule.limit * 1.2 ? "breach" : "warn",
        detail: `${a.ticker} is ${a.weight.toFixed(1)}% (limit: ${maxPosRule.limit}%)`,
      })
    }
  }

  // Cash floor
  const cashRule = findRule(rules, "cash-floor")
  if (cashPct < cashRule.limit) {
    violations.push({
      rule: cashRule,
      current: cashPct,
      severity: "breach",
      detail: `Cash is ${cashPct.toFixed(1)}% (minimum: ${cashRule.limit}%)`,
    })
  }

  // Max drawdown
  const ddRule = findRule(rules, "max-drawdown")
  if (peakValue > 0) {
    const drawdown = ((peakValue - currentValue) / peakValue) * 100
    if (drawdown > ddRule.limit) {
      violations.push({
        rule: ddRule,
        current: drawdown,
        severity: "breach",
        detail: `Drawdown is ${drawdown.toFixed(1)}% (limit: ${ddRule.limit}%)`,
      })
    }
  }

  // Max holdings count
  const countRule = findRule(rules, "max-holdings")
  if (allocations.length > countRule.limit) {
    violations.push({
      rule: countRule,
      current: allocations.length,
      severity: "warn",
      detail: `${allocations.length} holdings (limit: ${countRule.limit})`,
    })
  }

  return violations
}

export function suggestRebalance(
  allocations: AllocationItem[],
  cashPct: number,
  rules: GovernanceRule[] = loadRules(),
): RebalanceSuggestion[] {
  const suggestions: RebalanceSuggestion[] = []
  const n = allocations.length
  if (n === 0) return suggestions

  const cashRule = findRule(rules, "cash-floor")
  const maxPosRule = findRule(rules, "max-position")

  const availableForHoldings = 100 - Math.max(cashPct, cashRule.limit)
  const targetWeight = availableForHoldings / n
  const effectiveTarget = Math.min(targetWeight, maxPosRule.limit)

  for (const a of allocations) {
    const delta = a.weight - effectiveTarget
    if (Math.abs(delta) < 1) continue

    suggestions.push({
      ticker: a.ticker,
      action: delta > 0 ? "trim" : "add",
      currentWeight: a.weight,
      targetWeight: effectiveTarget,
      delta: Math.abs(delta),
    })
  }

  suggestions.sort((a, b) => b.delta - a.delta)
  return suggestions
}

// ── Config path helper (for routes) ─────────────────────────────────────────

export function getConfigPath(): string {
  return configPath()
}