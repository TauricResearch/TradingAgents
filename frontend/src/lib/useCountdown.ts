/** Live countdown seconds to an ISO instant (review R2.3): the API's
 * seconds_until is a snapshot of fetch time, and rendering it verbatim
 * showed "in 1h 9m" for an event two hours past. This ticks locally from
 * the timestamp between refetches. */
import { useEffect, useReducer } from "react";

const TICK_MS = 30_000;

export function useCountdown(atIso: string | null | undefined): number | null {
  const [, tick] = useReducer((n: number) => n + 1, 0);
  useEffect(() => {
    if (!atIso) return;
    const id = setInterval(tick, TICK_MS);
    return () => clearInterval(id);
  }, [atIso]);
  if (!atIso) return null;
  const at = Date.parse(atIso);
  if (Number.isNaN(at)) return null;
  return Math.floor((at - Date.now()) / 1000);
}

/** An event this far past is no longer "next" — hide it and let the next
 * refetch surface the following one. */
export function countdownExpired(seconds: number | null): boolean {
  return seconds != null && seconds < -15 * 60;
}
