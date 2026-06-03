const base = "";

export interface WatchlistRow {
  ticker: string;
  company_name: string;
  exchange: string;
  added_at: string | null;
  last_decision: string | null;
  last_decision_at: string | null;
}

export interface RunRow {
  id: number;
  ticker: string;
  started_at: string | null;
  finished_at: string | null;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  decision_action: string | null;
  decision_target: number | null;
  decision_rationale: string | null;
  decision_confidence: number | null;
}

export interface LlmCallRow {
  id: number;
  run_id: number;
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

export interface RunDetail {
  run: RunRow;
  events: Array<{ id: number; type: string; ts: string | null; data: unknown }>;
  llm_calls: LlmCallRow[];
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
  if (!r.ok && r.status !== 201) throw new Error(`add ${r.status}`);
}

export async function removeFromWatchlist(ticker: string): Promise<void> {
  const r = await fetch(`${base}/api/watchlist/${encodeURIComponent(ticker)}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`remove ${r.status}`);
}

export async function fetchPrices(): Promise<Record<string, unknown>> {
  const r = await fetch(`${base}/api/prices`);
  if (!r.ok) throw new Error(`prices ${r.status}`);
  return r.json();
}

export async function startRun(ticker: string, force: boolean = false): Promise<{ run_id: number }> {
  const r = await fetch(`${base}/api/runs`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ticker, force }),
  });
  if (!r.ok) throw new Error(`start ${r.status}`);
  return r.json();
}

export async function cancelRun(runId: number): Promise<void> {
  const r = await fetch(`${base}/api/runs/${runId}/cancel`, { method: "POST" });
  if (!r.ok) throw new Error(`cancel ${r.status}`);
}

export async function fetchRunDetail(runId: number): Promise<RunDetail> {
  const r = await fetch(`${base}/api/runs/${runId}`);
  if (!r.ok) throw new Error(`run ${r.status}`);
  return r.json();
}

export async function fetchTickerRuns(ticker: string): Promise<RunRow[]> {
  const r = await fetch(`${base}/api/tickers/${encodeURIComponent(ticker)}/runs`);
  if (!r.ok) throw new Error(`ticker-runs ${r.status}`);
  return r.json();
}
