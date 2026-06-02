import { useMutation, useQueryClient } from "@tanstack/react-query";
import { startRun, cancelRun } from "../lib/api";
import { useUi } from "../store/ui";

interface Props { ticker: string; price?: number; changePct?: number; }

export function TickerHeader({ ticker, price, changePct }: Props) {
  const qc = useQueryClient();
  const activeRunId = useUi((s) => s.activeRunIdByTicker[ticker] ?? null);
  const setActiveRunIdForTicker = useUi((s) => s.setActiveRunIdForTicker);
  const setLastRunIdForTicker = useUi((s) => s.setLastRunIdForTicker);
  const clearActiveRunForTicker = useUi((s) => s.clearActiveRunForTicker);
  const clearBuffer = useUi((s) => s.clearBuffer);

  const start = useMutation({
    mutationFn: () => startRun(ticker),
    onSuccess: ({ run_id }) => {
      clearBuffer();
      // Mark this run as the active stream for the ticker AND as the
      // sticky "last run" so the buffer/decision panel can resolve to
      // it after the stream closes.
      setActiveRunIdForTicker(ticker, run_id);
      setLastRunIdForTicker(ticker, run_id);
      qc.invalidateQueries({ queryKey: ["runs", "list"] });
    },
  });

  const cancel = useMutation({
    mutationFn: () => cancelRun(activeRunId!),
    onSuccess: () => {
      // Optimistic clear: the server's run_failed will arrive over the
      // WS and is handled by useRunStream, but we don't want to leave
      // the UI showing "running" while that propagates.
      clearActiveRunForTicker(ticker);
    },
  });

  const isRunning = !!activeRunId;

  return (
    <div className="flex items-center justify-between mb-4">
      <div>
        <h2 className="text-2xl font-semibold">{ticker}</h2>
        <p className="text-sm text-slate-500">
          {price != null ? `$${price.toFixed(2)}` : "—"}
          {changePct != null && (
            <span className={changePct >= 0 ? "text-emerald-600 ml-2" : "text-rose-600 ml-2"}>
              {changePct >= 0 ? "+" : ""}{(changePct * 100).toFixed(2)}%
            </span>
          )}
        </p>
      </div>
      <div className="flex gap-2">
        <button
          disabled={isRunning || start.isPending}
          onClick={() => start.mutate()}
          className="px-3 py-1.5 text-sm font-medium rounded-md bg-blue-600 text-white disabled:opacity-50"
        >
          {start.isPending ? "Starting…" : "Run analysis"}
        </button>
        {isRunning && (
          <button
            onClick={() => cancel.mutate()}
            className="px-3 py-1.5 text-sm font-medium rounded-md border border-slate-300"
          >
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}
