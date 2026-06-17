import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteRun, deleteRuns, resumeRun, type RunRow } from "../lib/api";
import { runLabel } from "./TickerHeader";
import { useUi } from "../store/ui";

interface Props {
  ticker: string;
  runs: RunRow[];
  selectedRunId: string | null; // null = "Latest (live)"
  onSelect: (runId: string | null) => void;
  disabled: boolean;
}

export function RunHistoryMenu({ ticker, runs, selectedRunId, onSelect, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const containerRef = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();

  const clearHistoricalRunForTicker = useUi((s) => s.clearHistoricalRunForTicker);
  const clearLastRunIdForTicker = useUi((s) => s.clearLastRunIdForTicker);

  // Click-outside handler
  useEffect(() => {
    if (!open) return;
    const onMouseDown = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, [open]);

  const closeAndReset = useCallback(() => {
    setOpen(false);
    setChecked(new Set());
  }, []);

  const toggleChecked = (runId: string) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(runId)) {
        next.delete(runId);
      } else {
        next.add(runId);
      }
      return next;
    });
  };

  const currentLabel = selectedRunId
    ? runs.find((r) => r.id === selectedRunId)
      ? runLabel(runs.find((r) => r.id === selectedRunId)!)
      : selectedRunId.slice(0, 16)
    : "Latest (live)";

  const setActiveRunIdForTicker = useUi((s) => s.setActiveRunIdForTicker);
  const setLastRunIdForTicker = useUi((s) => s.setLastRunIdForTicker);
  const clearBuffer = useUi((s) => s.clearBuffer);

  const delOne = useMutation({
    mutationFn: (runId: string) => deleteRun(runId),
    onSuccess: () => {
      invalidateAfterDelete();
    },
  });

  const delBulk = useMutation({
    mutationFn: (runIds: string[]) => deleteRuns(runIds),
    onSuccess: () => {
      invalidateAfterDelete();
      setChecked(new Set());
    },
  });

  const resume = useMutation({
    mutationFn: (runId: string) => resumeRun(runId),
    onSuccess: ({ run_id }) => {
      clearBuffer();
      clearHistoricalRunForTicker(ticker);
      setActiveRunIdForTicker(ticker, run_id);
      setLastRunIdForTicker(ticker, run_id);
      closeAndReset();
      qc.invalidateQueries({ queryKey: ["ticker-runs", ticker] });
      qc.invalidateQueries({ queryKey: ["runs", "list"] });
    },
  });

  function invalidateAfterDelete() {
    // Clear any local references that may point to now-deleted runs
    const state = useUi.getState();
    for (const [t, lastId] of Object.entries(state.lastRunIdByTicker)) {
      if (t !== ticker) continue;
      if (lastId && !runs.some((r) => r.id === lastId)) {
        clearLastRunIdForTicker(t);
      }
    }
    // The selected run might have been deleted — switch back to "live"
    clearHistoricalRunForTicker(ticker);
    qc.invalidateQueries({ queryKey: ["ticker-runs", ticker] });
    qc.invalidateQueries({ queryKey: ["runs", "list"] });
  }

  const checkedCount = checked.size;

  return (
    <div ref={containerRef} className="relative">
      {/* Trigger button */}
      <button
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        className="px-2 py-1.5 text-sm bg-slate-800 border border-slate-700 rounded-lg text-slate-300
                   hover:bg-slate-700 hover:border-slate-600 focus:outline-none focus:ring-2 focus:ring-sky-500/30
                   disabled:opacity-40 disabled:cursor-not-allowed transition-all flex items-center gap-1.5"
      >
        <svg className="w-3.5 h-3.5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span className="max-w-[200px] truncate">{currentLabel}</span>
        <svg className="w-3 h-3 text-slate-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Dropdown panel */}
      {open && (
        <div className="absolute right-0 top-full mt-1 z-50 min-w-[360px] max-w-[480px] bg-slate-800 border border-slate-700 rounded-xl shadow-2xl overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700/60">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Run history ({runs.length})
            </span>
            <button onClick={closeAndReset} className="text-slate-500 hover:text-slate-300 text-lg leading-none px-1">&times;</button>
          </div>

          {/* Run list */}
          <div className="max-h-[300px] overflow-y-auto">
            {/* "Latest (live)" row */}
            <label
              className={`flex items-center gap-2 px-3 py-2 cursor-pointer transition-colors text-sm ${
                selectedRunId === null ? "bg-sky-500/10 text-sky-300" : "text-slate-300 hover:bg-slate-700/50"
              }`}
            >
              <input
                type="radio"
                name={`run-radio-${ticker}`}
                checked={selectedRunId === null}
                onChange={() => { onSelect(null); closeAndReset(); }}
                className="accent-sky-500 shrink-0"
              />
              <span className="font-medium">Latest (live)</span>
              <span className="ml-auto text-[10px] text-slate-500">Current view</span>
            </label>

            {runs.map((r) => {
              const isSelected = r.id === selectedRunId;
              return (
                <div
                  key={r.id}
                  className={`group flex items-center gap-1.5 px-3 py-1.5 transition-colors text-sm ${
                    isSelected ? "bg-sky-500/10" : "hover:bg-slate-700/50"
                  }`}
                >
                  {/* Checkbox for bulk selection */}
                  <input
                    type="checkbox"
                    checked={checked.has(r.id)}
                    onChange={() => toggleChecked(r.id)}
                    onClick={(e) => e.stopPropagation()}
                    className="accent-sky-500 shrink-0"
                  />

                  {/* Radio for single selection */}
                  <input
                    type="radio"
                    name={`run-radio-${ticker}`}
                    checked={isSelected}
                    onChange={() => { onSelect(r.id); closeAndReset(); }}
                    className="accent-sky-500 shrink-0"
                  />

                  {/* Run label (clicking selects) */}
                  <span
                    onClick={() => { onSelect(r.id); closeAndReset(); }}
                    className="flex-1 min-w-0 cursor-pointer truncate text-slate-300 py-0.5"
                    title={runLabel(r)}
                  >
                    {runLabel(r)}
                    {r.status === "running" && (
                      <span className="ml-1.5 inline-block w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse align-middle" />
                    )}
                    {r.status === "failed" && (
                      <span className="ml-1.5 text-[10px] text-red-400 font-medium">failed</span>
                    )}
                  </span>

                  {/* Per-row resume button for failed/cancelled runs */}
                  {(r.status === "failed" || r.status === "cancelled") && (
                    <button
                      disabled={resume.isPending}
                      onClick={(e) => {
                        e.stopPropagation();
                        resume.mutate(r.id);
                      }}
                      className="shrink-0 opacity-0 group-hover:opacity-100 text-sky-400 hover:text-sky-300 
                                  disabled:opacity-30 transition-all text-base leading-none p-1"
                      title="Resume this run"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                    </button>
                  )}

                  {/* Per-row delete button */}
                  <button
                    disabled={delOne.isPending}
                    onClick={(e) => {
                      e.stopPropagation();
                      delOne.mutate(r.id);
                    }}
                    className="shrink-0 opacity-0 group-hover:opacity-100 text-slate-500 hover:text-red-400 
                                disabled:opacity-30 transition-all text-base leading-none px-1"
                    title="Delete this run"
                  >
                    ×
                  </button>
                </div>
              );
            })}
          </div>

          {/* Bulk delete bar */}
          {checkedCount > 0 && (
            <div className="flex items-center justify-between px-3 py-2 border-t border-slate-700/60 bg-slate-900/50">
              <span className="text-xs text-slate-400">{checkedCount} selected</span>
              <button
                disabled={delBulk.isPending}
                onClick={() => delBulk.mutate(Array.from(checked))}
                className="btn-danger text-xs"
              >
                {delBulk.isPending ? "Deleting…" : `Delete ${checkedCount}`}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
