/** TanStack Query hooks for every endpoint. Polling is the fallback
 * transport (5s, matching the legacy page); when SSE is healthy the
 * interval relaxes to 60s and push updates carry the freshness. */
import { useQuery, type QueryClient } from "@tanstack/react-query";
import type { z } from "zod";

import { ApiError, apiFetch, apiHeaders } from "./client";
import {
  AgentPerfSchema,
  CorrelationsSchema,
  AlertFeedSchema,
  BacktestSchema,
  BacktestEquityArtifactSchema,
  BacktestJobSchema,
  BacktestRunSchema,
  BacktestRunsSchema,
  BacktestStrategiesSchema,
  BacktestTradesArtifactSchema,
  BarsSchema,
  CalendarSchema,
  EvidencePanelsSchema,
  IndicatorSeriesSchema,
  IntelSchema,
  JournalSchema,
  PortfolioStatsSchema,
  ScannerSchema,
  RiskBudgetSchema,
  MemorySchema,
  NotificationsSchema,
  OverviewSchema,
  PrefsSchema,
  RecommendationSchema,
  RunListSchema,
  StatusSchema,
  SymbolsSchema,
  TimelineSchema,
  VolumeProfileSchema,
  WatchlistsSchema,
  PriceAlertListSchema,
  RegimeSchema,
  ChartAnnotationsSchema,
} from "./types";

export const qk = {
  overview: ["overview"] as const,
  status: ["status"] as const,
  alerts: ["alerts"] as const,
  runs: ["runs"] as const,
  runTimeline: (id: string) => ["runs", id, "timeline"] as const,
  runEvidence: (id: string) => ["runs", id, "evidence"] as const,
  recommendation: (symbol?: string) =>
    ["recommendation", "latest", symbol ?? "any"] as const,
  runRecommendation: (id: string) => ["runs", id, "recommendation"] as const,
  regime: ["regime"] as const,
  priceAlerts: ["price-alerts"] as const,
  journal: ["journal"] as const,
  portfolioStats: ["portfolio", "stats"] as const,
  scanner: ["scanner"] as const,
  riskBudget: ["risk", "budget"] as const,
  backtest: ["backtest"] as const,
  backtestJob: ["backtest", "job"] as const,
  backtestRuns: ["backtest", "runs"] as const,
  backtestRun: (id: string) => ["backtest", "runs", id] as const,
  backtestArtifact: (id: string, name: string) =>
    ["backtest", "runs", id, "artifacts", name] as const,
  backtestStrategies: ["backtest", "strategies"] as const,
  memory: ["memory"] as const,
  agents: ["agents"] as const,
  symbols: ["symbols"] as const,
  bars: (symbol: string, tf: string, limit: number) =>
    ["bars", symbol, tf, limit] as const,
  chartAnnotations: (symbol: string) =>
    ["chartAnnotations", symbol] as const,
  indicators: (symbol: string, tf: string, names: string) =>
    ["indicators", symbol, tf, names] as const,
  intel: ["intel"] as const,
  correlations: (window: number) => ["correlations", window] as const,
  calendar: ["calendar"] as const,
  notifications: ["notifications"] as const,
  prefs: ["prefs"] as const,
  watchlists: ["watchlists"] as const,
};

function fetchParsed<S extends z.ZodTypeAny>(url: string, schema: S) {
  return async (): Promise<z.infer<S>> => schema.parse(await apiFetch(url));
}

/** Set by the SSE transport: healthy push → relaxed polling. */
export let pollingInterval = 5_000;
export function setPollingInterval(ms: number) {
  pollingInterval = ms;
}

const live = () => ({
  // function form: re-evaluated per cycle, so a healthy SSE transport
  // relaxes polling on already-mounted queries too
  refetchInterval: () => pollingInterval,
  refetchIntervalInBackground: false,
  staleTime: 4_000,
});

export const useOverview = () =>
  useQuery({ queryKey: qk.overview, queryFn: fetchParsed("/api/overview", OverviewSchema), ...live() });

