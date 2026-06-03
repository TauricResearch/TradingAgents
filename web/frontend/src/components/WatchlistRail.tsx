import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchWatchlist, fetchPrices, removeFromWatchlist } from "../lib/api";
import { TickerRow } from "./TickerRow";
import { AddTickerCommand } from "./AddTickerCommand";
import { useUi } from "../store/ui";

type RunStatus = "idle" | "queued" | "running" | "done" | "errored";

function statusForTicker(_ticker: string, lastDecision: string | null, events: any[]): RunStatus {
  if (!lastDecision) return "idle";
  const last = events.filter((e) => e.type === "run_started" || e.type === "run_finished" || e.type === "run_failed").pop();
  if (!last) return "idle";
  if (last.type === "run_started") return "running";
  if (last.type === "run_finished") return "done";
  return "errored";
}

export function WatchlistRail() {
  const qc = useQueryClient();
  const { data: watchlist = [] } = useQuery({ queryKey: ["watchlist"], queryFn: fetchWatchlist });
  const { data: prices = {} } = useQuery({ queryKey: ["prices"], queryFn: fetchPrices });
  const focused = useUi((s) => s.focusedTicker);
  const setFocused = useUi((s) => s.setFocusedTicker);
  const clearLast = useUi((s) => s.clearLastRunIdForTicker);

  const handleRemove = useCallback(async (ticker: string) => {
    try {
      await removeFromWatchlist(ticker);
    } catch {
      return;
    }
    clearLast(ticker);
    qc.invalidateQueries({ queryKey: ["watchlist"] });
    if (focused === ticker) {
      const next = watchlist.find((w) => w.ticker !== ticker);
      setFocused(next ? next.ticker : null);
    }
  }, [focused, watchlist, qc, clearLast, setFocused]);

  return (
    <aside className="w-64 border-r border-slate-200 p-2 h-screen overflow-y-auto">
      <div className="text-xs uppercase tracking-wide text-slate-500 px-2 py-1">Watchlist</div>
      {watchlist.map((row) => {
        const price = (prices as any)[row.ticker] || {};
        return (
          <TickerRow
            key={row.ticker}
            ticker={row.ticker}
            companyName={row.company_name}
            lastDecision={row.last_decision}
            sparkline={price.sparkline || []}
            status={statusForTicker(row.ticker, row.last_decision, [])}
            onRemove={handleRemove}
          />
        );
      })}
      <AddTickerCommand />
    </aside>
  );
}
