// API contract of web/api. Times are ISO 8601 UTC strings; unknown values are null.

export interface WatchlistEntry {
  research: string
  swap: string
  spot: string
}

export interface Account {
  id: string
  kind: string
  /** Null with `validation_start` and `halted` while the account has no ledger yet. */
  capital: number | null
  validation_start: string | null
  halted: boolean | null
  watchlist: WatchlistEntry[]
  /** The hourly-signal account (ADR 0006): no rating settlement, no monthly budget cap. */
  intraday: boolean
  /** The account that executes on the exchange (ADR 0008), following the intraday signals: no LLM spend of its own. */
  demo: boolean
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
  /** The priced fields are null while OKX gives no quote (see `MarketStatus`). */
  price: number | null
  notional: number | null
  unrealized: number | null
  /** Return on the position's value at entry, the side's sign applied. */
  unrealized_pct: number | null
  stop_distance: number | null
}

/** The day's PnL against the midnight snapshot `since` (null before the first one). */
export interface Today {
  since: string | null
  /** Null without the snapshot or without the quotes that price the equity. */
  pnl: number | null
  pct: number | null
}

/** Account sums; the marked ones are null while a position has no quote. */
export interface Totals {
  unrealized: number | null
  notional: number | null
  leverage: number | null
  /** Cash less capital: what closed trades, fees and funding have added since the account opened. */
  realized: number
  pnl: number | null
  pnl_pct: number | null
}

/** Whether the API's last request to OKX succeeded; `since` is when the failures began. */
export interface MarketStatus {
  ok: boolean
  error: string | null
  since: string | null
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
  /** Null with `drawdown` while OKX gives no quote for a position (see `market`). */
  equity: number | null
  cash: number
  capital: number
  peak: number
  drawdown: number | null
  halted: boolean
  processed_to: string
  validation_start: string | null
  days: number
  today: Today
  totals: Totals
  performance: Performance
  /** Null for the demo account, which makes no LLM calls of its own. */
  llm: LlmUsage | null
  positions: Position[]
  /** Null for the intraday account, which has signals instead of daily research, and for the demo account. */
  latest: Latest | null
  market: MarketStatus
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
  /** `equity` is null while OKX gives no quote for a position (see `market`). */
  live: { ts: string; equity: number | null }
  market: MarketStatus
}

/** One UTC day of the validation period: midnight snapshot to the next, the last one to the live equity. */
export interface DailyRow {
  /** The UTC date the day starts on. */
  date: string
  start_ts: string
  open: number
  /** Null for the day in progress while OKX gives no quote; `pnl` and `pct` with it. */
  close: number | null
  pnl: number | null
  pct: number | null
  fills: number
  funding: number
  llm_cost: number
  /** The day in progress: `close` is the live equity. */
  partial: boolean
}

export interface MonthRow {
  /** "2026-11" */
  month: string
  open: number
  close: number | null
  pnl: number | null
  pct: number | null
  days: number
  partial: boolean
}

export interface Daily {
  /** Newest first. */
  days: DailyRow[]
  /** Newest first, over every day regardless of the page. */
  months: MonthRow[]
  market: MarketStatus
}

/** `manual` only on the demo account: a fill on the exchange the program did not make (ADR 0008). */
export type FillReason = 'trade' | 'stop' | 'kill' | 'manual'

