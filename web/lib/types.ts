// Mirrors service/schemas.py. Keep these in sync.
// (We could codegen from the OpenAPI schema later; manual for now.)

export type Trigger = {
  condition: string;
  action: string;
};

export type Brief = {
  decision: string;
  tldr: string;
  timeframe: string;
  position_size: string;
  entry_strategy: string;
  stop_loss: string;
  take_profit: string;
  triggers: Trigger[];
  key_risks: string[];
  benchmark_view: string;
};

export type RunSummary = {
  run_id: string;
  ticker: string;
  trade_date: string;
  provider?: string | null;
  deep_model?: string | null;
  quick_model?: string | null;
  debate_rounds?: number | null;
  risk_rounds?: number | null;
  status: string;
  decision?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  llm_calls: number;
  tool_calls: number;
  tokens_in: number;
  tokens_out: number;
  log_path?: string | null;
  error_message?: string | null;
};

export type RunDetail = RunSummary & {
  state: Record<string, any>;
  tool_trace: Array<Record<string, any>>;
};

export type RunEvent = {
  type: string;
  data: Record<string, any>;
};

export type Note = {
  id: number;
  title: string;
  body: string;
  ticker?: string | null;
  run_id?: string | null;
  tags?: string | null;
  created_at: string;
  updated_at: string;
};

export type ChatMessage = {
  id: number;
  run_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  model?: string | null;
};

export type ProviderKey = {
  provider: string;
  env_name: string;
  label: string;
  set_in_env: boolean;
  set_in_config: boolean;
};

export type Settings = {
  api_keys: ProviderKey[];
  defaults: Record<string, any>;
  config_path: string;
};

export type MemoryEntry = {
  raw: string;
  resolved: boolean;
};

export type MemoryResponse = {
  path: string;
  entries: MemoryEntry[];
  total: number;
  resolved_count: number;
  pending_count: number;
};

export type ChartPoint = {
  date: string;
  values: Record<string, number>;
};

export type ChartComparisonResponse = {
  ticker: string;
  trade_date: string;
  benchmarks: string[];
  points: ChartPoint[];
  realised_returns?: Array<Record<string, string>> | null;
};

export type ExportFile = {
  ext: "json" | "md" | "html" | "pdf";
  path: string;
  filename: string;
  size_bytes: number;
};

export type RunCreateRequest = {
  ticker: string;
  trade_date: string;
  llm_provider: string;
  deep_think_llm: string;
  quick_think_llm: string;
  max_debate_rounds: number;
  max_risk_discuss_rounds: number;
  data_vendors: Record<string, string>;
};

// ---- Watchlist + portfolio + streaming ---------------------------------

export type WatchlistEntry = {
  id: number;
  ticker: string;
  added_at: string;
  notes?: string | null;
};

export type Position = {
  id: number;
  ticker: string;
  shares: number;
  cost_basis_per_share: number;
  opened_at: string;
  closed_at?: string | null;
  closing_price?: number | null;
  account?: string | null;
  notes?: string | null;
};

export type PositionWithLive = Position & {
  cost: number;
  live_price: number | null;
  value: number | null;
  unrealized: number | null;
  unrealized_pct: number | null;
};

export type PortfolioSummary = {
  open_positions: PositionWithLive[];
  total_cost: number;
  total_value: number;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  realized_pnl: number;
  open_count: number;
  closed_count: number;
};

export type PriceTick = {
  type: "price";
  ticker: string;
  price: number;
  change: number | null;
  change_pct: number | null;
  volume: number | null;
  polled_at: number;
  history: Array<{ ts: number; price: number }>;
};

export type NewsItem = {
  ticker: string;
  title: string;
  summary?: string | null;
  publisher?: string | null;
  link?: string | null;
  published_at?: string | null;
};

// ---- Calendar ----------------------------------------------------------

export type CalendarEvent = {
  date: string;
  ticker?: string | null;
  kind: "earnings" | "dividend" | "run" | "ex_dividend";
  title: string;
  detail?: string | null;
  payload?: Record<string, any> | null;
};

// ---- Simulation --------------------------------------------------------

export type SimTrade = {
  ticker: string;
  shares: number;
  entry_price: number;
  hold_days: number;
};

export type SimRunRequest = {
  name?: string;
  base_run_id?: string;
  starting_capital: number;
  trades: SimTrade[];
  history_days?: number;
};

export type SimPoint = {
  day: number;
  portfolio: number;
  baseline_spy: number;
  portfolio_low: number;
  portfolio_high: number;
};

export type SimResult = {
  name: string;
  starting_capital: number;
  expected_final_value: number;
  expected_return_pct: number;
  baseline_final_value: number;
  baseline_return_pct: number;
  alpha_pct: number;
  horizon_days: number;
  points: SimPoint[];
  per_trade: Array<Record<string, any>>;
};

export type SimRow = {
  id: number;
  name?: string | null;
  base_run_id?: string | null;
  ticker?: string | null;
  created_at: string;
};

export type SimDetail = SimRow & {
  scenario: Record<string, any>;
  result: SimResult;
};
