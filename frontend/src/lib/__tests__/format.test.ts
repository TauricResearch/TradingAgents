import { describe, expect, it } from "vitest";

import {
  DIRECTION_GLYPH,
  directionOf,
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
});
