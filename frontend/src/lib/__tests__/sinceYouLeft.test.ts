import { describe, expect, it } from "vitest";

import { computeStanceFlips } from "../sinceYouLeft";

const SINCE = new Date("2026-07-16T12:00:00Z");

function run(symbol: string, action: string | null, at: string, id = "r") {
  return { run_id: id, symbol, action, started_at: at };
}

describe("stance flips since marker", () => {
  it("reports a per-symbol change of mind", () => {
    const flips = computeStanceFlips(
      [
        run("XAUUSD", "SELL", "2026-07-16T10:00:00Z"),
        run("XAUUSD", "HOLD", "2026-07-16T13:00:00Z", "new1"),
        run("BTC-USD", "HOLD", "2026-07-16T09:00:00Z"),
        run("BTC-USD", "HOLD", "2026-07-16T14:00:00Z"),
      ],
      SINCE,
    );
    expect(flips).toEqual([
      { symbol: "XAUUSD", from: "SELL", to: "HOLD", run_id: "new1" },
    ]);
  });

  it("uses the LATEST stance on each side of the marker", () => {
    const flips = computeStanceFlips(
      [
        run("XAUUSD", "BUY", "2026-07-16T08:00:00Z"),
        run("XAUUSD", "SELL", "2026-07-16T11:00:00Z"),
        run("XAUUSD", "HOLD", "2026-07-16T13:00:00Z"),
        run("XAUUSD", "SELL", "2026-07-16T15:00:00Z", "latest"),
      ],
      SINCE,
    );
    // last before marker = SELL, latest after = SELL -> no flip
    expect(flips).toEqual([]);
  });

  it("rejected runs (no action) are not a stance", () => {
    const flips = computeStanceFlips(
      [
        run("XAUUSD", "SELL", "2026-07-16T10:00:00Z"),
        run("XAUUSD", null, "2026-07-16T13:00:00Z"),
      ],
      SINCE,
    );
    expect(flips).toEqual([]);
  });

  it("no prior stance means nothing to flip from", () => {
    const flips = computeStanceFlips(
      [run("BTC-USD", "BUY", "2026-07-16T13:00:00Z")],
      SINCE,
    );
    expect(flips).toEqual([]);
  });
});
