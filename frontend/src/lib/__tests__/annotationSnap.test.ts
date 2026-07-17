import { describe, expect, it } from "vitest";

import { snapToBar } from "@/components/charts/annotationSnap";

const BARS = [100, 200, 300, 400, 500];

describe("snapToBar", () => {
  it("returns the exact bar on a direct hit", () => {
    expect(snapToBar(BARS, 300)).toBe(300);
    expect(snapToBar(BARS, 100)).toBe(100);
    expect(snapToBar(BARS, 500)).toBe(500);
  });

  it("snaps between-bar times down to the containing bar", () => {
    expect(snapToBar(BARS, 250)).toBe(200);
    expect(snapToBar(BARS, 499)).toBe(400);
  });

  it("drops times before the first bar (off the loaded window)", () => {
    expect(snapToBar(BARS, 99)).toBeNull();
    expect(snapToBar(BARS, 0)).toBeNull();
  });

  it("clamps times after the last bar to the last bar", () => {
    expect(snapToBar(BARS, 9999)).toBe(500);
  });

  it("handles empty and single-bar arrays", () => {
    expect(snapToBar([], 100)).toBeNull();
    expect(snapToBar([42], 41)).toBeNull();
    expect(snapToBar([42], 42)).toBe(42);
    expect(snapToBar([42], 43)).toBe(42);
  });
});
