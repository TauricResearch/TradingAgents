import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { Controls } from "./Controls";
import type {
  ConfigResponseDTO,
  RunCreateRequestDTO,
  RunSnapshotDTO,
} from "../../api/contracts";

// --- Mocks (hoisted so vi.mock factories can reference them) -------------

const mockStore = vi.hoisted(() => ({
  run_id: null as string | null,
  selectRun: vi.fn(),
  stream: {
    state: null,
    status: "idle" as string,
    error: null,
    close: vi.fn(),
  },
}));

vi.mock("../../state/WorkbenchStore", () => ({
  useWorkbenchStore: () => mockStore,
}));

const mockClient = vi.hoisted(() => ({
  getConfig: vi.fn(),
  createRun: vi.fn(),
  cancelRun: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  getConfig: mockClient.getConfig,
  createRun: mockClient.createRun,
  cancelRun: mockClient.cancelRun,
}));

// --- Fixtures ------------------------------------------------------------

function makeConfig(): ConfigResponseDTO {
  return {
    providers: [
      {
        id: "deepseek",
        configured: true,
        requires_api_key: true,
        models: {
          quick: [
            { label: "DeepSeek Chat", id: "deepseek-chat" },
            { label: "DeepSeek Reasoner", id: "deepseek-reasoner" },
          ],
          deep: [{ label: "DeepSeek Reasoner", id: "deepseek-reasoner" }],
        },
        custom_model_allowed: false,
      },
      {
        id: "openai",
        configured: false,
        requires_api_key: true,
        models: {
          quick: [{ label: "GPT-4o", id: "gpt-4o" }],
          deep: [{ label: "GPT-4o", id: "gpt-4o" }],
        },
        custom_model_allowed: false,
      },
    ],
    configured_keys: { deepseek: true, openai: false },
    analysts: [
      { id: "market" },
      { id: "social" },
      { id: "news" },
      { id: "fundamentals" },
    ],
    depths: [1, 3, 5],
    output_languages: ["English", "Chinese"],
    checkpoint_available: true,
    defaults: {
      llm_provider: "deepseek",
      quick_think_llm: "deepseek-chat",
      deep_think_llm: "deepseek-reasoner",
      output_language: "Chinese",
      research_depth: 3,
      checkpoint_enabled: false,
    },
  };
}

function makeSnapshot(): RunSnapshotDTO {
  return {
    run_id: "run_x",
    status: "created",
    ticker: "600519",
    asset_type: "stock",
    analysis_date: "2026-07-19",
    selected_analysts: ["market", "social", "news", "fundamentals"],
    max_debate_rounds: 3,
    max_risk_discuss_rounds: 3,
    output_language: "Chinese",
    llm_provider: "deepseek",
    quick_think_llm: "deepseek-chat",
    deep_think_llm: "deepseek-reasoner",
    configured_keys: { deepseek: true },
    created_at: "2026-07-19T00:00:00Z",
    updated_at: "2026-07-19T00:00:00Z",
    latest_sequence: 0,
    artifacts: [],
    redaction_manifest: [],
    event_schema_version: 1,
    metadata: {},
  };
}

// --- Helpers -------------------------------------------------------------

async function waitForConfig(): Promise<void> {
  await waitFor(() => {
    expect(
      (screen.getByLabelText("LLM Provider") as HTMLSelectElement).options
        .length,
    ).toBe(2);
  });
}

// --- Tests ---------------------------------------------------------------

