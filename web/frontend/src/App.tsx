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
      <div className="min-h-screen p-6">
        <p className="text-sm text-slate-500">Loading watchlist…</p>
      </div>
    );
  }

  const decisionEvent = [...events].reverse().find((e) => e.type === "decision");
  const decision = decisionEvent?.data as { action: string; target: number; rationale: string; confidence: number } | undefined;

  return (
    <div className="min-h-screen flex">
      <WatchlistRail />
      <main className="flex-1 p-6">
        <header className="flex items-center justify-between mb-4">
          <h1 className="text-lg font-semibold">TradingAgents</h1>
          {focused && (
            <button onClick={() => setHistoryOpen(true)} className="text-sm text-blue-600">History</button>
          )}
        </header>
        {focused ? (
          <>
            {showStaleBanner && (
              <div
                data-testid="stale-ticker-banner"
                role="alert"
                className="mb-4 flex items-center justify-between gap-4 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900"
              >
                <span>
                  <strong className="font-semibold">{focused}</strong> is not available
                  on Yahoo Finance, so price and history are unavailable.
                </span>
                <span className="flex items-center gap-3 shrink-0">
                  <button
                    onClick={handleRemoveFocused}
                    data-testid="stale-ticker-remove"
                    className="rounded bg-amber-700 px-2 py-1 text-xs font-medium text-white hover:bg-amber-800"
                  >
                    Remove from watchlist
                  </button>
                  <button
                    onClick={() => setDismissedStaleBanner(focused)}
                    className="text-amber-700 hover:text-amber-900"
                    aria-label="Dismiss"
                  >
                    ×
                  </button>
                </span>
              </div>
            )}
            <TickerHeader ticker={focused} price={price.price} changePct={price.change_pct} stale={priceStale} />
            <RunTimeline />
            <LiveEventStream />
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
          <div className="mt-12 text-center text-slate-500">
            <p className="text-base">Your watchlist is empty.</p>
            <p className="text-sm mt-1">Use “+ Add ticker” in the rail on the left to get started.</p>
          </div>
        )}
      </main>
      {focused && historyOpen && (
        <HistoricalAnalysisDrawer ticker={focused} onClose={() => setHistoryOpen(false)} />
      )}
    </div>
  );
}
