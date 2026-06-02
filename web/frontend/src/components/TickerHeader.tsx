import { useMutation, useQueryClient } from "@tanstack/react-query";
import { startRun, cancelRun } from "../lib/api";
import { useUi } from "../store/ui";

interface Props { ticker: string; price?: number; changePct?: number; }

export function TickerHeader({ ticker, price, changePct }: Props) {
  const qc = useQueryClient();
  const connectedRunId = useUi((s) => s.connectedRunId);
  const setConnectedRunId = useUi((s) => s.setConnectedRunId);
  const clearBuffer = useUi((s) => s.clearBuffer);

  const start = useMutation({
    mutationFn: () => startRun(ticker),
    onSuccess: ({ run_id }) => {
      clearBuffer();
      setConnectedRunId(run_id);
      qc.invalidateQueries({ queryKey: ["runs", "list"] });
    },
  });

  const cancel = useMutation({
    mutationFn: () => cancelRun(connectedRunId!),
    onSuccess: () => {
      // runner emits run_failed with reason=cancelled; buffer will pick it up
    },
  });

  const isRunning = !!connectedRunId;

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
