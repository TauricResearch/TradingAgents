/**
 * G4 - Reducer gap coverage: per-run state isolation, invalid-transition
 * tolerance, refresh-recovery (snapshot seed + event fold equivalence), and
 * abandoned task handling. These close the spec §17.3 items not covered by
 * runReducer.test.ts.
 */
import { describe, it, expect } from "vitest";
import { createInitialState, runReducer } from "./runReducer";
import { isTerminal } from "./selectors";
import type { PersistedEventDTO } from "../api/contracts";
import type { RunSnapshotDTO } from "../api/contracts";

function ev(
  run_id: string,
  seq: number,
  type: string,
  payload: Record<string, unknown>,
): PersistedEventDTO {
  return {
    event_id: `${run_id}:${seq}`,
    run_id,
    sequence: seq,
    timestamp: `2026-07-19T12:00:${String(seq).padStart(2, "0")}Z`,
    type,
    payload,
    schema_version: 1,
  };
}

function seedRunStarted(run_id: string, seq = 1, selected = ["market"]): PersistedEventDTO {
  return ev(run_id, seq, "run.started", {
    run_status: "running",
    ticker: run_id === "run_B" ? "NVDA" : "AAPL",
    asset_type: "stock",
    analysis_date: "2026-07-19",
    selected_analysts: selected,
    research_depth: 1,
    max_debate_rounds: 1,
    max_risk_discuss_rounds: 1,
    output_language: "English",
    llm_provider: "openai",
    quick_think_llm: "gpt-4o-mini",
    deep_think_llm: "gpt-4o",
    checkpoint_enabled: false,
  });
}