export const useStatus = () =>
  useQuery({ queryKey: qk.status, queryFn: fetchParsed("/api/status", StatusSchema), ...live() });

export const useAlerts = () =>
  useQuery({ queryKey: qk.alerts, queryFn: fetchParsed("/api/alerts", AlertFeedSchema), ...live() });

export const useRuns = () =>
  useQuery({ queryKey: qk.runs, queryFn: fetchParsed("/api/runs", RunListSchema), ...live() });

export const useRunTimeline = (runId: string | null, isLatest: boolean) =>
  useQuery({
    queryKey: qk.runTimeline(runId ?? "none"),
    queryFn: fetchParsed(`/api/runs/${runId}/timeline`, TimelineSchema),
    enabled: runId != null,
    // completed runs are immutable — never refetch them
    staleTime: isLatest ? 4_000 : Infinity,
    refetchInterval: isLatest ? () => pollingInterval : false,
  });

export const useRunEvidence = (runId: string | null, isLatest: boolean) =>
  useQuery({
    queryKey: qk.runEvidence(runId ?? "none"),
    queryFn: fetchParsed(`/api/runs/${runId}/evidence`, EvidencePanelsSchema),
    enabled: runId != null,
    staleTime: isLatest ? 4_000 : Infinity,
    refetchInterval: isLatest ? () => pollingInterval : false,
  });

export const useRecommendation = (symbol?: string) =>
  useQuery({
    queryKey: qk.recommendation(symbol),
    queryFn: fetchParsed(
      symbol
        ? `/api/recommendation/latest?symbol=${encodeURIComponent(symbol)}`
        : "/api/recommendation/latest",
      RecommendationSchema,
    ),
    ...live(),
  });

/** Full persisted ticket of any historical run (G8). 404 = the run
 * predates ticket persistence; callers show an honest fallback. */
export const useRunRecommendation = (runId: string | null | undefined) =>
  useQuery({
    queryKey: qk.runRecommendation(runId ?? "none"),
    queryFn: fetchParsed(`/api/runs/${runId}/recommendation`, RecommendationSchema),
    enabled: runId != null,
    staleTime: Infinity,
    retry: false,
  });

export const usePriceAlerts = () =>
  useQuery({
    queryKey: qk.priceAlerts,
    queryFn: fetchParsed("/api/price-alerts", PriceAlertListSchema),
    staleTime: 10_000,
  });

/** Notify-only by design: a triggered alert raises a notification, it
 * can never place or modify an order. */
export interface EvidenceAnswer {
  run_id: string;
  answerable: boolean;
  answer: string;
  cited_agent_ids: string[];
}

/** Grounded Q&A over one run's record (A1). Not cached — each question is
 * a one-shot POST; the model answers only from that run's evidence. */
export async function askRun(
  runId: string,
  question: string,
): Promise<EvidenceAnswer> {
  return apiFetch<EvidenceAnswer>(`/api/runs/${runId}/ask`, {
    method: "POST",
    body: JSON.stringify({ question }),
    headers: { "Content-Type": "application/json" },
  });
}

/** Streaming ask (PB.2): calls onToken with each text chunk as it arrives.
 * Throws so the caller can fall back to the structured askRun. */
export async function askRunStream(
  runId: string,
  question: string,
  onToken: (text: string) => void,
): Promise<void> {
  const resp = await fetch(`/api/runs/${runId}/ask/stream`, {
    method: "POST",
    body: JSON.stringify({ question }),
    headers: { ...apiHeaders(), "Content-Type": "application/json" },
  });
  // any non-ok (incl. 401) throws → caller falls back to askRun, whose
  // apiFetch triggers the shared unauthorized handler
  if (!resp.ok || !resp.body) {
    throw new ApiError(resp.status, resp.statusText, resp.url);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    if (value) onToken(decoder.decode(value, { stream: true }));
  }
}

