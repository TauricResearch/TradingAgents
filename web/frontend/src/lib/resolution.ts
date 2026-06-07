/**
 * Candle resolution: the time bucket each candle on the chart represents.
 * "auto" means "use the API's resolution unchanged" (no client-side
 * resampling). The other values trigger a re-binning of the API bars
 * into coarser buckets.
 */
export type CandleResolution =
  | "auto"
  | "1m"
  | "5m"
  | "15m"
  | "1h"
  | "4h"
  | "1d"
  | "1w";

/** Width of one time bucket in ms. */
export const RESOLUTION_MS: Record<Exclude<CandleResolution, "auto">, number> = {
  "1m": 60_000,
  "5m": 5 * 60_000,
  "15m": 15 * 60_000,
  "1h": 60 * 60_000,
  "4h": 4 * 60 * 60_000,
  "1d": 24 * 60 * 60_000,
  "1w": 7 * 24 * 60 * 60_000,
};

/**
 * Pick a tick-format scale for a resolution. m = minute-precision
 * ("HH:MM"), h = hour-precision ("MMM d HH:MM"), d = day-precision
 * ("MMM d"). 1d and 1w both use the day scale.
 */
export function scaleFor(
  resolution: Exclude<CandleResolution, "auto">,
): "m" | "h" | "d" {
  if (resolution === "1d" || resolution === "1w") return "d";
  if (resolution === "1h" || resolution === "4h") return "h";
  return "m"; // 1m, 5m, 15m
}
