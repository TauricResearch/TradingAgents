/** Snap annotation times to exact bar times (LWC v5 requirement: a time
 * that is not in the series data renders nothing / returns null from
 * timeToCoordinate). Pure — vitest-covered. */

/** Greatest bar time <= t (binary search). Null when t precedes the first
 * bar — the annotation is off-range for the loaded window and is dropped
 * (it reappears when older bars are paged in). */
export function snapToBar(barTimes: number[], t: number): number | null {
  if (barTimes.length === 0 || t < barTimes[0]!) return null;
  let lo = 0;
  let hi = barTimes.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (barTimes[mid]! <= t) lo = mid;
    else hi = mid - 1;
  }
  return barTimes[lo]!;
}
