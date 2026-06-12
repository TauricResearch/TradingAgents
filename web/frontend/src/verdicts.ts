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

// ---- Accuracy-curve types and functions ----

export type AccuracyPoint = {
  delta: number;
  total: number;
  right: number;
  wrong: number;
  unknown: number;
  rightPct: number | null;
};

/** Fixed set of delta horizons for the accuracy curve. */
export const ACCURACY_DELTAS: number[] = [
  5 * 60_000,               // 5m
  15 * 60_000,              // 15m
  30 * 60_000,              // 30m
  60 * 60_000,              // 1h
  2 * 60 * 60_000,          // 2h
  4 * 60 * 60_000,          // 4h
  8 * 60 * 60_000,          // 8h
  24 * 60 * 60_000,         // 1d
  3 * 24 * 60 * 60_000,     // 3d
  7 * 24 * 60 * 60_000,     // 1w
  14 * 24 * 60 * 60_000,    // 2w
  30 * 24 * 60 * 60_000,    // 1mo (approx)
  90 * 24 * 60 * 60_000,    // 3mo
  182 * 24 * 60 * 60_000,   // 6mo
  365 * 24 * 60 * 60_000,   // 1y
];

/**
 * Compute a verdict for a run using the single bar nearest to T+Δ.
 * Thin wrapper around `computeVerdict` — finds the closest bar to the
 * target time and passes it as a single-element window.
 */
export function computeVerdictNearestPrice(
  run: RunLike,
  bars: Bar[],
  deltaMs: number,
  holdThresholdPct: number,
  nowIso: string,
): Verdict {
  const targetTimeMs = isoToMs(run.startedAt) + deltaMs;
  const nearestBar = findNearestBar(bars, targetTimeMs);
  const windowBars = nearestBar ? [nearestBar] : [];
  return computeVerdict(run, windowBars, deltaMs, holdThresholdPct, nowIso);
}

/**
 * Compute the accuracy curve: for each delta horizon, compute aggregate
 * stats across all runs using nearest-price evaluation.
 *
 * Deltas where no runs have scoring data (right + wrong === 0) are
 * omitted from the result array.
 */
export function computeAccuracyCurve(
  runs: RunLike[],
  bars: Bar[],
  deltas: number[],
  holdThresholdPct: number,
  nowIso: string,
): AccuracyPoint[] {
  const out: AccuracyPoint[] = [];
  for (const delta of deltas) {
    let right = 0, wrong = 0, unknown = 0;
    for (const run of runs) {
      const v = computeVerdictNearestPrice(run, bars, delta, holdThresholdPct, nowIso);
      if (v.status === "right") right++;
      else if (v.status === "wrong") wrong++;
      else unknown++;
    }
    if (right + wrong === 0) continue;
    const rightPct = right / (right + wrong);
    out.push({ delta, total: runs.length, right, wrong, unknown, rightPct });
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

export function computeVerdict(
  run: RunLike,
  windowBars: Bar[],
  deltaMs: number,
  holdThresholdPct: number,
  nowIso: string,
): Verdict {
  const base: Pick<Verdict, "pctMove" | "targetHit" | "maxHigh" | "minLow" | "endPrice"> = {
    pctMove: null, targetHit: null, maxHigh: null, minLow: null, endPrice: null,
  };

  const action = run.decisionAction;
  if (action !== "BUY" && action !== "SELL" && action !== "HOLD") {
    return { runId: run.id, status: "unknown", reason: "unknown_action", ...base };
  }
  if (run.startPrice == null) {
    return { runId: run.id, status: "unknown", reason: "no_start_price", ...base };
  }
  const startMs = isoToMs(run.startedAt);
  if (startMs + deltaMs > isoToMs(nowIso)) {
    return { runId: run.id, status: "unknown", reason: "incomplete_window", ...base };
  }
  if (windowBars.length === 0) {
    return { runId: run.id, status: "unknown", reason: "no_data", ...base };
  }

  const maxHigh = windowBars.reduce((m, b) => Math.max(m, b.h), -Infinity);
  const minLow = windowBars.reduce((m, b) => Math.min(m, b.l), Infinity);
  const endPrice = windowBars[windowBars.length - 1].c;
  const pctMove = ((endPrice - run.startPrice) / run.startPrice) * 100;
  const filled = { pctMove, targetHit: null, maxHigh, minLow, endPrice };

  if (action === "HOLD") {
    if (Math.abs(pctMove) <= holdThresholdPct) {
      return { runId: run.id, status: "right", reason: "within_threshold", ...filled };
    }
    return { runId: run.id, status: "wrong", reason: "threshold_exceeded", ...filled };
  }

  if (run.decisionTarget != null) {
    if (action === "BUY") {
      const hit = maxHigh >= run.decisionTarget;
      return { runId: run.id, status: hit ? "right" : "wrong", reason: hit ? "target_hit" : "target_miss", ...filled, targetHit: hit };
    }
    const hit = minLow <= run.decisionTarget;
    return { runId: run.id, status: hit ? "right" : "wrong", reason: hit ? "target_hit" : "target_miss", ...filled, targetHit: hit };
  }

  // No-target BUY/SELL: direction rule with tie protection.
  if (endPrice === run.startPrice) {
    return { runId: run.id, status: "unknown", reason: "tie", ...filled };
  }
  const up = endPrice > run.startPrice;
  const right = action === "BUY" ? up : !up;
  return { runId: run.id, status: right ? "right" : "wrong", reason: "direction", ...filled };
}

/**
 * Find the bar whose timestamp is closest to `targetTimeMs`.
 * Returns null for an empty array.
 */
export function findNearestBar(bars: Bar[], targetTimeMs: number): Bar | null {
  if (bars.length === 0) return null;
  let best = bars[0];
  let bestDist = Math.abs(isoToMs(bars[0].t) - targetTimeMs);
  for (let i = 1; i < bars.length; i++) {
    const dist = Math.abs(isoToMs(bars[i].t) - targetTimeMs);
    if (dist < bestDist) {
      bestDist = dist;
      best = bars[i];
    }
  }
  return best;
}

export function computeStats(
  runs: RunLike[],
  bars: Bar[],
  deltaMs: number,
  holdThresholdPct: number,
  nowIso: string,
): Stats {
  const byAction: Stats["byAction"] = {
    BUY:  { right: 0, wrong: 0, unknown: 0 },
    SELL: { right: 0, wrong: 0, unknown: 0 },
    HOLD: { right: 0, wrong: 0, unknown: 0 },
  };
  let right = 0, wrong = 0, unknown = 0, pending = 0;

  for (const run of runs) {
    const windowBars = barsInWindow(bars, run.startedAt, deltaMs, nowIso);
    const v = computeVerdict(run, windowBars, deltaMs, holdThresholdPct, nowIso);

    if (v.status === "right") right++;
    else if (v.status === "wrong") wrong++;
    else unknown++;

    if (v.reason === "incomplete_window") pending++;

    const action = run.decisionAction;
    if (action === "BUY" || action === "SELL" || action === "HOLD") {
      const bucket = byAction[action];
      if (v.status === "right") bucket.right++;
      else if (v.status === "wrong") bucket.wrong++;
      else bucket.unknown++;
    }
  }

  const counted = right + wrong;
  const rightPct = counted === 0 ? null : right / counted;

  return { total: runs.length, right, wrong, unknown, pending, rightPct, byAction };
}
