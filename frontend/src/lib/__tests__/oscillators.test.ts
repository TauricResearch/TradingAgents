import { describe, expect, it } from "vitest";

import {
  macdCrossLabel,
  oscillatorLevels,
} from "@/components/charts/oscillators";

describe("oscillatorLevels", () => {
  it("RSI gets 70/50/30 with a faint midline, families included", () => {
    for (const n of ["RSI_14", "RSI_9"]) {
      const lv = oscillatorLevels(n);
      expect(lv.map((l) => l.price)).toEqual([70, 50, 30]);
      expect(lv.find((l) => l.price === 50)!.mid).toBe(true);
    }
  });
  it("bounded oscillators get their conventional bands", () => {
    expect(oscillatorLevels("STOCH").map((l) => l.price)).toEqual([80, 20]);
    expect(oscillatorLevels("CCI_14").map((l) => l.price)).toEqual([100, -100]);
    expect(oscillatorLevels("WILLR_14").map((l) => l.price)).toEqual([-20, -80]);
    expect(oscillatorLevels("MACD").map((l) => l.price)).toEqual([0]);
    expect(oscillatorLevels("ADX").map((l) => l.price)).toEqual([25]);
  });
  it("overlays and unknowns get no levels", () => {
    expect(oscillatorLevels("EMA_10")).toEqual([]);
    expect(oscillatorLevels("VWAP")).toEqual([]);
  });
});

describe("macdCrossLabel", () => {
  const at = (vals: number[]) => vals.map((value, i) => ({ time: i, value }));
  it("detects a bull cross (macd rises above signal on the last bar)", () => {
    expect(macdCrossLabel(at([-1, 1]), at([0, 0]))).toBe("bull cross");
  });
  it("detects a bear cross", () => {
    expect(macdCrossLabel(at([1, -1]), at([0, 0]))).toBe("bear cross");
  });
  it("reports steady bullish/bearish ordering without a cross", () => {
    expect(macdCrossLabel(at([2, 3]), at([0, 0]))).toBe("bullish");
    expect(macdCrossLabel(at([-2, -3]), at([0, 0]))).toBe("bearish");
  });
  it("null when data is too short or times don't align", () => {
    expect(macdCrossLabel(at([1]), at([0]))).toBeNull();
    expect(
      macdCrossLabel(
        [{ time: 5, value: 1 }, { time: 6, value: 2 }],
        [{ time: 1, value: 0 }, { time: 2, value: 0 }],
      ),
    ).toBeNull();
  });
});
