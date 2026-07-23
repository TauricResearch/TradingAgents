import { describe, expect, it } from "vitest";

import { buildGrid, verdictTone } from "../OptimizePanel";
import type { BacktestStrategy } from "@/lib/api/types";

const strategy: BacktestStrategy = {
  id: "trend_following_v1",
  description: "",
  params: [
    { name: "donchian_period", kind: "int", low: 10, high: 100, step: null, choices: [], default: 20 },
    { name: "trail_pct", kind: "float", low: 0.01, high: 0.1, step: 0.01, choices: [], default: 0.05 },
    { name: "allow_short", kind: "categorical", low: null, high: null, step: null, choices: ["yes", "no"], default: "yes" },
  ],
};

describe("buildGrid", () => {
  it("parses ints, floats and categoricals into a param_grid", () => {
    const grid = buildGrid(strategy, {
      donchian_period: "15, 20, 25",
      trail_pct: "0.03,0.05",
      allow_short: "yes,no",
    });
    expect(grid).toEqual({
      donchian_period: [15, 20, 25],
      trail_pct: [0.03, 0.05],
      allow_short: ["yes", "no"],
    });
  });

  it("rounds int params and drops non-numeric entries", () => {
    const grid = buildGrid(strategy, { donchian_period: "15.7, oops, 25" });
    expect(grid.donchian_period).toEqual([16, 25]);
  });

  it("omits blank params (they keep the strategy default)", () => {
    const grid = buildGrid(strategy, { donchian_period: "", trail_pct: "0.05" });
    expect(grid.donchian_period).toBeUndefined();
    expect(grid.trail_pct).toEqual([0.05]);
  });

  it("de-dupes repeated values so a trial never runs twice", () => {
    const grid = buildGrid(strategy, { donchian_period: "20,20,25" });
    expect(grid.donchian_period).toEqual([20, 25]);
  });

  it("returns an empty grid when nothing is filled or no strategy", () => {
    expect(buildGrid(strategy, {})).toEqual({});
    expect(buildGrid(undefined, { donchian_period: "20" })).toEqual({});
  });
});

describe("verdictTone", () => {
  it("flags a high PBO or low deflated Sharpe as bearish (don't deploy)", () => {
    expect(verdictTone(0.8, 1.2)).toBe("bear");
    expect(verdictTone(0.2, 0.4)).toBe("bear");
  });

  it("passes a config that clears both guards", () => {
    expect(verdictTone(0.2, 1.5)).toBe("default");
  });

  it("is neutral when the guards are unavailable", () => {
    expect(verdictTone(null, null)).toBe("neutral");
    expect(verdictTone(undefined, 1.5)).toBe("neutral");
  });
});
