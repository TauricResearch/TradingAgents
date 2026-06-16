import { useCallback, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchWatchlist, fetchPrices, removeFromWatchlist, reorderWatchlist, updateWatchlistItem, addToWatchlist, ApiError } from "../lib/api";
import { TickerRow } from "./TickerRow";
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
  const { data: prices = {} } = useQuery({ queryKey: ["prices"], queryFn: fetchPrices, refetchInterval: 2_000 });
  const clearLast = useUi((s) => s.clearLastRunIdForTicker);
  const setFocusedTicker = useUi((s) => s.setFocusedTicker);
  const collapsedGroups = useUi((s) => s.watchlistCollapsedGroups);
  const setCollapsedGroup = useUi((s) => s.setWatchlistCollapsedGroup);

  const [dragTicker, setDragTicker] = useState<string | null>(null);
  const [filterTicker, setFilterTicker] = useState("");
  const [addingTicker, setAddingTicker] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

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
      const updated = await reorderWatchlist(ordered);
      qc.setQueryData(["watchlist"], updated);
    } catch {
      return;
    }
  }, [dragTicker, watchlist, qc]);

  const handleDragEnd = useCallback(() => {
    setDragTicker(null);
  }, []);

  const handleAddFromFilter = useCallback(async () => {
    const ticker = filterTicker.trim().toUpperCase();
    if (!ticker) return;
    setAddingTicker(true);
    setAddError(null);
    try {
      await addToWatchlist(ticker, "", "");
      setFilterTicker("");
      setAddError(null);
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    } catch (e) {
      if (e instanceof ApiError) {
        const detail = (e.body as { detail?: { error?: string } } | null)?.detail;
        if (e.status === 400 && detail?.error === "ticker_not_found") {
          setAddError(`"${ticker}" was not found on Yahoo Finance.`);
        } else if (e.status === 409) {
          setAddError(`"${ticker}" is already in the watchlist.`);
          setFilterTicker("");
        } else {
          setAddError(`Could not add "${ticker}". Try again.`);
        }
      } else {
        setAddError(`Could not add "${ticker}". Try again.`);
      }
    } finally {
      setAddingTicker(false);
    }
  }, [filterTicker, qc]);

  /* ---------- Filter ---------- */
  const lowerFilter = filterTicker.toLowerCase();
  const filteredWatchlist = filterTicker
    ? watchlist.filter(
        (r) =>
          r.ticker.toLowerCase().includes(lowerFilter) ||
          (r.company_name && r.company_name.toLowerCase().includes(lowerFilter)),
      )
    : watchlist;

  /* ---------- Group helpers ---------- */
  const grouped: Record<string, typeof watchlist> = {};
  const ungrouped: typeof watchlist = [];
  for (const row of filteredWatchlist) {
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
          <span className="text-[10px] text-slate-600 ml-auto">
            {filterTicker ? `${filteredWatchlist.length}/${watchlist.length}` : watchlist.length}
          </span>
        </div>
        <div className="relative mt-2">
          <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-600 pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
          </svg>
          <input
            type="text"
            value={filterTicker}
            onChange={(e) => { setFilterTicker(e.target.value); setAddError(null); }}
            onKeyDown={(e) => {
              if (e.key !== "Enter" || !filterTicker) return;
              if (filteredWatchlist.length === 1) {
                setFocusedTicker(filteredWatchlist[0].ticker);
                setFilterTicker("");
                setAddError(null);
              } else if (filteredWatchlist.length === 0 && watchlist.length > 0) {
                handleAddFromFilter();
              }
            }}
            placeholder="Search ticker…"
            className="w-full bg-slate-800/60 border border-slate-700/50 rounded-md pl-7 pr-7 py-1.5 text-xs text-slate-300 placeholder-slate-500 outline-none focus:border-slate-600 focus:bg-slate-800 transition-colors"
          />
          {filterTicker && (
            <button
              type="button"
              onClick={() => { setFilterTicker(""); setAddError(null); }}
              className="absolute right-1.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
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
        {filteredWatchlist.length === 0 && watchlist.length === 0 && (
          <p className="text-xs text-slate-500 text-center py-8">Add tickers to get started</p>
        )}
        {filteredWatchlist.length === 0 && watchlist.length > 0 && filterTicker && (
          <div className="flex flex-col items-center py-6 px-4">
            <p className="text-xs text-slate-500 mb-3">
              No tickers match &ldquo;{filterTicker}&rdquo;
            </p>
            <button
              type="button"
              disabled={addingTicker}
              onClick={handleAddFromFilter}
              className="flex items-center gap-1.5 text-xs font-medium text-sky-400 hover:text-sky-300 disabled:text-slate-600 transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              {addingTicker ? "Adding…" : `Add ${filterTicker.toUpperCase()} to watchlist`}
            </button>
            {addError && <p className="text-xs text-red-400 mt-2 text-center" role="alert">{addError}</p>}
          </div>
        )}
      </div>
      
    </aside>
  );
}
