import { describe, expect, it } from "vitest";

import { toHeikinAshi } from "@/components/charts/transform";
import type { Bar } from "@/lib/api/types";

const bar = (i: number, open: number, close: number): Bar => ({
  time: 1_700_000_000 + i * 86_400,
  open,
  high: Math.max(open, close) + 1,
  low: Math.min(open, close) - 1,
  close,
  volume: 100,
});

describe("toHeikinAshi", () => {
  it("computes HA close as OHLC mean and chains opens", () => {
    const bars = [bar(0, 100, 104), bar(1, 104, 102)];
    const ha = toHeikinAshi(bars);
    // HA close = (O+H+L+C)/4
    expect(ha[0]!.close).toBeCloseTo((100 + 105 + 99 + 104) / 4);
    // first HA open = (O+C)/2
    expect(ha[0]!.open).toBeCloseTo((100 + 104) / 2);
    // subsequent HA open = mean of previous HA open/close
    expect(ha[1]!.open).toBeCloseTo((ha[0]!.open + ha[0]!.close) / 2);
    // high/low envelope includes HA open/close
    expect(ha[1]!.high).toBeGreaterThanOrEqual(Math.max(ha[1]!.open, ha[1]!.close));
    expect(ha[1]!.low).toBeLessThanOrEqual(Math.min(ha[1]!.open, ha[1]!.close));
  });

  it("preserves times and length", () => {
    const bars = [bar(0, 1, 2), bar(1, 2, 3), bar(2, 3, 2)];
    const ha = toHeikinAshi(bars);
    expect(ha).toHaveLength(3);
    expect(ha.map((b) => b.time)).toEqual(bars.map((b) => b.time));
  });
});
