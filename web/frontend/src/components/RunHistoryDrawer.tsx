import { useQuery } from "@tanstack/react-query";
import { fetchRunDetail, type RunRow } from "../lib/api";

async function fetchRuns(): Promise<RunRow[]> {
  const r = await fetch("/api/runs?limit=50");
  if (!r.ok) throw new Error(`runs ${r.status}`);
  return r.json();
}

export function RunHistoryDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data: runs = [] } = useQuery({ queryKey: ["runs", "list"], queryFn: fetchRuns, enabled: open });

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
  const { data: detail } = useQuery({
    queryKey: ["run", run.id],
    queryFn: () => fetchRunDetail(run.id),
  });
  return (
    <details className="border-b border-slate-100 p-3">
      <summary className="cursor-pointer">
        <span className="text-sm font-medium">{run.ticker}</span>{" "}
        <span className="text-xs text-slate-500">#{run.id} · {run.status}</span>
        {run.decision_action && <span className="ml-2 text-xs">{run.decision_action}{run.decision_target ? ` @ $${run.decision_target}` : ""}</span>}
      </summary>
      <pre className="mt-2 text-xs text-slate-600 overflow-x-auto">
        {JSON.stringify(detail?.events.map((e) => ({ type: e.type, data: e.data })) ?? [], null, 2)}
      </pre>
    </details>
  );
}
