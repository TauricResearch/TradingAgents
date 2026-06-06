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
}

export type RunStatus =
  | "queued"
  | "running"
  | "done"
  | "failed"
  | "cancelled"
  | "superseded";

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
  id: number;
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
  if (!r.ok && r.status !== 201) {
    throw new ApiError(`add ${r.status}`, r.status, await readJsonOrNull(r));
  }
}

export async function removeFromWatchlist(ticker: string): Promise<void> {
  const r = await fetch(`${base}/api/watchlist/${encodeURIComponent(ticker)}`, { method: "DELETE" });
  if (!r.ok) {
    throw new ApiError(`remove ${r.status}`, r.status, await readJsonOrNull(r));
  }
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

export function buildRunId(ticker: string, startedAtIso: string): string {
  return `${ticker}:${startedAtIso}`;
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
