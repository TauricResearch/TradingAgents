import { useCallback, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchWatchlist, fetchPrices, removeFromWatchlist, reorderWatchlist, updateWatchlistItem } from "../lib/api";
import { TickerRow } from "./TickerRow";
import { AddTickerCommand } from "./AddTickerCommand";
import { useUi } from "../store/ui";

type RunStatus = "idle" | "queued" | "running" | "done" | "errored";

function statusForTicker(_ticker: string, lastDecision: string | null): RunStatus {
  if (!lastDecision) return "idle";
  return "idle";
}

const GROUP_PALETTE = ["#38bdf8", "#fb923c", "#a78bfa", "#34d399", "#f472b6", "#fbbf24", "#f87171", "#2dd4bf"];

function groupColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return GROUP_PALETTE[Math.abs(hash) % GROUP_PALETTE.length];
}

export function WatchlistRail() {
  const qc = useQueryClient();
  const { data: watchlist = [] } = useQuery({ queryKey: ["watchlist"], queryFn: fetchWatchlist });
  const { data: prices = {} } = useQuery({ queryKey: ["prices"], queryFn: fetchPrices });
  const clearLast = useUi((s) => s.clearLastRunIdForTicker);
  const collapsedGroups = useUi((s) => s.watchlistCollapsedGroups);
  const setCollapsedGroup = useUi((s) => s.setWatchlistCollapsedGroup);

  const [dragTicker, setDragTicker] = useState<string | null>(null);

  const handleRemove = useCallback(async (ticker: string) => {
    try {
      await removeFromWatchlist(ticker);
    } catch {
      return;
    }
    clearLast(ticker);
    qc.invalidateQueries({ queryKey: ["watchlist"] });
  }, [qc, clearLast]);

  const handleGroupChange = useCallback(async (ticker: string, group: string | null) => {
    try {
      await updateWatchlistItem(ticker, { group });
    } catch {
      return;
    }
    qc.invalidateQueries({ queryKey: ["watchlist"] });
  }, [qc]);

  /* ---------- DnD ---------- */
  const handleDragStart = useCallback((_e: React.DragEvent, ticker: string) => {
    setDragTicker(ticker);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  const handleDrop = useCallback(async (_e: React.DragEvent, targetTicker: string) => {
    const sourceTicker = dragTicker;
    if (!sourceTicker || sourceTicker === targetTicker) {
      setDragTicker(null);
      return;
    }

    const ordered = watchlist.map((r) => r.ticker);
    const srcIdx = ordered.indexOf(sourceTicker);
    const tgtIdx = ordered.indexOf(targetTicker);
    if (srcIdx === -1 || tgtIdx === -1) {
      setDragTicker(null);
      return;
    }

    ordered.splice(srcIdx, 1);
    ordered.splice(ordered.indexOf(targetTicker), 0, sourceTicker);

    setDragTicker(null);

    try {
      await reorderWatchlist(ordered);
    } catch {
      return;
    }
    qc.invalidateQueries({ queryKey: ["watchlist"] });
  }, [dragTicker, watchlist, qc]);

  const handleDragEnd = useCallback(() => {
    setDragTicker(null);
  }, []);

  /* ---------- Group helpers ---------- */
  const grouped: Record<string, typeof watchlist> = {};
  const ungrouped: typeof watchlist = [];
  for (const row of watchlist) {
    if (row.group) {
      if (!grouped[row.group]) grouped[row.group] = [];
      grouped[row.group].push(row);
    } else {
      ungrouped.push(row);
    }
  }
  const groupNames = Object.keys(grouped).sort();

  const renderRow = useCallback((row: (typeof watchlist)[number]) => {
    const price = (prices as any)[row.ticker] || {};
    return (
      <TickerRow
        key={row.ticker}
        ticker={row.ticker}
        companyName={row.company_name}
        lastDecision={row.last_decision}
        sparkline={price.sparkline || []}
        status={statusForTicker(row.ticker, row.last_decision)}
        price={price.price}
        changePct={price.change_pct}
        stale={price.stale === true}
        onRemove={handleRemove}
        group={row.group}
        groupColor={row.group ? groupColor(row.group) : undefined}
        onGroupChange={handleGroupChange}
        dragHandleProps={{
          draggable: true,
          onDragStart: (e) => handleDragStart(e, row.ticker),
          onDragOver: handleDragOver,
          onDragEnd: handleDragEnd,
        }}
        onDrop={(e) => handleDrop(e, row.ticker)}
      />
    );
  }, [prices, handleRemove, handleGroupChange, handleDragStart, handleDragOver, handleDragEnd, handleDrop]);

  return (
    <aside className="w-64 border-r border-slate-800 bg-slate-900/50 backdrop-blur-sm flex flex-col h-screen overflow-hidden">
      <div className="shrink-0 px-4 py-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]" />
          <span className="text-xs font-semibold uppercase tracking-widest text-slate-400">Watchlist</span>
          <span className="text-[10px] text-slate-600 ml-auto">{watchlist.length}</span>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-0.5">
        {groupNames.map((name) => {
          const collapsed = collapsedGroups[name] ?? false;
          const gc = groupColor(name);
          return (
            <div key={name}>
              <button
                type="button"
                onClick={() => setCollapsedGroup(name, !collapsed)}
                className="w-full flex items-center gap-1.5 px-1 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500 hover:text-slate-300 transition-colors"
              >
                <span className={`transition-transform text-xs ${collapsed ? "" : "rotate-90"}`}>▸</span>
                <span
                  className="px-1.5 py-0.5 rounded-md text-[10px] leading-none"
                  style={{ backgroundColor: `${gc}18`, color: gc, border: `1px solid ${gc}30` }}
                >
                  {name}
                </span>
                <span className="text-slate-600 font-normal normal-case ml-auto">{grouped[name].length}</span>
              </button>
              {!collapsed && grouped[name].map(renderRow)}
            </div>
          );
        })}
        {ungrouped.length > 0 && (
          <div>
            {groupNames.length > 0 && (
              <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-600 px-1 py-1.5">
                Ungrouped
              </div>
            )}
            {ungrouped.map(renderRow)}
          </div>
        )}
        {watchlist.length === 0 && (
          <p className="text-xs text-slate-600 text-center py-8">Add tickers to get started</p>
        )}
      </div>
      <div className="shrink-0 border-t border-slate-800">
        <AddTickerCommand />
      </div>
    </aside>
  );
}
