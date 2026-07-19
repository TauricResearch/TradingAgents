/**
 * F3 - RunHistory component tests.
 *
 * Mocks listRuns and useWorkbenchStore to verify: render of a 3-run fixture
 * (completed/failed/running), click -> selectRun wiring, and the empty-list
 * placeholder. Runs render newest-first as returned by the backend.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { RunSummaryDTO } from "../../api/contracts";

const mockStore = vi.hoisted(() => ({
  useWorkbenchStore: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  listRuns: vi.fn(),
}));

vi.mock("../../state/WorkbenchStore", () => ({
  useWorkbenchStore: mockStore.useWorkbenchStore,
}));

import { listRuns } from "../../api/client";
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

function makeStore(overrides: Partial<{
  run_id: string | null;
  selectRun: ReturnType<typeof vi.fn>;
}> = {}) {
  return {
    run_id: null as string | null,
    selectRun: vi.fn(),
    stream: {
      state: null,
      status: "idle" as const,
      error: null,
      close: vi.fn(),
    },
    ...overrides,
  };
}

describe("RunHistory", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStore.useWorkbenchStore.mockReturnValue(makeStore());
  });

  it("renders runs from the mocked listRuns fixture", async () => {
    vi.mocked(listRuns).mockResolvedValue(FIXTURES);
    render(<RunHistory />);

    await waitFor(() => {
      expect(screen.getByText("600519.SS")).toBeInTheDocument();
    });

    // 3 history items, newest-first as returned by the backend.
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);

    expect(screen.getByText("600519.SS")).toBeInTheDocument();
    expect(screen.getByText("000001.SZ")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();

    expect(screen.getByText(/已完成/)).toBeInTheDocument();
    expect(screen.getByText(/失败/)).toBeInTheDocument();
    expect(screen.getByText(/运行中/)).toBeInTheDocument();
  });

  it("calls selectRun with the run_id when an item is clicked", async () => {
    vi.mocked(listRuns).mockResolvedValue(FIXTURES);
    const selectRun = vi.fn();
    mockStore.useWorkbenchStore.mockReturnValue(makeStore({ selectRun }));

    render(<RunHistory />);

    await waitFor(() => {
      expect(screen.getByText("600519.SS")).toBeInTheDocument();
    });

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);

    // Click the first (newest) item -> selectRun("run-1").
    fireEvent.click(items[0]);
    expect(selectRun).toHaveBeenCalledWith("run-1");
  });

  it("renders the placeholder when there are no runs", async () => {
    vi.mocked(listRuns).mockResolvedValue([]);
    render(<RunHistory />);

    await waitFor(() => {
      expect(screen.getByText("暂无运行记录")).toBeInTheDocument();
    });
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });
});