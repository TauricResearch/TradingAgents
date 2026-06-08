import { describe, it, expect } from "vitest";
import { fmtEta } from "./format";

describe("fmtEta", () => {
  it("returns 'Calculating...' for null", () => {
    expect(fmtEta(null)).toBe("Calculating...");
  });

  it("formats < 60s as 'Xs'", () => {
    expect(fmtEta(0)).toBe("0s");
    expect(fmtEta(45)).toBe("45s");
    expect(fmtEta(59.4)).toBe("60s");
  });

  it("formats < 1h as 'Xm Ys'", () => {
    expect(fmtEta(60)).toBe("1m 0s");
    expect(fmtEta(125)).toBe("2m 5s");
    expect(fmtEta(3599)).toBe("59m 59s");
  });

  it("formats >= 1h as 'Hh Mm'", () => {
    expect(fmtEta(3600)).toBe("1h 0m");
    expect(fmtEta(3700)).toBe("1h 1m");
    expect(fmtEta(7325)).toBe("2h 2m");
  });
});
