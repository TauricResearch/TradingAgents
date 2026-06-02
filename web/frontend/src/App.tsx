import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchWatchlist, fetchPrices } from "./lib/api";
import { useUi } from "./store/ui";
import { useRunStream } from "./hooks/useRunStream";
import { WatchlistRail } from "./components/WatchlistRail";
import { TickerHeader } from "./components/TickerHeader";
import { StageGrid } from "./components/StageGrid";
import { LiveEventStream } from "./components/LiveEventStream";
import { DecisionPanel } from "./components/DecisionPanel";
import { RunHistoryDrawer } from "./components/RunHistoryDrawer";

export default function App() {
  const focused = useUi((s) => s.focusedTicker);
  const setFocused = useUi((s) => s.setFocusedTicker);
  const runId = useUi((s) => s.connectedRunId);
  const events = useUi((s) => s.eventBuffer);
  const { data: watchlist = [] } = useQuery({ queryKey: ["watchlist"], queryFn: fetchWatchlist });
  const { data: prices = {} } = useQuery({ queryKey: ["prices"], queryFn: fetchPrices });
  const [historyOpen, setHistoryOpen] = useState(false);

  useRunStream(runId);

  useEffect(() => {
    if (!focused && watchlist.length > 0) setFocused(watchlist[0].ticker);
  }, [watchlist, focused, setFocused]);

  if (!focused) {
    return (
      <div className="min-h-screen p-6">
        <p className="text-sm text-slate-500">Loading watchlist…</p>
      </div>
    );
  }

  const price = (prices as any)[focused] || {};
  const decisionEvent = [...events].reverse().find((e) => e.type === "decision");
  const decision = decisionEvent?.data as { action: string; target: number; rationale: string; confidence: number } | undefined;

  return (
    <div className="min-h-screen flex">
      <WatchlistRail />
      <main className="flex-1 p-6">
        <header className="flex items-center justify-between mb-4">
          <h1 className="text-lg font-semibold">TradingAgents</h1>
          <button onClick={() => setHistoryOpen(true)} className="text-sm text-blue-600">History</button>
        </header>
        <TickerHeader ticker={focused} price={price.price} changePct={price.change_pct} />
        <StageGrid />
        <LiveEventStream />
        {decision && (
          <DecisionPanel
            action={decision.action}
            target={decision.target ?? null}
            confidence={decision.confidence ?? 0}
            rationale={decision.rationale ?? ""}
          />
        )}
      </main>
      <RunHistoryDrawer open={historyOpen} onClose={() => setHistoryOpen(false)} />
    </div>
  );
}
