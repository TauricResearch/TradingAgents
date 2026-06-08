import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BackgroundRunsDrawer } from "./BackgroundRunsDrawer";
import * as api from "../lib/api";
import type { BackgroundRunState } from "../lib/api";

beforeEach(() => {
  vi.restoreAllMocks();
});

function makeState(over: Partial<BackgroundRunState> = {}): BackgroundRunState {
  return {
    job_id: "bgr_TEST",
    ticker: "NVDA",
    date_from: "2024-01-01",
    date_to: "2024-06-30",
    every: "1d",
    parallel: 2,
    total: 130,
    current_index: 12,
    avg_duration_s: 47.3,
    eta_s: 2851,
    started_at: "2026-06-07T19:30:00Z",
    finished_at: null,
    status: "running",
    durations_s: [],
    ...over,
  };
}

function renderDrawer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <BackgroundRunsDrawer focusedTicker="NVDA" />
    </QueryClientProvider>
  );
}

function mockFetchBackgroundRuns(jobs: BackgroundRunState[]) {
  (globalThis as any).fetch = vi.fn((url: string) => {
    if (String(url) === "/api/background-runs") {
      return Promise.resolve(new Response(JSON.stringify({ jobs }), { status: 200 }));
    }
    if (String(url) === "/api/watchlist") {
      return Promise.resolve(new Response(JSON.stringify([{ ticker: "NVDA", company_name: "NVIDIA Corp", exchange: "NASDAQ", added_at: null, last_decision: null, last_decision_at: null }]), { status: 200 }));
    }
    return Promise.resolve(new Response("{}", { status: 200 }));
  }) as any;
}

describe("BackgroundRunsDrawer form", () => {
  it("renders the focused ticker preselected", () => {
    renderDrawer();
    const select = screen.getByLabelText(/ticker/i) as HTMLSelectElement;
    expect(select.value).toBe("NVDA");
  });

  it("calls startBackgroundRun on submit and shows a 422 error inline on failure", async () => {
    const spy = vi.spyOn(api, "startBackgroundRun").mockRejectedValue(
      new Error("validation: date_to cannot be in the future")
    );
    renderDrawer();
    await userEvent.click(screen.getByRole("button", { name: /start/i }));
    await waitFor(() => expect(spy).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText(/validation: date_to cannot be in the future/)).toBeInTheDocument());
  });
});

describe("BackgroundRunsDrawer active job card", () => {
  it("renders ticker, range, and progress", async () => {
    mockFetchBackgroundRuns([makeState()]);
    renderDrawer();
    expect(await screen.findByText(/2024-01-01 -> 2024-06-30/)).toBeInTheDocument();
    expect(screen.getByText(/12 \/ 130/)).toBeInTheDocument();
  });

  it("formats ETA via fmtEta when status is running", async () => {
    mockFetchBackgroundRuns([makeState({ eta_s: 2851 })]);
    renderDrawer();
    expect(await screen.findByText(/ETA: 47m 31s/)).toBeInTheDocument();
  });

  it("shows 'Calculating...' when current_index is 0 and eta_s is 0", async () => {
    mockFetchBackgroundRuns([makeState({ current_index: 0, eta_s: 0, avg_duration_s: 0 })]);
    renderDrawer();
    expect(await screen.findByText(/Calculating.../)).toBeInTheDocument();
  });

  it("hides ETA when current_index equals total", async () => {
    mockFetchBackgroundRuns([makeState({ current_index: 130, eta_s: 0, status: "done" })]);
    renderDrawer();
    expect(await screen.findByText(/NVDA/)).toBeInTheDocument();
    expect(screen.queryByText(/ETA:/)).not.toBeInTheDocument();
  });

  it("Pause and Cancel buttons trigger the right endpoints", async () => {
    mockFetchBackgroundRuns([makeState()]);
    const cancel = vi.spyOn(api, "cancelBackgroundRun").mockResolvedValue({ status: "ok" });
    const pause = vi.spyOn(api, "pauseBackgroundRun").mockResolvedValue({ status: "ok" });
    renderDrawer();
    await screen.findByText(/2024-01-01 -> 2024-06-30/);
    await userEvent.click(screen.getByRole("button", { name: /pause/i }));
    await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(pause).toHaveBeenCalledWith("bgr_TEST");
    expect(cancel).toHaveBeenCalledWith("bgr_TEST");
  });
});

describe("BackgroundRunsDrawer live iteration feed", () => {
  it("renders the feed for a running job", async () => {
    mockFetchBackgroundRuns([makeState({ status: "running" })]);
    renderDrawer();
    expect(await screen.findByText(/recent iterations/i)).toBeInTheDocument();
  });
});

describe("BackgroundRunsDrawer past jobs list", () => {
  it("renders terminal jobs in a collapsible section", async () => {
    mockFetchBackgroundRuns([makeState({ status: "done", current_index: 130 })]);
    renderDrawer();
    expect(await screen.findByText(/Past jobs/)).toBeInTheDocument();
  });

  it("hides the past jobs section when no terminal jobs exist", async () => {
    mockFetchBackgroundRuns([]);
    renderDrawer();
    expect(screen.queryByText(/Past jobs/)).not.toBeInTheDocument();
  });
});
