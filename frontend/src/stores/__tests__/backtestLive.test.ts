import { beforeEach, describe, expect, it } from "vitest";

import { useBacktestLiveStore } from "@/stores/backtestLive";
import type { BacktestProgress } from "@/stores/backtestLive";

const progress = (over: Partial<BacktestProgress> = {}): BacktestProgress => ({
  decisions: 1,
  total: 10,
  pct: 10,
  open_count: 1,
  closed_trades: 0,
  equity: 100_000,
  pnl: 0,
  ...over,
});

describe("backtestLive store", () => {
  beforeEach(() => useBacktestLiveStore.getState().reset());

  it("start resets prior state and marks running", () => {
    const s = useBacktestLiveStore.getState();
    s.addTrade({ id: "x", symbol: "BTC-USD", side: "BUY", quantity: 1, entry_price: 1 });
    s.start("job1");
    const next = useBacktestLiveStore.getState();
    expect(next.status).toBe("running");
    expect(next.jobId).toBe("job1");
    expect(next.closedTrades).toHaveLength(0); // reset
  });

  it("setProgress accumulates the equity curve and open trades", () => {
    const s = useBacktestLiveStore.getState();
    s.start("job1");
    s.setProgress(progress({ equity: 100_000 }), [
      { id: "a", symbol: "BTC-USD", side: "BUY", quantity: 1, entry_price: 100 },
    ]);
    s.setProgress(progress({ decisions: 2, equity: 101_000 }), []);
    const next = useBacktestLiveStore.getState();
    expect(next.equityCurve).toEqual([100_000, 101_000]);
    expect(next.openTrades).toEqual([]);
    expect(next.progress?.decisions).toBe(2);
  });

  it("addTrade appends closed trades in arrival order", () => {
    const s = useBacktestLiveStore.getState();
    s.start("job1");
    s.addTrade({ id: "a", symbol: "BTC-USD", side: "BUY", quantity: 1, entry_price: 1, pnl: 5 });
    s.addTrade({ id: "b", symbol: "BTC-USD", side: "SELL", quantity: 1, entry_price: 1, pnl: -2 });
    expect(useBacktestLiveStore.getState().closedTrades.map((t) => t.id)).toEqual(["a", "b"]);
  });

  it("setDone stores the result and clears live scaffolding", () => {
    const s = useBacktestLiveStore.getState();
    s.start("job1");
    s.setProgress(progress(), [{ id: "a", symbol: "BTC-USD", side: "BUY", quantity: 1, entry_price: 1 }]);
    s.setDone({ provider: "deterministic", n_trades: 3 });
    const next = useBacktestLiveStore.getState();
    expect(next.status).toBe("done");
    expect(next.result?.n_trades).toBe(3);
    expect(next.openTrades).toEqual([]);
    expect(next.progress).toBeNull();
  });

  it("setError records the message", () => {
    const s = useBacktestLiveStore.getState();
    s.start("job1");
    s.setError("boom");
    expect(useBacktestLiveStore.getState().status).toBe("error");
    expect(useBacktestLiveStore.getState().error).toBe("boom");
  });
});
