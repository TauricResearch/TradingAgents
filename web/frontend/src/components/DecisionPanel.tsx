interface Props {
  action: "BUY" | "SELL" | "HOLD" | string;
  target: number | null;
  confidence: number;
  rationale: string;
  degraded?: boolean;
}

export function DecisionPanel({ action, target, confidence, rationale, degraded }: Props) {
  const actionColor = action === "BUY" ? "text-emerald-600" : action === "SELL" ? "text-rose-600" : "text-slate-600";
  const pct = Math.max(0, Math.min(1, confidence)) * 100;
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 mt-4">
      <div className="flex items-center gap-3 mb-2">
        <span className={`text-2xl font-semibold ${actionColor}`}>{action}</span>
        {target != null && <span className="text-lg text-slate-700">@ ${target.toFixed(2)}</span>}
        <div className="flex-1" />
        {degraded && <span className="text-xs text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded">degraded</span>}
      </div>
      <div className="text-xs text-slate-500 mb-1">Confidence</div>
      <div className="h-2 bg-slate-100 rounded">
        <div className="h-2 rounded bg-blue-500" style={{ width: `${pct}%` }} />
      </div>
      <p className="text-sm text-slate-700 mt-3 whitespace-pre-wrap">{rationale}</p>
    </div>
  );
}
