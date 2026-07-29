import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import type { ReducerState, RunMeta } from "../../state/model";
import { ROLE_REGISTRY } from "../../state/model";
import { deriveSwarmProgress, deriveWorkerRows, SwarmStatusCard } from "./SwarmStatusCard";

function buildState(): ReducerState {
  const meta: RunMeta = {
    run_id: "run-status",
    status: "running",
    ticker: "600519.SS",
    asset_type: "stock",
    analysis_date: "2026-07-23",
    selected_analysts: ["market", "social", "news", "fundamentals"],
    research_depth: 3,
    max_debate_rounds: 3,
    max_risk_discuss_rounds: 3,
    output_language: "zh-CN",
    llm_provider: "openai",
    quick_think_llm: "quick",
    deep_think_llm: "deep",
    configured_keys: {},
    checkpoint_enabled: false,
    created_at: "2026-07-23T00:00:00.000Z",
    updated_at: "2026-07-23T00:00:30.000Z",
    latest_sequence: 18,
    redaction_manifest: [],
    event_schema_version: 1,
  };
  return {
    meta,
    roles: {
      "analyst.market": {
        actor_id: "analyst.market",
        node_id: "Market Analyst",
        team_id: "analysts",
        status: "completed",
      },
      "analyst.news": {
        actor_id: "analyst.news",
        node_id: "News Analyst",
        team_id: "analysts",
        status: "running",
        current_round: 2,
      },
    },
    turns: {
      market: {
        turn_id: "market",
        role_instance_id: "run-status:analyst.market",
        actor_id: "analyst.market",
        turn_index: 1,
        status: "completed",
        duration_ms: 10_000,
        model_call_ids: [],
        tool_call_ids: [],
        vendor_call_ids: [],
      },
      news: {
        turn_id: "news",
        role_instance_id: "run-status:analyst.news",
        actor_id: "analyst.news",
        turn_index: 2,
        status: "started",
        model_call_ids: [],
        tool_call_ids: ["tool-1"],
        vendor_call_ids: ["vendor-1"],
      },
      candidate: {
        turn_id: "candidate",
        role_instance_id: "run-status:analyst.market",
        actor_id: "analyst.market",
        turn_index: 2,
        status: "output_ready",
        artifact_id: "artifact-1",
        model_call_ids: [],
        tool_call_ids: [],
        vendor_call_ids: [],
      },
    },
    model_calls: {},
    tool_calls: {
      "tool-1": {
        tool_call_id: "tool-1",
        turn_id: "news",
        graph_task_id: "task-1",
        attempt_id: "attempt-1",
        tool_name: "get_market_news",
        status: "requested",
        executions: [{ tool_execution_id: "exec-1", status: "started" }],
      },
    },
    vendor_calls: {
      "vendor-1": {
        vendor_call_id: "vendor-1",
        turn_id: "news",
        graph_task_id: "task-1",
        method: "news",
        vendor: "Tavily",
        stage: "fetch",
        data_status: "running",
        status: "progress",
        cache_hit_ids: [],
      },
    },
    artifacts: {},
    reports: [],
    graph_tasks: {},
    latest_graph_step: 2,
  };
}

describe("SwarmStatusCard", () => {
  it("derives actual worker/tool/source progress from reducer state", () => {
    const progress = deriveSwarmProgress(buildState());

    expect(ROLE_REGISTRY).toHaveLength(13);
    expect(progress.completed_workers).toBe(1);
    expect(progress.settled_workers).toBe(1);
    expect(progress.active_worker?.actor_id).toBe("analyst.news");
    expect(progress.active_turn?.turn_id).toBe("news");
    expect(progress.active_tool?.tool_name).toBe("get_market_news");
    expect(progress.output_ready_count).toBe(1);
    expect(progress.elapsed_label).toBe("30s");
    expect(progress.eta_label).toBe("参考余量 2m 0s");
    expect(progress.aligned_sources[0]?.vendor).toBe("Tavily");
  });

  it("does not invent an ETA without completed duration evidence", () => {
    const state = buildState();
    state.turns.market = { ...state.turns.market, duration_ms: undefined };

    expect(deriveSwarmProgress(state).eta_label).toBeNull();
  });

  it("treats zero duration as unavailable for ETA and worker rows", () => {
    const state = buildState();
    state.turns.market = { ...state.turns.market, duration_ms: 0 };

    expect(deriveSwarmProgress(state).eta_label).toBeNull();
    expect(
      deriveWorkerRows(state).find(
        (row) => row.actor_id === "analyst.market",
      )?.duration_label,
    ).toBe("-");

    render(<SwarmStatusCard state={state} streamStatus="live" />);
    expect(screen.queryByText("0s")).not.toBeInTheDocument();
  });

  it("renders real current worker, tool, output and source alignment", () => {
    render(<SwarmStatusCard state={buildState()} streamStatus="live" />);

    // After adding the per-role worker table, several labels (active worker
    // name, current tool, round) now appear both in the summary header and in
    // the table rows, so assert presence rather than uniqueness.
    expect(screen.getAllByText("新闻分析师").length).toBeGreaterThan(0);
    expect(screen.getByText("1 / 13 已完成")).toBeInTheDocument();
    expect(screen.getByText("1 已就绪")).toBeInTheDocument();
    expect(screen.getAllByText("第 2 轮").length).toBeGreaterThan(0);
    expect(screen.getByText("参考余量 2m 0s")).toBeInTheDocument();
    expect(screen.getAllByText("get_market_news").length).toBeGreaterThan(0);
    expect(screen.getAllByText("执行中").length).toBeGreaterThan(0);
    expect(screen.getByText("Tavily")).toBeInTheDocument();
    expect(screen.getByLabelText("链路推进 8%")).toBeInTheDocument();
  });

  it("derives one stable row per registered role from reducer state", () => {
    const rows = deriveWorkerRows(buildState());

    expect(rows).toHaveLength(13);

    const market = rows.find((r) => r.actor_id === "analyst.market");
    expect(market?.status).toBe("completed");
    expect(market?.tool_name).toBeNull();
    expect(market?.duration_label).toBe("10s");
    expect(market?.round_label).toBe("第 2 轮");

    const news = rows.find((r) => r.actor_id === "analyst.news");
    expect(news?.status).toBe("running");
    expect(news?.tool_name).toBe("get_market_news");
    expect(news?.duration_label).toBe("-");
    expect(news?.round_label).toBe("第 2 轮");

    const steward = rows.find((r) => r.actor_id === "evidence.steward");
    expect(steward?.status).toBe("not_reached");
    expect(steward?.tool_name).toBeNull();
    expect(steward?.duration_label).toBe("-");
    expect(steward?.round_label).toBeNull();
  });

  it("renders a 13-row worker table with per-role status, tool, duration and round", () => {
    render(<SwarmStatusCard state={buildState()} streamStatus="live" />);

    const table = screen.getByLabelText("逐角色状态");
    // 13 body rows + 1 header row, scoped to the worker table only.
    expect(within(table).getAllByRole("row")).toHaveLength(14);
    // Only 2 of 13 roles are seeded; the rest are unreachable.
    expect(within(table).getAllByText("未到达").length).toBeGreaterThan(0);
    expect(within(table).getByText("10s")).toBeInTheDocument();
    expect(within(table).getAllByText("第 2 轮").length).toBe(2);
  });
});
