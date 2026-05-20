/**
 * Screening engine — pure function that evaluates candidates against
 * screening rules and enrichment data.
 *
 * No side effects, no I/O. Takes rules + enrichment + price data,
 * returns matched candidates with match reasons.
 */

import type { EnrichmentRow, ScreenCondition, ScreeningRule } from "./screening-data.ts"

// ── Match Result ─────────────────────────────────────────────────────────────

export interface MatchResult {
  ticker: string
  exchange: string
  stage: string
  priority: string
  matched_rules: string[]
  match_reasons: string[]
  priority_score: number
  enrichment: EnrichmentRow | null
}

// ── Field Extraction ─────────────────────────────────────────────────────────

export type CandidateData = {
  ticker: string
  exchange: string
  stage: string
  priority: string
  enrichment: EnrichmentRow | null
  current_price?: number
  sentiment_avg?: number | null
}

function getFieldValue(
  data: CandidateData,
  field: ScreenCondition["field"],
): number | string | null {
  if (!data.enrichment) return null

  switch (field) {
    case "pe_forward":
      return data.enrichment.pe_forward
    case "eps_growth_1y":
      return data.enrichment.eps_growth_1y
    case "operating_margin":
      return data.enrichment.operating_margin
    case "beta_1y":
      return data.enrichment.beta_1y
    case "price_to_sales":
      return data.enrichment.price_to_sales
    case "sector":
      return data.enrichment.sector
    case "region":
      return data.enrichment.region
    case "price":
      return data.current_price ?? null
    case "sentiment_score":
      return data.sentiment_avg ?? null
    // Pattern features (R08)
    case "trend_strength":
      return data.enrichment.trend_strength
    case "trend_linearity":
      return data.enrichment.trend_linearity
    case "seasonality_strength":
      return data.enrichment.seasonality_strength
    case "seasonality_stability":
      return data.enrichment.seasonality_stability
    case "residual_acf1":
      return data.enrichment.residual_acf1
    case "spectral_entropy":
      return data.enrichment.spectral_entropy
    case "is_stationary":
      return data.enrichment.is_stationary
    default:
      return null
  }
}

// ── Condition Evaluation ─────────────────────────────────────────────────────

function evaluateCondition(condition: ScreenCondition, data: CandidateData): boolean {
  const value = getFieldValue(data, condition.field)

  // No enrichment data = condition can't be evaluated
  if (value === null) return false

  switch (condition.operator) {
    case "gt":
      return typeof value === "number" ? value > (condition.value as number) : false
    case "lt":
      return typeof value === "number" ? value < (condition.value as number) : false
    case "gte":
      return typeof value === "number" ? value >= (condition.value as number) : false
    case "lte":
      return typeof value === "number" ? value <= (condition.value as number) : false
    case "eq":
      return value === condition.value
    case "in":
      return Array.isArray(condition.value) ? condition.value.includes(value as string) : false
    case "bottom_pct": {
      // Distribution-based operators require knowing the full field distribution.
      // TODO(td-??): implement bottom_pct — requires pre-computing percentile buckets
      // biome-ignore lint/suspicious/noConsole: intentional warning for unsupported operator
      console.warn(`[screening-engine] bottom_pct not implemented (field=${condition.field})`)
      return false
    }
    case "top_pct": {
      // TODO(td-??): implement top_pct — requires pre-computing percentile buckets
      // biome-ignore lint/suspicious/noConsole: intentional warning for unsupported operator
      console.warn(`[screening-engine] top_pct not implemented (field=${condition.field})`)
      return false
    }
    default:
      return false
  }
}

// ── Reason Formatting ─────────────────────────────────────────────────────────