export async function createPriceAlert(
  client: QueryClient,
  alert: { symbol: string; level: number; direction: "above" | "below"; note?: string },
): Promise<{ id?: string }> {
  const created = await apiFetch<{ id?: string }>("/api/price-alerts", {
    method: "POST",
    body: JSON.stringify(alert),
    headers: { "Content-Type": "application/json" },
  });
  await client.invalidateQueries({ queryKey: qk.priceAlerts });
  return created ?? {};
}

export async function deletePriceAlert(client: QueryClient, id: string) {
  await apiFetch(`/api/price-alerts/${id}`, { method: "DELETE" });
  await client.invalidateQueries({ queryKey: qk.priceAlerts });
}

export const useRegime = () =>
  useQuery({
    queryKey: qk.regime,
    queryFn: fetchParsed("/api/regime", RegimeSchema),
    staleTime: 240_000,
    refetchInterval: 300_000,
  });

export const useJournal = () =>
  useQuery({ queryKey: qk.journal, queryFn: fetchParsed("/api/journal", JournalSchema), ...live() });

export const useScanner = () =>
  useQuery({
    queryKey: qk.scanner,
    queryFn: fetchParsed("/api/scanner", ScannerSchema),
    staleTime: 120_000,
    refetchInterval: 300_000,
  });

export const usePortfolioStats = () =>
  useQuery({
    queryKey: qk.portfolioStats,
    queryFn: fetchParsed("/api/portfolio/stats", PortfolioStatsSchema),
    ...live(),
  });

export const useRiskBudget = () =>
  useQuery({
    queryKey: qk.riskBudget,
    queryFn: fetchParsed("/api/risk/budget", RiskBudgetSchema),
    ...live(),
  });

export const useBacktest = () =>
  useQuery({
    queryKey: qk.backtest,
    queryFn: fetchParsed("/api/backtest", BacktestSchema),
    staleTime: 60_000,
  });

export const useBacktestRuns = () =>
  useQuery({
    queryKey: qk.backtestRuns,
    queryFn: fetchParsed("/api/backtest/runs", BacktestRunsSchema),
    staleTime: 30_000,
  });

/** Registered strategies + their declared parameter schema (track T1),
 * so the run controls render the strategy picker + param inputs dynamically.
 * The set changes only on deploy, so it's effectively static. */
export const useBacktestStrategies = () =>
  useQuery({
    queryKey: qk.backtestStrategies,
    queryFn: fetchParsed("/api/backtest/strategies", BacktestStrategiesSchema),
    staleTime: Infinity,
  });

export const useBacktestRun = (id: string | null) =>
  useQuery({
    queryKey: qk.backtestRun(id ?? "none"),
    queryFn: fetchParsed(`/api/backtest/runs/${id}`, BacktestRunSchema),
    enabled: id != null,
    staleTime: Infinity,
  });

/** Full-fidelity bulk data (every equity point / trade / decision) for one
 * run — streamed from the per-run artifact files. Immutable once written. */
export const useBacktestEquityArtifact = (id: string | null) =>
  useQuery({
    queryKey: qk.backtestArtifact(id ?? "none", "equity"),
    queryFn: fetchParsed(
      `/api/backtest/runs/${id}/artifacts/equity`,
      BacktestEquityArtifactSchema,
    ),
    enabled: id != null,
    staleTime: Infinity,
    retry: 1, // legacy runs predate artifacts — 404 is expected there
  });

export const useBacktestTradesArtifact = (id: string | null) =>
  useQuery({
    queryKey: qk.backtestArtifact(id ?? "none", "trades"),
    queryFn: fetchParsed(
      `/api/backtest/runs/${id}/artifacts/trades`,
      BacktestTradesArtifactSchema,
    ),
    enabled: id != null,
    staleTime: Infinity,
    retry: 1,
  });

/** Stop the in-flight run; the partial is saved labeled "cancelled".
 * Retries through transient edge failures (Firebase Hosting 429s under a
 * busy session) — a cancel click must not be silently dropped. A 409 means
 * the run already ended: success, not an error. */
