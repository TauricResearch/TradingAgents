export const base = "";

/**
 * Thrown by the api helpers on non-2xx responses. ``body`` is the parsed
 * JSON error payload (typically ``{ detail: { error, ... } }`` from
 * FastAPI) so callers can render a specific message instead of a
 * generic status code.
 */
export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

async function readJsonOrNull(r: Response): Promise<unknown> {
  try {
    return await r.json();
  } catch {
    return null;
  }
}

export interface WatchlistRow {
  ticker: string;
  company_name: string;
  exchange: string;
  added_at: string | null;
  last_decision: string | null;
  last_decision_at: string | null;
  sort_order: number | null;
  group: string | null;
  source?: string;
}

export type RunStatus =
  | "queued"
  | "running"
  | "done"
  | "failed"
  | "cancelled"
  | "superseded";

export interface ConfigModels {
  llm_provider: string | null;
  deep_think_model: string | null;
  quick_think_model: string | null;
}

export async function fetchConfigModels(): Promise<ConfigModels> {
  const r = await fetch(`${base}/api/config/models`);
  if (!r.ok) throw new ApiError(`config ${r.status}`, r.status, await readJsonOrNull(r));
  return r.json();
}

export interface RunRow {
  id: string;
  slug: string;
  ticker: string;
  started_at: string | null;
  finished_at: string | null;
  status: RunStatus;
  cancel_requested: boolean;
  decision_action: string | null;
  decision_target: number | null;
  decision_rationale: string | null;
  decision_confidence: number | null;
  // Run-metadata enrichment: all nullable for backward compatibility
  // with runs persisted before the schema change.
  llm_provider: string | null;
  deep_think_model: string | null;
  quick_think_model: string | null;
  start_price: number | null;
  start_price_at: string | null;
  total_duration_s: number | null;
  // Derived: only set when status === "running". null for terminal runs.
  elapsed_s: number | null;
}

export interface LlmCallRow {
  id: string;
  run_id: string;
  ticker: string;
  node_name: string;
  started_at: string | null;
  model: string;
  prompt_text: string;
  response_text: string;
  tool_calls: unknown[];
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  duration_ms: number;
}

export interface RunDetail extends RunRow {
  events: Array<{ id: string; type: string; ts: string | null; data: unknown }>;
  llm_calls: LlmCallRow[];
  stages: unknown[];
}

export async function fetchWatchlist(): Promise<WatchlistRow[]> {
  const r = await fetch(`${base}/api/watchlist`);
  if (!r.ok) throw new Error(`watchlist ${r.status}`);
  return r.json();
}

export async function addToWatchlist(ticker: string, company_name: string, exchange: string): Promise<void> {
  const r = await fetch(`${base}/api/watchlist`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ticker, company_name, exchange }),
  });
  if (!r.ok) {
    throw new ApiError(`add ${r.status}`, r.status, await readJsonOrNull(r));
  }
}

export async function removeFromWatchlist(ticker: string): Promise<void> {
  const r = await fetch(`${base}/api/watchlist/${encodeURIComponent(ticker)}`, { method: "DELETE" });
  if (!r.ok) {
    throw new ApiError(`remove ${r.status}`, r.status, await readJsonOrNull(r));
  }
}

