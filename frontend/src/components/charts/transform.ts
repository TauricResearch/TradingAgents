/** Pure presentation transforms. Heikin-Ashi is a redraw of the same
 * bars, not new information — safe client-side; anything that feeds a
 * trading decision stays server-computed. */
import type { Bar } from "@/lib/api/types";

/** Running-max shortfall of an equity curve, as negative fractions
 * (0 → at peak, -0.05 → 5% under water). Pure presentation of the same
 * numbers the backend computed. */
export function toDrawdown(curve: number[]): number[] {
  let peak = -Infinity;
  return curve.map((value) => {
    if (value > peak) peak = value;
    return peak > 0 ? value / peak - 1 : 0;
  });
}

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
