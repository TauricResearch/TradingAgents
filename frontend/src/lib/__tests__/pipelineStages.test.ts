import { describe, expect, it } from "vitest";

import { bucketOf, PIPELINE_BUCKETS, stageProgress } from "../pipelineStages";

describe("pipeline progress vocabulary", () => {
  it("collapses raw LangGraph nodes into the 10 board buckets", () => {
    expect(bucketOf("team_macro")).toBe("teams");
    expect(bucketOf("technical_bear")).toBe("debate");
    expect(bucketOf("sentiment")).toBe("debate");
    expect(bucketOf("critic")).toBe("review");
    expect(bucketOf("reflection")).toBe("review");
    expect(bucketOf("portfolio_manager")).toBe("sizing");
    expect(bucketOf("human_approval")).toBe("approval");
    expect(bucketOf("judge")).toBe("judge");
  });

  it("board and chip count on the same k/N scale", () => {
    // the review's live finding: board said "stage 2/10" while the chip
    // said "team_macro (5/18)" for the same moment of the same run
    expect(stageProgress("team_macro")).toEqual({ index: 2, total: 10 });
    expect(stageProgress("technical_bear")).toEqual({ index: 4, total: 10 });
    expect(stageProgress("judge")).toEqual({ index: 7, total: 10 });
    expect(stageProgress("execution")).toEqual({
      index: PIPELINE_BUCKETS.length,
      total: PIPELINE_BUCKETS.length,
    });
  });

  it("unknown nodes clamp to stage 1, never 0 or negative", () => {
    expect(stageProgress("mystery_node")).toEqual({ index: 1, total: 10 });
    expect(stageProgress(null)).toEqual({ index: 1, total: 10 });
  });
});