function formatReason(
  rule: ScreeningRule,
  condition: ScreenCondition,
  data: CandidateData,
): string {
  const value = getFieldValue(data, condition.field)
  const op = condition.operator
  const target = condition.value

  const fieldLabel = condition.field.replace(/_/g, " ")
  const opLabel =
    {
      gt: ">",
      lt: "<",
      gte: "≥",
      lte: "≤",
      eq: "=",
      in: "∈",
      bottom_pct: "bottom%",
      top_pct: "top%",
    }[op] ?? op

  const valueStr = typeof target === "number" ? target.toFixed(2) : String(target)
  const actualStr = typeof value === "number" ? value.toFixed(2) : String(value ?? "—")

  return `${rule.name}: ${fieldLabel} ${opLabel} ${valueStr} (actual: ${actualStr})`
}

// ── Main Screening Function ───────────────────────────────────────────────────

export interface ScreenInput {
  candidates: CandidateData[]
  rules: ScreeningRule[]
  stageFilter?: string[] // e.g. ["researching", "analyzed", "candidate"]
}

export interface ScreenResult {
  matches: MatchResult[]
  total_candidates: number
  matched_count: number
  rules_evaluated: number
}

export function screenCandidates(input: ScreenInput): ScreenResult {
  const { candidates, rules, stageFilter } = input

  // Filter rules to enabled only, sorted by priority
  const activeRules = rules.filter((r) => r.enabled).sort((a, b) => b.priority - a.priority)

  // Optionally filter by stage
  const filtered = stageFilter
    ? candidates.filter((c) => stageFilter.includes(c.stage))
    : candidates

  const matches: MatchResult[] = []

  for (const candidate of filtered) {
    const matchedRules: string[] = []
    const matchReasons: string[] = []

    for (const rule of activeRules) {
      const allConditionsMet = rule.conditions.every((cond) => evaluateCondition(cond, candidate))

      if (allConditionsMet) {
        matchedRules.push(rule.name)
        // Add reason for each condition (already verified all pass via allConditionsMet)
        for (const cond of rule.conditions) {
          matchReasons.push(formatReason(rule, cond, candidate))
        }
      }
    }

    if (matchedRules.length > 0) {
      // Score = sum of matched rule priorities
      const score = activeRules
        .filter((r) => matchedRules.includes(r.name))
        .reduce((sum, r) => sum + r.priority + 1, 0)

      matches.push({
        ticker: candidate.ticker,
        exchange: candidate.exchange,
        stage: candidate.stage,
        priority: candidate.priority,
        matched_rules: matchedRules,
        match_reasons: matchReasons,
        priority_score: score,
        enrichment: candidate.enrichment,
      })
    }
  }

  // Sort by score descending
  matches.sort((a, b) => b.priority_score - a.priority_score)

  return {
    matches,
    total_candidates: candidates.length,
    matched_count: matches.length,
    rules_evaluated: activeRules.length,
  }
}

// ── Shock Stock Detection ─────────────────────────────────────────────────────

export interface ShockStockInput {
  candidates: CandidateData[]
  priceDropPct: number // e.g. 10 = drop >10%
  minMarginPct: number // e.g. 20 = operating margin >20%
  maxPSRatio: number // e.g. 5 = P/S in bottom percentile
}

export function detectShockStocks(input: ShockStockInput): MatchResult[] {
  const { candidates, priceDropPct, minMarginPct, maxPSRatio } = input

  return candidates
    .filter((c) => {
      if (!c.enrichment) return false

      const margin = c.enrichment.operating_margin
      const ps = c.enrichment.price_to_sales
      const priceDrop =
        (c as CandidateData & { price_drop_pct?: number }).price_drop_pct ?? priceDropPct

      // Must have fundamentals
      if (margin == null || ps == null) return false

      return priceDrop >= priceDropPct && margin >= minMarginPct && ps <= maxPSRatio
    })
    .map((c) => ({
      ticker: c.ticker,
      exchange: c.exchange,
      stage: c.stage,
      priority: c.priority,
      matched_rules: ["shock_stock"],
      match_reasons: [
        `Fundamentals strong (margin: ${c.enrichment?.operating_margin?.toFixed(1)}%, P/S: ${c.enrichment?.price_to_sales?.toFixed(2)})`,
      ],
      priority_score: 10,
      enrichment: c.enrichment,
    }))
}
