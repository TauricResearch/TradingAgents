const base = "";

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
  TRADINGAGENTS_FREE_KEYS_ENABLED: string;
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

// ---- Free LLM Keys (from alistaitsacle/free-llm-api-keys) ----

export type FreeKeyStatus = "working" | "low_balance" | "no_access" | "rate_limited" | "error" | "unknown";

export interface FreeLlmKey {
  key: string;
  masked_key: string;
  model: string;
  provider: string;
  budget: string;
  rate_limit: string;
  expires: string;
  description: string;
  status: FreeKeyStatus;
  test_response: string | null;
  error_message: string | null;
}

export interface FreeLlmKeysResponse {
  keys: FreeLlmKey[];
  base_url: string;
}

export async function fetchFreeLlmKeys(): Promise<FreeLlmKeysResponse> {
  const r = await fetch(`${base}/api/free-llm-keys/fetch`, { method: "POST" });
  if (!r.ok) {
    throw new ApiError(`free-keys ${r.status}`, r.status, await readJsonOrNull(r));
  }
  return r.json();
}

// ── Free Keys Disk Cache ──

export interface FreeLlmKeysCache {
  saved_at: string;
  keys: FreeLlmKey[];
  base_url: string;
}

/** Trigger a background refresh: fetch, test all keys, and populate the disk cache. */
export async function refreshFreeKeysCache(): Promise<{ status: string; count: number }> {
  const r = await fetch(`${base}/api/free-llm-keys/refresh-cache`, { method: "POST" });
  if (!r.ok) throw new ApiError(`refresh-cache ${r.status}`, r.status, await readJsonOrNull(r));
  return r.json();
}

/** Read previously-fetched free keys from the server-side disk cache. */
export async function fetchCachedFreeKeys(): Promise<FreeLlmKeysCache | null> {
  const r = await fetch(`${base}/api/free-llm-keys/cached`);
  if (r.status === 404) return null;
  if (!r.ok) throw new ApiError(`cached-keys ${r.status}`, r.status, await readJsonOrNull(r));
  return r.json();
}

/**
 * Streaming version of ``fetchFreeLlmKeys``.
 *
 * Reads a Server-Sent Events (SSE) stream from the backend and invokes the
 * supplied callbacks as each key result arrives, so the UI can render
 * progress in real time.
 *
 * Callbacks (all optional):
 *   - ``onMeta`` – called once with ``{ total, base_url }``.
 *   - ``onKeyResult`` – called for each tested key as soon as it completes.
 *   - ``onProgress`` – called after each key with ``{ tested, total }``.
 *   - ``onDone`` – called once when all tests finish, with the final sorted
 *     key list and ``base_url``.
 *   - ``onError`` – called on stream error.
 */
export async function fetchFreeLlmKeysStream(callbacks: {
  onMeta?: (meta: { total: number; base_url: string }) => void;
  onKeyResult?: (key: FreeLlmKey) => void;
  onProgress?: (tested: number, total: number) => void;
  onDone?: (keys: FreeLlmKey[], base_url: string) => void;
  onError?: (error: string) => void;
}): Promise<void> {
  const r = await fetch(`${base}/api/free-llm-keys/fetch`, { method: "POST" });
  if (!r.ok) {
    const body = await readJsonOrNull(r);
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as Record<string, unknown>).detail)
        : `HTTP ${r.status}`;
    callbacks.onError?.(detail);
    return;
  }

  const reader = r.body?.getReader();
  if (!reader) {
    callbacks.onError?.("Response has no body");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "";
  let currentData = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const raw of lines) {
      const line = raw.trimEnd();
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        currentData = line.slice(6).trim();
      } else if (line === "") {
        if (currentEvent && currentData) {
          try {
            const data: Record<string, unknown> = JSON.parse(currentData);
            switch (currentEvent) {
              case "meta":
                callbacks.onMeta?.(data as { total: number; base_url: string });
                break;
              case "key_result":
                callbacks.onKeyResult?.(data as unknown as FreeLlmKey);
                break;
              case "progress":
                callbacks.onProgress?.(
                  Number(data.tested),
                  Number(data.total),
                );
                break;
              case "done":
                callbacks.onDone?.(
                  (data.keys ?? []) as FreeLlmKey[],
                  String(data.base_url ?? ""),
                );
                break;
            }
          } catch {
            // skip
          }
        }
        currentEvent = "";
        currentData = "";
      }
    }
  }
}
