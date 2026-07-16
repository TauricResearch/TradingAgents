import { describe, expect, it } from "vitest";

import {
  DIRECTION_GLYPH,
  directionOf,
  fmtCountdown,
  fmtMetricValue,
  fmtPct,
  fmtPnl,
  fmtPrice,
  relativeAge,
} from "../format";

describe("directionOf", () => {
  it("maps trading vocabulary to canonical directions", () => {
    expect(directionOf("BUY")).toBe("bull");
    expect(directionOf("bullish")).toBe("bull");
    expect(directionOf("SELL")).toBe("bear");
    expect(directionOf("bearish")).toBe("bear");
    expect(directionOf("HOLD")).toBe("neutral");
    expect(directionOf(null)).toBe("neutral");
  });

  it("every direction has a glyph (A11Y-01)", () => {
    expect(DIRECTION_GLYPH.bull).toBe("▲");
    expect(DIRECTION_GLYPH.bear).toBe("▼");
    expect(DIRECTION_GLYPH.neutral).toBe("–");
  });
});

describe("formatters", () => {
  it("never renders NaN", () => {
    expect(fmtPrice(NaN)).toBe("—");
    expect(fmtPnl(undefined)).toBe("—");
    expect(fmtPct(null)).toBe("—");
  });

  it("signs P&L", () => {
    expect(fmtPnl(12.3)).toBe("+12.30");
    expect(fmtPnl(-4)).toBe("-4.00");
  });

  it("relative ages", () => {
    const now = new Date();
    expect(relativeAge(new Date(now.getTime() - 5_000).toISOString())).toMatch(/s ago/);
    expect(relativeAge(new Date(now.getTime() - 120_000).toISOString())).toBe("2m ago");
  });

  it("funding rates render as %/8h with annualization, never sci-notation", () => {
    // the review's live finding: FUNDING RATE displayed as "8.57e-5"
    expect(fmtMetricValue("FUNDING_RATE", 8.57e-5)).toBe("0.0086%/8h · 9.4% ann.");
    expect(fmtMetricValue("FUNDING_RATE", -1.2e-4)).toBe("-0.0120%/8h · -13.1% ann.");
  });

  it("tiny non-funding values render as plain decimals", () => {
    expect(fmtMetricValue("SOME_RATIO", 8.57e-5)).toBe("0.0000857");
    expect(fmtMetricValue("SOME_RATIO", 8.57e-5)).not.toMatch(/e-/);
  });

  it("ordinary metric values keep localized formatting", () => {
    expect(fmtMetricValue("OPEN_INTEREST", 102240.19)).toBe("102,240.19");
    expect(fmtMetricValue("DXY", null)).toBe("—");
  });

  it("countdowns render compactly at every scale", () => {
    expect(fmtCountdown(42 * 60)).toBe("42m");
    expect(fmtCountdown(3 * 3600 + 12 * 60)).toBe("3h 12m");
    expect(fmtCountdown(2 * 86_400 + 4 * 3600)).toBe("2d 4h");
    expect(fmtCountdown(30)).toBe("1m"); // sub-minute rounds up, never "0m"
    expect(fmtCountdown(0)).toBe("now");
    expect(fmtCountdown(null)).toBe("now");
  });
});