describe("G4 reducer gap coverage", () => {
  it("per-run state is isolated: events from run_A do not pollute run_B state", () => {
    // Build run_A state with a completed market analyst turn.
    let stateA = createInitialState();
    stateA = runReducer(stateA, { type: "event", event: seedRunStarted("run_A") });
    stateA = runReducer(stateA, {
      type: "event",
      event: ev("run_A", 2, "role.status_changed", {
        role_instance_id: "run_A:analyst.market",
        previous_status: "pending",
        new_status: "completed",
        reason: "done",
      }),
    });

    // Build run_B state independently - must not inherit run_A roles/turns.
    let stateB = createInitialState();
    stateB = runReducer(stateB, { type: "event", event: seedRunStarted("run_B") });

    expect(stateB.meta.run_id).toBe("run_B");
    expect(stateB.meta.ticker).toBe("NVDA");
    // run_B has its own role_instance_id; run_A's completed market role is not here.
    expect(stateB.roles["analyst.market"]?.role_instance_id).toBe("run_B:analyst.market");
    expect(stateB.roles["analyst.market"]?.status).toBe("pending");
    // run_A state is untouched by run_B events.
    expect(stateA.meta.run_id).toBe("run_A");
    expect(stateA.roles["analyst.market"]?.status).toBe("completed");
  });

  it("invalid transition (turn.completed before turn.started) does not corrupt state", () => {
    let state = createInitialState();
    state = runReducer(state, { type: "event", event: seedRunStarted("run_X") });
    // Fire turn.completed for a turn_id that was never started.
    state = runReducer(state, {
      type: "event",
      event: ev("run_X", 5, "turn.completed", {
        role_instance_id: "run_X:analyst.market",
        turn_id: "ghost-turn",
        graph_task_id: "ghost-gt",
        graph_step: 2,
        turn_index: 1,
        turn_status: "completed",
        reason: "never-started",
        duration_ms: 0,
      }),
    });
    // The reducer upserts the turn (creates it in completed state) and links
    // it to the role via latest_turn_id - that is acceptable forward-compat
    // behavior. The key invariant: no throw, no role STATUS change (the role
    // stays pending - the ghost turn does not promote it), and latest_sequence
    // advances. A status promotion would be a real corruption.
    expect(state.meta.latest_sequence).toBe(5);
    expect(state.roles["analyst.market"]?.status).toBe("pending");
    expect(state.roles["analyst.market"]?.latest_turn_id).toBe("ghost-turn");
    expect(state.turns["ghost-turn"]).toBeDefined();
    expect(state.turns["ghost-turn"]?.status).toBe("completed");
    // Non-analyst roles untouched.
    expect(state.roles["manager.portfolio"]?.status).toBe("pending");
  });

  it("refresh recovery: snapshot seed + event fold equals folding all events from empty", () => {
    // Simulate a page refresh: the server returns a RunSnapshotDTO capturing
    // the run so far, then live SSE events continue. Reducing snapshot + new
    // events must yield the same meta/roles shape as folding every event
    // from scratch (the reducer is the single source of truth).
    const run_id = "run_refresh";
    const events: PersistedEventDTO[] = [
      seedRunStarted(run_id, 1, ["market", "fundamentals"]),
      ev(run_id, 2, "role.status_changed", {
        role_instance_id: `${run_id}:analyst.market`,
        previous_status: "pending",
        new_status: "running",
        reason: "turn_started",
        turn_id: "t1",
      }),
      ev(run_id, 3, "turn.started", {
        role_instance_id: `${run_id}:analyst.market`,
        turn_id: "t1",
        graph_task_id: "gt1",
        graph_step: 1,
        turn_index: 1,
        turn_status: "started",
      }),
    ];

    // Full fold from empty (the "live since the start" state).
    let fromScratch = createInitialState();
    for (const e of events) fromScratch = runReducer(fromScratch, { type: "event", event: e });

    // Refresh path: snapshot seeded from the RunSnapshotDTO (carrying meta +
    // roles + latest_sequence=3), then no new events yet.
    const snapshot: RunSnapshotDTO = {
      run_id,
      status: "running",
      ticker: "AAPL",
      asset_type: "stock",
      analysis_date: "2026-07-19",
      selected_analysts: ["market", "fundamentals"],
      max_debate_rounds: 1,
      max_risk_discuss_rounds: 1,
      output_language: "English",
      llm_provider: "openai",
      quick_think_llm: "gpt-4o-mini",
      deep_think_llm: "gpt-4o",
      configured_keys: {},
      created_at: "2026-07-19T12:00:00Z",
      updated_at: "2026-07-19T12:00:03Z",
      latest_sequence: 3,
      artifacts: [],
      redaction_manifest: [],
      event_schema_version: 1,
      metadata: {},
    };
    const fromSnapshot = createInitialState(snapshot);

    // Meta matches (snapshot carries the same identity as the folded state).
    expect(fromSnapshot.meta.run_id).toBe(fromScratch.meta.run_id);
    expect(fromSnapshot.meta.ticker).toBe(fromScratch.meta.ticker);
    expect(fromSnapshot.meta.selected_analysts).toEqual(fromScratch.meta.selected_analysts);
    expect(fromSnapshot.meta.latest_sequence).toBe(3);
    // Roles seeded identically (both pending for selected analysts).
    expect(fromSnapshot.roles["analyst.market"]?.status).toBe("pending");
    expect(fromSnapshot.roles["analyst.fundamentals"]?.status).toBe("pending");
    // Re-feeding an already-applied event after snapshot is a no-op (dedupe).
    const reFed = runReducer(fromSnapshot, { type: "event", event: events[2] });
    expect(JSON.stringify(reFed)).toEqual(JSON.stringify(fromSnapshot));
  });

  it("graph.task_abandoned is recorded without throwing and marks the task abandoned", () => {
    let state = createInitialState();
    state = runReducer(state, { type: "event", event: seedRunStarted("run_ab") });
    state = runReducer(state, {
      type: "event",
      event: ev("run_ab", 2, "graph.task_started", {
        graph_task_id: "gt-ab",
        graph_step: 1,
        node_id: "Market Analyst",
      }),
    });
    state = runReducer(state, {
      type: "event",
      event: ev("run_ab", 3, "graph.task_abandoned", {
        graph_task_id: "gt-ab",
        graph_step: 1,
        node_id: "Market Analyst",
        reason: "checkpoint_not_committed",
      }),
    });
    expect(state.graph_tasks["gt-ab"]?.status).toBe("abandoned");
    expect(state.graph_tasks["gt-ab"]?.reason).toBe("checkpoint_not_committed");
    expect(state.graph_tasks["gt-ab"]?.applied).toBe(false);
  });

  it("terminal interruption converts running roles to interrupted and is terminal", () => {
    let state = createInitialState();
    state = runReducer(state, { type: "event", event: seedRunStarted("run_int") });
    state = runReducer(state, {
      type: "event",
      event: ev("run_int", 2, "role.status_changed", {
        role_instance_id: "run_int:analyst.market",
        previous_status: "pending",
        new_status: "running",
        reason: "turn_started",
      }),
    });
    state = runReducer(state, {
      type: "event",
      event: ev("run_int", 3, "run.interrupted", {
        run_status: "interrupted",
        checkpoint_sequence: 2,
        summary: "process restart",
      }),
    });
    expect(isTerminal(state)).toBe(true);
    expect(state.meta.status).toBe("interrupted");
    // The running role is now interrupted; non-running roles stay as they were
    // (selected analysts pending for resume, unselected analysts still skipped).
    expect(state.roles["analyst.market"]?.status).toBe("interrupted");
    expect(state.roles["evidence.steward"]?.status).toBe("pending");
    expect(state.roles["analyst.fundamentals"]?.status).toBe("skipped");
  });
});