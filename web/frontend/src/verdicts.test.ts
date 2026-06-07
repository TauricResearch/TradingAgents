import { describe, it, expect } from "vitest";
import { barsInWindow, type Bar } from "./verdicts";

const t0 = "2026-06-01T12:00:00Z";
const delta1h = 60 * 60 * 1000;

function bar(t: string, c: number, o = c, h = c + 0.5, l = c - 0.5, v = 1000): Bar {
  return { t, o, h, l, c, v };
}

describe("barsInWindow", () => {
  it("returns bars whose t is in [start, start+delta]", () => {
    const bars = [
      bar("2026-06-01T11:00:00Z", 100), // before
      bar(t0, 100),                       // T
      bar("2026-06-01T12:30:00Z", 101),
      bar("2026-06-01T13:00:00Z", 102), // T+delta
      bar("2026-06-01T13:30:00Z", 103), // after
    ];
    const inWin = barsInWindow(bars, t0, delta1h, "2026-06-01T15:00:00Z");
    expect(inWin.map((b) => b.t)).toEqual([t0, "2026-06-01T12:30:00Z", "2026-06-01T13:00:00Z"]);
  });

  it("clips the window at nowIso", () => {
    const bars = [bar(t0, 100), bar("2026-06-01T12:30:00Z", 101), bar("2026-06-01T13:00:00Z", 102)];
    const inWin = barsInWindow(bars, t0, delta1h, "2026-06-01T12:45:00Z");
    expect(inWin.map((b) => b.t)).toEqual([t0, "2026-06-01T12:30:00Z"]);
  });

  it("returns an empty array for empty input or no bars in window", () => {
    expect(barsInWindow([], t0, delta1h, "2026-06-01T15:00:00Z")).toEqual([]);
    const far = [bar("2026-06-01T10:00:00Z", 100)];
    expect(barsInWindow(far, t0, delta1h, "2026-06-01T15:00:00Z")).toEqual([]);
  });
});
