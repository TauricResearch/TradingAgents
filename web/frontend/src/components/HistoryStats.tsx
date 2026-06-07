import type { Stats } from "../verdicts";

export function HistoryStats({ stats }: { stats: Stats }) {
  const headline = stats.rightPct == null ? "—" : `${Math.round(stats.rightPct * 100)}%`;
  const scored = stats.right + stats.wrong;
  return (
    <div className="border-b border-slate-200 px-3 py-2 text-xs text-slate-700">
      <div className="font-medium text-slate-900">
        {stats.total} runs · {stats.right} right · {stats.wrong} wrong · {stats.pending} pending · {headline} right
      </div>
      {scored === 0 && (
        <div className="text-slate-500 mt-0.5">No scored runs at this Δ.</div>
      )}
      <div className="mt-1 flex flex-wrap gap-x-3">
        <span><strong className="text-slate-900">BUY</strong> {stats.byAction.BUY.right}/{stats.byAction.BUY.right + stats.byAction.BUY.wrong} right</span>
        <span><strong className="text-slate-900">SELL</strong> {stats.byAction.SELL.right}/{stats.byAction.SELL.right + stats.byAction.SELL.wrong} right</span>
        <span><strong className="text-slate-900">HOLD</strong> {stats.byAction.HOLD.right}/{stats.byAction.HOLD.right + stats.byAction.HOLD.wrong} right</span>
      </div>
    </div>
  );
}
