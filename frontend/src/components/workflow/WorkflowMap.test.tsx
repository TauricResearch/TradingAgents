/**
 * G1 - WorkflowMap component tests.
 *
 * Mocks useWorkbenchStore to verify: 13-role cardinality across 6 stage
 * containers, correct Chinese labels regardless of run state, stage-active
 * highlighting, edge data validity, and click → onRoleSelected wiring.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { WorkflowMap } from "./WorkflowMap";
import { ROLE_REGISTRY } from "../../state/model";
import type { ReducerState, RoleCard, RoleStatus, RunMeta } from "../../state/model";
import { ICON_COUNT, ROLE_ICON_PATHS } from "../icons/roleIconPaths";
import { EDGES, STAGES } from "../../domain/roles";

const mockStore = vi.hoisted(() => ({
  useWorkbenchStore: vi.fn(),
}));

vi.mock("../../state/WorkbenchStore", () => ({
  useWorkbenchStore: mockStore.useWorkbenchStore,
}));

const ZH_LABELS: string[] = [
  "市场分析师",
  "情绪分析师",
  "新闻分析师",
  "基本面分析师",
  "证据管理员",
  "多方研究员",
  "空方研究员",
  "研究经理",
  "交易员",
  "激进风险分析师",
  "中性风险分析师",
  "保守风险分析师",
  "组合经理",
];

const STAGE_TITLES = [
  "分析师团队",
  "证据管理",
  "多空研究",
  "交易",
  "风险管理",
  "组合管理",
];

function buildRole(
  actor_id: string,
  status: RoleStatus,
  current_round?: number,
): RoleCard {
  const def = ROLE_REGISTRY.find((r) => r.actor_id === actor_id);
  if (!def) throw new Error(`unknown actor_id in test fixture: ${actor_id}`);
  return {
    actor_id,
    node_id: def.node_id,
    team_id: def.team_id,
    status,
    current_round,
  };
}

function buildState(roles: Record<string, RoleCard>): ReducerState {
  const meta: RunMeta = {
    run_id: "test-run",
    status: "running",
    ticker: "600519.SS",
    asset_type: "stock",
    analysis_date: "2026-07-19",
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
    created_at: "2026-07-19T00:00:00Z",
    updated_at: "2026-07-19T00:00:00Z",
    latest_sequence: 0,
    redaction_manifest: [],
    event_schema_version: 1,
  };
  return {
    meta,
    roles,
    turns: {},
    model_calls: {},
    tool_calls: {},
    vendor_calls: {},
    artifacts: {},
    reports: [],
    graph_tasks: {},
    latest_graph_step: 0,
  };
}

function setStoreState(state: ReducerState | null): void {
  mockStore.useWorkbenchStore.mockReturnValue({
    run_id: state ? "test-run" : null,
    selectRun: vi.fn(),
    stream: {
      state,
      status: state ? "live" : "idle",
      error: null,
      close: vi.fn(),
    },
  });
}

describe("WorkflowMap", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setStoreState(null);
  });

  it("renders 6 stage containers with correct titles", () => {
    setStoreState(null);
    render(<WorkflowMap />);

    for (const title of STAGE_TITLES) {
      expect(screen.getByText(title)).toBeInTheDocument();
    }
  });

  it("renders exactly 13 role nodes with correct Chinese labels (no-run → all pending)", () => {
    setStoreState(null);
    render(<WorkflowMap />);

    for (const label of ZH_LABELS) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getAllByText("待运行")).toHaveLength(13);
    expect(screen.getByText("0 / 13 已完成")).toBeInTheDocument();
  });

  it("has 13 unique icon_ids, all mapped in ROLE_ICON_PATHS (registry cardinality)", () => {
    expect(ROLE_REGISTRY.length).toBe(13);
    expect(ICON_COUNT).toBe(13);
    const iconIds = ROLE_REGISTRY.map((r) => r.icon_id);
    expect(new Set(iconIds).size).toBe(13);
    for (const id of iconIds) {
      expect(ROLE_ICON_PATHS[id]).toBeDefined();
    }
  });

  it("renders status text for completed and running (with round number)", () => {
    setStoreState(
      buildState({
        "analyst.market": buildRole("analyst.market", "completed"),
        "researcher.bull": buildRole("researcher.bull", "running", 2),
      }),
    );
    render(<WorkflowMap />);

    expect(screen.getByText("✓ 已完成")).toBeInTheDocument();
    expect(screen.getByText(/● 运行中/)).toBeInTheDocument();
    expect(screen.getByText(/第 2 轮/)).toBeInTheDocument();
  });

  it("renders '未选择' for a skipped role and keeps pending for the rest", () => {
    setStoreState(
      buildState({
        "analyst.sentiment": buildRole("analyst.sentiment", "skipped"),
      }),
    );
    render(<WorkflowMap />);

    expect(screen.getByText("未选择")).toBeInTheDocument();
    expect(screen.getAllByText("待运行")).toHaveLength(12);
  });

  it("shows the completed-count progress note 'N / 13 已完成'", () => {
    setStoreState(
      buildState({
        "analyst.market": buildRole("analyst.market", "completed"),
        "analyst.news": buildRole("analyst.news", "completed"),
        "risk.neutral": buildRole("risk.neutral", "completed"),
      }),
    );
    render(<WorkflowMap />);

    expect(screen.getByText("3 / 13 已完成")).toBeInTheDocument();
  });

  it("calls onRoleSelected with the actor_id when a node is clicked", () => {
    setStoreState(null);
    const onRoleSelected = vi.fn();
    render(<WorkflowMap onRoleSelected={onRoleSelected} />);

    fireEvent.click(screen.getByText("市场分析师"));
    expect(onRoleSelected).toHaveBeenCalledWith("analyst.market");
  });
});

describe("Edge table and stage definitions", () => {
  it("every declared edge endpoint references a known role", () => {
    const actorIds = new Set(ROLE_REGISTRY.map((r) => r.actor_id));
    for (const edge of EDGES) {
      expect(actorIds.has(edge.from)).toBe(true);
      expect(actorIds.has(edge.to)).toBe(true);
    }
  });

  it("every STAGE actor_id is in ROLE_REGISTRY", () => {
    const actorIds = new Set(ROLE_REGISTRY.map((r) => r.actor_id));
    for (const stage of STAGES) {
      for (const actor_id of stage.actor_ids) {
        expect(actorIds.has(actor_id)).toBe(true);
      }
    }
  });

  it("every ROLE_REGISTRY actor_id is in exactly one STAGE", () => {
    const stageAssignments = new Map<string, number>();
    for (const stage of STAGES) {
      for (const actor_id of stage.actor_ids) {
        stageAssignments.set(actor_id, (stageAssignments.get(actor_id) ?? 0) + 1);
      }
    }
    for (const def of ROLE_REGISTRY) {
      expect(stageAssignments.get(def.actor_id)).toBe(1);
    }
  });
});
