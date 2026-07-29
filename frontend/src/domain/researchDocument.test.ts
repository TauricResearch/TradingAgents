import { describe, expect, it } from "vitest";
import { buildResearchDocument } from "./researchDocument";
import { createInitialState } from "../state/runReducer";
import type { ReducerState, Turn } from "../state/model";

function stateWith(...turns: Turn[]): ReducerState {
  const state = createInitialState();
  state.meta = {
    ...state.meta,
    run_id: "run-demo",
    selected_analysts: ["market", "news"],
  };
  state.turns = Object.fromEntries(turns.map((turn) => [turn.turn_id, turn]));
  return state;
}

function completed(
  actor_id: string,
  turn_index: number,
  artifact_id = `artifact-${actor_id}-${turn_index}`,
): Turn {
  return {
    turn_id: `turn-${actor_id}-${turn_index}`,
    role_instance_id: `run-demo:${actor_id}`,
    actor_id,
    graph_task_id: `task-${actor_id}-${turn_index}`,
    turn_index,
    status: "completed",
    artifact_id,
    model_call_ids: [],
    tool_call_ids: [],
    vendor_call_ids: [],
  };
}

describe("buildResearchDocument", () => {
  it("shows only selected analysts and uses the highest canonical report revision", () => {
    const market = completed("analyst.market", 1);
    const state = stateWith(market, completed("analyst.news", 1));
    state.graph_tasks[market.graph_task_id!] = {
      graph_task_id: market.graph_task_id!,
      graph_step: 1,
      node_id: "Market Analyst",
      status: "output_ready",
      applied: true,
    };
    state.reports = [
      { turn_id: market.turn_id, report_kind: "market", revision: 1, artifact_id: "market-v1" },
      { turn_id: market.turn_id, report_kind: "market", revision: 2, artifact_id: "market-v2" },
    ];

    const document = buildResearchDocument(state);

    expect(document.analysts.map((entry) => entry.actor_id)).toEqual([
      "analyst.market",
      "analyst.news",
    ]);
    expect(document.analysts[0]).toMatchObject({
      status: "committed",
      artifact_id: "market-v2",
      artifact_kind: "report",
    });
  });

  it("keeps a completed but unapplied task out of the reading surface", () => {
    const bull = completed("researcher.bull", 1, "candidate-bull");
    const state = stateWith(bull);
    state.graph_tasks[bull.graph_task_id!] = {
      graph_task_id: bull.graph_task_id!,
      graph_step: 2,
      node_id: "Bull Researcher",
      status: "output_ready",
      applied: false,
      business_delta_artifact_id: "candidate-bull",
    };

    const round = buildResearchDocument(state).debate_rounds[0];

    expect(round.bull).toMatchObject({ status: "completed", artifact_id: "candidate-bull" });
    expect(round.bear).toMatchObject({ status: "waiting", turn_index: 1 });
  });

  it("groups Bull and Bear strictly by round without inventing a missing counterpart", () => {
    const bullOne = completed("researcher.bull", 1);
    const bearTwo = completed("researcher.bear", 2);
    const state = stateWith(bullOne, bearTwo);
    for (const turn of [bullOne, bearTwo]) {
      state.graph_tasks[turn.graph_task_id!] = {
        graph_task_id: turn.graph_task_id!,
        graph_step: turn.turn_index,
        node_id: turn.actor_id,
        status: "output_ready",
        applied: true,
      };
    }

    const rounds = buildResearchDocument(state).debate_rounds;

    expect(rounds).toHaveLength(2);
    expect(rounds[0]).toMatchObject({ round: 1, bull: { status: "committed" }, bear: { status: "waiting" } });
    expect(rounds[1]).toMatchObject({ round: 2, bull: { status: "waiting" }, bear: { status: "committed" } });
  });

  it("keeps risk roles in their own round and lets legacy terminal turns remain readable", () => {
    const aggressive = completed("risk.aggressive", 1);
    const neutral = completed("risk.neutral", 2);
    const state = stateWith(aggressive, neutral);
    // No graph task models a legacy replay.  The terminal turn is still the
    // strongest available commitment marker for that historical run.

    const rounds = buildResearchDocument(state).risk_rounds;

    expect(rounds).toHaveLength(2);
    expect(rounds[0]).toMatchObject({
      aggressive: { status: "committed" },
      conservative: { status: "waiting" },
      neutral: { status: "waiting" },
    });
    expect(rounds[1]).toMatchObject({
      aggressive: { status: "waiting" },
      conservative: { status: "waiting" },
      neutral: { status: "committed" },
    });
  });
});