describe("Controls", () => {
  beforeEach(() => {
    mockStore.run_id = null;
    mockStore.selectRun = vi.fn();
    mockStore.stream.status = "idle";
    mockClient.getConfig.mockReset();
    mockClient.createRun.mockReset();
    mockClient.cancelRun.mockReset();
  });

  it("renders ticker/date/depth/analysts/provider/model selects from config", async () => {
    mockClient.getConfig.mockResolvedValue(makeConfig());
    render(<Controls />);

    await waitForConfig();

    expect(screen.getByLabelText("股票代码")).toBeInTheDocument();
    expect(screen.getByLabelText("分析日期")).toBeInTheDocument();
    expect(screen.getByLabelText("研究深度")).toBeInTheDocument();
    expect(screen.getByLabelText("LLM Provider")).toBeInTheDocument();
    expect(screen.getByLabelText("快速思考模型")).toBeInTheDocument();
    expect(screen.getByLabelText("深度思考模型")).toBeInTheDocument();

    // Analyst checkboxes for all four wire keys.
    expect(screen.getByLabelText("market")).toBeInTheDocument();
    expect(screen.getByLabelText("social")).toBeInTheDocument();
    expect(screen.getByLabelText("news")).toBeInTheDocument();
    expect(screen.getByLabelText("fundamentals")).toBeInTheDocument();

    // Provider select offers both providers; default is the configured one.
    const providerSelect = screen.getByLabelText(
      "LLM Provider",
    ) as HTMLSelectElement;
    expect(providerSelect.options.length).toBe(2);
    expect(providerSelect).toHaveValue("deepseek");

    // Default quick/deep models seeded from config.defaults.
    expect(screen.getByLabelText("快速思考模型")).toHaveValue("deepseek-chat");
    expect(screen.getByLabelText("深度思考模型")).toHaveValue(
      "deepseek-reasoner",
    );
  });

  it("resets quick/deep to the new provider's first option on provider change", async () => {
    mockClient.getConfig.mockResolvedValue(makeConfig());
    render(<Controls />);

    await waitForConfig();

    // Initial: deepseek -> deepseek-chat / deepseek-reasoner.
    expect(screen.getByLabelText("快速思考模型")).toHaveValue("deepseek-chat");
    expect(screen.getByLabelText("深度思考模型")).toHaveValue(
      "deepseek-reasoner",
    );

    // Switch to openai.
    fireEvent.change(screen.getByLabelText("LLM Provider"), {
      target: { value: "openai" },
    });

    // openai quick/deep both only offer gpt-4o; selection resets to it.
    await waitFor(() => {
      expect(screen.getByLabelText("快速思考模型")).toHaveValue("gpt-4o");
      expect(screen.getByLabelText("深度思考模型")).toHaveValue("gpt-4o");
    });

    const quickSelect = screen.getByLabelText(
      "快速思考模型",
    ) as HTMLSelectElement;
    expect(quickSelect.options.length).toBe(1);
    expect(quickSelect.options[0].value).toBe("gpt-4o");
  });

  it("disables start when the selected provider is not configured", async () => {
    const cfg = makeConfig();
    cfg.defaults.llm_provider = "openai";
    cfg.defaults.quick_think_llm = "gpt-4o";
    cfg.defaults.deep_think_llm = "gpt-4o";
    mockClient.getConfig.mockResolvedValue(cfg);
    render(<Controls />);

    await waitForConfig();

    // Type a ticker so the only blocking error is provider-not-configured.
    fireEvent.change(screen.getByLabelText("股票代码"), {
      target: { value: "600519" },
    });

    expect(
      screen.getByRole("button", { name: /开始分析/ }),
    ).toBeDisabled();
    expect(
      screen.getByText(/所选 Provider 未配置 API Key/),
    ).toBeInTheDocument();
  });

  it("disables start when no analysts are selected", async () => {
    mockClient.getConfig.mockResolvedValue(makeConfig());
    render(<Controls />);

    await waitForConfig();

    fireEvent.change(screen.getByLabelText("股票代码"), {
      target: { value: "600519" },
    });

    // Uncheck every analyst (all start checked by default).
    for (const id of ["market", "social", "news", "fundamentals"]) {
      fireEvent.click(screen.getByLabelText(id));
    }

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /开始分析/ }),
      ).toBeDisabled();
    });
    expect(screen.getByText(/至少选择一个分析师/)).toBeInTheDocument();
  });

  it("calls createRun with the built DTO and selectRun with the returned run_id", async () => {
    mockClient.getConfig.mockResolvedValue(makeConfig());
    mockClient.createRun.mockResolvedValue(makeSnapshot());
    render(<Controls />);

    await waitForConfig();

    fireEvent.change(screen.getByLabelText("股票代码"), {
      target: { value: "600519" },
    });

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /开始分析/ }),
      ).not.toBeDisabled();
    });

    fireEvent.click(screen.getByRole("button", { name: /开始分析/ }));

    await waitFor(() => {
      expect(mockClient.createRun).toHaveBeenCalledTimes(1);
    });

    const body: RunCreateRequestDTO = mockClient.createRun.mock.calls[0][0];
    expect(body).toMatchObject({
      ticker: "600519",
      llm_provider: "deepseek",
      quick_think_llm: "deepseek-chat",
      deep_think_llm: "deepseek-reasoner",
      research_depth: 3,
      output_language: "Chinese",
      checkpoint_enabled: false,
      asset_type: null,
    });
    expect(body.selected_analysts).toEqual([
      "market",
      "social",
      "news",
      "fundamentals",
    ]);

    await waitFor(() => {
      expect(mockStore.selectRun).toHaveBeenCalledWith("run_x");
    });
  });
});