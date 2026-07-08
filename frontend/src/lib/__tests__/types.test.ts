/** Contract lock: fixtures captured from the live view models must keep
 * parsing. If the backend drifts, this fails before any component does. */
import { describe, expect, it } from "vitest";

import {
  AlertFeedSchema,
  BarsSchema,
  RecommendationSchema,
  StatusSchema,
} from "../api/types";

describe("API schemas", () => {
  it("parses a rejected recommendation", () => {
    const parsed = RecommendationSchema.parse({
      status: "rejected",
      rejection: { stage: "risk_gate", reasons: ["VaR95 exceeds limit"] },
    });
    expect(parsed.status).toBe("rejected");
  });

  it("parses a full recommendation view", () => {
    const parsed = RecommendationSchema.parse({
      schema_version: "0.2",
      id: "abc",
      symbol: "XAUUSD",
      action: "BUY",
      confidence: 72,
      entry_price: 130,
      stop_loss: 125,
      take_profits: [{ price: 135, size_fraction: 0.5 }],
      position_size: { quantity: 76.9, pct_of_equity: 10 },
      market_regime: "trending_up",
      evidence: [],
      counterarguments: [],
      vote_breakdown: { votes: [{ agent_id: "rsi", vote: "BUY", confidence: 60 }] },
      historical_analogs: [],
      risk_reward: 1.5,
      vote_tally: { BUY: 46, HOLD: 0, SELL: 0 },
      n_evidence: 45,
      n_counterarguments: 0,
      invalidation: "close below stop",
      rejection: null,
      created_at: "2026-07-08T10:00:00+00:00",
    });
    expect(parsed.action).toBe("BUY");
    expect(parsed.take_profits![0]!.price).toBe(135);
  });

  it("parses detached and attached status", () => {
    expect(StatusSchema.parse({ attached: false, trading_halted: null }).attached).toBe(
      false,
    );
    const attached = StatusSchema.parse({
      attached: true,
      trading_halted: true,
      kill_switch: { engaged: true, reason: "drill" },
      circuit_breaker: { tripped: false, reason: "" },
      open_positions: [{ symbol: "XAUUSD", quantity: 5 }],
      equity: 100000,
    });
    expect(attached.trading_halted).toBe(true);
  });

  it("parses bars and alerts", () => {
    expect(
      BarsSchema.parse([
        { time: 1751932800, open: 1, high: 2, low: 0.5, close: 1.5, volume: 10 },
      ]),
    ).toHaveLength(1);
    expect(
      AlertFeedSchema.parse({
        alerts: [
          { time: "t", run_id: "r", severity: "critical", text: "quarantined" },
        ],
      }).alerts[0]!.severity,
    ).toBe("critical");
  });
});
