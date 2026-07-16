import { afterEach, describe, expect, it, vi } from "vitest";

import {
  _resetForTests,
  _snapshotForTests,
  connectionState,
  recordSuccess,
  STALE_AFTER_SECONDS,
} from "../staleness";

afterEach(() => {
  _resetForTests();
  vi.useRealTimers();
});

describe("connectionState", () => {
  it("starts disconnected", () => {
    expect(connectionState().state).toBe("disconnected");
  });

  it("live within the threshold, stale after it", () => {
    vi.useFakeTimers();
    const t0 = Date.now();
    recordSuccess(t0);
    expect(connectionState(t0 + 5_000).state).toBe("live");
    const past = t0 + (STALE_AFTER_SECONDS + 1) * 1000;
    const result = connectionState(past);
    expect(result.state).toBe("stale");
    expect(result.ageSeconds).toBe(STALE_AFTER_SECONDS + 1);
  });

  it("recovers to live on the next success", () => {
    const t0 = Date.now();
    recordSuccess(t0 - 60_000);
    expect(connectionState(t0).state).toBe("stale");
    recordSuccess(t0);
    expect(connectionState(t0).state).toBe("live");
  });

  it("snapshot identity survives a same-second success burst", () => {
    // regression: a mount-time burst of recordSuccess calls (one per
    // resolving query) must NOT mint a new snapshot per call — that loops
    // useSyncExternalStore's commit consistency check into React #185
    vi.useFakeTimers();
    vi.setSystemTime(1_700_000_000_000); // clean second boundary: +200ms stays in-second
    const t0 = Date.now();
    recordSuccess(t0);
    const first = _snapshotForTests();
    for (let i = 1; i <= 200; i++) recordSuccess(t0 + i); // +1ms each, same second
    expect(_snapshotForTests()).toBe(first);
    // but a new SECOND is a real change and must produce a new snapshot
    recordSuccess(t0 + 1_000);
    expect(_snapshotForTests()).not.toBe(first);
  });
});