export async function updateWatchlistItem(ticker: string, data: { group?: string | null }): Promise<WatchlistRow> {
  const r = await fetch(`${base}/api/watchlist/${encodeURIComponent(ticker)}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!r.ok) {
    throw new ApiError(`update ${r.status}`, r.status, await readJsonOrNull(r));
  }
  return r.json();
}

export async function reorderWatchlist(tickers: string[]): Promise<WatchlistRow[]> {
  const r = await fetch(`${base}/api/watchlist/reorder`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ tickers }),
  });
  if (!r.ok) {
    throw new ApiError(`reorder ${r.status}`, r.status, await readJsonOrNull(r));
  }
  return r.json();
}

export async function fetchPrices(): Promise<Record<string, unknown>> {
  const r = await fetch(`${base}/api/prices`);
  if (!r.ok) {
    throw new ApiError(`prices ${r.status}`, r.status, await readJsonOrNull(r));
  }
  return r.json();
}

// ---- Market indicators ----

export type IndicatorKind =
  | "vix"
  | "fear_greed"
  | "red_days"
  | "s5fi"
  | "green_streak"
  | "price_vs_moving_averages";

export interface IndicatorDefinition {
  id: string;
  kind: IndicatorKind;
  name: string;
  description: string;
  threshold: number;
  comparator: "above" | "below" | "at_least" | "within";
  unit: string;
  enabled: boolean;
  source: "builtin" | "custom";
}

export interface IndicatorResult {
  triggered: boolean;
  value: unknown;
  threshold: number;
  message: string;
  checked_at: string;
}

export interface IndicatorCheck {
  indicator: IndicatorDefinition;
  result: IndicatorResult | null;
}

export async function fetchIndicators(): Promise<{ indicators: IndicatorDefinition[] }> {
  const r = await fetch(`${base}/api/indicators`);
  if (!r.ok) throw new ApiError(`indicators ${r.status}`, r.status, await readJsonOrNull(r));
  return r.json();
}

export async function addIndicator(body: {
  kind: IndicatorKind;
  name?: string;
  threshold?: number;
  description?: string;
}): Promise<IndicatorDefinition> {
  const r = await fetch(`${base}/api/indicators`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new ApiError(`add-indicator ${r.status}`, r.status, await readJsonOrNull(r));
  return r.json();
}

export async function removeIndicator(id: string): Promise<void> {
  const r = await fetch(`${base}/api/indicators/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!r.ok) throw new ApiError(`remove-indicator ${r.status}`, r.status, await readJsonOrNull(r));
}

