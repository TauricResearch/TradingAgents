/**
 * F3 - RunHistory component tests.
 *
 * RunHistory is now a pure renderer receiving runs/loading/error as props
 * (the fetch lives in WorkbenchLayout via useRunHistory). Verifies: render
 * of a 3-run fixture (completed/failed/running), click -> selectRun wiring,
 * empty-list placeholder, loading placeholder, and error display.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { RunSummaryDTO } from "../../api/contracts";

const mockStore = vi.hoisted(() => ({
  useWorkbenchStore: vi.fn(),
}));

vi.mock("../../state/WorkbenchStore", () => ({
  useWorkbenchStore: mockStore.useWorkbenchStore,
}));

import { RunHistory } from "./RunHistory";

const FIXTURES: RunSummaryDTO[] = [
  {
    run_id: "run-1",
    status: "completed",
    ticker: "600519.SS",
    analysis_date: "2026-07-18",
    asset_type: "stock",
    created_at: "2026-07-18T10:00:00Z",
    updated_at: "2026-07-18T10:30:00Z",
    latest_sequence: 42,
    final_signal: "Buy",
    summary: "Bullish",
  },
  {
    run_id: "run-2",
    status: "failed",
    ticker: "000001.SZ",
    analysis_date: "2026-07-18",
    asset_type: "stock",
    created_at: "2026-07-18T09:00:00Z",
    updated_at: "2026-07-18T09:15:00Z",
    latest_sequence: 10,
    final_signal: null,
    summary: null,
  },
  {
    run_id: "run-3",
    status: "running",
    ticker: "AAPL",
    analysis_date: "2026-07-19",
    asset_type: "stock",
    created_at: "2026-07-19T08:00:00Z",
    updated_at: "2026-07-19T08:05:00Z",
    latest_sequence: 5,
    final_signal: null,
    summary: null,
  },
];

function makeStore(
  overrides: Partial<{
    run_id: string | null;
    selectRun: ReturnType<typeof vi.fn>;
  }> = {},
) {
  return {
    run_id: null as string | null,
    selectRun: vi.fn(),
    stream: {
      state: null,
      status: "idle" as const,
      error: null,
    },
    ...overrides,
  };
}

describe("RunHistory", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStore.useWorkbenchStore.mockReturnValue(makeStore());
  });

  it("renders runs from props (newest-first as provided)", () => {
    render(<RunHistory runs={FIXTURES} loading={false} error={null} />);

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);

    expect(screen.getByText("600519.SS")).toBeInTheDocument();
    expect(screen.getByText("000001.SZ")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();

    expect(screen.getByText(/已完成/)).toBeInTheDocument();
    expect(screen.getByText(/失败/)).toBeInTheDocument();
    expect(screen.getByText(/运行中/)).toBeInTheDocument();
  });

  it("calls selectRun with the run_id when an item is clicked", () => {
    const selectRun = vi.fn();
    mockStore.useWorkbenchStore.mockReturnValue(makeStore({ selectRun }));

    render(<RunHistory runs={FIXTURES} loading={false} error={null} />);

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);

    fireEvent.click(items[0]);
    expect(selectRun).toHaveBeenCalledWith("run-1");
  });

  it("renders the placeholder when there are no runs", () => {
    render(<RunHistory runs={[]} loading={false} error={null} />);
    expect(screen.getByText("暂无运行记录")).toBeInTheDocument();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it("renders the loading placeholder while loading with no runs yet", () => {
    render(<RunHistory runs={[]} loading={true} error={null} />);
    expect(screen.getByText("加载中…")).toBeInTheDocument();
  });

  it("renders the error message when fetch failed", () => {
    render(
      <RunHistory
        runs={[]}
        loading={false}
        error={new Error("network down")}
      />,
    );
    expect(screen.getByText(/加载失败/)).toBeInTheDocument();
    expect(screen.getByText(/network down/)).toBeInTheDocument();
  });
});
