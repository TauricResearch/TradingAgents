import { describe, expect, it } from "vitest";

import { executedBars, replayAsOf } from "../BacktestReplay";
import {
  BacktestDecisionsArtifactSchema,
  BacktestExtendedSchema,
} from "@/lib/api/types";
import type { BacktestDecisionRow, BacktestTrade } from "@/lib/api/types";

const equity: [string, number][] = [
  ["2024-01-01T00:00:00", 100_000],
  ["2024-01-02T00:00:00", 100_500],
  ["2024-01-03T00:00:00", 100_200],
  ["2024-01-04T00:00:00", 101_000],
];

const trades: BacktestTrade[] = [
  {
    id: "t1", symbol: "BTCUSD", side: "BUY", quantity: 1, entry_price: 100,
    exit_price: 105, pnl: 5, opened_at: "2024-01-02T00:00:00",
    closed_at: "2024-01-04T00:00:00",
  },
];

const decisions: BacktestDecisionRow[] = [
  { index: 60, time: "2024-01-01T00:00:00", outcome: "hold", action: "HOLD" },
  { index: 61, time: "2024-01-02T00:00:00", outcome: "executed", action: "BUY" },
  { index: 62, time: "2024-01-03T00:00:00", outcome: "rejected:critic" },
  { index: 63, time: "2024-01-04T00:00:00", outcome: "hold" },
];

describe("replayAsOf", () => {
  it("shows the trade open only between its open and close bars", () => {
    // cursor 2 → as-of 2024-01-02: opened this bar, not yet closed → open
    const at2 = replayAsOf(equity, trades, decisions, 2);
    expect(at2.time).toBe("2024-01-02T00:00:00");
    expect(at2.equity).toBe(100_500);
    expect(at2.openFills).toHaveLength(1);
    expect(at2.closedCount).toBe(0);
    expect(at2.curve).toEqual([100_000, 100_500]);

    // cursor 4 → as-of 2024-01-04: closed_at <= now → no longer open, counted closed
    const at4 = replayAsOf(equity, trades, decisions, 4);
    expect(at4.openFills).toHaveLength(0);
    expect(at4.closedCount).toBe(1);
  });

  it("surfaces the decision as-of the cursor bar", () => {
    expect(replayAsOf(equity, trades, decisions, 2).decision?.outcome).toBe("executed");
    expect(replayAsOf(equity, trades, decisions, 1).decision?.action).toBe("HOLD");
  });

  it("is empty at cursor 0", () => {
    const snap = replayAsOf(equity, trades, decisions, 0);
    expect(snap.time).toBeNull();
    expect(snap.openFills).toHaveLength(0);
  });
});

describe("executedBars", () => {
  it("marks the 0-based indices of executed decisions (replay pause points)", () => {
    expect([...executedBars(decisions)]).toEqual([1]);
  });
});

describe("artifact schemas", () => {
  it("round-trips the decisions artifact", () => {
    expect(BacktestDecisionsArtifactSchema.parse(decisions)).toHaveLength(4);
  });

  it("parses an extended bundle with scalars + series", () => {
    const parsed = BacktestExtendedSchema.parse({
      cagr: 0.12, calmar: 1.4, beta: 0.8,
      drawdown_curve: [0, 0.01, 0],
      monthly_returns: [["2024-01", 0.03]],
    });
    expect(parsed.cagr).toBe(0.12);
    expect(parsed.monthly_returns?.[0]).toEqual(["2024-01", 0.03]);
  });
});
