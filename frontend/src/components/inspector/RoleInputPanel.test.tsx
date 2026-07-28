import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ArtifactRecord, ReducerState, RunMeta, Turn } from "../../state/model";
import { RoleInputPanel } from "./RoleInputPanel";

const mockStore = vi.hoisted(() => ({ useWorkbenchStore: vi.fn() }));
const mockClient = vi.hoisted(() => ({ readArtifactText: vi.fn() }));

vi.mock("../../state/WorkbenchStore", () => ({ useWorkbenchStore: mockStore.useWorkbenchStore }));
vi.mock("../../api/client", () => ({ readArtifactText: mockClient.readArtifactText }));

function meta(run_id = "inspector-run"): RunMeta {
  return {
    run_id, status: "running", ticker: "600519.SS", asset_type: "stock",
    analysis_date: "2026-07-28", selected_analysts: ["market"], research_depth: 3,
    max_debate_rounds: 3, max_risk_discuss_rounds: 2, output_language: "zh",
    llm_provider: "deepseek", quick_think_llm: "quick", deep_think_llm: "deep",
    configured_keys: {}, checkpoint_enabled: true, created_at: "2026-07-28T00:00:00Z",
    updated_at: "2026-07-28T00:00:00Z", latest_sequence: 10,
    redaction_manifest: [], event_schema_version: 1,
  };
}

function artifact(artifact_id: string, kind: string, turn_id: string, input_capture_kinds: string[] = []): ArtifactRecord {
  return {
    artifact_id, kind, media_type: kind === "response" ? "text/markdown" : "application/json",
    content_sha256: `sha-${artifact_id}`, byte_size: 123, locator: `runs/${turn_id}/${artifact_id}`,
    written_sequence: Number(artifact_id.replace(/\D/g, "")) || 1, input_capture_kinds, turn_id,
  };
}

function turn(overrides: Partial<Turn> = {}): Turn {
  return {
    turn_id: "turn-1", role_instance_id: "inspector-run:researcher.bull",
    actor_id: "researcher.bull", turn_index: 2, status: "completed", duration_ms: 0,
    artifact_id: "output-1", model_call_ids: ["model-started", "model-completed"],
    tool_call_ids: [], vendor_call_ids: [], ...overrides,
  };
}

function state(currentTurn = turn(), artifacts: ArtifactRecord[] = []): ReducerState {
  return {
    meta: meta(), roles: {}, turns: { [currentTurn.turn_id]: currentTurn },
    model_calls: {
      "model-started": {
        model_call_id: "model-started", turn_id: currentTurn.turn_id, graph_task_id: "task-1",
        attempt_id: "attempt-1", provider: "old-provider", model: "old-model",
        invocation_path: "old", status: "started", prompt_artifact_ids: [],
      },
      "model-completed": {
        model_call_id: "model-completed", turn_id: currentTurn.turn_id, graph_task_id: "task-1",
        attempt_id: "attempt-2", provider: "openai", model: "gpt-test",
        invocation_path: "new", status: "completed", prompt_artifact_ids: ["prompt-1"],
      },
    },
    tool_calls: {}, vendor_calls: {},
    artifacts: Object.fromEntries(artifacts.map((item) => [item.artifact_id, item])),
    reports: [], graph_tasks: {}, latest_graph_step: 1,
  };
}

function useStateFixture(value: ReducerState | null): void {
  mockStore.useWorkbenchStore.mockReturnValue({
    run_id: value?.meta.run_id ?? null, selectRun: vi.fn(),
    stream: { state: value, status: value ? "live" : "idle", error: null, close: vi.fn() },
  });
}

