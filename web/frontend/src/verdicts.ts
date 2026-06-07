/**
 * Pure verdict logic for the historical analysis chart.
 *
 * Zero React / UI imports. The drawer, chart, and run list all consume
 * the output of these functions; verdict rules live here and nowhere else.
 *
 * Coordinate convention: bar timestamps are ISO-8601 strings with a "Z"
 * suffix. The chart layer converts to ms numbers at its boundary; this
 * module never sees a Date or a number for time.
 */

export type Bar = { t: string; o: number; h: number; l: number; c: number; v: number };

export type Action = "BUY" | "SELL" | "HOLD";

export type VerdictReason =
  | "target_hit"            // BUY/SELL with target that was hit (right)
  | "target_miss"           // BUY/SELL with target that was missed (wrong)
  | "direction"             // no-target BUY/SELL, status carried by .status (right or wrong)
  | "within_threshold"      // HOLD: |pctMove| <= holdThresholdPct (right)
  | "threshold_exceeded"    // HOLD: |pctMove| > holdThresholdPct (wrong)
  | "incomplete_window"     // T + Δ > now (unknown, counted as pending)
  | "no_data"               // zero bars in window (unknown)
  | "tie"                   // no-target BUY/SELL with close == start_price (unknown)
  | "no_start_price"        // run is missing start_price (unknown)
  | "unknown_action";       // defensive: action is not BUY/SELL/HOLD (unknown)

export type VerdictStatus = "right" | "wrong" | "unknown";

export interface Verdict {
  runId: string;
  status: VerdictStatus;
  reason: VerdictReason;
  pctMove: number | null;     // signed % from T to last bar in window
  targetHit: boolean | null;  // null for HOLD, no-target BUY/SELL
  maxHigh: number | null;     // for BUY target context
  minLow: number | null;      // for SELL target context
  endPrice: number | null;    // close of the last bar in window
}

export interface RunLike {
  id: string;
  startedAt: string;
  decisionAction: Action | string | null;
  decisionTarget: number | null;
  startPrice: number | null;
}

export interface Stats {
  total: number;
  right: number;
  wrong: number;
  unknown: number;
  pending: number;            // unknown AND reason == "incomplete_window"
  rightPct: number | null;    // right / (right + wrong), null if counted == 0
  byAction: Record<"BUY" | "SELL" | "HOLD", { right: number; wrong: number; unknown: number }>;
}

function isoToMs(iso: string): number {
  return new Date(iso).getTime();
}

/**
 * Filter ``bars`` to those whose ``t`` falls in ``[start, start+delta]``.
 * Clipped at ``nowIso`` for in-flight windows. End-boundary is inclusive.
 */
export function barsInWindow(
  bars: Bar[],
  startIso: string,
  deltaMs: number,
  nowIso: string,
): Bar[] {
  if (bars.length === 0) return [];
  const startMs = isoToMs(startIso);
  const endMs = Math.min(startMs + deltaMs, isoToMs(nowIso));
  const out: Bar[] = [];
  for (const b of bars) {
    const t = isoToMs(b.t);
    if (t >= startMs && t <= endMs) out.push(b);
  }
  return out;
}

// ---- Action colors / tints (used by HistoryChart and RunListItem) ----

export const ACTION_COLORS: Record<Action, string> = {
  BUY: "#16a34a",   // green-600
  SELL: "#dc2626",  // red-600
  HOLD: "#6b7280",  // gray-500
};

export const ACTION_TINTS: Record<Action, string> = {
  BUY: "rgba(22, 163, 74, 0.10)",
  SELL: "rgba(220, 38, 38, 0.10)",
  HOLD: "rgba(107, 114, 128, 0.10)",
};

export function actionColor(action: string | null | undefined): string {
  if (action === "BUY" || action === "SELL" || action === "HOLD") return ACTION_COLORS[action];
  return "#94a3b8"; // slate-400, neutral
}

export function actionTint(action: string | null | undefined): string {
  if (action === "BUY" || action === "SELL" || action === "HOLD") return ACTION_TINTS[action];
  return "rgba(148, 163, 184, 0.10)";
}

// computeVerdict and computeStats are added in Tasks 12 and 13.
