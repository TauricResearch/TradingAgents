import { describe, expect, it } from "vitest";

import { computePositionPlan } from "../positionPlan";

const BASE = {
  side: "long" as const,
  entry: 4000,
  stop: 3980,
  target: 4040,
  equity: 100_000,
  riskPct: 1,
};

describe("position plan calculator", () => {
  it("sizes so entry→stop loses exactly riskPct of equity", () => {
    const plan = computePositionPlan(BASE);
    // risk budget 1000, per-unit risk 20 -> 50 units... notional 200k > 10% cap
    expect(plan.valid).toBe(true);
    expect(plan.capped).toBe(true); // 50 * 4000 = 200k > 10k cap
    expect(plan.quantity).toBeCloseTo(2.5); // 10k / 4000
    expect(plan.riskAmount).toBeCloseTo(50); // capped size risks less
    expect(plan.rr).toBeCloseTo(2);
    expect(plan.breakevenWinRate).toBeCloseTo(1 / 3);
  });

  it("uncapped when the notional stays under the position cap", () => {
    const plan = computePositionPlan({
      ...BASE,
      entry: 100,
      stop: 90,
      target: 130,
      maxPositionPct: 100,
    });
    // budget 1000 / 10 risk = 100 units, notional 10k, 10% of equity
    expect(plan.capped).toBe(false);
    expect(plan.quantity).toBeCloseTo(100);
    expect(plan.riskAmount).toBeCloseTo(1000);
    expect(plan.rewardAmount).toBeCloseTo(3000);
    expect(plan.pctOfEquity).toBeCloseTo(10);
  });

  it("mirrors for shorts", () => {
    const plan = computePositionPlan({
      ...BASE,
      side: "short",
      entry: 4037.27,
      stop: 4049.88,
      target: 4011.99,
      maxPositionPct: 100,
    });
    expect(plan.valid).toBe(true);
    expect(plan.rr).toBeCloseTo(25.28 / 12.61, 2);
  });

  it("rejects wrong-sided geometry with a reason", () => {
    const plan = computePositionPlan({ ...BASE, stop: 4010 });
    expect(plan.valid).toBe(false);
    expect(plan.reason).toMatch(/stop below entry/);
    const short = computePositionPlan({
      ...BASE,
      side: "short",
      stop: 3990,
      target: 3950,
    });
    expect(short.valid).toBe(false);
  });

  it("rejects nonsense inputs", () => {
    expect(computePositionPlan({ ...BASE, equity: 0 }).valid).toBe(false);
    expect(computePositionPlan({ ...BASE, riskPct: 0 }).valid).toBe(false);
    expect(computePositionPlan({ ...BASE, entry: -1 }).valid).toBe(false);
  });
});
