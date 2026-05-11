/** Shared types used across multiple route files. */

export interface PriceResult {
  price: number | null
  currency: string
}

// Re-export from lib/benchmark.ts for use in routes
export type { BenchmarkPrice, PeriodReturn } from "./benchmark.ts"

// ── Alert Types ────────────────────────────────────────────────────────────────

export type AlertConditionType =
  | "price_below"
  | "price_above"
  | "pct_change_day"
  | "pct_change_week"
  | "signal_change"
  | "price_cross"

export interface AlertCondition {
  type: AlertConditionType
  threshold?: number
  direction?: "up" | "down"
}

export interface AlertRule {
  id: number
  name: string
  ticker: string | null
  condition: AlertCondition
  platform: string
  severity: "critical" | "warning" | "info"
  message: string | null
  channel: "telegram" | "email" | "webhook" | "none"
  enabled: boolean
  lastChecked: string | null
  lastTriggered: string | null
  createdAt: string
  updatedAt: string
}

export interface TriggeredAlert {
  alert: AlertRule
  currentPrice: number | null
  pctChange?: number
  message: string
}
