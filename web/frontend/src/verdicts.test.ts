import { describe, it, expect } from "vitest";
import { barsInWindow, computeVerdict, computeStats, type Bar, type RunLike } from "./verdicts";

const t0 = "2026-06-01T12:00:00Z";
const delta1h = 60 * 60 * 1000;

function bar(t: string, c: number, o = c, h = c + 0.5, l = c - 0.5, v = 1000): Bar {
  return { t, o, h, l, c, v };
}

describe("barsInWindow", () => {
  it("returns bars whose t is in [start, start+delta]", () => {
    const bars = [
      bar("2026-06-01T11:00:00Z", 100), // before
      bar(t0, 100),                       // T
      bar("2026-06-01T12:30:00Z", 101),
      bar("2026-06-01T13:00:00Z", 102), // T+delta
      bar("2026-06-01T13:30:00Z", 103), // after
    ];
    const inWin = barsInWindow(bars, t0, delta1h, "2026-06-01T15:00:00Z");
    expect(inWin.map((b) => b.t)).toEqual([t0, "2026-06-01T12:30:00Z", "2026-06-01T13:00:00Z"]);
  });

  it("clips the window at nowIso", () => {
    const bars = [bar(t0, 100), bar("2026-06-01T12:30:00Z", 101), bar("2026-06-01T13:00:00Z", 102)];
    const inWin = barsInWindow(bars, t0, delta1h, "2026-06-01T12:45:00Z");
    expect(inWin.map((b) => b.t)).toEqual([t0, "2026-06-01T12:30:00Z"]);
  });

  it("returns an empty array for empty input or no bars in window", () => {
    expect(barsInWindow([], t0, delta1h, "2026-06-01T15:00:00Z")).toEqual([]);
    const far = [bar("2026-06-01T10:00:00Z", 100)];
    expect(barsInWindow(far, t0, delta1h, "2026-06-01T15:00:00Z")).toEqual([]);
  });
});

describe("computeVerdict", () => {
  const baseRun: RunLike = {
    id: "run-1", startedAt: t0,
    decisionAction: "BUY", decisionTarget: 110, startPrice: 100,
  };

  it("BUY with target: target_hit when max(high) >= target", () => {
    const win = [
      bar(t0, 100),
      bar("2026-06-01T12:30:00Z", 112, 110, 112.5, 110, 1000), // high 112.5 hits 110
      bar("2026-06-01T12:45:00Z", 108),
    ];
    const v = computeVerdict(baseRun, win, delta1h, 1.0, "2026-06-01T15:00:00Z");
    expect(v.status).toBe("right");
    expect(v.reason).toBe("target_hit");
    expect(v.targetHit).toBe(true);
    expect(v.maxHigh).toBe(112.5);
  });

  it("BUY with target: target_miss when max(high) < target", () => {
    const win = [bar(t0, 100), bar("2026-06-01T12:30:00Z", 103)];
    const v = computeVerdict(baseRun, win, delta1h, 1.0, "2026-06-01T15:00:00Z");
    expect(v.status).toBe("wrong");
    expect(v.reason).toBe("target_miss");
    expect(v.targetHit).toBe(false);
  });

  it("SELL with target: target_hit when min(low) <= target", () => {
    const run: RunLike = { ...baseRun, decisionAction: "SELL", decisionTarget: 92 };
    const win = [bar(t0, 100), bar("2026-06-01T12:30:00Z", 92, 93, 92, 91.5, 1000)];
    const v = computeVerdict(run, win, delta1h, 1.0, "2026-06-01T15:00:00Z");
    expect(v.status).toBe("right");
    expect(v.reason).toBe("target_hit");
    expect(v.minLow).toBe(91.5);
  });

  it("SELL with target: target_miss when min(low) > target", () => {
    const run: RunLike = { ...baseRun, decisionAction: "SELL", decisionTarget: 80 };
    const win = [bar(t0, 100), bar("2026-06-01T12:30:00Z", 95)];
    const v = computeVerdict(run, win, delta1h, 1.0, "2026-06-01T15:00:00Z");
    expect(v.status).toBe("wrong");
    expect(v.reason).toBe("target_miss");
  });

  it("HOLD within threshold is right (within_threshold)", () => {
    const run: RunLike = { ...baseRun, decisionAction: "HOLD", decisionTarget: null };
    const win = [bar(t0, 100), bar("2026-06-01T12:30:00Z", 100.5)]; // 0.5% ≤ 1.0
    const v = computeVerdict(run, win, delta1h, 1.0, "2026-06-01T15:00:00Z");
    expect(v.status).toBe("right");
    expect(v.reason).toBe("within_threshold");
    expect(v.pctMove).toBeCloseTo(0.5, 1);
  });

  it("HOLD over threshold is wrong (threshold_exceeded)", () => {
    const run: RunLike = { ...baseRun, decisionAction: "HOLD", decisionTarget: null };
    const win = [bar(t0, 100), bar("2026-06-01T12:30:00Z", 102)]; // 2.0% > 1.0
    const v = computeVerdict(run, win, delta1h, 1.0, "2026-06-01T15:00:00Z");
    expect(v.status).toBe("wrong");
    expect(v.reason).toBe("threshold_exceeded");
  });

  it("BUY no-target: close > start is right (direction); close < start is wrong", () => {
    const run: RunLike = { ...baseRun, decisionAction: "BUY", decisionTarget: null };
    expect(computeVerdict(run, [bar(t0, 100), bar("2026-06-01T12:30:00Z", 101)], delta1h, 1.0, "2026-06-01T15:00:00Z").status).toBe("right");
    expect(computeVerdict(run, [bar(t0, 100), bar("2026-06-01T12:30:00Z", 99)],  delta1h, 1.0, "2026-06-01T15:00:00Z").status).toBe("wrong");
  });

  it("SELL no-target: close < start is right (direction); close > start is wrong", () => {
    const run: RunLike = { ...baseRun, decisionAction: "SELL", decisionTarget: null };
    expect(computeVerdict(run, [bar(t0, 100), bar("2026-06-01T12:30:00Z", 99)],  delta1h, 1.0, "2026-06-01T15:00:00Z").status).toBe("right");
    expect(computeVerdict(run, [bar(t0, 100), bar("2026-06-01T12:30:00Z", 101)], delta1h, 1.0, "2026-06-01T15:00:00Z").status).toBe("wrong");
  });

  it("BUY/SELL no-target tie → unknown: tie", () => {
    const buy: RunLike = { ...baseRun, decisionAction: "BUY", decisionTarget: null };
    const sell: RunLike = { ...baseRun, decisionAction: "SELL", decisionTarget: null };
    const win = [bar(t0, 100), bar("2026-06-01T12:30:00Z", 100)];
    expect(computeVerdict(buy,  win, delta1h, 1.0, "2026-06-01T15:00:00Z").reason).toBe("tie");
    expect(computeVerdict(sell, win, delta1h, 1.0, "2026-06-01T15:00:00Z").reason).toBe("tie");
  });

  it("missing start_price → unknown: no_start_price", () => {
    const run: RunLike = { ...baseRun, startPrice: null };
    const v = computeVerdict(run, [], delta1h, 1.0, "2026-06-01T15:00:00Z");
    expect(v.status).toBe("unknown");
    expect(v.reason).toBe("no_start_price");
  });

  it("empty window → unknown: no_data", () => {
    const v = computeVerdict(baseRun, [], delta1h, 1.0, "2026-06-01T15:00:00Z");
    expect(v.status).toBe("unknown");
    expect(v.reason).toBe("no_data");
  });

  it("incomplete window (T+Δ > nowIso) → unknown: incomplete_window", () => {
    const v = computeVerdict(baseRun, [], delta1h, 1.0, "2026-06-01T12:30:00Z");
    expect(v.status).toBe("unknown");
    expect(v.reason).toBe("incomplete_window");
  });

  it("incomplete window flips to definite once nowIso passes T+Δ", () => {
    const run: RunLike = { ...baseRun, decisionTarget: null };
    const win = [bar(t0, 100), bar("2026-06-01T13:00:00Z", 105)];
    expect(computeVerdict(run, win, delta1h, 1.0, "2026-06-01T12:30:00Z").reason).toBe("incomplete_window");
    expect(computeVerdict(run, win, delta1h, 1.0, "2026-06-01T14:00:00Z").status).toBe("right");
  });

  it("defensive: unknown action → unknown: unknown_action", () => {
    const run: RunLike = { ...baseRun, decisionAction: "SOMETHING" };
    const v = computeVerdict(run, [], delta1h, 1.0, "2026-06-01T15:00:00Z");
    expect(v.status).toBe("unknown");
    expect(v.reason).toBe("unknown_action");
  });
});

