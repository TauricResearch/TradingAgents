import { afterEach, describe, expect, it, vi } from "vitest";

import {
  _resetForTests,
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
});
