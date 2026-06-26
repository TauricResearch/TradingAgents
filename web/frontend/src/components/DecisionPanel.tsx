import type { RunDetail } from "../lib/api";

interface Props {
  action: "BUY" | "SELL" | "HOLD" | string;
  target: number | null;
  confidence: number;
  rationale: string;
  degraded?: boolean;
  run?: RunDetail | null;
}

export function DecisionPanel({ action, target, confidence, rationale, degraded }: Props) {
  const isBuy = action === "BUY";
  const isSell = action === "SELL";
  const actionColor = isBuy ? "text-emerald-400" : isSell ? "text-red-400" : "text-slate-400";
  const actionBg = isBuy ? "bg-emerald-500/10 border-emerald-500/25" : isSell ? "bg-red-500/10 border-red-500/25" : "bg-slate-700/30 border-slate-600/50";
  const accentBorder = isBuy ? "border-l-emerald-500" : isSell ? "border-l-red-500" : "border-l-slate-500";
  const progressColor = isBuy ? "bg-emerald-500" : isSell ? "bg-red-500" : "bg-slate-500";
  const pct = Math.max(0, Math.min(1, confidence)) * 100;
  return (
    <div
      className={`glass-panel mt-4 border-l-2 ${accentBorder} ${degraded ? "opacity-80" : ""}`}
      role="region"
      aria-label={`Decision: ${action}${target != null ? ` at $${target}` : ""}`}
    >
      <div className="flex items-center gap-3 mb-3">
        <span className={`tag ${actionBg} text-sm font-semibold ${actionColor}`} role="status" aria-label={`Action: ${action}`}>
          {isBuy && (
            <svg className="w-3.5 h-3.5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 10.5L12 3m0 0l7.5 7.5M12 3v18" />
            </svg>
          )}
          {isSell && (
            <svg className="w-3.5 h-3.5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 13.5L12 21m0 0l-7.5-7.5M12 21V3" />
            </svg>
          )}
          {action}
        </span>
        {target != null && <span className="text-lg data-text text-slate-300">@ ${target.toFixed(2)}</span>}
        <div className="flex-1" />
        {degraded && <span className="text-[10px] font-medium text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-md">degraded</span>}
      </div>
      <div className="flex items-center justify-between text-xs text-slate-500 mb-1.5">
        <span id="confidence-label">Confidence</span>
        <span className="data-text font-semibold text-slate-300" aria-labelledby="confidence-label">{pct.toFixed(0)}%</span>
      </div>
      <div className="progress-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className={`progress-fill ${progressColor}`} style={{ width: `${pct}%` }} />
      </div>
      <p className="text-sm text-slate-400 mt-3 whitespace-pre-wrap leading-relaxed">{rationale}</p>
    </div>
  );
}
