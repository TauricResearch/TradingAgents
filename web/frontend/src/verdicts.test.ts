import { describe, it, expect } from "vitest";
import { barsInWindow, computeVerdict, computeStats, findNearestBar, computeAccuracyCurve, computeDeltasFromRuns, ACCURACY_DELTAS, type Bar, type RunLike } from "./verdicts";

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

describe("findNearestBar", () => {
  it("returns the bar whose timestamp is closest to the target", () => {
    const bars = [
      bar("2026-06-01T12:00:00Z", 100),
      bar("2026-06-01T13:00:00Z", 101),
      bar("2026-06-01T14:00:00Z", 102),
    ];
    // target exactly at 13:30 → bar at 14:00 is 30m away, 13:00 is 30m away → 13:00 wins (first)
    expect(findNearestBar(bars, new Date("2026-06-01T13:30:00Z").getTime())!.t).toBe("2026-06-01T13:00:00Z");
    // target at 12:45 → 12:00 is 45m away, 13:00 is 15m away → 13:00 wins
    expect(findNearestBar(bars, new Date("2026-06-01T12:45:00Z").getTime())!.t).toBe("2026-06-01T13:00:00Z");
    // target exactly at a bar
    expect(findNearestBar(bars, new Date("2026-06-01T13:00:00Z").getTime())!.t).toBe("2026-06-01T13:00:00Z");
  });

  it("returns null for empty bars", () => {
    expect(findNearestBar([], 1000)).toBeNull();
  });

  it("handles single bar", () => {
    const bars = [bar("2026-06-01T12:00:00Z", 100)];
    expect(findNearestBar(bars, 0)!.t).toBe("2026-06-01T12:00:00Z");
    expect(findNearestBar(bars, 1e15)!.t).toBe("2026-06-01T12:00:00Z");
  });
});

describe("computeAccuracyCurve", () => {
  const t0 = "2026-06-01T12:00:00Z";

  function runWith(id: string, action: "BUY" | "SELL" | "HOLD", target: number | null, startPrice: number): RunLike {
    return { id, startedAt: t0, decisionAction: action, decisionTarget: target, startPrice };
  }

  it("returns one point per delta, filtering out unscored deltas", () => {
    const bars: Bar[] = [];
    const testDeltas = [5 * 60_000, 30 * 60_000];
    for (const d of testDeltas) {
      const t = new Date(new Date(t0).getTime() + d).toISOString().replace(/\.\d{3}Z$/, "Z");
      bars.push(bar(t, 105, 100, 106, 99, 1000));
    }
    const runs = [runWith("r1", "BUY", null, 100)];

    const curve = computeAccuracyCurve(runs, bars, testDeltas, 1.0, "2026-06-02T12:00:00Z");
    expect(curve.length).toBe(2);
    for (const p of curve) {
      expect(p.right).toBe(1);
      expect(p.wrong).toBe(0);
      expect(p.rightPct).toBe(1.0);
    }
  });

  it("omits deltas where no runs have scoring data", () => {
    const bars: Bar[] = [bar(t0, 100)];
    const runs = [runWith("r1", "BUY", null, 100)];
    const deltas = [5 * 60_000];
    const curve = computeAccuracyCurve(runs, bars, deltas, 1.0, "2026-06-02T12:00:00Z");
    expect(curve.length).toBe(0);
  });

  it("works with the full ACCURACY_DELTAS set", () => {
    const bars: Bar[] = [];
    for (const d of ACCURACY_DELTAS) {
      const t = new Date(new Date(t0).getTime() + d).toISOString().replace(/\.\d{3}Z$/, "Z");
      bars.push(bar(t, 105, 100, 106, 99, 1000));
    }
    const runs = [runWith("r1", "BUY", null, 100)];
    const curve = computeAccuracyCurve(runs, bars, ACCURACY_DELTAS, 1.0, "2028-01-01T00:00:00Z");
    expect(curve.length).toBe(ACCURACY_DELTAS.length);
    for (const p of curve) {
      expect(p.rightPct).toBe(1.0);
    }
  });

  it("respects holdThresholdPct", () => {
    const bars = [bar(new Date(new Date(t0).getTime() + 5 * 60_000).toISOString().replace(/\.\d{3}Z$/, "Z"), 100.2)];
    const runs = [runWith("r1", "HOLD", null, 100)];
    const curve = computeAccuracyCurve(runs, bars, [5 * 60_000], 0.5, "2026-06-02T12:00:00Z");
    expect(curve[0].right).toBe(1);
    expect(curve[0].rightPct).toBe(1.0);
  });
});

describe("computeDeltasFromRuns", () => {
  it("returns unique positive deltas from run-bar pairs", () => {
    const run: RunLike = { id: "r1", startedAt: t0, decisionAction: "BUY", decisionTarget: null, startPrice: 100 };
    const bars = [
      bar("2026-06-01T12:05:00Z", 101), // +5m
      bar("2026-06-01T13:00:00Z", 102), // +1h
    ];
    const result = computeDeltasFromRuns([run], bars, 10);
    expect(result).toEqual([5 * 60_000, 60 * 60_000]);
  });

  it("samples to maxPoints when there are more unique deltas", () => {
    const run: RunLike = { id: "r1", startedAt: t0, decisionAction: "BUY", decisionTarget: null, startPrice: 100 };
    const bars = Array.from({ length: 50 }, (_, i) =>
      bar(new Date(new Date(t0).getTime() + (i + 1) * 60_000).toISOString().replace(/\.\d{3}Z$/, "Z"), 100 + i)
    );
    const result = computeDeltasFromRuns([run], bars, 10);
    expect(result.length).toBe(10);
    expect(result[0]).toBe(60_000);
    expect(result[result.length - 1]).toBe(50 * 60_000);
  });

  it("returns empty array for no runs or no bars", () => {
    const run: RunLike = { id: "r1", startedAt: t0, decisionAction: "BUY", decisionTarget: null, startPrice: 100 };
    expect(computeDeltasFromRuns([], [], 100)).toEqual([]);
    expect(computeDeltasFromRuns([run], [], 100)).toEqual([]);
    expect(computeDeltasFromRuns([], [bar("2026-06-01T12:00:00Z", 100)], 100)).toEqual([]);
  });
});
