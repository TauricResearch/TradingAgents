/**
 * F2 reducer core invariant: batch replay and one-by-one live reduction
 * must yield deep-equal state (spec §9.5). Plus sequence dedupe, unknown
 * event tolerance, 13-role initialization, repeated Bull/Bear rounds, and
 * terminal failure -> not_reached conversion.
 */
import { describe, it, expect } from "vitest";
import { createInitialState, runReducer } from "./runReducer";
import { roleList, turnTimeline, isTerminal } from "./selectors";
import { ROLE_REGISTRY } from "./model";
import type { PersistedEventDTO } from "../api/contracts";

const RUN_ID = "run_20260719T120000Z_aabbccdd";

function ev(
  seq: number,
  type: string,
  payload: Record<string, unknown>,
  extra: Partial<PersistedEventDTO> = {},
): PersistedEventDTO {
  return {
    event_id: `${RUN_ID}:${seq}`,
    run_id: RUN_ID,
    sequence: seq,
    timestamp: `2026-07-19T12:00:${String(seq).padStart(2, "0")}Z`,
    type,
    payload,
    schema_version: 1,
    ...extra,
  };
}

function roleInstance(actor_id: string): string {
  return `${RUN_ID}:${actor_id}`;
}

/** A realistic ~14-event slice spanning run start through a completed analyst. */
function sampleSequence(): PersistedEventDTO[] {
  const events: PersistedEventDTO[] = [];
  let seq = 1;
  events.push(
    ev(seq++, "run.started", {
      run_status: "running",
      ticker: "600519.SS",
      asset_type: "stock",
      analysis_date: "2026-07-19",
      selected_analysts: ["market", "social", "news", "fundamentals"],
      research_depth: 1,
      max_debate_rounds: 1,
      max_risk_discuss_rounds: 1,
      output_language: "Chinese",
      llm_provider: "deepseek",
      quick_think_llm: "deepseek-v4-flash",
      deep_think_llm: "deepseek-v4-pro",
      checkpoint_enabled: false,
    }),
  );
  // 13 initial role.status_changed: 4 analysts pending, others pending (skipped handled by reducer from selected_analysts)
  for (const def of ROLE_REGISTRY) {
    const isAnalyst = def.analyst_key !== null;
    const selected = isAnalyst && def.analyst_key !== null
      ? ["market", "social", "news", "fundamentals"].includes(def.analyst_key)
      : true;
    events.push(
      ev(seq++, "role.status_changed", {
        role_instance_id: roleInstance(def.actor_id),
        previous_status: "pending",
        new_status: selected ? "pending" : "skipped",
        reason: selected ? "initialized" : "not_selected",
      }),
    );
  }
  // analyst.market runs a turn
  events.push(
    ev(seq++, "role.status_changed", {
      role_instance_id: roleInstance("analyst.market"),
      previous_status: "pending",
      new_status: "running",
      reason: "node_entry",
      turn_id: "turn-market-1",
    }),
  );
  events.push(
    ev(seq++, "turn.started", {
      role_instance_id: roleInstance("analyst.market"),
      turn_id: "turn-market-1",
      graph_task_id: "gt-market-1",
      graph_step: 1,
      turn_index: 1,
      turn_status: "started",
    }),
  );
  events.push(
    ev(seq++, "model.started", {
      turn_id: "turn-market-1",
      graph_task_id: "gt-market-1",
      attempt_id: "att-1",
      model_call_id: "mc-1",
      provider: "deepseek",
      model: "deepseek-v4-flash",
      invocation_path: "quick",
    }),
  );
  events.push(
    ev(seq++, "model.completed", {
      turn_id: "turn-market-1",
      graph_task_id: "gt-market-1",
      attempt_id: "att-1",
      model_call_id: "mc-1",
      provider: "deepseek",
      model: "deepseek-v4-flash",
      invocation_path: "quick",
      duration_ms: 1200,
      usage: { total_tokens: 800 },
    }),
  );
  events.push(
    ev(seq++, "turn.output_ready", {
      role_instance_id: roleInstance("analyst.market"),
      turn_id: "turn-market-1",
      graph_task_id: "gt-market-1",
      graph_step: 1,
      turn_index: 1,
      turn_status: "output_ready",
      artifact_id: "art-market-1",
    }),
  );
  events.push(
    ev(seq++, "turn.completed", {
      role_instance_id: roleInstance("analyst.market"),
      turn_id: "turn-market-1",
      graph_task_id: "gt-market-1",
      graph_step: 1,
      turn_index: 1,
      turn_status: "completed",
      reason: "done",
      duration_ms: 1500,
    }),
  );
  events.push(
    ev(seq++, "role.status_changed", {
      role_instance_id: roleInstance("analyst.market"),
      previous_status: "running",
      new_status: "completed",
      reason: "node_complete",
      turn_id: "turn-market-1",
    }),
  );
  events.push(
    ev(seq++, "run.completed", {
      run_status: "completed",
      summary: "done",
      final_signal: "HOLD",
    }),
  );
  return events;
}