describe("computeStats", () => {
  it("rightPct is null when no runs are scored", () => {
    const runs: RunLike[] = [
      { id: "n", startedAt: t0, decisionAction: "BUY", decisionTarget: 110, startPrice: 100 },
    ];
    const s = computeStats(runs, [], delta1h, 1.0, "2026-06-01T15:00:00Z");
    expect(s.right).toBe(0);
    expect(s.wrong).toBe(0);
    expect(s.unknown).toBe(1);
    expect(s.rightPct).toBeNull();
  });

  it("counts pending incomplete_window runs separately", () => {
    const runs: RunLike[] = [
      { id: "x", startedAt: t0, decisionAction: "BUY", decisionTarget: 110, startPrice: 100 },
      { id: "y", startedAt: t0, decisionAction: "BUY", decisionTarget: 110, startPrice: 100 },
    ];
    const win = [bar(t0, 100), bar("2026-06-01T12:30:00Z", 100.5, 100, 112, 100, 1000)];
    const s = computeStats(runs, win, delta1h, 1.0, "2026-06-01T12:15:00Z");
    expect(s.pending).toBe(2);
    expect(s.unknown).toBe(2);
    expect(s.right).toBe(0);
    expect(s.wrong).toBe(0);
    expect(s.rightPct).toBeNull();
  });

  it("aggregates per-action counts and rightPct = right/(right+wrong)", () => {
    const buyRight: RunLike = { id: "1", startedAt: t0, decisionAction: "BUY", decisionTarget: 110, startPrice: 100 };
    const buyWrong: RunLike = { id: "2", startedAt: t0, decisionAction: "BUY", decisionTarget: 110, startPrice: 100 };
    const winA = [bar(t0, 100), bar("2026-06-01T12:30:00Z", 100.5, 100, 112, 100, 1000)];  // hits
    const winB = [bar(t0, 100), bar("2026-06-01T12:30:00Z", 105, 100, 106, 105, 1000)];     // misses
    const sRight = computeStats([buyRight], winA, delta1h, 1.0, "2026-06-01T15:00:00Z");
    const sWrong = computeStats([buyWrong], winB, delta1h, 1.0, "2026-06-01T15:00:00Z");
    expect(sRight.right).toBe(1); expect(sRight.wrong).toBe(0);
    expect(sWrong.right).toBe(0); expect(sWrong.wrong).toBe(1);
    expect(sRight.byAction.BUY).toEqual({ right: 1, wrong: 0, unknown: 0 });
    expect(sWrong.byAction.BUY).toEqual({ right: 0, wrong: 1, unknown: 0 });
    expect(sRight.rightPct).toBe(1.0);
    expect(sWrong.rightPct).toBe(0.0);
  });
});
