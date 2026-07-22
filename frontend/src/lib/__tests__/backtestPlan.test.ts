import { describe, expect, it } from "vitest";

import {
  LARGE_RUN_DECISIONS,
  MAX_LLM_DECISIONS,
  MIN_HISTORY,
  planRun,
} from "@/lib/backtestPlan";

describe("planRun (mirrors backend bars_for_duration)", () => {
  it("7D at 1d → 7 decision bars + warm-up", () => {
    const plan = planRun("BTC-USD", "1d", "7D", false)!;
    expect(plan.bars).toBe(7 + MIN_HISTORY);
    expect(plan.decisions).toBe(7);
    expect(plan.needsConfirm).toBe(false);
  });

  it("1Y at 5m is a large full-density run needing confirmation", () => {
    const plan = planRun("BTC-USD", "5m", "1Y", false)!;
    expect(plan.bars).toBe(105_120 + MIN_HISTORY);
    expect(plan.decisions).toBeGreaterThan(LARGE_RUN_DECISIONS);
    expect(plan.needsConfirm).toBe(true);
    expect(plan.estMinutes).toBeGreaterThan(10);
  });

  it("gold daily durations use trading days (1Y ≈ 261 bars, not 365)", () => {
    const gold = planRun("XAUUSD", "1d", "1Y", false)!;
    expect(gold.bars).toBe(261 + MIN_HISTORY); // ceil(365 * 5/7)
    const btc = planRun("BTC-USD", "1d", "1Y", false)!;
    expect(btc.bars).toBe(365 + MIN_HISTORY);
  });

  it("LLM runs are window-trimmed to the cost cap, never subsampled", () => {
    const plan = planRun("BTC-USD", "1h", "1Y", true)!;
    expect(plan.decisions).toBe(MAX_LLM_DECISIONS);
    expect(plan.llmCapped).toBe(true);
    expect(plan.needsConfirm).toBe(true);
  });

  it("unknown inputs return null", () => {
    expect(planRun("BTC-USD", "3h", "7D", false)).toBeNull();
    expect(planRun("BTC-USD", "1h", "2W", false)).toBeNull();
  });
});
