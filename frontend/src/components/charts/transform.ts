/** Pure presentation transforms. Heikin-Ashi is a redraw of the same
 * bars, not new information — safe client-side; anything that feeds a
 * trading decision stays server-computed. */
import type { Bar } from "@/lib/api/types";

export function toHeikinAshi(bars: Bar[]): Bar[] {
  const out: Bar[] = [];
  let prevOpen = 0;
  let prevClose = 0;
  bars.forEach((bar, i) => {
    const close = (bar.open + bar.high + bar.low + bar.close) / 4;
    const open = i === 0 ? (bar.open + bar.close) / 2 : (prevOpen + prevClose) / 2;
    out.push({
      time: bar.time,
      open,
      close,
      high: Math.max(bar.high, open, close),
      low: Math.min(bar.low, open, close),
      volume: bar.volume,
    });
    prevOpen = open;
    prevClose = close;
  });
  return out;
}
