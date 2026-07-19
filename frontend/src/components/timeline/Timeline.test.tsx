/**
 * G2 - Timeline component tests.
 *
 * Mocks useWorkbenchStore + readArtifactText. extractResponse is imported
 * from the real module (pure function, no side effects).
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { Timeline } from "./Timeline";
import { extractResponse } from "../../domain/responseExtractor";
import type { ReducerState, RunMeta, Turn, TurnStatus } from "../../state/model";

// --- Mocks (hoisted so vi.mock factories can reference them) -------------

const mockStore = vi.hoisted(() => ({
  useWorkbenchStore: vi.fn(),
}));

vi.mock("../../state/WorkbenchStore", () => ({
  useWorkbenchStore: mockStore.useWorkbenchStore,
}));

const mockClient = vi.hoisted(() => ({
  readArtifactText: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  readArtifactText: mockClient.readArtifactText,
}));

// --- Fixtures ------------------------------------------------------------

function buildTurn(
  turn_id: string,
  actor_id: string,
  status: TurnStatus,
  opts: { artifact_id?: string; turn_index?: number } = {},
): Turn {
  return {
    turn_id,
    role_instance_id: `test-run:${actor_id}`,
    actor_id,
    turn_index: opts.turn_index ?? 1,
    status,
    artifact_id: opts.artifact_id,
    model_call_ids: [],
    tool_call_ids: [],
    vendor_call_ids: [],
  };
}

function buildState(turns: Turn[]): ReducerState {
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
  const turnsMap: Record<string, Turn> = {};
  for (const t of turns) turnsMap[t.turn_id] = t;
  return {
    meta,
    roles: {},
    turns: turnsMap,
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

// --- Tests ---------------------------------------------------------------

describe("extractResponse", () => {
  it("extracts market_report for analyst.market", () => {
    const result = extractResponse("analyst.market", {
      market_report: "bullish tech",
    });
    expect(result).toEqual({ text: "bullish tech", badge: null });
  });

  it("extracts investment_debate_state.current_response for researcher.bull", () => {
    const result = extractResponse("researcher.bull", {
      investment_debate_state: { current_response: "bull case" },
    });
    expect(result).toEqual({ text: "bull case", badge: null });
  });

  it("extracts final_trade_decision for manager.portfolio", () => {
    const result = extractResponse("manager.portfolio", {
      final_trade_decision: "BUY",
    });
    expect(result).toEqual({ text: "BUY", badge: null });
  });

  it("returns null text for empty delta", () => {
    const result = extractResponse("analyst.market", {});
    expect(result).toEqual({ text: null, badge: null });
  });

  it("returns null text for non-string field", () => {
    const result = extractResponse("analyst.market", { market_report: 42 });
    expect(result).toEqual({ text: null, badge: null });
  });

  it("extracts evidence_status as badge for evidence.steward", () => {
    const result = extractResponse("evidence.steward", {
      evidence_report: "sufficient evidence",
      evidence_status: "Sufficient",
    });
    expect(result).toEqual({ text: "sufficient evidence", badge: "Sufficient" });
  });

  it("extracts judge_decision as badge for manager.portfolio", () => {
    const result = extractResponse("manager.portfolio", {
      final_trade_decision: "BUY",
      risk_debate_state: { judge_decision: "Aggressive" },
    });
    expect(result).toEqual({ text: "BUY", badge: "Aggressive" });
  });
});

describe("Timeline", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setStoreState(null);
  });

  it("renders turns with Chinese labels and filter buttons", () => {
    setStoreState(
      buildState([
        buildTurn("t1", "analyst.market", "completed", { artifact_id: "a1" }),
        buildTurn("t2", "researcher.bull", "started"),
        buildTurn("t3", "manager.portfolio", "completed", {
          artifact_id: "a3",
        }),
      ]),
    );
    render(<Timeline filter="" onTurnSelected={vi.fn()} />);

    expect(screen.getByText("市场分析师")).toBeInTheDocument();
    expect(screen.getByText("多方研究员")).toBeInTheDocument();
    expect(screen.getByText("组合经理")).toBeInTheDocument();
    expect(screen.getByText("（进行中）")).toBeInTheDocument();

    expect(screen.getByText("全部")).toBeInTheDocument();
    expect(screen.getByText("分析师")).toBeInTheDocument();
    expect(screen.getByText("多空辩论")).toBeInTheDocument();
    expect(screen.getByText("风险")).toBeInTheDocument();
    // "裁决" appears both as a filter button and as the manager.portfolio turn tag.
    expect(screen.getAllByText("裁决").length).toBeGreaterThanOrEqual(1);
  });

  it("renders placeholder when no run is selected", () => {
    setStoreState(null);
    render(<Timeline filter="" onTurnSelected={vi.fn()} />);
    expect(
      screen.getByText("发起分析后查看辩论时间线"),
    ).toBeInTheDocument();
  });

  it("filters turns by team when filter is set", () => {
    setStoreState(
      buildState([
        buildTurn("t1", "analyst.market", "completed", { artifact_id: "a1" }),
        buildTurn("t2", "researcher.bull", "started"),
        buildTurn("t3", "manager.portfolio", "completed", {
          artifact_id: "a3",
        }),
      ]),
    );
    render(<Timeline filter="research" onTurnSelected={vi.fn()} />);

    expect(screen.getByText("多方研究员")).toBeInTheDocument();
    expect(screen.queryByText("市场分析师")).not.toBeInTheDocument();
    expect(screen.queryByText("组合经理")).not.toBeInTheDocument();
  });

  it("shows candidate tag for output_ready turns, not for completed", () => {
    setStoreState(
      buildState([
        buildTurn("t1", "analyst.market", "output_ready", {
          artifact_id: "a1",
        }),
        buildTurn("t2", "researcher.bull", "completed", {
          artifact_id: "a2",
        }),
      ]),
    );
    render(<Timeline filter="" onTurnSelected={vi.fn()} />);

    expect(screen.getAllByText("候选")).toHaveLength(1);
  });

  it("lazy-loads response text on bubble click", async () => {
    mockClient.readArtifactText.mockResolvedValue(
      JSON.stringify({ market_report: "price up" }),
    );
    setStoreState(
      buildState([
        buildTurn("t1", "analyst.market", "completed", { artifact_id: "a1" }),
      ]),
    );
    render(<Timeline filter="" onTurnSelected={vi.fn()} />);

    expect(screen.getByText("点击展开")).toBeInTheDocument();
    fireEvent.click(screen.getByText("市场分析师"));
    await waitFor(() => {
      expect(screen.getByText("price up")).toBeInTheDocument();
    });
    expect(mockClient.readArtifactText).toHaveBeenCalledWith("test-run", "a1");
  });
});
