import type { RebalanceSuggestion, RuleViolation } from "./governance.ts"

export interface DbAccount {
  id: string
  provider: string
  account_type: string
  name: string
  balance: number
  currency: string
  notes: string | null
}

export interface DbPosition {
  id: number
  ticker: string
  exchange: string
  platform: string
  account_id: string | null
  quantity: number
  avg_cost: number
  entry_date: string
  thesis: string | null
}

export interface PositionWithValue {
  id: number
  ticker: string
  exchange: string
  platform: string
  account_id: string | null
  quantity: number
  avg_cost: number
  entry_date: string
  thesis: string | null
  current_price_gbp: number | null
  current_value_gbp: number | null
  cost_value_gbp: number
  pnl_gbp: number | null
  pnl_pct: number | null
  currency: string
  account_type?: string
}

export interface DbSpreadBet {
  id: number
  account_id: string
  ticker: string
  direction: string
  stake_per_point: number
  entry_price: number
  entry_date: string
  stop_price: number | null
  target_price: number | null
  current_price: number | null
  pnl_gbp: number | null
  status: string
  notes: string | null
}

export interface SpreadBetWithPnl {
  id: number
  account_id: string
  ticker: string
  direction: string
  stake_per_point: number
  entry_price: number
  entry_date: string
  stop_price: number | null
  target_price: number | null
  current_price_gbp: number | null
  current_value_gbp: number | null
  pnl_gbp: number | null
  pnl_pct: number | null
  notional_gbp: number
  status: string
  notes: string | null
}

export interface DbWatchlistItem {
  id: number
  ticker: string
  exchange: string
  priority: string
  thesis: string | null
  added_date: string
  last_signal: string | null
}

export interface CashBalance {
  platform: string
  currency: string
  amount: number
  amount_gbp: number
}

export interface PlatformAllocation {
  platform: string
  positions: PositionWithValue[]
  cash_gbp: number
  position_value_gbp: number
  total_value_gbp: number
  weight_pct: number
  cash_pct: number
}

export interface AssetClassAllocation {
  assetClass: string
  value_gbp: number
  weight_pct: number
}

export interface AllocationBar {
  targets: { cash_reserve_pct: number; spreadbet_pct: number; deployed_pct: number }
  actual: { cash_pct: number; spreadbet_pct: number; deployed_pct: number }
  buckets: Array<{
    bucket: string
    label: string
    value_gbp: number
    actual_pct: number
    target_pct: number
    color: string
  }>
}

export interface CashBreakdown {
  total_cash_gbp: number
  cash_negative: boolean
  reserve_gbp: number
  reserve_pct: number
  spreadbet_allocation_gbp: number
  spreadbet_allocation_pct: number
  investable_gbp: number
  investable_pct: number
}

export interface AccountSummary {
  id: string
  provider: string
  account_type: string
  name: string
  balance_gbp: number
  deployed_gbp: number
  spreadbet_gbp: number
  total_value_gbp: number
  positions_count: number
  bets_count: number
  notes: string | null
}

export interface PortfolioIntel {
  total_value_gbp: number
  cash_gbp: number
  cash_pct: number
  cash_pct_raw: number
  cash_negative: boolean
  position_value_gbp: number
  positions_count: number
  fx_rates: { GBPEUR: number; GBPUSD: number }
  allocation_bar: AllocationBar
  cash_breakdown: CashBreakdown
  accounts: AccountSummary[]
  platforms: PlatformAllocation[]
  asset_classes: AssetClassAllocation[]
  spreadbets: SpreadBetWithPnl[]
  research_queue: DbWatchlistItem[]
  governance: {
    violations: RuleViolation[]
    suggestions: RebalanceSuggestion[]
  }
}

export const ALLOCATION_TARGETS = {
  cash_reserve_pct: 10,
  spreadbet_pct: 20,
  deployed_pct: 70,
}