export interface Fill {
  ts: string
  inst: string
  coin: string | null
  qty: number
  price: number
  fee: number
  reason: FillReason
  trade_date: string | null
  /** PnL this fill realized against the average entry, before its fee; 0 when it opens or adds. */
  realized: number
  /** `realized` less `fee`: what the fill added to the cash. */
  realized_net: number
  /** The signed position the fill left; 0 when it closed. */
  position_after: number
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

export type SignalName = 'Long' | 'Short' | 'Flat'

/** One hourly LLM signal of the intraday account; `signal` is null when the call failed or gave no usable signal. */
export interface Signal {
  ts: string
  coin: string
  signal: SignalName | null
  /** 1 (weak) to 3 (strong); null when unknown. */
  conviction: number | null
  reason: string
  error: string | null
  tokens_in: number
  tokens_out: number
  cost_usd: number | null
  /** Demo account only: what it did about this signal in its hour; null before the account existed. */
  followed?: Followed | null
}

/** The demo account's hourly outcome for a signal it follows (ADR 0008). */
export type Followed = 'executed' | 'no_change' | 'skipped' | 'blocked' | 'paused' | 'failed' | 'pending'

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

/** LLM price in USD per million tokens: [input, output]. */
export type Price = [number, number]

/** The two model tiers of the research graph. */
export type Tier = 'deep' | 'quick'

/** One tier's model; the price is null when neither the settings nor the price table have one. */
export interface TierSelection {
  model: string
  provider: string
  price: Price | null
}

/** A tier in effect, with the price table's remark on its price. */
export interface CurrentTier extends TierSelection {
  /** E.g. "促销价至 2026-11-30" or "提示词≤100K 档"; null when the table has none. */
  price_note: string | null
}

export interface CurrentModels {
  deep: CurrentTier
  quick: CurrentTier
  /** Where the selection comes from: `.env`, or the settings.json the dashboard writes. */
  source: 'env' | 'settings'
  /** Last write of settings.json. */
  updated_at: string | null
  /** Per account id: whether its latest run used this selection. Accounts that never ran are absent. */
  applied: Record<string, boolean>
}

export interface ModelInfo {
  id: string
  label: string
  modes: Tier[]
  price: Price | null
  /** URL of the official price page. */
  price_source: string | null
  price_as_of: string | null
  /** The last day the rate holds (a promotion's end), when the price page says; else null. */
  price_until: string | null
  /** The price table's remark on the price, e.g. the tier it is or when a promotion ends. */
  price_note: string | null
  /** Listed by the upstream catalog; false for a configured model the catalog lacks. */
  in_catalog: boolean
}

export interface ProviderInfo {
  id: string
  name: string
  /** Whether the server has this provider's API key. */
  has_key: boolean
  /** Environment variable of the key, e.g. ANTHROPIC_API_KEY. */
  key_env: string | null
  models: ModelInfo[]
}

export interface ModelChange {
  at: string
  deep: string
  quick: string
  note: string
}

/** GET /api/models, and the reply of POST /api/settings/llm. */
export interface ModelsResponse {
  current: CurrentModels
  providers: ProviderInfo[]
  /** Newest first, at most 20. */
  history: ModelChange[]
  /** Whether POST /api/settings/llm wants the server's TRADER_WEB_TOKEN as a Bearer token. */
  write_protected: boolean
}

/** A tier as saved: the price is required. */
export interface PricedSelection extends TierSelection {
  price: Price
}

/** POST /api/settings/llm. */
export interface LlmSettingsRequest {
  deep: PricedSelection
  quick: PricedSelection
  confirm: true
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

/** Where the write token the user typed is kept: this tab only, gone when it closes. */
export const WRITE_TOKEN_KEY = 'trader.web_token'

export function writeToken(): string {
  try {
    return sessionStorage.getItem(WRITE_TOKEN_KEY) ?? ''
  } catch {
    return ''
  }
}

export function rememberWriteToken(token: string): void {
  try {
    if (token) sessionStorage.setItem(WRITE_TOKEN_KEY, token)
    else sessionStorage.removeItem(WRITE_TOKEN_KEY)
  } catch {
    // storage unavailable (private mode, quota): the token lives in the form only
  }
}

/**
 * POST a JSON body to the same-origin API, with the write token (when one is kept) as a
 * Bearer token; throws ApiError carrying the server's `detail` on non-2xx.
 */
export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const token = writeToken()
  const res = await fetch(path, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const detail = await res.json().then(detailOf, () => null)
    throw new ApiError(res.status, detail ?? `HTTP ${res.status} ${res.statusText}`.trim())
  }
  return (await res.json()) as T
}

/** FastAPI's error text: `detail` is a string, or for a 422 a list of `{ loc, msg }`. */
function detailOf(body: unknown): string | null {
  const detail = typeof body === 'object' && body !== null && 'detail' in body ? body.detail : null
  if (typeof detail === 'string') return detail
  if (!Array.isArray(detail)) return null
  const lines = detail.flatMap((d: unknown) => {
    if (typeof d !== 'object' || d === null || !('msg' in d) || typeof d.msg !== 'string') return []
    const loc = 'loc' in d && Array.isArray(d.loc) ? d.loc.filter((p: unknown) => p !== 'body').join('.') : ''
    return [loc ? `${loc}: ${d.msg}` : d.msg]
  })
  return lines.length > 0 ? lines.join('; ') : null
}

export const accountPath = (id: string, tail: string): string =>
  `/api/accounts/${encodeURIComponent(id)}/${tail}`

export const researchPath = (coin: string, tradeDate: string): string =>
  `/api/research/${encodeURIComponent(coin)}/${encodeURIComponent(tradeDate)}`

/** One position as the exchange reported it at the demo account's last reconciliation (ADR 0008). */
export interface ExchangePosition {
  inst: string
  coin: string | null
  /** Signed contracts: positive long, negative short. */
  contracts: number | null
  avg_price: number | null
  unrealized: number | null
  leverage: number | null
  margin_mode: string | null
  liquidation_price: number | null
  /** The stop the ledger keeps for it; the exchange-side order is in `stops`. */
  stop: number | null
}

/** One conditional stop order pending on the exchange. */
export interface PendingStop {
  inst: string
  coin: string | null
  side: 'buy' | 'sell' | null
  contracts: number | null
  trigger: number | null
  client_id: string | null
}

/** Why the account is paused, and since when (ADR 0010). */
export interface PauseReason {
  text: string
  since: string | null
}

/** The demo account's last reconciliation with the exchange; nothing here is live, `synced_at` says how old it is. */
export interface Execution {
  synced_at: string | null
  equity: number | null
  cash: number | null
  halted: boolean | null
  /** No new orders, positions and stops left as they are, until `python -m trader demo resume`. */
  paused: boolean
  pause_reasons: PauseReason[]
  /** The intraday hour the demo last followed. */
  decided_hour: string | null
  problems: string[]
  positions: ExchangePosition[]
  stops: PendingStop[]
}

export interface MirrorSide {
  qty: number
  entry: number
  stop: number | null
}

export interface MirrorPosition {
  inst: string
  coin: string
  demo: MirrorSide | null
  intraday: MirrorSide | null
  same_side: boolean
}

export interface MirrorFill {
  ts: string
  qty: number
  price: number
  fee: number
}

/** One demo trade beside the intraday fill of the same hour and contract. */
export interface MirrorTrade {
  hour: string
  inst: string
  coin: string | null
  demo: MirrorFill
  intraday: MirrorFill | null
  /** Basis points, positive when the demo did worse than the intraday price; null without a match. */
  slippage_bps: number | null
}

export interface MirrorPoint {
  ts: string
  demo: number | null
  intraday: number | null
}

/** The demo account beside the intraday account it follows. */
export interface Mirror {
  positions: MirrorPosition[]
  trades: MirrorTrade[]
  equity: MirrorPoint[]
  summary: {
    trades: number
    matched: number
    avg_slippage_bps: number | null
    demo_return: number | null
    intraday_return: number | null
  }
}