describe("F2 runReducer", () => {
  it("batch replay and one-by-one live reduction yield deep-equal state", () => {
    const events = sampleSequence();
    // Batch: fold all events from the initial snapshot-seeded state at once.
    const batchState = events.reduce(
      (s, e) => runReducer(s, { type: "event", event: e }),
      createInitialState(),
    );
    // Live: reduce one at a time (simulates SSE delivery).
    let liveState = createInitialState();
    for (const e of events) {
      liveState = runReducer(liveState, { type: "event", event: e });
    }
    expect(JSON.stringify(liveState)).toEqual(JSON.stringify(batchState));
  });

  it("dedupes by sequence (same event twice is a no-op)", () => {
    const events = sampleSequence();
    let state = createInitialState();
    for (const e of events) state = runReducer(state, { type: "event", event: e });
    const before = JSON.stringify(state);
    // Re-feed the last event - sequence already applied, must be ignored.
    state = runReducer(state, { type: "event", event: events[events.length - 1] });
    expect(JSON.stringify(state)).toEqual(before);
  });

  it("ignores unknown event types without throwing", () => {
    let state = createInitialState();
    const before = JSON.stringify(state);
    state = runReducer(state, {
      type: "event",
      event: ev(999, "future.unknown_type", { whatever: true }),
    });
    // State shape unchanged except latest_sequence/updated_at bumped.
    expect(state.meta.latest_sequence).toBe(999);
    expect(state.roles).toEqual({});
    expect(JSON.stringify({ ...state, meta: { ...state.meta, latest_sequence: 0, updated_at: "" } }))
      .toEqual(JSON.stringify({ ...JSON.parse(before), meta: { ...JSON.parse(before).meta, latest_sequence: 0, updated_at: "" } }));
  });

  it("initializes all 13 roles from run.started with selected/unselected split", () => {
    let state = createInitialState();
    state = runReducer(state, {
      type: "event",
      event: ev(1, "run.started", {
        run_status: "running",
        ticker: "AAPL",
        asset_type: "stock",
        analysis_date: "2026-07-19",
        selected_analysts: ["market"],
        research_depth: 1,
        max_debate_rounds: 1,
        max_risk_discuss_rounds: 1,
        output_language: "English",
        llm_provider: "openai",
        quick_think_llm: "gpt-4o-mini",
        deep_think_llm: "gpt-4o",
        checkpoint_enabled: false,
      }),
    });
    expect(roleList(state)).toHaveLength(13);
    const byActor = Object.fromEntries(state.roles && Object.entries(state.roles).map(([k, v]) => [k, v.status]));
    expect(byActor["analyst.market"]).toBe("pending");
    expect(byActor["analyst.sentiment"]).toBe("skipped");
    expect(byActor["analyst.news"]).toBe("skipped");
    expect(byActor["analyst.fundamentals"]).toBe("skipped");
    expect(byActor["evidence.steward"]).toBe("pending");
    expect(byActor["manager.portfolio"]).toBe("pending");
  });

  it("repeated Bull rounds keep distinct turn_ids on one role card", () => {
    let state = createInitialState();
    state = runReducer(state, {
      type: "event",
      event: ev(1, "run.started", {
        run_status: "running",
        ticker: "AAPL",
        asset_type: "stock",
        analysis_date: "2026-07-19",
        selected_analysts: ["market"],
        research_depth: 3,
        max_debate_rounds: 3,
        max_risk_discuss_rounds: 1,
        output_language: "English",
        llm_provider: "openai",
        quick_think_llm: "gpt-4o-mini",
        deep_think_llm: "gpt-4o",
        checkpoint_enabled: false,
      }),
    });
    const bullRi = roleInstance("researcher.bull");
    state = runReducer(state, { type: "event", event: ev(2, "turn.started", { role_instance_id: bullRi, turn_id: "bull-1", graph_task_id: "gt-1", graph_step: 2, turn_index: 1, turn_status: "started" }) });
    state = runReducer(state, { type: "event", event: ev(3, "turn.started", { role_instance_id: bullRi, turn_id: "bull-2", graph_task_id: "gt-2", graph_step: 3, turn_index: 2, turn_status: "started" }) });
    expect(Object.keys(state.turns)).toContain("bull-1");
    expect(Object.keys(state.turns)).toContain("bull-2");
    expect(state.roles["researcher.bull"].latest_turn_id).toBe("bull-2");
    expect(state.roles["researcher.bull"]).toBeDefined();
    expect(turnTimeline(state, "research").map((t) => t.turn_id)).toEqual(["bull-1", "bull-2"]);
  });

  it("terminal failure converts pending roles to not_reached", () => {
    let state = createInitialState();
    state = runReducer(state, {
      type: "event",
      event: ev(1, "run.started", {
        run_status: "running",
        ticker: "AAPL",
        asset_type: "stock",
        analysis_date: "2026-07-19",
        selected_analysts: ["market"],
        research_depth: 1,
        max_debate_rounds: 1,
        max_risk_discuss_rounds: 1,
        output_language: "English",
        llm_provider: "openai",
        quick_think_llm: "gpt-4o-mini",
        deep_think_llm: "gpt-4o",
        checkpoint_enabled: false,
      }),
    });
    // market completed before failure
    state = runReducer(state, { type: "event", event: ev(2, "role.status_changed", { role_instance_id: roleInstance("analyst.market"), previous_status: "running", new_status: "completed", reason: "done" }) });
    state = runReducer(state, { type: "event", event: ev(3, "run.failed", { run_status: "failed", summary: "provider exploded", error_category: "provider_failure" }) });
    expect(isTerminal(state)).toBe(true);
    expect(state.meta.status).toBe("failed");
    expect(state.meta.error_category).toBe("provider_failure");
    // market stays completed; pending roles (evidence, research, trader, risk, portfolio) -> not_reached
    expect(state.roles["analyst.market"].status).toBe("completed");
    expect(state.roles["evidence.steward"].status).toBe("not_reached");
    expect(state.roles["manager.portfolio"].status).toBe("not_reached");
  });
});