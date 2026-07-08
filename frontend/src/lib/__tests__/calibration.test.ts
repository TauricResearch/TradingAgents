import { describe, expect, it } from "vitest";

import { calibrationBuckets } from "@/components/CalibrationChart";
import type { AgentPerf } from "@/lib/api/types";

describe("calibrationBuckets", () => {
  it("weights hit rates by scored sample size", () => {
    const perf: AgentPerf = {
      sharp: { votes: 20, avg_confidence: 75, scored: 10, hit_rate: 0.8 },
      dull: { votes: 20, avg_confidence: 75, scored: 30, hit_rate: 0.5 },
    };
    const bucket = calibrationBuckets(perf).find((b) => b.midpoint === 0.75)!;
    expect(bucket.n).toBe(40);
    // (0.8*10 + 0.5*30)/40
    expect(bucket.hitRate).toBeCloseTo(0.575);
  });

  it("unscored agents contribute nothing", () => {
    const perf: AgentPerf = {
      idle: { votes: 5, avg_confidence: 60, scored: 0, hit_rate: null },
    };
    expect(calibrationBuckets(perf).every((b) => b.n === 0)).toBe(true);
  });
});