export async function cancelBacktest(): Promise<void> {
  let lastError: unknown = null;
  for (let attempt = 0; attempt < 4; attempt++) {
    try {
      await apiFetch("/api/backtest/cancel", { method: "POST" });
      return;
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) return; // already idle
      lastError = err;
      await new Promise((r) => setTimeout(r, 1_500 * (attempt + 1)));
    }
  }
  throw lastError;
}

export async function deleteBacktestRun(client: QueryClient, id: string) {
  await apiFetch(`/api/backtest/runs/${id}`, { method: "DELETE" });
  await client.invalidateQueries({ queryKey: qk.backtestRuns });
}

/** Live/last job snapshot — the reconnect fallback when SSE frames are
 * missed (progress + partial trades also arrive over the stream). Always
 * fetched fresh on mount so a reload/new tab can re-attach to a run that
 * is already in flight server-side; polls while one is running. The poll
 * relaxes when SSE is healthy (it's only a safety net then) — an aggressive
 * fixed 2s poll tripped Firebase Hosting's per-client rate limit on long
 * runs, which then starved OTHER requests (observed: cancel got 429'd). */
export const useBacktestJob = (polling: boolean) =>
  useQuery({
    queryKey: qk.backtestJob,
    queryFn: fetchParsed("/api/backtest/job", BacktestJobSchema),
    refetchInterval: polling
      ? () => (pollingInterval > 10_000 ? 10_000 : 3_000)
      : false,
    staleTime: 0,
    refetchOnMount: "always",
  });

export class BacktestCostConfirmation extends Error {
  constructor(readonly estimate: { decisions: number; est_cost_usd: number; est_minutes: number }) {
    super("cost confirmation required");
  }
}

/** Start a backtest job (202 → { job_id }). A 400 for an unconfirmed LLM
 * run throws BacktestCostConfirmation carrying the estimate so the caller
 * can show the warning and re-submit with confirm_cost. */
