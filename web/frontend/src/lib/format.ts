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