describe("RoleInputPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockClient.readArtifactText.mockResolvedValue("{}");
    useStateFixture(null);
  });

  it("renders the audit-selection empty state", () => {
    useStateFixture(state(turn({ artifact_id: undefined, model_call_ids: [] })));
    render(<RoleInputPanel turn_id={null} />);
    expect(screen.getByText("选择一个发言查看完整审计信息")).toBeInTheDocument();
  });

  it("renders the four fixed sections and only state_fields as evidence", async () => {
    const artifacts = [
      artifact("state-1", "state_snapshot", "turn-1", ["state_snapshot"]),
      artifact("config-1", "config_snapshot", "turn-1", ["config_snapshot"]),
      artifact("output-1", "response", "turn-1"),
    ];
    mockClient.readArtifactText.mockImplementation(async (_run: string, id: string) => ({
      "state-1": JSON.stringify({
        projection_version: 1, actor_id: "researcher.bull", node_id: "Bull Researcher",
        state_fields: { market_report: "## Market report\nActual prose", investment_debate_state: { history: "prior debate" } },
        effective_config_artifact_id: "config-1",
      }),
      "config-1": JSON.stringify({ values: { temperature: 0.2, output_language: "zh" } }),
      "output-1": "## Bull conclusion\nBuy with caution.",
    } as Record<string, string>)[id] ?? "{}");
    useStateFixture(state(turn(), artifacts));
    const { container } = render(<RoleInputPanel turn_id="turn-1" />);

    const headings = screen.getAllByRole("heading", { level: 3 }).map((node) => node.textContent);
    expect(headings).toEqual(["角色与执行事实", "证据、数据与工具", "角色输出"]);
    const sections = [...container.querySelectorAll(".inspector-section")];
    expect(sections.map((node) => node.className)).toEqual([
      "inspector-section inspector-identity",
      "inspector-section inspector-evidence",
      "inspector-section inspector-prompt",
      "inspector-section inspector-output",
    ]);
    expect(screen.getByText("多方研究员")).toBeInTheDocument();
    expect(screen.getByText("第 2 轮")).toBeInTheDocument();
    expect(screen.getByText("已完成")).toBeInTheDocument();
    expect(screen.getAllByText("不可用").length).toBeGreaterThan(0);
    expect(screen.getByText("openai")).toBeInTheDocument();
    expect(screen.getByText("gpt-test")).toBeInTheDocument();
    expect(screen.getByText("未调用工具")).toBeInTheDocument();

    await waitFor(() => expect(screen.getByText("Actual prose")).toBeInTheDocument());
    const parsedFields = screen.getByLabelText("解析后的字段值");
    expect(within(parsedFields).getByText("market_report")).toBeInTheDocument();
    expect(parsedFields).toHaveTextContent("prior debate");
    for (const metadata of ["actor_id", "node_id", "projection_version", "effective_config_artifact_id"]) {
      expect(within(parsedFields).queryByText(metadata)).not.toBeInTheDocument();
    }
    expect(await screen.findByText("0.2")).toBeInTheDocument();
    expect(await screen.findByText("Buy with caution.")).toBeInTheDocument();
    expect(container.querySelector(".output-artifact .prose")).not.toBeNull();
    expect(screen.queryByText("数据字段")).not.toBeInTheDocument();
    expect(screen.queryByText("原始值")).not.toBeInTheDocument();
    expect(container.querySelector(".audit-tabs")).toBeNull();
  });

  it("expands tool details and lazy-loads prompt content only after disclosure opens", async () => {
    const current = turn({ tool_call_ids: ["tool-1"], artifact_id: undefined });
    const snapshot = artifact("state-2", "state_snapshot", "turn-1", ["state_snapshot"]);
    const prompt = artifact("prompt-1", "prompt_snapshot", "turn-1", ["prompt_snapshot"]);
    const value = state(current, [snapshot, prompt]);
    value.tool_calls["tool-1"] = {
      tool_call_id: "tool-1", turn_id: "turn-1", graph_task_id: "task-1", attempt_id: "attempt-2",
      tool_name: "get_stock_data", arguments: { ticker: "600519.SS" }, status: "committed",
      executions: [{ tool_execution_id: "exec-1", status: "completed" }],
    };
    mockClient.readArtifactText.mockImplementation(async (_run: string, id: string) =>
      id === "state-2" ? JSON.stringify({ state_fields: { market_report: "ready" } }) : "SYSTEM: inspect evidence",
    );
    useStateFixture(value);
    const { container } = render(<RoleInputPanel turn_id="turn-1" />);

    fireEvent.click(screen.getByRole("button", { name: /get_stock_data/ }));
    expect(screen.getByText(/600519\.SS/)).toBeInTheDocument();
    expect(screen.getAllByText("已完成").length).toBeGreaterThan(0);

    const disclosure = container.querySelector("details.inspector-prompt") as HTMLDetailsElement;
    expect(disclosure.open).toBe(false);
    await waitFor(() => expect(mockClient.readArtifactText).toHaveBeenCalledWith("inspector-run", "state-2"));
    expect(mockClient.readArtifactText).not.toHaveBeenCalledWith("inspector-run", "prompt-1");
    fireEvent.click(within(disclosure).getByText("模型实际输入"));
    expect(disclosure.open).toBe(true);
    expect(await screen.findByText(/SYSTEM: inspect evidence/)).toBeInTheDocument();
    expect(mockClient.readArtifactText).toHaveBeenCalledWith("inspector-run", "prompt-1");
    expect(container.querySelector(".prompt-artifact .datablock")).not.toBeNull();
  });
});
