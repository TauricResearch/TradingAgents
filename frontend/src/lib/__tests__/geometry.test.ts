import { beforeEach, describe, expect, it } from "vitest";

import {
  FIB_LEVELS,
  fibPrices,
  pointToRayDistance,
  pointToSegmentDistance,
} from "@/components/charts/drawings/geometry";
import { useDrawingsStore } from "@/stores/drawings";
import type { Drawing } from "@/components/charts/drawings/types";

describe("fibPrices", () => {
  it("spans the anchors: level 0 at second point, level 1 at first", () => {
    const levels = fibPrices(100, 50);
    expect(levels[0]).toEqual({ level: 0, price: 50 });
    expect(levels[levels.length - 1]).toEqual({ level: 1, price: 100 });
    const half = levels.find((l) => l.level === 0.5)!;
    expect(half.price).toBeCloseTo(75);
  });

  it("works with inverted anchors (downtrend retracement)", () => {
    const levels = fibPrices(50, 100);
    expect(levels.find((l) => l.level === 0.618)!.price).toBeCloseTo(
      100 + (50 - 100) * 0.618,
    );
    expect(levels).toHaveLength(FIB_LEVELS.length);
  });
});

describe("pointToSegmentDistance", () => {
  const a = { x: 0, y: 0 };
  const b = { x: 10, y: 0 };

  it("measures perpendicular distance inside the segment", () => {
    expect(pointToSegmentDistance({ x: 5, y: 3 }, a, b)).toBeCloseTo(3);
  });

  it("clamps to endpoints beyond the segment", () => {
    expect(pointToSegmentDistance({ x: -3, y: 4 }, a, b)).toBeCloseTo(5);
    expect(pointToSegmentDistance({ x: 13, y: 4 }, a, b)).toBeCloseTo(5);
  });

  it("degenerate zero-length segment collapses to point distance", () => {
    expect(pointToSegmentDistance({ x: 3, y: 4 }, a, a)).toBeCloseTo(5);
  });

  it("ray distance extends to the right edge only", () => {
    expect(pointToRayDistance({ x: 50, y: 2 }, { x: 10, y: 0 }, 100)).toBeCloseTo(2);
    expect(pointToRayDistance({ x: 0, y: 0 }, { x: 10, y: 0 }, 100)).toBeCloseTo(10);
  });
});

describe("drawings store", () => {
  const drawing = (id: string): Drawing => ({
    id,
    kind: "trend",
    points: [
      { time: 1, price: 10 },
      { time: 2, price: 20 },
    ],
  });

  beforeEach(() => {
    useDrawingsStore.setState({ bySymbol: {} });
  });

  it("adds, removes, clears per symbol", () => {
    const store = useDrawingsStore.getState();
    store.add("XAUUSD", drawing("a"));
    store.add("XAUUSD", drawing("b"));
    store.add("BTC-USD", drawing("c"));
    expect(useDrawingsStore.getState().bySymbol["XAUUSD"]).toHaveLength(2);
    store.remove("XAUUSD", "a");
    expect(useDrawingsStore.getState().bySymbol["XAUUSD"]!.map((d) => d.id)).toEqual(["b"]);
    store.clear("XAUUSD");
    expect(useDrawingsStore.getState().bySymbol["XAUUSD"]).toEqual([]);
    expect(useDrawingsStore.getState().bySymbol["BTC-USD"]).toHaveLength(1);
  });

  it("caps drawings per symbol, dropping oldest", () => {
    const store = useDrawingsStore.getState();
    for (let i = 0; i < 105; i++) store.add("XAUUSD", drawing(`d${i}`));
    const kept = useDrawingsStore.getState().bySymbol["XAUUSD"]!;
    expect(kept).toHaveLength(100);
    expect(kept[0]!.id).toBe("d5");
  });

  it("hydrate accepts objects and rejects junk", () => {
    const store = useDrawingsStore.getState();
    store.hydrate({ XAUUSD: [drawing("x")] });
    expect(useDrawingsStore.getState().bySymbol["XAUUSD"]).toHaveLength(1);
    store.hydrate("garbage");
    expect(useDrawingsStore.getState().bySymbol["XAUUSD"]).toHaveLength(1);
  });
});
