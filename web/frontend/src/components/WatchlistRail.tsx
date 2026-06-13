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
  const clearLast = useUi((s) => s.clearLastRunIdForTicker);

  const handleRemove = useCallback(async (ticker: string) => {
    try {
      await removeFromWatchlist(ticker);
    } catch {
      return;
    }
    clearLast(ticker);
    qc.invalidateQueries({ queryKey: ["watchlist"] });
  }, [qc, clearLast]);

  return (
    <aside className="w-64 border-r border-slate-800 bg-slate-900/50 backdrop-blur-sm flex flex-col h-screen overflow-hidden">
      <div className="shrink-0 px-4 py-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]" />
          <span className="text-xs font-semibold uppercase tracking-widest text-slate-400">Watchlist</span>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-0.5">
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
              price={price.price}
              changePct={price.change_pct}
              stale={price.stale === true}
              onRemove={handleRemove}
            />
          );
        })}
      </div>
      <div className="shrink-0 border-t border-slate-800">
        <AddTickerCommand />
      </div>
    </aside>
  );
}
