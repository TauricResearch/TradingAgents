// Thin fetch wrapper around the FastAPI service.
//
// Browser → Next.js rewrite → FastAPI:
//   /api/runs  →  http://localhost:8000/runs   (dev or behind reverse proxy)
//
// All paths in this file start with `/api/...` so they hit the rewrite.

import type {
  Brief,
  ChatMessage,
  ChartComparisonResponse,
  ExportFile,
  MemoryResponse,
  Note,
  RunCreateRequest,
  RunDetail,
  RunSummary,
  Settings,
} from "./types";

const API_BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  // 204 / empty response
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as T;
  }
  return (await res.json()) as T;
}

// ---- Runs ---------------------------------------------------------------

export const Runs = {
  list: (ticker?: string) =>
    request<RunSummary[]>(
      `/runs${ticker ? `?ticker=${encodeURIComponent(ticker)}` : ""}`,
    ),
  get: (runId: string) => request<RunDetail>(`/runs/${runId}`),
  create: (req: RunCreateRequest) =>
    request<RunSummary>("/runs", {
      method: "POST",
      body: JSON.stringify(req),
    }),
  cancel: (runId: string) =>
    request<{ cancelled: boolean }>(`/runs/${runId}/cancel`, { method: "POST" }),
  diskIndex: () => request<any[]>(`/runs/disk/index`),
};

// ---- Briefs -------------------------------------------------------------

export const Briefs = {
  get: (runId: string) =>
    request<{ run_id: string; brief: Brief | null; cached: boolean }>(
      `/runs/${runId}/brief`,
    ),
  generate: (runId: string, force = false) =>
    request<{ run_id: string; brief: Brief; cached: boolean }>(
      `/runs/${runId}/brief${force ? "?force=true" : ""}`,
      { method: "POST" },
    ),
};

// ---- Chat ---------------------------------------------------------------

export const Chat = {
  list: (runId: string) =>
    request<ChatMessage[]>(`/runs/${runId}/chat`),
  clear: (runId: string) =>
    request<{ cleared: boolean }>(`/runs/${runId}/chat`, { method: "DELETE" }),
};

// ---- Notes --------------------------------------------------------------

export const Notes = {
  list: (params?: { ticker?: string; run_id?: string; q?: string }) => {
    const qp = new URLSearchParams();
    if (params?.ticker) qp.set("ticker", params.ticker);
    if (params?.run_id) qp.set("run_id", params.run_id);
    if (params?.q) qp.set("q", params.q);
    const qs = qp.toString();
    return request<Note[]>(`/notes${qs ? `?${qs}` : ""}`);
  },
  create: (req: { title: string; body: string; ticker?: string; run_id?: string; tags?: string }) =>
    request<Note>("/notes", { method: "POST", body: JSON.stringify(req) }),
  update: (id: number, req: { title: string; body: string; tags?: string }) =>
    request<Note>(`/notes/${id}`, { method: "PUT", body: JSON.stringify(req) }),
  delete: (id: number) =>
    request<{ deleted: boolean }>(`/notes/${id}`, { method: "DELETE" }),
};

// ---- Settings -----------------------------------------------------------

export const SettingsApi = {
  get: () => request<Settings>("/settings"),
  update: (req: { api_keys?: Record<string, string>; defaults?: Record<string, any> }) =>
    request<Settings>("/settings", { method: "PUT", body: JSON.stringify(req) }),
};

// ---- Memory -------------------------------------------------------------

export const Memory = {
  get: () => request<MemoryResponse>("/memory"),
};

// ---- Charts -------------------------------------------------------------

export const Charts = {
  comparison: (params: {
    ticker: string;
    trade_date: string;
    days_back?: number;
    days_forward?: number;
    benchmarks?: string[];
  }) => {
    const qp = new URLSearchParams();
    qp.set("ticker", params.ticker);
    qp.set("trade_date", params.trade_date);
    if (params.days_back) qp.set("days_back", String(params.days_back));
    if (params.days_forward) qp.set("days_forward", String(params.days_forward));
    (params.benchmarks ?? ["SPY", "QQQ"]).forEach((b) => qp.append("benchmarks", b));
    return request<ChartComparisonResponse>(`/charts/comparison?${qp}`);
  },
};

// ---- Exports ------------------------------------------------------------

export const Exports = {
  list: (runId: string) =>
    request<ExportFile[]>(`/runs/${runId}/exports`),
  downloadUrl: (runId: string, ext: ExportFile["ext"]) =>
    `${API_BASE}/runs/${runId}/exports/${ext}`,
  regenerate: (runId: string) =>
    request<Array<{ ext: string; path: string }>>(
      `/runs/${runId}/exports/regenerate`,
      { method: "POST" },
    ),
};
