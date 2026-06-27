import { useState, useEffect, useCallback, useMemo, useRef } from "react";
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
import { LogPanel } from "./components/LogPanel";
import { ToastContainer } from "./ui";
import "./lib/console-capture";

import { AuthGate } from "./components/AuthGate";
import { WatchlistRail } from "./components/WatchlistRail";
import { TickerHeader } from "./components/TickerHeader";
import { TickerChatBar } from "./components/TickerChatBar";
import { TopBar } from "./components/TopBar";
import { LoadingScreen } from "./components/LoadingScreen";
import { EmptyWatchlist } from "./components/EmptyWatchlist";
import { StaleBanner } from "./components/StaleBanner";
import { TraceTabs } from "./components/TraceTabs";

import { LiveEventStream } from "./components/LiveEventStream";
import { ReportPanel } from "./components/ReportPanel";
import { DecisionPanel } from "./components/DecisionPanel";
import { HistoricalAnalysisDrawer } from "./components/HistoricalAnalysisDrawer";
import { BackgroundRunsDrawer } from "./components/BackgroundRunsDrawer";
import { TickerAgentDrawer } from "./components/TickerAgentDrawer";
import BatchDownloadDialog from "./components/BatchDownloadDialog";
import { SettingsPanel } from "./components/SettingsPanel";
import { PipelineFlow } from "./components/PipelineFlow";
import { LlmTracePanel } from "./components/LlmTracePanel";
import { AgentObservatory } from "./components/AgentObservatory";
import { ErrorBoundary } from "./components/ErrorBoundary";

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
          const delay = Math.min(1000 * 2 ** Math.min(healthAttempt.current++, 16), 8000);
          setTimeout(poll, delay);
        })
        .catch(() => {
          if (cancelled) return;
          const delay = Math.min(1000 * 2 ** Math.min(healthAttempt.current++, 16), 8000);
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
  const historyOpenByTicker = useUi((s) => s.historyOpenByTicker);
  const [dismissedStaleBanner, setDismissedStaleBanner] = useState<string | null>(null);
  const [traceView, setTraceView] = useState<"events" | "llm" | "observatory">("events");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [batchDialogOpen, setBatchDialogOpen] = useState(false);

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
    const active = s.activeRunIdByTicker[focused];
    if (active != null) return active;
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

  const handleSetTraceView = useCallback((view: "events" | "llm" | "observatory") => {
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
  const decisionEvent = useMemo(() => [...events].reverse().find((e) => e.type === "decision"), [events]);
  const decision = decisionEvent?.data as { action: string; target: number; rationale: string; confidence: number } | undefined;

  const currentModelSummary = configModels
    ? [
        configModels.deep_think_model ? `Deep: ${configModels.deep_think_model}` : null,
        configModels.quick_think_model ? `Quick: ${configModels.quick_think_model}` : null,
      ]
        .filter(Boolean)
        .join(" | ")
    : null;

  const sidebarCollapsed = useUi((s) => s.sidebarCollapsed);

  const appContent = !serverReady ? (
    <LoadingScreen message="Connecting to server…" submessage="Waiting for backend to start" />
  ) : watchlistLoading ? (
    <LoadingScreen message="Loading watchlist…" />
  ) : (
    <div className="min-h-screen flex flex-col bg-market-DEFAULT">
      {/* Ambient background gradient */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden" aria-hidden="true">
        <div className="absolute -top-40 -left-40 w-[500px] h-[500px] rounded-full bg-sky-500/5 blur-[120px]" />
        <div className="absolute -bottom-40 -right-40 w-[600px] h-[600px] rounded-full bg-emerald-500/5 blur-[150px]" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] bg-sky-400/3 blur-[200px]" />
      </div>

      <TopBar
        currentModelSummary={currentModelSummary}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenBatchDownload={() => setBatchDialogOpen(true)}
      />

      <div className="flex flex-1 min-h-0 relative">
        {/* Mobile sidebar backdrop */}
        {mobileSidebarOpen && (
          <div
            className="fixed inset-0 z-30 bg-black/60 backdrop-blur-sm md:hidden"
            onClick={() => setMobileSidebarOpen(false)}
            aria-hidden
          />
        )}

        <WatchlistRail />
        <main className={`flex-1 p-3 md:p-6 relative z-10 min-w-0 transition-all duration-300 ${sidebarCollapsed ? "md:ml-0" : ""}`}>
          {focused ? (
            <>
              {showStaleBanner && (
                <StaleBanner
                  ticker={focused}
                  onRemove={handleRemoveFocused}
                  onDismiss={() => setDismissedStaleBanner(focused)}
                />
              )}
              <TickerHeader ticker={focused} price={price.price} changePct={price.change_pct} stale={priceStale} />
              <TickerChatBar ticker={focused} price={price} run={focusedRunDetail} />
              <div className="mb-4">
                <ErrorBoundary>
                  <PipelineFlow events={events} />
                </ErrorBoundary>
              </div>
              <TraceTabs value={traceView} onChange={handleSetTraceView} />
              {traceView === "events" ? (
                <ErrorBoundary>
                  <LiveEventStream />
                </ErrorBoundary>
              ) : traceView === "observatory" ? (
                <ErrorBoundary>
                  <AgentObservatory events={events} />
                </ErrorBoundary>
              ) : (
                <div className="glass-panel">
                  <div className="max-h-[400px] overflow-y-auto p-3">
                    <LlmTracePanel calls={focusedRunDetail?.llm_calls ?? []} />
                  </div>
                </div>
              )}
              <ReportPanel />
              {decision && (
                <ErrorBoundary>
                  <DecisionPanel
                    action={decision.action}
                    target={decision.target ?? null}
                    confidence={decision.confidence ?? 0}
                    rationale={decision.rationale ?? ""}
                    run={focusedRunDetail}
                  />
                </ErrorBoundary>
              )}
            </>
          ) : (
            <EmptyWatchlist />
          )}
        </main>
      </div>

      {focused && (
        <HistoricalAnalysisDrawer
          ticker={focused}
          open={!!historyOpenByTicker[focused]}
          onClose={() => useUi.getState().setHistoryOpen(focused, false)}
        />
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
      {batchDialogOpen && (
        <BatchDownloadDialog
          tickers={watchlist.map((w) => w.ticker)}
          onClose={() => setBatchDialogOpen(false)}
        />
      )}
    </div>
  );

  return (
    <AuthGate>
      {appContent}
      <LogPanel />
      <ToastContainer />
    </AuthGate>
  );
}

