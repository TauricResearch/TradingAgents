/** Bet-math (G9) is pure arithmetic over backend numbers — verify the
 * identities and that nothing is fabricated when inputs are missing. */
import { describe, expect, it } from "vitest";

import { betMath } from "@/components/DecisionCard";
import { RecommendationSchema, StatusSchema } from "@/lib/api/types";

const baseRec = {
  symbol: "XAUUSD",
  action: "SELL",
  confidence: 72,
  entry_price: 4000.2,
  stop_loss: 4175.63,
  take_profits: [
    { price: 3824.77, size_fraction: 0.5 },
    { price: 3649.34, size_fraction: 0.5 },
  ],
  position_size: { quantity: 2.4999, notional: 10000, pct_of_equity: 10 },
  risk_reward: 1.5,
};

describe("betMath", () => {
  it("computes breakeven and dollar risk/reward from the ladder", () => {
    const rec = RecommendationSchema.parse(baseRec);
    const math = betMath(rec)!;
    expect(math.breakevenPct).toBeCloseTo(40, 0); // 1/(1+1.5)
    expect(math.riskUsd).toBeCloseTo(Math.abs(4000.2 - 4175.63) * 2.4999, 2);
    // first target = take_profits[0] (closest), not the furthest
    expect(math.rewardUsd).toBeCloseTo(Math.abs(3824.77 - 4000.2) * 2.4999, 2);
  });

  it("returns null without an R:R and nulls without levels", () => {
    expect(betMath(RecommendationSchema.parse({ ...baseRec, risk_reward: null }))).toBeNull();
    const math = betMath(
      RecommendationSchema.parse({ ...baseRec, stop_loss: null, take_profits: [] }),
    )!;
    expect(math.breakevenPct).toBeCloseTo(40, 0);
    expect(math.riskUsd).toBeNull();
    expect(math.rewardUsd).toBeNull();
  });
});

describe("StatusSchema open-risk fields (G2)", () => {
  it("parses enriched positions and honest nulls", () => {
    const status = StatusSchema.parse({
      attached: true,
      trading_halted: false,
      open_positions: [
        {
          symbol: "XAUUSD", quantity: -2.44, entry_price: 4077.7,
          mark_price: 4005.1, mark_source: "live",
          unrealized_pnl: 177.14, exposure_pct: 9.8,
        },
        { symbol: "BTC-USD", quantity: 0.5, entry_price: null,
          mark_price: null, mark_source: "entry",
          unrealized_pnl: null, exposure_pct: null },
      ],
      unrealized_total: 177.14,
      equity: 100000,
    });
    expect(status.open_positions?.[0]?.unrealized_pnl).toBeCloseTo(177.14);
    expect(status.open_positions?.[1]?.unrealized_pnl).toBeNull();
    expect(status.unrealized_total).toBeCloseTo(177.14);
  });
});
