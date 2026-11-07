// API contract of web/api. Times are ISO 8601 UTC strings; unknown values are null.

export interface WatchlistEntry {
  research: string
  swap: string
  spot: string
}

export interface Account {
  id: string
  kind: string
  capital: number
  validation_start: string | null
  halted: boolean
  watchlist: WatchlistEntry[]
}

export interface Perf {
  cumulative: number
  annualized: number | null
  sharpe: number | null
  max_drawdown: number
  calmar: number | null
}

export interface Performance {
  strategy: Perf | null
  equal_weight: Perf | null
  btc: Perf | null
}

export interface LlmUsage {
  trade_date: string
  today: number
  month: number
  cap: number | null
  learned_days: number
  learning_days: number
  unknown: boolean
}

export interface Position {
  inst: string
  coin: string | null
  qty: number
  entry: number
  stop: number | null
  price: number
  notional: number
  unrealized: number
  stop_distance: number | null
}

export type CoinState = 'done' | 'failed' | 'pending'

export interface LatestFill {
  qty: number
  price: number
}

export interface LatestCoin {
  coin: string
  state: CoinState
  rating: string | null
  error: string | null
  cost_usd: number | null
  fills: LatestFill[]
}

export interface Latest {
  trade_date: string
  executed: boolean
  coins: LatestCoin[]
}

export interface Overview {
  equity: number
  cash: number
  peak: number
  drawdown: number
  halted: boolean
  processed_to: string
  validation_start: string | null
  days: number
  performance: Performance
  llm: LlmUsage
  positions: Position[]
  latest: Latest
}

export interface EquityPoint {
  ts: string
  strategy: number
  strategy_net: number
  equal_weight: number | null
  btc: number | null
}

export interface Equity {
  points: EquityPoint[]
  live: { ts: string; equity: number }
}

export type FillReason = 'trade' | 'stop' | 'kill'

export interface Fill {
  ts: string
  inst: string
  coin: string | null
  qty: number
  price: number
  fee: number
  reason: FillReason
  trade_date: string | null
}

export interface Funding {
  ts: string
  inst: string
  coin: string
  rate: number
  amount: number
}

export interface LedgerEvent {
  ts: string
  kind: string
  text: string
}

export interface Attempt {
  trade_date: string
  coin: string
  ts: string
  rating: string | null
  error: string | null
  tokens_in: number
  tokens_out: number
  cost_usd: number | null
}

export interface RatingStats {
  count: number
  hit_rate: number | null
  mean_alpha: number
}

export interface Accuracy {
  resolved: number
  pending: number
  unscored: number
  holding: string
  benchmark: string
  by_rating: Record<string, RatingStats>
}

export interface ResearchSummary {
  coin: string
  trade_date: string
  rating: string | null
  cost_usd: number | null
  tokens_in: number
  tokens_out: number
}

export interface InvestmentDebateState {
  bull_history: string
  bear_history: string
  history: string
  current_response: string
}

export interface RiskDebateState {
  aggressive_history: string
  conservative_history: string
  neutral_history: string
  history: string
}

export interface RunSettings {
  version: string | number
  llm_provider: string
  deep_think_llm: string
  quick_think_llm: string
  analysts: string[]
  max_debate_rounds: number
  max_risk_discuss_rounds: number
  output_language: string
  [extra: string]: unknown
}

export interface ResearchDetail {
  company_of_interest: string
  trade_date: string
  market_report: string
  sentiment_report: string
  news_report: string
  fundamentals_report: string
  investment_debate_state: InvestmentDebateState
  investment_plan: string
  trader_investment_plan: string
  risk_debate_state: RiskDebateState
  final_trade_decision: string
  final_rating: string | null
  run_settings: RunSettings
}

/** GET /api/strategy: the constants the trader runs on, quoted by the guide and the `?` marks. */
export interface Strategy {
  risk_per_unit: number
  stop_atr_mult: number
  atr_days: number
  rating_weights: Record<string, number>
  max_coin_exposure: number
  max_gross_exposure: number
  rebalance_threshold: number
  taker_fee: number
  slippage: number
  kill_drawdown: number
  max_attempts: number
  retry_wait_seconds: number
  budget_learning_days: number
  budget_headroom: number
  analysts: string[]
  benchmark: string
  watchlist: string[]
  holding_period_days: number
  deep_model: string
  quick_model: string
}

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** GET a JSON document from the same-origin API; throws ApiError on non-2xx. */
export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, { signal, headers: { Accept: 'application/json' } })
  if (!res.ok) {
    throw new ApiError(res.status, `HTTP ${res.status} ${res.statusText}`.trim())
  }
  return (await res.json()) as T
}

export const accountPath = (id: string, tail: string): string =>
  `/api/accounts/${encodeURIComponent(id)}/${tail}`

export const researchPath = (coin: string, tradeDate: string): string =>
  `/api/research/${encodeURIComponent(coin)}/${encodeURIComponent(tradeDate)}`
