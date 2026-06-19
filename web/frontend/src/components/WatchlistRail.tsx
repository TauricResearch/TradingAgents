import { useCallback, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchWatchlist, fetchPrices, removeFromWatchlist, reorderWatchlist, updateWatchlistItem, addToWatchlist, getAccuracyLeaderboard, ApiError } from "../lib/api";
import { TickerRow } from "./TickerRow";
import { useUi } from "../store/ui";

type RunStatus = "idle" | "queued" | "running" | "done" | "errored";

function statusForTicker(_ticker: string, lastDecision: string | null): RunStatus {
  if (!lastDecision) return "idle";
  return "idle";
}

const GROUP_PALETTE = ["#38bdf8", "#fb923c", "#a78bfa", "#34d399", "#f472b6", "#fbbf24", "#f87171", "#2dd4bf"];

function groupColor(name: string, customColors?: Record<string, string>): string {
  if (customColors?.[name]) return customColors[name];
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
  const { data: accuracyData } = useQuery({
    queryKey: ["ticker-agent", "leaderboard"],
    queryFn: getAccuracyLeaderboard,
    refetchInterval: 30000,
    staleTime: 10000,
  });
  const clearLast = useUi((s) => s.clearLastRunIdForTicker);
  const setFocusedTicker = useUi((s) => s.setFocusedTicker);
  const collapsedGroups = useUi((s) => s.watchlistCollapsedGroups);
  const setCollapsedGroup = useUi((s) => s.setWatchlistCollapsedGroup);
  const customGroupColors = useUi((s) => s.customGroupColors);
  const setCustomGroupColor = useUi((s) => s.setCustomGroupColor);
  const removeCustomGroupColor = useUi((s) => s.removeCustomGroupColor);
  const groupOrder = useUi((s) => s.groupOrder);
  const setGroupOrder = useUi((s) => s.setGroupOrder);

  const [dragTicker, setDragTicker] = useState<string | null>(null);
  const [dragGroup, setDragGroup] = useState<string | null>(null);
  const [filterTicker, setFilterTicker] = useState("");
  const [addingTicker, setAddingTicker] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [sortMode, setSortMode] = useState<"default" | "accuracy">("default");

  // Group inline editing state
  const [editingGroup, setEditingGroup] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [confirmDeleteGroup, setConfirmDeleteGroup] = useState<string | null>(null);
  const [creatingGroup, setCreatingGroup] = useState(false);
  const [newGroupName, setNewGroupName] = useState("");
  const [groupDropTarget, setGroupDropTarget] = useState<string | null>(null);

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

  /* ---------- DnD (reorder) ---------- */
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
    setDragGroup(null);
    setGroupDropTarget(null);
  }, []);

  /* ---------- DnD (group assignment) ---------- */
  const handleGroupDrop = useCallback((group: string | null) => {
    const ticker = dragTicker;
    setGroupDropTarget(null);
    setDragTicker(null);
    if (!ticker) return;
    handleGroupChange(ticker, group);
  }, [dragTicker, handleGroupChange]);

  /* ---------- Group drag-reorder ---------- */
  const handleGroupDragStart = useCallback((_e: React.DragEvent, name: string) => {
    setDragGroup(name);
    _e.dataTransfer.effectAllowed = "move";
  }, []);

  const handleGroupReorder = useCallback((source: string, target: string) => {
    if (source === target) return;
    setGroupDropTarget(null);
    setDragGroup(null);
    const idx = groupOrder.indexOf(source);
    const tgtIdx = groupOrder.indexOf(target);
    if (idx === -1 || tgtIdx === -1) return;
    const next = [...groupOrder];
    next.splice(idx, 1);
    next.splice(next.indexOf(target), 0, source);
    setGroupOrder(next);
  }, [groupOrder, setGroupOrder]);

  /* ---------- Group rename / delete / create ---------- */
  const renameMutation = useMutation({
    mutationFn: async ({ oldName, newName }: { oldName: string; newName: string }) => {
      const tickers = (grouped[oldName] ?? []);
      for (const row of tickers) {
        await updateWatchlistItem(row.ticker, { group: newName });
      }
    },
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["watchlist"] });
      setEditingGroup(null);
      if (customGroupColors[variables.oldName]) {
        setCustomGroupColor(variables.newName, customGroupColors[variables.oldName]);
        removeCustomGroupColor(variables.oldName);
      }
    },
  });

  const deleteGroupMutation = useMutation({
    mutationFn: async (groupName: string) => {
      const tickers = (grouped[groupName] ?? []);
      for (const row of tickers) {
        await updateWatchlistItem(row.ticker, { group: null });
      }
    },
    onSuccess: (_data, groupName) => {
      removeCustomGroupColor(groupName);
      setGroupOrder(groupOrder.filter((n) => n !== groupName));
      qc.invalidateQueries({ queryKey: ["watchlist"] });
      setConfirmDeleteGroup(null);
    },
  });

  const handleStartRename = (name: string) => {
    setEditingGroup(name);
    setEditName(name);
  };

  const handleRename = () => {
    const trimmed = editName.trim();
    if (!editingGroup || !trimmed || trimmed === editingGroup) {
      setEditingGroup(null);
      return;
    }
    const idx = groupOrder.indexOf(editingGroup);
    if (idx !== -1) {
      const next = [...groupOrder];
      next[idx] = trimmed;
      setGroupOrder(next);
    }
    renameMutation.mutate({ oldName: editingGroup, newName: trimmed });
  };

  const handleCreateGroup = () => {
    const trimmed = newGroupName.trim();
    if (!trimmed) return;
    setCreatingGroup(false);
    setNewGroupName("");
    if (!customGroupColors[trimmed]) {
      setCustomGroupColor(trimmed, groupColor(trimmed));
    }
    if (!groupOrder.includes(trimmed)) {
      setGroupOrder([...groupOrder, trimmed]);
    }
  };

  const cycleGroupColor = (name: string) => {
    const current = customGroupColors[name] || groupColor(name);
    const idx = GROUP_PALETTE.indexOf(current);
    const next = GROUP_PALETTE[(idx + 1) % GROUP_PALETTE.length];
    if (next === groupColor(name)) {
      removeCustomGroupColor(name);
    } else {
      setCustomGroupColor(name, next);
    }
  };

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

  /* ---------- Filter & Sort ---------- */
  const lowerFilter = filterTicker.toLowerCase();
  const scoreMap = useMemo(() => {
    if (!accuracyData?.scores) return new Map<string, number>();
    const m = new Map<string, number>();
    for (const [t, s] of Object.entries(accuracyData.scores as Record<string, Record<string, unknown>>)) {
      const pct = s.accuracy_pct as number | undefined;
      if (pct != null) m.set(t, pct);
    }
    return m;
  }, [accuracyData]);

  let filteredWatchlist = filterTicker
    ? watchlist.filter(
        (r) =>
          r.ticker.toLowerCase().includes(lowerFilter) ||
          (r.company_name && r.company_name.toLowerCase().includes(lowerFilter)),
      )
    : [...watchlist];

  if (sortMode === "accuracy") {
    filteredWatchlist.sort((a, b) => {
      const aPct = scoreMap.get(a.ticker) ?? -1;
      const bPct = scoreMap.get(b.ticker) ?? -1;
      return bPct - aPct;
    });
  }

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
  const rawGroupNames = Array.from(new Set([...Object.keys(grouped), ...Object.keys(customGroupColors)]));
  const groupNames = useMemo(() => {
    const ordered = (groupOrder || []).filter((n) => rawGroupNames.includes(n));
    const rest = rawGroupNames.filter((n) => !ordered.includes(n)).sort();
    return [...ordered, ...rest];
  }, [rawGroupNames, groupOrder]);

  // Initialize groupOrder if empty
  if (groupOrder.length === 0 && rawGroupNames.length > 0) {
    setGroupOrder(rawGroupNames.sort());
  }

  const renderRow = useCallback((row: (typeof watchlist)[number]) => {
    const price = (prices[row.ticker] as Record<string, unknown>) ?? {};
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
        groupColor={row.group ? groupColor(row.group, customGroupColors) : undefined}
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
  }, [prices, handleRemove, handleGroupChange, handleDragStart, handleDragOver, handleDragEnd, handleDrop, customGroupColors]);

  const mobileSidebarOpen = useUi((s) => s.mobileSidebarOpen);
  const setMobileSidebarOpen = useUi((s) => s.setMobileSidebarOpen);

  return (
    <>
      <aside
        className={`
          fixed md:static inset-y-0 left-0 z-40
          w-72 md:w-64
          border-r border-slate-800 bg-slate-900/95 md:bg-slate-900/50 backdrop-blur-sm
          flex flex-col h-screen overflow-hidden
          transition-transform duration-300 ease-out
          ${mobileSidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}
        `}
      >
        <div className="md:hidden shrink-0 flex items-center justify-between px-4 py-2 border-b border-slate-800 safe-area-top">
          <span className="text-xs font-semibold uppercase tracking-widest text-slate-400">Watchlist</span>
          <button
            onClick={() => setMobileSidebarOpen(false)}
            className="p-1 hover:bg-slate-700/50 rounded-lg text-slate-500 hover:text-slate-300 transition-colors"
            aria-label="Close watchlist"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="shrink-0 px-4 py-3 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]" />
            <span className="text-xs font-semibold uppercase tracking-widest text-slate-400">Watchlist</span>
            <button
              type="button"
              onClick={() => setSortMode(sortMode === "accuracy" ? "default" : "accuracy")}
              className={`text-[10px] font-medium px-1.5 py-0.5 rounded transition-colors ${
                sortMode === "accuracy"
                  ? "text-sky-300 bg-sky-500/10 border border-sky-500/20"
                  : "text-slate-600 hover:text-slate-400"
              }`}
              title={sortMode === "accuracy" ? "Sorted by accuracy — click for default order" : "Sort by accuracy"}
            >
              {sortMode === "accuracy" ? "By Accuracy" : "Default"}
            </button>
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
              onChange={(e) => { setFilterTicker(e.target.value.toUpperCase()); setAddError(null); }}
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
          {/* Create group inline input */}
          {creatingGroup && (
            <div className="flex items-center gap-2 px-2 py-1.5 bg-slate-800/40 rounded-lg border border-slate-700/50">
              <input
                autoFocus
                type="text"
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleCreateGroup();
                  if (e.key === "Escape") { setCreatingGroup(false); setNewGroupName(""); }
                }}
                placeholder="Group name"
                className="flex-1 bg-slate-900 border border-slate-700 rounded px-1.5 py-1 text-xs text-slate-200 focus:outline-none focus:border-sky-500/50 placeholder-slate-500"
              />
              <button type="button" disabled={!newGroupName.trim()} onClick={handleCreateGroup} className="text-[10px] text-sky-400 hover:text-sky-300 font-medium disabled:opacity-30">Create</button>
              <button type="button" onClick={() => { setCreatingGroup(false); setNewGroupName(""); }} className="text-[10px] text-slate-500 hover:text-slate-300">Cancel</button>
            </div>
          )}

          {/* Group headers */}
          {groupNames.map((name) => {
            const collapsed = collapsedGroups[name] ?? false;
            const gc = customGroupColors[name] || groupColor(name);
            const tickers = grouped[name] ?? [];
            const isEmpty = tickers.length === 0;
            const isOver = groupDropTarget === name;

            return (
              <div key={name}>
                <div
                  draggable
                  onDragStart={(e) => handleGroupDragStart(e, name)}
                  onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = dragGroup ? "move" : "move"; }}
                  onDragEnter={() => setGroupDropTarget(name)}
                  onDragLeave={() => setGroupDropTarget(null)}
                  onDrop={() => {
                    if (dragGroup) {
                      handleGroupReorder(dragGroup, name);
                    } else {
                      handleGroupDrop(name);
                    }
                  }}
                  className={`flex items-center gap-1 px-1 py-1.5 rounded transition-colors ${
                    isOver ? "bg-sky-500/10 ring-1 ring-sky-500/40" : ""
                  } ${isEmpty ? "opacity-60" : ""}`}
                >
                  {/* Drag grip */}
                  <svg className="w-3 h-3 text-slate-600 cursor-grab active:cursor-grabbing shrink-0" viewBox="0 0 24 24" fill="currentColor"><circle cx="8" cy="6" r="1.5"/><circle cx="16" cy="6" r="1.5"/><circle cx="8" cy="12" r="1.5"/><circle cx="16" cy="12" r="1.5"/><circle cx="8" cy="18" r="1.5"/><circle cx="16" cy="18" r="1.5"/></svg>

                  {/* Color dot */}
                  <button
                    type="button"
                    onClick={() => cycleGroupColor(name)}
                    className="w-3 h-3 rounded-full shrink-0 border border-white/10 hover:scale-125 transition-transform"
                    style={{ backgroundColor: gc }}
                    title="Click to change color"
                  />

                  {/* Expand toggle */}
                  <button
                    type="button"
                    onClick={() => setCollapsedGroup(name, !collapsed)}
                    className="text-slate-500 hover:text-slate-300 transition-colors text-[10px]"
                  >
                    <span className={`inline-block transition-transform ${collapsed ? "" : "rotate-90"}`}>▸</span>
                  </button>

                  {/* Group name (or rename input) */}
                  {editingGroup === name ? (
                    <div className="flex-1 flex items-center gap-1 min-w-0">
                      <input
                        autoFocus
                        type="text"
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleRename();
                          if (e.key === "Escape") setEditingGroup(null);
                        }}
                        className="flex-1 bg-slate-900 border border-slate-700 rounded px-1.5 py-0.5 text-[10px] text-slate-200 focus:outline-none focus:border-sky-500/50"
                      />
                      <button type="button" disabled={renameMutation.isPending} onClick={handleRename} className="text-[10px] text-sky-400 hover:text-sky-300 font-medium disabled:opacity-30">Save</button>
                      <button type="button" onClick={() => setEditingGroup(null)} className="text-[10px] text-slate-500 hover:text-slate-300">Cancel</button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleStartRename(name)}
                      className="flex-1 text-left text-[10px] font-semibold uppercase tracking-wider text-slate-500 hover:text-slate-300 transition-colors truncate"
                      title="Click to rename group"
                    >
                      {name}
                    </button>
                  )}

                  {/* Count */}
                  <span className="text-[10px] text-slate-600">{tickers.length}</span>

                  {/* Delete */}
                  {confirmDeleteGroup === name ? (
                    <div className="flex items-center gap-0.5">
                      <button type="button" disabled={deleteGroupMutation.isPending} onClick={() => deleteGroupMutation.mutate(name)} className="text-[10px] text-red-400 hover:text-red-300 font-medium disabled:opacity-30">Confirm</button>
                      <button type="button" onClick={() => setConfirmDeleteGroup(null)} className="text-[10px] text-slate-500 hover:text-slate-300">Cancel</button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setConfirmDeleteGroup(name)}
                      className="text-slate-500 hover:text-red-400 transition-colors text-xs leading-none px-0.5"
                      title="Delete group"
                    >
                      ×
                    </button>
                  )}
                </div>

                {isEmpty && (
                  <div className="text-[10px] text-slate-600 italic px-2 py-1 text-center">
                    Drag a ticker here
                  </div>
                )}

                {!collapsed && tickers.map(renderRow)}
              </div>
            );
          })}

          {/* Add group button */}
          {!creatingGroup && (
            <button
              type="button"
              onClick={() => setCreatingGroup(true)}
              className="w-full flex items-center gap-1.5 px-1 py-1 text-[10px] text-slate-500 hover:text-sky-400 transition-colors"
            >
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              Add group
            </button>
          )}

          {/* Ungrouped section */}
          {ungrouped.length > 0 && (
            <div
              onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; }}
              onDragEnter={() => setGroupDropTarget("__ungrouped__")}
              onDragLeave={() => setGroupDropTarget(null)}
              onDrop={() => handleGroupDrop(null)}
              className={`rounded transition-colors ${
                groupDropTarget === "__ungrouped__" ? "bg-sky-500/10 ring-1 ring-sky-500/40" : ""
              }`}
            >
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
    </>
  );
}
