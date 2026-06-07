import type { Verdict } from "../verdicts";
import { actionColor } from "../verdicts";
import { fmtPct, fmtPrice, fmtTime } from "../lib/format";

export interface RunListItemProps {
  run: {
    id: string;
    started_at: string | null;
    decision_action: string | null;
    decision_target: number | null;
    start_price: number | null;
  };
  verdict: Verdict;
  selected: boolean;
  scale: "m" | "h" | "d";
  onClick: () => void;
}

function verdictBadge(v: Verdict): { glyph: string; tone: string; subtext: string } {
  if (v.status === "right") {
    return { glyph: "✓", tone: "text-green-700", subtext: v.reason === "within_threshold" ? "within" : "hit" };
  }
  if (v.status === "wrong") {
    return { glyph: "✗", tone: "text-red-700", subtext: v.reason === "threshold_exceeded" ? "exceeded" : "miss" };
  }
  if (v.reason === "incomplete_window") return { glyph: "?", tone: "text-slate-500", subtext: "pending" };
  if (v.reason === "no_data") return { glyph: "?", tone: "text-slate-500", subtext: "no data" };
  if (v.reason === "tie") return { glyph: "?", tone: "text-slate-500", subtext: "tie" };
  if (v.reason === "no_start_price") return { glyph: "?", tone: "text-slate-500", subtext: "no start price" };
  if (v.reason === "unknown_action") return { glyph: "?", tone: "text-slate-500", subtext: "unknown action" };
  return { glyph: "?", tone: "text-slate-500", subtext: "unknown" };
}

export function RunListItem({ run, verdict, selected, scale, onClick }: RunListItemProps) {
  const t = run.started_at ? new Date(run.started_at).getTime() : null;
  const badge = verdictBadge(verdict);
  const pct = verdict.pctMove;
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={`run-row-${run.id}`}
      className={`w-full text-left px-3 py-2 border-b border-slate-100 hover:bg-slate-50 ${
        selected ? "bg-slate-100 border-l-2 border-l-slate-700" : ""
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs text-slate-500 w-24 shrink-0">
            {t != null ? fmtTime(t, scale) : "—"}
          </span>
          <span
            className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded"
            style={{ color: actionColor(run.decision_action), border: `1px solid ${actionColor(run.decision_action)}` }}
          >
            {run.decision_action ?? "—"}
          </span>
          {run.start_price != null && (
            <span className="text-xs text-slate-700">${fmtPrice(run.start_price)}</span>
          )}
          {run.decision_target != null && run.decision_action !== "HOLD" && (
            <>
              <span className="text-xs text-slate-400">→</span>
              <span className="text-xs text-slate-700">${fmtPrice(run.decision_target)}</span>
            </>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {pct != null && (
            <span className={`text-xs font-mono ${pct >= 0 ? "text-green-700" : "text-red-700"}`}>
              {fmtPct(pct)}
            </span>
          )}
          <span className={`text-sm ${badge.tone}`} title={badge.subtext}>
            {badge.glyph}
          </span>
        </div>
      </div>
    </button>
  );
}