export async function runBacktest(
  req: {
    symbol: string;
    timeframe: string;
    duration: string;
    use_llm?: boolean;
    confirm_cost?: boolean;
    initial_equity?: number;
    risk_per_trade_pct?: number;
    max_position_pct?: number;
    strategy_id?: string;
    strategy_params?: Record<string, string | number>;
  },
): Promise<{ job_id: string }> {
  try {
    return await apiFetch<{ job_id: string }>("/api/backtest/run", {
      method: "POST",
      body: JSON.stringify(req),
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    if (err instanceof ApiError && err.status === 400) {
      try {
        const detail = JSON.parse(err.detail) as {
          estimate?: BacktestCostConfirmation["estimate"];
        };
        if (detail?.estimate) throw new BacktestCostConfirmation(detail.estimate);
      } catch (parseErr) {
        if (parseErr instanceof BacktestCostConfirmation) throw parseErr;
      }
    }
    throw err;
  }
}

export const useMemoryInsights = () =>
  useQuery({ queryKey: qk.memory, queryFn: fetchParsed("/api/memory", MemorySchema), ...live() });

export const useAgents = () =>
  useQuery({ queryKey: qk.agents, queryFn: fetchParsed("/api/agents", AgentPerfSchema), ...live() });

export const useSymbols = () =>
  useQuery({
    queryKey: qk.symbols,
    queryFn: fetchParsed("/api/symbols", SymbolsSchema),
    staleTime: 300_000,
  });

/** The AI's record for one symbol, chart-paintable (chart Phase 1). SSE
 * `run`/`position` events invalidate it, so it repaints without polling
 * hard. */
export const useChartAnnotations = (symbol: string) =>
  useQuery({
    queryKey: qk.chartAnnotations(symbol),
    queryFn: fetchParsed(
      `/api/chart/annotations?symbol=${encodeURIComponent(symbol)}`,
      ChartAnnotationsSchema,
    ),
    staleTime: 60_000,
  });

export const useBars = (symbol: string, timeframe: string, limit = 300) =>
  useQuery({
    queryKey: qk.bars(symbol, timeframe, limit),
    queryFn: fetchParsed(
      `/api/bars?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}`,
      BarsSchema,
    ),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });

export const useVolumeProfile = (
  symbol: string,
  timeframe: string,
  enabled: boolean,
  limit = 300,
) =>
  useQuery({
    queryKey: ["volume-profile", symbol, timeframe, limit],
    queryFn: fetchParsed(
      `/api/bars/volume-profile?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}`,
      VolumeProfileSchema,
    ),
    enabled,
    staleTime: 60_000,
    refetchInterval: 120_000,
  });

export const useIndicators = (symbol: string, timeframe: string, names: string[]) =>
  useQuery({
    queryKey: qk.indicators(symbol, timeframe, names.join(",")),
    queryFn: fetchParsed(
      `/api/bars/indicators?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&names=${names.join(",")}`,
      IndicatorSeriesSchema,
    ),
    enabled: names.length > 0,
    staleTime: 30_000,
  });

export const useIntel = () =>
  useQuery({
    queryKey: qk.intel,
    queryFn: fetchParsed("/api/intel", IntelSchema),
    staleTime: 60_000,
    refetchInterval: 60_000,
  });

export const useCorrelations = (window = 30) =>
  useQuery({
    queryKey: qk.correlations(window),
    queryFn: fetchParsed(`/api/intel/correlations?window=${window}`,
                         CorrelationsSchema),
    staleTime: 3_600_000,
  });

export const useCalendar = () =>
  useQuery({
    queryKey: qk.calendar,
    queryFn: fetchParsed("/api/calendar", CalendarSchema),
    staleTime: 3_600_000,
  });

export const useNotifications = () =>
  useQuery({
    queryKey: qk.notifications,
    queryFn: fetchParsed("/api/notifications", NotificationsSchema),
    ...live(),
  });

export const usePrefs = () =>
  useQuery({
    queryKey: qk.prefs,
    queryFn: fetchParsed("/api/prefs", PrefsSchema),
    staleTime: Infinity,
  });

export const useWatchlists = () =>
  useQuery({
    queryKey: qk.watchlists,
    queryFn: fetchParsed("/api/watchlists", WatchlistsSchema),
    staleTime: 60_000,
  });

export async function savePrefs(client: QueryClient, prefs: unknown) {
  const saved = await apiFetch("/api/prefs", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(prefs),
  });
  client.setQueryData(qk.prefs, PrefsSchema.parse(saved));
  return saved;
}

/** Read-modify-write over the cached prefs document. */
export async function patchPrefs(
  client: QueryClient,
  patch: Record<string, unknown>,
) {
  // read-modify-write over the SERVER document: an empty cache (mount-time
  // writes racing the first fetch) must never PUT client defaults — that
  // silently resets server-side fields (found via operator_label)
  const current =
    client.getQueryData(qk.prefs) ??
    (await client.fetchQuery({
      queryKey: qk.prefs,
      queryFn: fetchParsed("/api/prefs", PrefsSchema),
    }));
  return savePrefs(client, { ...(current as Record<string, unknown>), ...patch });
}

export async function upsertWatchlist(
  client: QueryClient,
  watchlist: { name: string; symbols: string[] },
) {
  await apiFetch("/api/watchlists", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(watchlist),
  });
  await client.invalidateQueries({ queryKey: qk.watchlists });
}

export async function deleteWatchlist(client: QueryClient, name: string) {
  await apiFetch(`/api/watchlists/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
  await client.invalidateQueries({ queryKey: qk.watchlists });
}

export async function markNotificationsRead(client: QueryClient, ids?: string[]) {
  await apiFetch("/api/notifications/read", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(ids ? { ids } : {}),
  });
  await client.invalidateQueries({ queryKey: qk.notifications });
}
