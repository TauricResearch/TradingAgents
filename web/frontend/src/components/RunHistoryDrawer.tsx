import { useQuery } from "@tanstack/react-query";
import { fetchTickerRuns, type RunRow } from "../lib/api";
import { useUi } from "../store/ui";
import { formatDuration } from "../lib/format";

export function RunHistoryDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const focused = useUi((s) => s.focusedTicker);
  const { data: runs = [] } = useQuery({
    queryKey: ["ticker-runs", focused],
    queryFn: () => (focused ? fetchTickerRuns(focused) : Promise.resolve([])),
    enabled: open && !!focused,
  });

  if (!open) return null;

  return (
    <div className="fixed inset-y-0 right-0 w-96 bg-white border-l border-slate-200 shadow-xl z-10">
      <div className="flex items-center justify-between p-3 border-b border-slate-200">
        <h3 className="font-semibold">Run history</h3>
        <button onClick={onClose} className="text-sm text-slate-500">Close</button>
      </div>
      <div className="overflow-y-auto h-full pb-12">
        {runs.map((r) => <RunRowItem key={r.id} run={r} />)}
      </div>
    </div>
  );
}

function RunRowItem({ run }: { run: RunRow }) {
  const model = run.deep_think_model ?? null;
  const price = run.start_price != null ? `$${run.start_price.toFixed(2)}` : null;
  const dur = run.total_duration_s != null ? formatDuration(run.total_duration_s * 1000) : null;
  return (
    <details className="border-b border-slate-100 p-3">
      <summary className="cursor-pointer">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">{run.ticker}</span>
          <span className="text-xs text-slate-500">#{run.id} · {run.status}</span>
        </div>
        {run.decision_action && (
          <div className="mt-1 text-xs">
            {run.decision_action}{run.decision_target ? ` @ $${run.decision_target}` : ""}
          </div>
        )}
        <div className="mt-1 text-[11px] text-slate-500 flex flex-wrap gap-x-2">
          {model && <span>{model}</span>}
          {price && <span>· {price}</span>}
          {dur && <span>· {dur}</span>}
        </div>
      </summary>
    </details>
  );
}
