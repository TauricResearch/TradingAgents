/**
 * Portfolio governance — risk rules and rebalancing checks.
 *
 * Rules are defined in code (for now) and evaluated against
 * current holdings from hLedger.
 */

export interface GovernanceRule {
  id: string;
  name: string;
  limit: number;
  unit: "%" | "EUR" | "count";
  description: string;
}

export interface RuleViolation {
  rule: GovernanceRule;
  current: number;
  severity: "warn" | "breach";
  detail: string;
}

export interface AllocationItem {
  ticker: string;
  value: number;
  weight: number; // percentage
}

export interface RebalanceSuggestion {
  ticker: string;
  action: "trim" | "add";
  currentWeight: number;
  targetWeight: number;
  delta: number; // percentage points to adjust
}

export const DEFAULT_RULES: GovernanceRule[] = [
  {
    id: "max-position",
    name: "Max single position",
    limit: 15,
    unit: "%",
    description: "No single holding > 15% of portfolio",
  },
  {
    id: "max-sector",
    name: "Max sector concentration",
    limit: 30,
    unit: "%",
    description: "No sector > 30% of portfolio",
  },
  {
    id: "cash-floor",
    name: "Cash floor",
    limit: 10,
    unit: "%",
    description: "Minimum 10% cash reserve",
  },
  {
    id: "max-drawdown",
    name: "Max portfolio drawdown",
    limit: 15,
    unit: "%",
    description: "If portfolio drops 15%, reduce to 50% cash",
  },
  {
    id: "max-holdings",
    name: "Max number of holdings",
    limit: 24,
    unit: "count",
    description: "Keep portfolio manageable (< 24 positions)",
  },
];

/**
 * Check holdings against governance rules.
 * Returns violations (warnings and breaches).
 */
export function checkRules(
  allocations: AllocationItem[],
  cashPct: number,
  peakValue: number,
  currentValue: number,
): RuleViolation[] {
  const violations: RuleViolation[] = [];
  const totalValue = allocations.reduce((s, a) => s + a.value, 0) + (cashPct / 100) * currentValue;

  // Max single position
  const maxPosRule = DEFAULT_RULES.find((r) => r.id === "max-position")!;
  for (const a of allocations) {
    if (a.weight > maxPosRule.limit) {
      violations.push({
        rule: maxPosRule,
        current: a.weight,
        severity: a.weight > maxPosRule.limit * 1.2 ? "breach" : "warn",
        detail: `${a.ticker} is ${a.weight.toFixed(1)}% (limit: ${maxPosRule.limit}%)`,
      });
    }
  }

  // Cash floor
  const cashRule = DEFAULT_RULES.find((r) => r.id === "cash-floor")!;
  if (cashPct < cashRule.limit) {
    violations.push({
      rule: cashRule,
      current: cashPct,
      severity: "breach",
      detail: `Cash is ${cashPct.toFixed(1)}% (minimum: ${cashRule.limit}%)`,
    });
  }

  // Max drawdown
  const ddRule = DEFAULT_RULES.find((r) => r.id === "max-drawdown")!;
  if (peakValue > 0) {
    const drawdown = ((peakValue - currentValue) / peakValue) * 100;
    if (drawdown > ddRule.limit) {
      violations.push({
        rule: ddRule,
        current: drawdown,
        severity: "breach",
        detail: `Drawdown is ${drawdown.toFixed(1)}% (limit: ${ddRule.limit}%)`,
      });
    }
  }

  // Max holdings count
  const countRule = DEFAULT_RULES.find((r) => r.id === "max-holdings")!;
  if (allocations.length > countRule.limit) {
    violations.push({
      rule: countRule,
      current: allocations.length,
      severity: "warn",
      detail: `${allocations.length} holdings (limit: ${countRule.limit})`,
    });
  }

  return violations;
}

/**
 * Generate rebalancing suggestions based on allocation drift.
 * Target: equal-weight for holdings + cash floor.
 */
export function suggestRebalance(
  allocations: AllocationItem[],
  cashPct: number,
): RebalanceSuggestion[] {
  const suggestions: RebalanceSuggestion[] = [];
  const n = allocations.length;
  if (n === 0) return suggestions;

  // Target: equal weight for holdings, respecting cash floor
  const cashRule = DEFAULT_RULES.find((r) => r.id === "cash-floor")!;
  const availableForHoldings = 100 - Math.max(cashPct, cashRule.limit);
  const targetWeight = availableForHoldings / n;
  const maxPosRule = DEFAULT_RULES.find((r) => r.id === "max-position")!;
  const effectiveTarget = Math.min(targetWeight, maxPosRule.limit);

  for (const a of allocations) {
    const delta = a.weight - effectiveTarget;
    if (Math.abs(delta) < 1) continue; // Ignore < 1% drift

    suggestions.push({
      ticker: a.ticker,
      action: delta > 0 ? "trim" : "add",
      currentWeight: a.weight,
      targetWeight: effectiveTarget,
      delta: Math.abs(delta),
    });
  }

  // Sort by delta descending (biggest drift first)
  suggestions.sort((a, b) => b.delta - a.delta);
  return suggestions;
}
