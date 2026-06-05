import { describe, it, expect } from "vitest";
import { formatDuration } from "../lib/format";

describe("formatDuration", () => {
  it("formats milliseconds under 1 second", () => {
    expect(formatDuration(2)).toBe("2 ms");
    expect(formatDuration(900)).toBe("900 ms");
  });
  it("formats seconds", () => {
    expect(formatDuration(1000)).toBe("1.0s");
    expect(formatDuration(1400)).toBe("1.4s");
    expect(formatDuration(42_000)).toBe("42.0s");
  });
  it("formats minutes + seconds", () => {
    expect(formatDuration(60_000)).toBe("1m 0s");
    expect(formatDuration(83_000)).toBe("1m 23s");
    expect(formatDuration(125_000)).toBe("2m 5s");
  });
  it("returns '—' for null / non-positive", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(0)).toBe("—");
    expect(formatDuration(undefined)).toBe("—");
  });
});
