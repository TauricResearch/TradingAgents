/**
 * G3 - RoleInputPanel component tests.
 *
 * Mocks useWorkbenchStore + readArtifactText. Covers: null-turn placeholder,
 * default upstream-input tab with lazy-loaded state_snapshot content, Prompt
 * switching, conditional configuration, and role-header Chinese label + icon.
 */
import { vi, describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { RoleInputPanel } from "./RoleInputPanel";
import type {
  ArtifactRecord,
  ReducerState,
  RunMeta,
  Turn,
  TurnStatus,
} from "../../state/model";

// --- Mocks (hoisted so vi.mock factories can reference them) ---

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

// --- Fixtures ---

function buildTurn(
  turn_id: string,
  actor_id: string,
  status: TurnStatus,
): Turn {
  return {
    turn_id,
    role_instance_id: `test-run:${actor_id}`,
    actor_id,
    turn_index: 1,
    status,
    model_call_ids: [],
    tool_call_ids: [],
    vendor_call_ids: [],
  };
}

function buildArtifact(
  artifact_id: string,
  opts: {
    kind?: string;
    turn_id?: string;
    input_capture_kinds?: string[];
    content_sha256?: string;
    locator?: string;
  } = {},
): ArtifactRecord {
  return {
    artifact_id,
    kind: opts.kind ?? "data_snapshot",
    media_type: "application/json",
    content_sha256: opts.content_sha256 ?? "abc123def456",
    byte_size: 100,
    locator: opts.locator ?? "s3://bucket/key",
    written_sequence: 1,
    input_capture_kinds: opts.input_capture_kinds ?? ["data_snapshot"],
    turn_id: opts.turn_id,
  };
}

function buildState(
  turns: Turn[],
  artifacts: ArtifactRecord[] = [],
): ReducerState {
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
  const artifactsMap: Record<string, ArtifactRecord> = {};
  for (const a of artifacts) artifactsMap[a.artifact_id] = a;
  return {
    meta,
    roles: {},
    turns: turnsMap,
    model_calls: {},
    tool_calls: {},
    vendor_calls: {},
    artifacts: artifactsMap,
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

// --- Tests ---

describe("RoleInputPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockClient.readArtifactText.mockResolvedValue("{}");
    setStoreState(null);
  });

  it("renders placeholder when turn_id is null", () => {
    setStoreState(buildState([]));
    render(<RoleInputPanel turn_id={null} />);
    expect(
      screen.getByText("选择一个角色查看其实际输入"),
    ).toBeInTheDocument();
  });

  it("renders 上游资料 by default and lazy-loads state_snapshot content", async () => {
    mockClient.readArtifactText.mockResolvedValue(
      JSON.stringify({ cash: 82.1, revenue: 300 }),
    );
    const turn = buildTurn("t1", "analyst.market", "completed");
    const artifact = buildArtifact("d1", {
      kind: "state_snapshot",
      turn_id: "t1",
      input_capture_kinds: ["state_snapshot"],
    });
    setStoreState(buildState([turn], [artifact]));
    render(<RoleInputPanel turn_id="t1" />);

    expect(screen.getByText("上游资料")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("82.1")).toBeInTheDocument();
      expect(screen.getByText("300")).toBeInTheDocument();
    });
    expect(mockClient.readArtifactText).toHaveBeenCalledWith("test-run", "d1");
  });

  it("shows prompt_snapshot content when switching to Prompt tab", async () => {
    mockClient.readArtifactText.mockResolvedValue("You are a market analyst.");
    const turn = buildTurn("t1", "analyst.market", "completed");
    const artifact = buildArtifact("p1", {
      kind: "prompt_snapshot",
      turn_id: "t1",
      input_capture_kinds: ["prompt_snapshot"],
    });
    setStoreState(buildState([turn], [artifact]));
    render(<RoleInputPanel turn_id="t1" />);

    // Default 上游资料 tab has no matching artifacts.
    expect(screen.getByText("该视图暂无数据")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Prompt"));
    await waitFor(() => {
      expect(
        screen.getByText("You are a market analyst."),
      ).toBeInTheDocument();
    });
  });

  it("hides configuration when the selected turn has no config snapshot", () => {
    const turn = buildTurn("t1", "analyst.market", "completed");
    const artifact = buildArtifact("d2", {
      kind: "data_snapshot",
      turn_id: "t1",
      input_capture_kinds: ["data_snapshot"],
    });
    setStoreState(buildState([turn], [artifact]));
    render(<RoleInputPanel turn_id="t1" />);

    // data_snapshot is not a role-input capture in actual runs.  It must not
    // create a permanent empty tab just because a synthetic artifact exists.
    expect(screen.getByText("该视图暂无数据")).toBeInTheDocument();
    expect(screen.queryByText("配置")).not.toBeInTheDocument();
  });

  it("shows 上游资料 tab content from a state_snapshot artifact", async () => {
    mockClient.readArtifactText.mockResolvedValue(
      JSON.stringify({ market_report: "bullish", investment_debate_state: { count: 2 } }),
    );
    const turn = buildTurn("t1", "researcher.bull", "completed");
    const artifact = buildArtifact("s1", {
      kind: "state_snapshot",
      turn_id: "t1",
      input_capture_kinds: ["state_snapshot"],
    });
    setStoreState(buildState([turn], [artifact]));
    render(<RoleInputPanel turn_id="t1" />);

    expect(screen.getByText("上游资料")).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => {
      expect(screen.getByText("market_report")).toBeInTheDocument();
      expect(screen.getByText("investment_debate_state")).toBeInTheDocument();
    });
  });

  it("does not expose an empty raw-data tab for data_snapshot artifacts", () => {
    const turn = buildTurn("t1", "analyst.fundamentals", "completed");
    const artifact = buildArtifact("d1", {
      kind: "data_snapshot",
      turn_id: "t1",
      input_capture_kinds: ["data_snapshot"],
      content_sha256: "abc123def456",
      locator: "data/d1.json",
    });
    setStoreState(buildState([turn], [artifact]));
    render(<RoleInputPanel turn_id="t1" />);

    expect(screen.queryByText("原始值")).not.toBeInTheDocument();
    expect(screen.getByText("该视图暂无数据")).toBeInTheDocument();
  });

  it("shows 配置 tab content from a config_snapshot artifact", async () => {
    mockClient.readArtifactText.mockResolvedValue(
      JSON.stringify({ llm_provider: "deepseek", checkpoint_enabled: false }),
    );
    const turn = buildTurn("t1", "evidence.steward", "completed");
    const artifact = buildArtifact("c1", {
      kind: "config_snapshot",
      turn_id: "t1",
      input_capture_kinds: ["config_snapshot"],
    });
    setStoreState(buildState([turn], [artifact]));
    render(<RoleInputPanel turn_id="t1" />);

    fireEvent.click(screen.getByText("配置"));
    await waitFor(() => {
      expect(screen.getByText("llm_provider")).toBeInTheDocument();
      expect(screen.getByText("deepseek")).toBeInTheDocument();
    });
  });

  it("shows the correct Chinese label and icon in role-header", () => {
    const turn = buildTurn("t1", "researcher.bull", "completed");
    setStoreState(buildState([turn]));
    const { container } = render(<RoleInputPanel turn_id="t1" />);

    expect(screen.getByText("多方研究员")).toBeInTheDocument();
    expect(container.querySelector(".role-header svg")).toBeInTheDocument();
  });
});
