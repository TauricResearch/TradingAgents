/** TanStack Query hooks for every endpoint. Polling is the fallback
 * transport (5s, matching the legacy page); when SSE is healthy the
 * interval relaxes to 60s and push updates carry the freshness. */
import { useQuery, type QueryClient } from "@tanstack/react-query";
import type { z } from "zod";

import { apiFetch } from "./client";
import {
  AgentPerfSchema,
  CorrelationsSchema,
  AlertFeedSchema,
  BacktestSchema,
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
