import { describe, expect, it } from "vitest";

import { toDrawdown } from "@/components/charts/transform";

describe("toDrawdown", () => {
  it("is zero at running peaks and negative under water", () => {
    const dd = toDrawdown([100, 110, 99, 121, 110]);
    expect(dd[0]).toBe(0);
    expect(dd[1]).toBe(0); // new peak
    expect(dd[2]).toBeCloseTo(99 / 110 - 1);
    expect(dd[3]).toBe(0); // recovered to a new peak
    expect(dd[4]).toBeCloseTo(110 / 121 - 1);
  });

  it("never returns positive values", () => {
    const dd = toDrawdown([50, 60, 55, 70, 65, 80]);
    expect(dd.every((v) => v <= 0)).toBe(true);
  });

  it("handles empty and single-point curves", () => {
    expect(toDrawdown([])).toEqual([]);
    expect(toDrawdown([100])).toEqual([0]);
  });
});