export async function updateIndicator(
  id: string,
  body: Partial<{ threshold: number; enabled: boolean }>
): Promise<IndicatorDefinition> {
  const r = await fetch(`${base}/api/indicators/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new ApiError(`update-indicator ${r.status}`, r.status, await readJsonOrNull(r));
  return r.json();
}

export async function resetIndicator(id: string): Promise<unknown> {
  const r = await fetch(`${base}/api/indicators/${encodeURIComponent(id)}/reset`, {
    method: "POST",
    headers: { "content-type": "application/json" },
  });
  if (!r.ok) throw new ApiError(`reset-indicator ${r.status}`, r.status, await readJsonOrNull(r));
  return r.json();
}

export async function resetIndicators(): Promise<{ indicators: IndicatorDefinition[] }> {
  const r = await fetch(`${base}/api/indicators/reset`, { method: "POST" });
  if (!r.ok) throw new ApiError(`reset-indicators ${r.status}`, r.status, await readJsonOrNull(r));
  return r.json();
}

export async function checkIndicators(): Promise<{ checks: IndicatorCheck[] }> {
  const r = await fetch(`${base}/api/indicators/check`, { method: "POST" });
  if (!r.ok) throw new ApiError(`check-indicators ${r.status}`, r.status, await readJsonOrNull(r));
  return r.json();
}

export async function fetchSchedule(): Promise<{ interval_ms: number }> {
  const r = await fetch(`${base}/api/indicators/schedule`);
  if (!r.ok) throw new ApiError(`fetch-schedule ${r.status}`, r.status, await readJsonOrNull(r));
  return r.json();
}

export async function updateSchedule(interval_ms: number): Promise<{ interval_ms: number }> {
  const r = await fetch(`${base}/api/indicators/schedule`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ interval_ms }),
  });
  if (!r.ok) throw new ApiError(`update-schedule ${r.status}`, r.status, await readJsonOrNull(r));
  return r.json();
}

// ---- Telegram notifier config ----

export interface NotifierConfig {
  enabled: boolean;
  bot_token: string | null;
  chat_id: string | null;
}

export async function fetchNotifierConfig(): Promise<NotifierConfig> {
  const r = await fetch(`${base}/api/notifier/config`);
  if (!r.ok) throw new ApiError(`notifier config ${r.status}`, r.status, await readJsonOrNull(r));
  return r.json();
}

export async function updateNotifierConfig(
  body: Partial<{ enabled: boolean; bot_token: string | null; chat_id: string | null }>,
): Promise<NotifierConfig> {
  const r = await fetch(`${base}/api/notifier/config`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new ApiError(`notifier config ${r.status}`, r.status, await readJsonOrNull(r));
  return r.json();
}

export async function testNotifier(): Promise<{ status: string; chat_id: string }> {
  const r = await fetch(`${base}/api/notifier/test`, { method: "POST" });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({ detail: r.statusText }));
    throw new ApiError(`notifier test ${r.status}`, r.status, detail);
  }
  return r.json();
}

export async function startRun(ticker: string, force: boolean = false): Promise<{ run_id: string }> {
  const r = await fetch(`${base}/api/runs`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ticker, force }),
  });
  if (!r.ok) {
    throw new ApiError(`start ${r.status}`, r.status, await readJsonOrNull(r));
  }
  return r.json();
}

export async function cancelRun(runId: string): Promise<void> {
  const r = await fetch(`${base}/api/runs/${runId}/cancel`, { method: "POST" });
  if (!r.ok) {
    throw new ApiError(`cancel ${r.status}`, r.status, await readJsonOrNull(r));
  }
}

export async function resumeRun(runId: string): Promise<{ run_id: string; previous_run_id: string }> {
  const r = await fetch(`${base}/api/runs/${encodeURIComponent(runId)}/resume`, { method: "POST" });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({ detail: r.statusText }));
    throw new ApiError(`resume ${r.status}`, r.status, detail);
  }
  return r.json();
}

export async function deleteRun(runId: string): Promise<void> {
  const r = await fetch(`${base}/api/runs/${runId}`, { method: "DELETE" });
  if (!r.ok) {
    throw new ApiError(`delete ${r.status}`, r.status, await readJsonOrNull(r));
  }
}

export interface DeleteBulkResponse {
  results: Array<{ run_id: string; deleted: boolean; error?: string; ticker?: string }>;
  total: number;
  deleted: number;
}

export async function deleteRuns(runIds: string[]): Promise<DeleteBulkResponse> {
  const r = await fetch(`${base}/api/runs/delete-bulk`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_ids: runIds }),
  });
  if (!r.ok) {
    throw new ApiError(`delete-bulk ${r.status}`, r.status, await readJsonOrNull(r));
  }
  return r.json();
}

export async function fetchRunDetail(runId: string): Promise<RunDetail> {
  const r = await fetch(`${base}/api/runs/${runId}`);
  if (!r.ok) {
    throw new ApiError(`run ${r.status}`, r.status, await readJsonOrNull(r));
  }
  return r.json();
}

export async function fetchTickerRuns(ticker: string): Promise<RunRow[]> {
  const r = await fetch(`${base}/api/tickers/${encodeURIComponent(ticker)}/runs`);
  if (!r.ok) {
    throw new ApiError(`ticker-runs ${r.status}`, r.status, await readJsonOrNull(r));
  }
  return r.json();
}

// ---- Historical analysis chart ----

export type Bar = {
  t: string; // ISO timestamp with Z suffix
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
};

export type HistoryRange = "1d" | "5d" | "1mo" | "3mo" | "6mo" | "1y" | "all" | "auto";

export interface HistoryResponse {
  ticker: string;
  range: HistoryRange;
  range_start: string;
  range_end: string;
  resolution: "1m" | "1h" | "1d";
  bars: Bar[];
  runs: RunDetail[];
}

// --- Background past runs ---

export type BackgroundEvery = "1d" | "1w" | "2w" | "1mo";
export type BackgroundStatus = "running" | "paused" | "done" | "cancelled" | "error";

export interface StartBackgroundRunRequest {
  ticker: string;
  date_from: string;
  date_to: string;
  every: BackgroundEvery;
  parallel: number;
}

export interface BackgroundRunState {
  job_id: string;
  ticker: string;
  date_from: string;
  date_to: string;
  every: BackgroundEvery;
  parallel: number;
  total: number;
  current_index: number;
  avg_duration_s: number;
  eta_s: number;
  started_at: string;
  finished_at: string | null;
  status: BackgroundStatus;
  durations_s: number[];
}

export interface BackgroundRunListResponse {
  jobs: BackgroundRunState[];
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function startBackgroundRun(body: StartBackgroundRunRequest): Promise<{ job_id: string }> {
  return postJson("/api/background-runs", body);
}

export function getBackgroundRuns(): Promise<BackgroundRunListResponse> {
  return getJson("/api/background-runs");
}

export function getBackgroundRun(jobId: string): Promise<BackgroundRunState> {
  return getJson(`/api/background-runs/${encodeURIComponent(jobId)}`);
}

export function cancelBackgroundRun(jobId: string): Promise<{ status: string }> {
  return postJson(`/api/background-runs/${encodeURIComponent(jobId)}/cancel`, {});
}

export function pauseBackgroundRun(jobId: string): Promise<{ status: string }> {
  return postJson(`/api/background-runs/${encodeURIComponent(jobId)}/pause`, {});
}

export function resumeBackgroundRun(jobId: string): Promise<{ status: string }> {
  return postJson(`/api/background-runs/${encodeURIComponent(jobId)}/resume`, {});
}

export function deleteBackgroundRun(jobId: string): Promise<{ status: string }> {
  return fetch(`/api/background-runs/${encodeURIComponent(jobId)}`, { method: "DELETE" }).then((r) => {
    if (!r.ok) throw new Error(`delete background-run ${r.status}`);
    return r.json();
  });
}

// ---- App Configuration (env-based) ----

export interface AppConfig {
  TRADINGAGENTS_LLM_PROVIDER: string;
  TRADINGAGENTS_DEEP_THINK_LLM: string;
  TRADINGAGENTS_QUICK_THINK_LLM: string;
  TRADINGAGENTS_LLM_BACKEND_URL: string;
  TRADINGAGENTS_OUTPUT_LANGUAGE: string;
  TRADINGAGENTS_MAX_DEBATE_ROUNDS: string;
  TRADINGAGENTS_MAX_RISK_ROUNDS: string;
  TRADINGAGENTS_TEMPERATURE: string;
  TRADINGAGENTS_BENCHMARK_TICKER: string;
  TRADINGAGENTS_CHECKPOINT_ENABLED: string;
  TRADINGAGENTS_LLM_CACHE_ENABLED: string;
  AUTH_DISABLED: string;
}

export interface ConfigResponse {
  config: AppConfig;
  api_keys: Record<string, boolean>;
}

export interface ConfigDefaultsResponse {
  defaults: Partial<AppConfig>;
}

export async function fetchConfig(): Promise<ConfigResponse> {
  const r = await fetch(`${base}/api/config`);
  if (!r.ok) {
    throw new ApiError(`config ${r.status}`, r.status, await readJsonOrNull(r));
  }
  return r.json();
}

export async function fetchConfigDefaults(): Promise<ConfigDefaultsResponse> {
  const r = await fetch(`${base}/api/config/defaults`);
  if (!r.ok) {
    throw new ApiError(`config-defaults ${r.status}`, r.status, await readJsonOrNull(r));
  }
  return r.json();
}

export async function saveConfig(updates: Partial<AppConfig> | Record<string, string>): Promise<ConfigResponse> {
  const r = await fetch(`${base}/api/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!r.ok) {
    throw new ApiError(`save-config ${r.status}`, r.status, await readJsonOrNull(r));
  }
  return r.json();
}

