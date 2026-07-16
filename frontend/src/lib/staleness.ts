/** Global staleness (ports ALERT-01 from the legacy page): any successful
 * fetch or SSE event bumps lastSuccess; the strip flips to STALE past 12s
 * and DISCONNECTED when nothing has ever landed. */
import { useSyncExternalStore } from "react";

export const STALE_AFTER_SECONDS = 12;

let lastSuccess = 0;
const listeners = new Set<() => void>();

export function recordSuccess(at = Date.now()) {
  lastSuccess = at;
  listeners.forEach((l) => l());
}

export type ConnState = "live" | "stale" | "disconnected";

export function connectionState(now = Date.now()): {
  state: ConnState;
  ageSeconds: number;
  lastSuccess: number;
} {
  if (!lastSuccess) return { state: "disconnected", ageSeconds: 0, lastSuccess: 0 };
  // clamp: a success stamped a few ms ahead of `now` (clock read order)
  // must read as age 0, not -1 — negative flicker churns the snapshot
  const ageSeconds = Math.max(0, Math.floor((now - lastSuccess) / 1000));
  return {
    state: ageSeconds > STALE_AFTER_SECONDS ? "stale" : "live",
    ageSeconds,
    lastSuccess,
  };
}

let ticker: ReturnType<typeof setInterval> | null = null;

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (!ticker) ticker = setInterval(() => listeners.forEach((l) => l()), 1000);
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && ticker) {
      clearInterval(ticker);
      ticker = null;
    }
  };
}

// snapshot must be referentially stable between changes — and stable at
// SECOND granularity: recordSuccess fires on every query success, so a
// mount-time burst (Trade page resolves ~10 queries in one flush) would
// otherwise mint a new snapshot per fetch and loop useSyncExternalStore's
// commit consistency check into React #185 (the production Trade crash).
// lastSuccess is only ever displayed as a wall-clock time, so same-second
// updates are invisible and must not churn the reference.
let cached = connectionState();
function snapshot() {
  const next = connectionState();
  if (
    next.state !== cached.state ||
    next.ageSeconds !== cached.ageSeconds ||
    Math.floor(next.lastSuccess / 1000) !== Math.floor(cached.lastSuccess / 1000)
  ) {
    cached = next;
  }
  return cached;
}

export function useConnectionState() {
  return useSyncExternalStore(subscribe, snapshot);
}

/** test hooks */
export function _resetForTests() {
  lastSuccess = 0;
  cached = connectionState();
}
export function _snapshotForTests() {
  return snapshot();
}
