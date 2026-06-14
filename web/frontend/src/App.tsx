import { useState, useEffect, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchWatchlist, fetchPrices, removeFromWatchlist, fetchRunDetail, type RunDetail } from "./lib/api";
import { useUi } from "./store/ui";
import { useRunStream } from "./hooks/useRunStream";
import { useGlobalStream } from "./hooks/useGlobalStream";
import { useFocusedRunEvents } from "./hooks/useFocusedRunEvents";
import { useRestoredRunEvents } from "./hooks/useRestoredRunEvents";
import { WatchlistRail } from "./components/WatchlistRail";
import { TickerHeader } from "./components/TickerHeader";
import { RunTimeline } from "./components/RunTimeline";
import { LiveEventStream } from "./components/LiveEventStream";
import { ReportPanel } from "./components/ReportPanel";
import { DecisionPanel } from "./components/DecisionPanel";
import { HistoricalAnalysisDrawer } from "./components/HistoricalAnalysisDrawer";
import { BackgroundRunsDrawer } from "./components/BackgroundRunsDrawer";
import { PipelineFlow } from "./components/PipelineFlow";
import { LlmTracePanel } from "./components/LlmTracePanel";

export default function App() {
  const focused = useUi((s) => s.focusedTicker);
  const setFocused = useUi((s) => s.setFocusedTicker);
  const clearLast = useUi((s) => s.clearLastRunIdForTicker);
  const qc = useQueryClient();
  // The new store keys active runs by ticker (multiple tickers can be
  // streaming concurrently in the global buffer). Subscribe to the
  // active run for the *focused* ticker only; the WS hook is short-lived
  // and re-opens when focus or the underlying run id changes.
  const runId = useUi((s) => (focused ? s.activeRunIdByTicker[focused] ?? null : null));
  const events = useFocusedRunEvents();
  const { data: watchlist = [], isLoading: watchlistLoading, isFetching: watchlistFetching } = useQuery({
    queryKey: ["watchlist"],
    queryFn: fetchWatchlist,
  });
  const { data: prices = {} } = useQuery({ queryKey: ["prices"], queryFn: fetchPrices });
  const [historyOpen, setHistoryOpen] = useState(false);
  const [dismissedStaleBanner, setDismissedStaleBanner] = useState<string | null>(null);
  const [traceView, setTraceView] = useState<"events" | "llm">("events");

  useRunStream(runId);
  useGlobalStream();
  useRestoredRunEvents(focused);

  // The run detail for the currently focused run (historical pick or
  // latest). Used to power the DecisionPanel's "incomplete" hint. The
  // query key matches useRestoredRunEvents' so both share the cache and
  // avoid a duplicate network round-trip.
  const focusedRunId = useUi((s) => {
    if (focused == null) return null;
    const historical = s.historicalRunIdByTicker[focused];
    if (historical != null) return historical;
    return s.lastRunIdByTicker[focused] ?? null;
  });
  const { data: focusedRunDetail } = useQuery<RunDetail | null>({
    queryKey: ["run-detail", focused, focusedRunId],
    queryFn: () => (focusedRunId ? fetchRunDetail(focusedRunId) : Promise.resolve(null)),
    enabled: focused != null && focusedRunId != null,
    staleTime: Infinity,
  });

  const handleSetTraceView = useCallback((view: "events" | "llm") => {
    setTraceView(view);
    if (view === "llm" && focused && focusedRunId) {
      qc.invalidateQueries({ queryKey: ["run-detail", focused, focusedRunId] });
    }
  }, [focused, focusedRunId, qc]);

  // Sync focusedTicker with the watchlist. This is the single source of
  // truth: the effect skips during refetches (when data may be stale) and
  // only acts on fresh server data.
  useEffect(() => {
    if (watchlistFetching) return;
    if (watchlist.length === 0 && focused !== null) {
      setFocused(null);
    } else if (focused && !watchlist.some((w) => w.ticker === focused)) {
      setFocused(watchlist[0]?.ticker ?? null);
    } else if (!focused && watchlist.length > 0) {
      setFocused(watchlist[0].ticker);
    }
  }, [watchlist, focused, setFocused, watchlistFetching]);

  const handleRemoveFocused = useCallback(async () => {
    if (!focused) return;
    try {
      await removeFromWatchlist(focused);
    } catch {
      return;
    }
    clearLast(focused);
    setDismissedStaleBanner(null);
    qc.invalidateQueries({ queryKey: ["watchlist"] });
  }, [focused, clearLast, qc]);

  const price = focused ? (prices as any)[focused] || {} : {};
  const priceStale = price.stale === true;
  // Re-show the banner whenever the user navigates to a different stale
  // ticker (don't let a dismissal on a previous one persist).
  useEffect(() => {
    if (!priceStale && dismissedStaleBanner === focused) {
      setDismissedStaleBanner(null);
    }
  }, [priceStale, focused, dismissedStaleBanner]);
  const showStaleBanner =
    !!focused && priceStale && dismissedStaleBanner !== focused;

  if (watchlistLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-market-DEFAULT">
        <div className="text-center animate-fade-in">
          <div className="w-12 h-12 mx-auto mb-4 rounded-full border-2 border-sky-500/30 border-t-sky-400 animate-spin" />
          <p className="text-sm text-slate-500 font-medium">Loading watchlist…</p>
        </div>
      </div>
    );
  }

  const decisionEvent = [...events].reverse().find((e) => e.type === "decision");
  const decision = decisionEvent?.data as { action: string; target: number; rationale: string; confidence: number } | undefined;

  return (
    <div className="min-h-screen flex bg-market-DEFAULT relative">
      {/* Ambient background gradient */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden" aria-hidden="true">
        <div className="absolute -top-40 -left-40 w-[500px] h-[500px] rounded-full bg-sky-500/5 blur-[120px]" />
        <div className="absolute -bottom-40 -right-40 w-[600px] h-[600px] rounded-full bg-emerald-500/5 blur-[150px]" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] bg-sky-400/3 blur-[200px]" />
      </div>
      <WatchlistRail />
      <main className="flex-1 p-6 relative z-10">
        <header className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-display font-semibold text-slate-100 tracking-tight">
              TradingAgents
            </h1>
            <span className="px-2 py-0.5 text-[10px] font-mono font-semibold uppercase tracking-widest 
                         bg-sky-500/10 text-sky-400 border border-sky-500/20 rounded-md">
              Multi-Agent
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => useUi.getState().setBackgroundRunsOpen(true)}
              className="btn-secondary text-xs"
            >
              Past Runs
            </button>
            {focused && (
              <button onClick={() => setHistoryOpen(true)} className="btn-secondary text-xs">History</button>
            )}
          </div>
        </header>
        {focused ? (
          <>
            {showStaleBanner && (
              <div
                data-testid="stale-ticker-banner"
                role="alert"
                className="mb-4 flex items-center justify-between gap-4 rounded-xl border border-amber-500/20 bg-amber-500/5 backdrop-blur-sm px-4 py-3 text-sm text-amber-300"
              >
                <span>
                  <strong className="font-semibold text-amber-200">{focused}</strong> is not available
                  on Yahoo Finance — price and history are unavailable.
                </span>
                <span className="flex items-center gap-3 shrink-0">
                  <button
                    onClick={handleRemoveFocused}
                    data-testid="stale-ticker-remove"
                    className="rounded-lg bg-amber-500/20 px-3 py-1.5 text-xs font-medium text-amber-300 border border-amber-500/20 hover:bg-amber-500/30 transition-colors"
                  >
                    Remove from watchlist
                  </button>
                  <button
                    onClick={() => setDismissedStaleBanner(focused)}
                    className="text-amber-400/60 hover:text-amber-300 transition-colors text-lg leading-none"
                    aria-label="Dismiss"
                  >
                    ×
                  </button>
                </span>
              </div>
            )}
            <TickerHeader ticker={focused} price={price.price} changePct={price.change_pct} stale={priceStale} />
            {/* Pipeline flow: 5-team workflow visualization */}
            <div className="mb-4">
              <PipelineFlow events={events} />
            </div>
            <RunTimeline />
            <div className="flex items-center gap-0 mb-4">
              <button
                onClick={() => handleSetTraceView("events")}
                className={`px-3 py-1.5 text-xs font-semibold rounded-l-lg border transition-all ${
                  traceView === "events"
                    ? "bg-sky-500/15 text-sky-300 border-sky-500/30 z-10"
                    : "text-slate-500 border-slate-700/50 hover:text-slate-300"
                }`}
              >
                <span className="flex items-center gap-1.5">
                  <span className={`w-1.5 h-1.5 rounded-full ${traceView === "events" ? "bg-sky-400 shadow-[0_0_4px_rgba(56,189,248,0.5)]" : "bg-slate-600"}`} />
                  Event Stream
                </span>
              </button>
              <button
                onClick={() => handleSetTraceView("llm")}
                className={`px-3 py-1.5 text-xs font-semibold rounded-r-lg border border-l-0 transition-all ${
                  traceView === "llm"
                    ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30 z-10"
                    : "text-slate-500 border-slate-700/50 hover:text-slate-300"
                }`}
              >
                <span className="flex items-center gap-1.5">
                  <span className={`w-1.5 h-1.5 rounded-full ${traceView === "llm" ? "bg-emerald-400 shadow-[0_0_4px_rgba(52,211,153,0.5)]" : "bg-slate-600"}`} />
                  LLM Trace
                </span>
              </button>
            </div>
            {traceView === "events" ? (
              <LiveEventStream />
            ) : (
              <div className="glass-panel">
                <div className="max-h-[400px] overflow-y-auto p-3">
                  <LlmTracePanel calls={focusedRunDetail?.llm_calls ?? []} />
                </div>
              </div>
            )}
            <ReportPanel />
            {decision && (
              <DecisionPanel
                action={decision.action}
                target={decision.target ?? null}
                confidence={decision.confidence ?? 0}
                rationale={decision.rationale ?? ""}
                run={focusedRunDetail}
              />
            )}
          </>
        ) : (
          <div className="mt-24 text-center animate-fade-in">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-slate-800/60 border border-slate-700/50 mb-4">
              <svg className="w-8 h-8 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />
              </svg>
            </div>
            <p className="text-base font-medium text-slate-400">Your watchlist is empty</p>
            <p className="text-sm text-slate-600 mt-1">Add tickers using the "+ Add ticker" button in the sidebar.</p>
          </div>
        )}
      </main>
      {focused && historyOpen && (
        <HistoricalAnalysisDrawer ticker={focused} onClose={() => setHistoryOpen(false)} />
      )}
      <BackgroundRunsDrawer focusedTicker={focused ?? "AAPL"} />
    </div>
  );
}
