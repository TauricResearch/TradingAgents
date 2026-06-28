import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { History, ChevronDown, Download, X, RefreshCw, Trash2 } from "lucide-react";
import { deleteRun, deleteRuns, resumeRun, type RunRow } from "../lib/api";
import { runLabel } from "./TickerHeader";
import { useUi } from "../store/ui";
import DownloadFormatDialog from "./DownloadFormatDialog";

interface Props {
  ticker: string;
  runs: RunRow[];
  selectedRunId: string | null;
  onSelect: (runId: string | null) => void;
  disabled: boolean;
}

export function RunHistoryMenu({ ticker, runs, selectedRunId, onSelect, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [formatDialogOpen, setFormatDialogOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();

  const clearHistoricalRunForTicker = useUi((s) => s.clearHistoricalRunForTicker);
  const clearLastRunIdForTicker = useUi((s) => s.clearLastRunIdForTicker);

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
    onSuccess: () => { invalidateAfterDelete(); },
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
    const state = useUi.getState();
    for (const [t, lastId] of Object.entries(state.lastRunIdByTicker)) {
      if (t !== ticker) continue;
      if (lastId && !runs.some((r) => r.id === lastId)) {
        clearLastRunIdForTicker(t);
      }
    }
    clearHistoricalRunForTicker(ticker);
    qc.invalidateQueries({ queryKey: ["ticker-runs", ticker] });
    qc.invalidateQueries({ queryKey: ["runs", "list"] });
  }

  const checkedCount = checked.size;

  return (
    <div ref={containerRef} className="relative">
      <button
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        className="px-2 py-1.5 text-sm bg-slate-800 border border-slate-700 rounded-lg text-slate-300
                   hover:bg-slate-700 hover:border-slate-600 focus:outline-none focus:ring-2 focus:ring-sky-500/30
                   disabled:opacity-40 disabled:cursor-not-allowed transition-all flex items-center gap-1.5"
      >
        <History className="w-3.5 h-3.5 text-slate-500" />
        <span className="max-w-[200px] truncate">{currentLabel}</span>
        <ChevronDown className="w-3 h-3 text-slate-500 shrink-0" />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 z-50 min-w-[280px] sm:min-w-[360px] max-w-[90vw] sm:max-w-[480px] bg-slate-800 border border-slate-700 rounded-xl shadow-2xl overflow-hidden">
          <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700/60">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Run history ({runs.length})
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setFormatDialogOpen(true)}
                title="Download all data for this ticker"
                className="p-1 rounded text-slate-400 hover:text-sky-400 hover:bg-slate-700/50 transition-colors"
                aria-label="Download ticker data"
              >
                <Download className="w-4 h-4" />
              </button>
              <button onClick={closeAndReset} aria-label="Close" className="p-1 rounded text-slate-500 hover:text-slate-300 hover:bg-slate-700/50 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          <div className="max-h-[300px] overflow-y-auto">
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
                  <input
                    type="checkbox"
                    checked={checked.has(r.id)}
                    onChange={() => toggleChecked(r.id)}
                    onClick={(e) => e.stopPropagation()}
                    className="accent-sky-500 shrink-0"
                  />
                  <input
                    type="radio"
                    name={`run-radio-${ticker}`}
                    checked={isSelected}
                    onChange={() => { onSelect(r.id); closeAndReset(); }}
                    className="accent-sky-500 shrink-0"
                  />
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

                  {(r.status === "failed" || r.status === "cancelled") && (
                    <button
                      disabled={resume.isPending}
                      onClick={(e) => { e.stopPropagation(); resume.mutate(r.id); }}
                      className="shrink-0 sm:opacity-0 sm:group-hover:opacity-100 text-sky-400 hover:text-sky-300 
                                  disabled:opacity-30 transition-all p-1 rounded"
                      title="Resume this run"
                    >
                      <RefreshCw className="w-3.5 h-3.5" />
                    </button>
                  )}

                  <button
                    disabled={delOne.isPending}
                    onClick={(e) => { e.stopPropagation(); delOne.mutate(r.id); }}
                    className="shrink-0 sm:opacity-0 sm:group-hover:opacity-100 text-slate-500 hover:text-red-400 
                                disabled:opacity-30 transition-all p-1 rounded"
                    title="Delete this run"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            })}
          </div>

          {checkedCount > 0 && (
            <div className="flex items-center justify-between px-3 py-2 border-t border-slate-700/60 bg-slate-900/50">
              <span className="text-xs text-slate-400">{checkedCount} selected</span>
              <button
                disabled={delBulk.isPending}
                onClick={() => delBulk.mutate(Array.from(checked))}
                className="btn-danger text-xs"
              >
                {delBulk.isPending ? "Deleting..." : `Delete ${checkedCount}`}
              </button>
            </div>
          )}
        </div>
      )}

      {formatDialogOpen && (
        <DownloadFormatDialog ticker={ticker} onClose={() => setFormatDialogOpen(false)} />
      )}
    </div>
  );
}
