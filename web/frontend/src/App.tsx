import { useState, useEffect, useCallback, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchWatchlist, fetchPrices, removeFromWatchlist, fetchRunDetail, fetchConfigModels, type ConfigModels, type RunDetail } from "./lib/api";
import { useUi } from "./store/ui";
import { useRunStream } from "./hooks/useRunStream";
import { useGlobalStream } from "./hooks/useGlobalStream";
import { useFocusedRunEvents } from "./hooks/useFocusedRunEvents";
import { useRestoredRunEvents } from "./hooks/useRestoredRunEvents";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import { useRunNotifications } from "./hooks/useRunNotifications";
import { useTheme } from "./hooks/useTheme";
import { WatchlistRail } from "./components/WatchlistRail";
import { TickerHeader } from "./components/TickerHeader";

import { LiveEventStream } from "./components/LiveEventStream";
import { ReportPanel } from "./components/ReportPanel";
import { DecisionPanel } from "./components/DecisionPanel";
import { HistoricalAnalysisDrawer } from "./components/HistoricalAnalysisDrawer";
import { BackgroundRunsDrawer } from "./components/BackgroundRunsDrawer";
import { TickerAgentDrawer } from "./components/TickerAgentDrawer";
import { SettingsPanel } from "./components/SettingsPanel";
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

  // ── Backend ready gate ─────────────────────────────────────────
  // The Python backend (uvicorn) takes ~2 s to import and start up.
  // Without this gate, the first N <api calls fail with ECONNREFUSED,
  // React Query retries once (~2 s), and the user stares at the
  // loading spinner.  Poll /api/health first, then let queries fire.
  const [serverReady, setServerReady] = useState(false);
  const healthAttempt = useRef(0);
  useEffect(() => {
    if (serverReady) return;
    let cancelled = false;
    const poll = () => {
      if (cancelled) return;
      fetch("/api/health")
        .then((r) => {
          if (cancelled) return;
          if (r.ok) { setServerReady(true); return; }
          const delay = Math.min(1000 * 2 ** (healthAttempt.current++), 8000);
          setTimeout(poll, delay);
        })
        .catch(() => {
          if (cancelled) return;
          const delay = Math.min(1000 * 2 ** (healthAttempt.current++), 8000);
          setTimeout(poll, delay);
        });
    };
    poll();
    return () => { cancelled = true; };
  }, [serverReady]);

  // All hooks MUST be called unconditionally (rules of hooks).
  // Use `enabled` on useQuery + conditional rendering instead of early returns.
  const { data: watchlist = [], isLoading: watchlistLoading, isFetching: watchlistFetching } = useQuery({
    queryKey: ["watchlist"],
    queryFn: fetchWatchlist,
    enabled: serverReady,
  });
  const { data: prices = {} } = useQuery({ queryKey: ["prices"], queryFn: fetchPrices, enabled: serverReady });
  const { data: configModels } = useQuery<ConfigModels>({ queryKey: ["config-models"], queryFn: fetchConfigModels, staleTime: Infinity, enabled: serverReady });
  const [historyOpen, setHistoryOpen] = useState(false);
  const [dismissedStaleBanner, setDismissedStaleBanner] = useState<string | null>(null);
  const [traceView, setTraceView] = useState<"events" | "llm">("events");
  const [settingsOpen, setSettingsOpen] = useState(false);

  useRunStream(runId);
  useGlobalStream();
  useRestoredRunEvents(focused);
  useKeyboardShortcuts();
  useRunNotifications();
  const { theme, toggleTheme } = useTheme();
  const mobileSidebarOpen = useUi((s) => s.mobileSidebarOpen);
  const setMobileSidebarOpen = useUi((s) => s.setMobileSidebarOpen);
  const tickerAgentDrawerOpen = useUi((s) => s.tickerAgentDrawerOpen);
  const setTickerAgentDrawerOpen = useUi((s) => s.setTickerAgentDrawerOpen);

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

  const price = focused ? (prices[focused] as Record<string, unknown>) ?? {} : {};
  const priceStale = price.stale === true;
  // Re-show the banner whenever the user navigates to a different stale
  // ticker (don't let a dismissal on a previous one persist).
  useEffect(() => {
    if (!priceStale && dismissedStaleBanner === focused) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setDismissedStaleBanner(null);
    }
  }, [priceStale, focused, dismissedStaleBanner]);
  const showStaleBanner =
    !!focused && priceStale && dismissedStaleBanner !== focused;

  // ── Conditional rendering ──────────────────────────────────────
  if (!serverReady) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-market-DEFAULT">
        <div className="text-center animate-fade-in">
          <div className="w-12 h-12 mx-auto mb-4 rounded-full border-2 border-sky-500/30 border-t-sky-400 animate-spin" />
          <p className="text-sm text-slate-500 font-medium">Connecting to server…</p>
          <p className="text-xs text-slate-600 mt-2">Waiting for backend to start</p>
        </div>
      </div>
    );
  }

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

  const currentModelSummary = configModels
    ? [
        configModels.deep_think_model ? `Deep: ${configModels.deep_think_model}` : null,
        configModels.quick_think_model ? `Quick: ${configModels.quick_think_model}` : null,
      ]
        .filter(Boolean)
        .join(" · ")
    : null;

  return (
    <div className="min-h-screen flex bg-market-DEFAULT relative">
      {/* Ambient background gradient */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden" aria-hidden="true">
        <div className="absolute -top-40 -left-40 w-[500px] h-[500px] rounded-full bg-sky-500/5 blur-[120px]" />
        <div className="absolute -bottom-40 -right-40 w-[600px] h-[600px] rounded-full bg-emerald-500/5 blur-[150px]" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] bg-sky-400/3 blur-[200px]" />
      </div>

      {/* Mobile sidebar backdrop */}
      {mobileSidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/60 backdrop-blur-sm md:hidden"
          onClick={() => setMobileSidebarOpen(false)}
          aria-hidden
        />
      )}

      <WatchlistRail />
      <main className="flex-1 p-3 md:p-6 relative z-10 min-w-0">
        <header className="flex flex-wrap items-start justify-between gap-2 mb-4">
          <div className="flex items-center gap-2 min-w-0">
            {/* Mobile hamburger */}
            <button
              onClick={() => setMobileSidebarOpen(true)}
              className="md:hidden btn-secondary text-xs shrink-0"
              aria-label="Open watchlist"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
              </svg>
            </button>
            <h1 className="text-base md:text-lg font-display font-semibold text-slate-100 tracking-tight shrink-0">
              TradingAgents
            </h1>
            <span className="hidden sm:inline-flex px-2 py-0.5 text-[10px] font-mono font-semibold uppercase tracking-widest bg-sky-500/10 text-sky-400 border border-sky-500/20 rounded-md">
              Loaded models:
            </span>
            {currentModelSummary && (
              <span className="hidden sm:inline-flex px-2 py-0.5 text-[10px] font-mono font-semibold rounded-md bg-gradient-to-r from-sky-500/15 via-slate-900/80 to-emerald-500/15 text-slate-100 border border-slate-700/70 shadow-[0_0_20px_rgba(56,189,248,0.12)] truncate max-w-[200px] md:max-w-none">
                {currentModelSummary}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5 md:gap-2">
            <button
              onClick={() => setSettingsOpen(true)}
              className="btn-secondary text-xs"
              title="Settings"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.075-.124l-1.217.456a1.125 1.125 0 0 1-1.37-.49l-1.296-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.296-2.247a1.125 1.125 0 0 1 1.37-.491l1.217.456c.355.133.75.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
              </svg>
            </button>
            <button
              onClick={() => useUi.getState().setBackgroundRunsOpen(true)}
              className="btn-secondary text-xs"
            >
              Past Runs
            </button>
            <button
              onClick={() => setTickerAgentDrawerOpen(true)}
              className="btn-secondary text-xs"
              title="Ticker Accuracy Agent"
            >
              Agent
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
                className="mb-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 rounded-xl border border-amber-500/20 bg-amber-500/5 backdrop-blur-sm px-3 sm:px-4 py-3 text-xs sm:text-sm text-amber-300"
              >
                <span>
                  <strong className="font-semibold text-amber-200">{focused}</strong> is not available
                  on Yahoo Finance — price and history are unavailable.
                </span>
                <span className="flex items-center gap-3 shrink-0 self-end sm:self-auto">
                  <button
                    onClick={handleRemoveFocused}
                    data-testid="stale-ticker-remove"
                    className="rounded-lg bg-amber-500/20 px-3 py-1.5 text-xs font-medium text-amber-300 border border-amber-500/20 hover:bg-amber-500/30 transition-colors"
                  >
                    Remove
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
            {/* Pipeline flow: merged timeline dots + team cards visualization */}
            <div className="mb-4">
              <PipelineFlow events={events} />
            </div>
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
                  <span className="hidden sm:inline">Event Stream</span>
                  <span className="sm:hidden">Events</span>
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
      <TickerAgentDrawer
        open={tickerAgentDrawerOpen}
        onClose={() => setTickerAgentDrawerOpen(false)}
      />
      <BackgroundRunsDrawer focusedTicker={focused ?? "AAPL"} />
      <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        theme={theme}
        toggleTheme={toggleTheme}
      />
    </div>
  );
}


