/** Format a duration in milliseconds for compact display.
 *
 *  < 1s  -> "X ms"
 *  < 60s -> "X.Ys"  (always one decimal)
 *  >= 60s -> "Xm Ys"
 *  null/undefined/<=0 -> "—"
 */
export function formatDuration(ms: number | null | undefined): string {
  if (ms == null || ms <= 0) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const totalSec = Math.floor(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}m ${s}s`;
}

/** Snap a Δ value to the nearest "named" horizon and format it.
 *
 *  < 1h   → "Xm"
 *  < 1d   → "Xh"
 *  < 1y   → "Xd"
 *  >= 1y  → "Xy" (rounded to whole years)
 */
export function fmtDelta(deltaMs: number): string {
  const min = 5 * 60_000;
  const hour = 60 * 60_000;
  const day = 24 * hour;
  const year = 365 * day;
  if (deltaMs < hour) return `${Math.max(1, Math.round(deltaMs / min))}m`;
  if (deltaMs < day) {
    const h = Math.round(deltaMs / hour);
    return `${h}h`;
  }
  if (deltaMs < year) {
    const d = Math.round(deltaMs / day);
    return `${d}d`;
  }
  const y = Math.round(deltaMs / year);
  return `${y}y`;
}

/** Format a price for axis tick labels: 2 decimals, no $ sign. */
export function fmtPrice(p: number): string {
  if (p == null || Number.isNaN(p)) return "—";
  return p.toFixed(2);
}

/** Format a signed percentage with a leading sign and 1 decimal. */
export function fmtPct(p: number | null | undefined): string {
  if (p == null || Number.isNaN(p)) return "—";
  const s = p.toFixed(1);
  return p > 0 ? `+${s}%` : `${s}%`;
}

/** Format an ms timestamp for a chart x-axis tick.
 *
 *  ``scale`` controls the granularity:
 *    "m"  (≤ 1d)  → "HH:MM"
 *    "h"  (≤ 60d) → "MMM d HH:MM"
 *    "d"  (> 60d) → "MMM d"
 */
export function fmtTime(ms: number, scale: "m" | "h" | "d"): string {
  const d = new Date(ms);
  if (scale === "d") {
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }
  if (scale === "h") {
    const date = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    const time = d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
    return `${date} ${time}`;
  }
  return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
}
