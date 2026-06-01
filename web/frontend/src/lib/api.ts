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

export interface RunDetail {
  run: RunRow;
  events: Array<{ id: number; type: string; ts: string | null; data: unknown }>;
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

export async function startRun(ticker: string): Promise<{ run_id: number }> {
  const r = await fetch(`${base}/api/runs`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ticker }),
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
