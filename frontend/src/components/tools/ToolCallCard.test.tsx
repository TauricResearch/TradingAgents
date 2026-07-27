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
  describe("prose mode (default)", () => {
    it("renders headings as heading elements", () => {
      const content = "# H1\n\n## H2\n\n### H3";
      const { container } = render(<SafeMarkdown content={content} />);
      expect(container.querySelector("h1")).not.toBeNull();
      expect(container.querySelector("h2")).not.toBeNull();
      expect(container.querySelector("h3")).not.toBeNull();
      expect(container.querySelector("h1")?.textContent).toBe("H1");
    });

    it("renders bullet and numbered lists", () => {
      const content = "- item a\n- item b\n\n1. first\n2. second";
      const { container } = render(<SafeMarkdown content={content} />);
      const ul = container.querySelector("ul");
      const ol = container.querySelector("ol");
      expect(ul).not.toBeNull();
      expect(ol).not.toBeNull();
      expect(ul?.querySelectorAll("li").length).toBe(2);
      expect(ol?.querySelectorAll("li").length).toBe(2);
    });

    it("renders GFM tables with alignment row consumed", () => {
      const content = [
        "| Name | Value |",
        "| :--- | ----: |",
        "| foo  |    42 |",
        "| bar  |     7 |",
      ].join("\n");
      const { container } = render(<SafeMarkdown content={content} />);
      const table = container.querySelector("table");
      expect(table).not.toBeNull();
      const ths = table?.querySelectorAll("th");
      const tds = table?.querySelectorAll("td");
      expect(ths?.length).toBe(2);
      expect(tds?.length).toBe(4);
      expect(ths?.[0]?.textContent).toBe("Name");
      // Alignment row is consumed into th styling, not a data row.
      expect(table?.querySelectorAll("tr").length).toBe(3); // header + 2 data
    });

    it("strips <script> tags via sanitization", () => {
      const content = "hello <script>alert(1)</script> world";
      const { container } = render(<SafeMarkdown content={content} />);
      expect(container.querySelector("script")).toBeNull();
      expect(container.textContent).toContain("hello");
      expect(container.textContent).toContain("world");
    });

    it("strips event handler attributes", () => {
      const content = '![x](y) onerror="alert(1)"';
      const { container } = render(<SafeMarkdown content={content} />);
      const img = container.querySelector("img");
      expect(img).not.toBeNull();
      expect(img?.hasAttribute("onerror")).toBe(false);
    });

    it("rejects javascript: href scheme", () => {
      const content = '[click](javascript:alert(1))';
      const { container } = render(<SafeMarkdown content={content} />);
      const a = container.querySelector("a");
      // Either the link is stripped entirely, or it renders without the href.
      if (a) {
        expect(a.getAttribute("href")).not.toMatch(/javascript/i);
      }
    });

    it("allows http/https links with safe attributes", () => {
      const content = "[ext](https://example.com/page)";
      const { container } = render(<SafeMarkdown content={content} />);
      const a = container.querySelector("a");
      expect(a).not.toBeNull();
      expect(a?.getAttribute("href")).toBe("https://example.com/page");
      expect(a?.getAttribute("target")).toBe("_blank");
      expect(a?.getAttribute("rel")).toContain("noopener");
      expect(a?.getAttribute("rel")).toContain("noreferrer");
    });

    it("wraps output in .prose container", () => {
      const { container } = render(<SafeMarkdown content="text" />);
      expect(container.querySelector(".prose")).not.toBeNull();
    });
  });

  describe("data mode", () => {
    it("leaves markdown syntax literal — no headings, no bold", () => {
      const content = "# Not a heading\n**not bold**";
      const { container } = render(<SafeMarkdown content={content} mode="data" />);
      expect(container.querySelector("h1")).toBeNull();
      expect(container.querySelector("strong")).toBeNull();
      expect(container.textContent).toContain("# Not a heading");
      expect(container.textContent).toContain("**not bold**");
    });

    it("renders in a <pre> with .datablock class", () => {
      const { container } = render(<SafeMarkdown content="{}" mode="data" />);
      const pre = container.querySelector("pre.datablock");
      expect(pre).not.toBeNull();
      expect(pre?.textContent).toBe("{}");
    });

    it("preserves whitespace and line breaks", () => {
      const content = "line 1\n  indented\nline 3";
      const { container } = render(<SafeMarkdown content={content} mode="data" />);
      expect(container.textContent).toBe(content);
    });
  });
});