export async function getTickerHistory(
  ticker: string,
  range: HistoryRange = "auto",
): Promise<HistoryResponse> {
  const r = await fetch(
    `${base}/api/tickers/${encodeURIComponent(ticker)}/history?range=${encodeURIComponent(range)}`,
  );
  if (!r.ok) {
    throw new ApiError(`history ${r.status}`, r.status, await readJsonOrNull(r));
  }
  return r.json();
}

export async function downloadSingleTicker(ticker: string, format: string = "zip"): Promise<void> {
  const safe = encodeURIComponent(ticker);
  const r = await fetch(`${base}/api/tickers/${safe}/download?format=${encodeURIComponent(format)}`);
  if (!r.ok) {
    throw new ApiError(`download ${r.status}`, r.status, await readJsonOrNull(r));
  }
  const blob = await r.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${ticker.toUpperCase()}-data.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

export async function downloadTickers(tickers: string[], format: string = "zip"): Promise<void> {
  const r = await fetch(`${base}/api/tickers/download`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ tickers, format }),
  });
  if (!r.ok) {
    throw new ApiError(`download ${r.status}`, r.status, await readJsonOrNull(r));
  }
  const blob = await r.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const ext = format === "zip" ? "zip" : format === "csv" ? "csv" : "json";
  a.download = `tickers-bundle.${ext}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

