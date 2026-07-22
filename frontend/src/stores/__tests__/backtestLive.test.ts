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
    expect(next.closedTotal).toBe(0);
  });

  it("setProgress accumulates the equity curve and ignores stale frames", () => {
    const s = useBacktestLiveStore.getState();
    s.start("job1");
    s.setProgress(progress({ equity: 100_000 }), []);
    s.setProgress(progress({ decisions: 5, equity: 101_000 }), []);
    s.setProgress(progress({ decisions: 3, equity: 90_000 }), []); // stale
    const next = useBacktestLiveStore.getState();
    expect(next.equityCurve).toEqual([100_000, 101_000]);
    expect(next.progress?.decisions).toBe(5);
  });

  it("fetching-phase frames pass through without touching the curve", () => {
    const s = useBacktestLiveStore.getState();
    s.start("job1");
    s.setProgress({ phase: "fetching", bars_have: 500, bars_needed: 2000, pct: 25 }, []);
    const next = useBacktestLiveStore.getState();
    expect(next.progress?.phase).toBe("fetching");
    expect(next.equityCurve).toEqual([]);
  });

  it("syncClosed reconciles from a snapshot only when the total advances", () => {
    const s = useBacktestLiveStore.getState();
    s.start("job1");
    s.addTrade({ id: "a", symbol: "BTC-USD", side: "BUY", quantity: 1, entry_price: 1 });
    s.syncClosed([{ id: "z", symbol: "BTC-USD", side: "SELL", quantity: 1, entry_price: 1 }], 5);
    expect(useBacktestLiveStore.getState().closedTotal).toBe(5);
    expect(useBacktestLiveStore.getState().closedTrades[0]!.id).toBe("z");
    // stale snapshot (lower total) ignored
    s.syncClosed([], 2);
    expect(useBacktestLiveStore.getState().closedTotal).toBe(5);
  });

  it("finish records the run id for the result view and clears live scaffolding", () => {
    const s = useBacktestLiveStore.getState();
    s.start("job1");
    s.setProgress(progress(), [
      { id: "a", symbol: "BTC-USD", side: "BUY", quantity: 1, entry_price: 1 },
    ]);
    s.finish("cancelled", "job1");
    const next = useBacktestLiveStore.getState();
    expect(next.status).toBe("cancelled");
    expect(next.finishedRunId).toBe("job1");
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
