/**
 * G3 - Tests for ToolCallCard, VendorProvenance, and SafeMarkdown.
 *
 * Covers: collapsed/expanded rendering + arguments/executions visibility,
 * status tone labels (已提交 green / 失败 red), vendor-call filtering by turn
 * + empty placeholder, and SafeMarkdown HTML escaping (<script> rendered as
 * inert escaped text, not executed).
 *
 * useWorkbenchStore is mocked (hoisted) for VendorProvenance; ToolCallCard and
 * SafeMarkdown are pure-prop components and need no store context.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ToolCallCard } from "./ToolCallCard";
import { VendorProvenance } from "./VendorProvenance";
import { SafeMarkdown } from "../shared/SafeMarkdown";
import type {
  LogicalToolCall,
  ReducerState,
  RunMeta,
  VendorCall,
} from "../../state/model";

// --- Mocks (hoisted so vi.mock factories can reference them) -------------

const mockStore = vi.hoisted(() => ({
  useWorkbenchStore: vi.fn(),
}));

vi.mock("../../state/WorkbenchStore", () => ({
  useWorkbenchStore: mockStore.useWorkbenchStore,
}));

// --- Fixtures ------------------------------------------------------------

function buildTool(
  overrides: Partial<LogicalToolCall> = {},
): LogicalToolCall {
  return {
    tool_call_id: "tc1",
    turn_id: "turn-abc-123",
    graph_task_id: "gt1",
    attempt_id: "att1",
    tool_name: "get_stock_data",
    arguments: { ticker: "600519.SS", period: "1d" },
    status: "committed",
    executions: [
      { tool_execution_id: "ex1", status: "completed" },
      { tool_execution_id: "ex2", status: "completed" },
    ],
    ...overrides,
  };
}

function buildVendorCall(
  overrides: Partial<VendorCall> = {},
): VendorCall {
  return {
    vendor_call_id: "vc1",
    turn_id: "turn-1",
    graph_task_id: "gt1",
    method: "daily",
    vendor: "tushare",
    stage: "fetch",
    data_status: "ok",
    status: "completed",
    duration_ms: 120,
    cache_hit_ids: [],
    ...overrides,
  };
}

function buildState(vendorCalls: VendorCall[]): ReducerState {
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
  const vendor_calls: Record<string, VendorCall> = {};
  for (const vc of vendorCalls) vendor_calls[vc.vendor_call_id] = vc;
  return {
    meta,
    roles: {},
    turns: {},
    model_calls: {},
    tool_calls: {},
    vendor_calls,
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

// --- ToolCallCard --------------------------------------------------------

describe("ToolCallCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders tool_name + status; collapsed by default (no arguments shown)", () => {
    const tool = buildTool();
    const { container } = render(
      <ToolCallCard tool={tool} run_id="test-run" />,
    );

    expect(screen.getByText("get_stock_data")).toBeInTheDocument();
    expect(screen.getByText("已提交")).toBeInTheDocument();
    // Body is not rendered when collapsed: arguments + executions absent.
    expect(container.textContent).not.toContain("600519");
    expect(container.textContent).not.toContain("ex1");
  });

  it("expands on click and shows arguments JSON + executions", () => {
    const tool = buildTool();
    const { container } = render(
      <ToolCallCard tool={tool} run_id="test-run" />,
    );

    fireEvent.click(screen.getByText("get_stock_data"));

    expect(container.textContent).toContain("600519.SS");
    expect(container.textContent).toContain("ex1");
    expect(container.textContent).toContain("ex2");
  });

  it("shows 已提交 (green) for committed and 失败 (red) for failed", () => {
    const committed = buildTool({
      tool_call_id: "tc-c",
      status: "committed",
    });
    const { rerender } = render(
      <ToolCallCard tool={committed} run_id="test-run" />,
    );

    const committedStatus = screen.getByText("已提交");
    expect(committedStatus).toBeInTheDocument();
    expect(committedStatus).toHaveAttribute("data-tone", "green");

    const failed = buildTool({
      tool_call_id: "tc-f",
      status: "failed",
    });
    rerender(<ToolCallCard tool={failed} run_id="test-run" />);

    const failedStatus = screen.getByText("失败");
    expect(failedStatus).toBeInTheDocument();
    expect(failedStatus).toHaveAttribute("data-tone", "red");
  });
});

// --- VendorProvenance ----------------------------------------------------

describe("VendorProvenance", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders vendor calls for the turn; empty shows placeholder", () => {
    setStoreState(
      buildState([
        buildVendorCall({
          vendor_call_id: "vc1",
          turn_id: "turn-1",
          vendor: "tushare",
        }),
        buildVendorCall({
          vendor_call_id: "vc2",
          turn_id: "turn-2",
          vendor: "akshare",
        }),
      ]),
    );

    const { rerender } = render(<VendorProvenance turn_id="turn-1" />);

    expect(screen.getByText("tushare")).toBeInTheDocument();
    // vc2 belongs to turn-2, must NOT appear for turn-1.
    expect(screen.queryByText("akshare")).not.toBeInTheDocument();

    // No calls match turn-99 -> placeholder.
    rerender(<VendorProvenance turn_id="turn-99" />);
    expect(screen.getByText("本轮无数据调用")).toBeInTheDocument();
  });
});

// --- SafeMarkdown --------------------------------------------------------

describe("SafeMarkdown", () => {
  it("escapes HTML: <script> renders as escaped text, not executed", () => {
    const content = "<script>alert(1)</script>";
    const { container } = render(<SafeMarkdown content={content} />);

    // No live script element is created in the DOM.
    expect(container.querySelector("script")).toBeNull();
    // Angle brackets are escaped to entities in the serialized HTML.
    expect(container.innerHTML).toContain("&lt;script&gt;");
    // Visible text is the literal <script> source, not executed.
    expect(container.textContent).toContain("<script>alert(1)</script>");
  });
});
