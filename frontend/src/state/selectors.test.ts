import { describe, expect, it } from "vitest";
import type { ReducerState, RunMeta, Turn } from "./model";
import { debateScript } from "./selectors";

function buildTurn(
  turn_id: string,
  actor_id: string,
  turn_index: number,
): Turn {
  return {
    turn_id,
    actor_id,
    role_instance_id: `run:${actor_id}`,
    turn_index,
    status: "completed",
    model_call_ids: [],
    tool_call_ids: [],
    vendor_call_ids: [],
  };
}

function buildState(turns: Turn[], overrides: Partial<RunMeta> = {}): ReducerState {
  const meta: RunMeta = {
    run_id: "run",
    status: "running",
    ticker: "AAPL",
    asset_type: "stock",
    analysis_date: "2026-07-28",
    selected_analysts: ["market", "social", "news", "fundamentals"],
    research_depth: 3,
    max_debate_rounds: 3,
    max_risk_discuss_rounds: 3,
    output_language: "zh",
    llm_provider: "deepseek",
    quick_think_llm: "deepseek-chat",
    deep_think_llm: "deepseek-reasoner",
    configured_keys: {},
    checkpoint_enabled: false,
    created_at: "2026-07-28T00:00:00Z",
    updated_at: "2026-07-28T00:00:00Z",
    latest_sequence: 0,
    redaction_manifest: [],
    event_schema_version: 1,
    ...overrides,
  };
  return {
    meta,
    roles: {},
    turns: Object.fromEntries(turns.map((turn) => [turn.turn_id, turn])),
    model_calls: {},
    tool_calls: {},
    vendor_calls: {},
    artifacts: {},
    reports: [],
    graph_tasks: {},
    latest_graph_step: 0,
  };
}

describe("debateScript", () => {
  it("groups a two-round research debate by turn_index", () => {
    const state = buildState([
      buildTurn("bull-1", "researcher.bull", 1),
      buildTurn("bear-1", "researcher.bear", 1),
      buildTurn("bull-2", "researcher.bull", 2),
      buildTurn("bear-2", "researcher.bear", 2),
    ], { max_debate_rounds: 2 });

    const blocks = debateScript(state);
    expect(blocks).toHaveLength(2);
    expect(blocks.map((block) => block.kind)).toEqual(["round", "round"]);
    expect(blocks.map((block) => block.kind === "round" && block.index)).toEqual([1, 2]);
    expect(blocks[0]).toMatchObject({
      kind: "round",
      stage: "research",
      lanes: [
        { id: "bull", turns: [{ turn_id: "bull-1" }] },
        { id: "bear", turns: [{ turn_id: "bear-1" }] },
      ],
    });
  });

  it("keeps round 1 structural when the configured budget is 3", () => {
    const state = buildState([
      buildTurn("bear-1", "researcher.bear", 1),
      buildTurn("bull-1", "researcher.bull", 1),
    ]);

    expect(debateScript(state)).toMatchObject([
      { kind: "round", stage: "research", index: 1 },
    ]);
    expect(state.meta.max_debate_rounds).toBe(3);
  });

  it("projects a three-way risk debate into stable lane order", () => {
    const state = buildState([
      buildTurn("neutral", "risk.neutral", 1),
      buildTurn("conservative", "risk.conservative", 1),
      buildTurn("aggressive", "risk.aggressive", 1),
    ]);

    const [round] = debateScript(state);
    expect(round).toMatchObject({
      kind: "round",
      stage: "risk",
      index: 1,
      lanes: [
        { id: "aggressive", turns: [{ turn_id: "aggressive" }] },
        { id: "neutral", turns: [{ turn_id: "neutral" }] },
        { id: "conservative", turns: [{ turn_id: "conservative" }] },
      ],
    });
  });

  it("places judging turns after their debate as verdict blocks", () => {
    const state = buildState([
      buildTurn("manager", "manager.research", 1),
      buildTurn("bull", "researcher.bull", 1),
      buildTurn("bear", "researcher.bear", 1),
    ]);

    expect(debateScript(state).map((block) => block.kind)).toEqual([
      "round",
      "verdict",
    ]);
    expect(debateScript(state)[1]).toMatchObject({
      kind: "verdict",
      turn: { turn_id: "manager" },
    });
  });

  it("keeps non-adversarial analyst turns linear", () => {
    const state = buildState([
      buildTurn("market", "analyst.market", 1),
      buildTurn("news", "analyst.news", 1),
    ]);

    expect(debateScript(state)).toMatchObject([
      { kind: "linear", turn: { turn_id: "market" } },
      { kind: "linear", turn: { turn_id: "news" } },
    ]);
  });

  it("does not let object insertion order change round or lane order", () => {
    const state = buildState([
      buildTurn("bear-2", "researcher.bear", 2),
      buildTurn("bull-2", "researcher.bull", 2),
      buildTurn("bear-1", "researcher.bear", 1),
      buildTurn("bull-1", "researcher.bull", 1),
    ]);

    const blocks = debateScript(state);
    expect(blocks.map((block) => block.kind === "round" && block.index)).toEqual([1, 2]);
    expect(blocks[0]).toMatchObject({
      kind: "round",
      lanes: [
        { id: "bull", turns: [{ turn_id: "bull-1" }] },
        { id: "bear", turns: [{ turn_id: "bear-1" }] },
      ],
    });
  });
});
