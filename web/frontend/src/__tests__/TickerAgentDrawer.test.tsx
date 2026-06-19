import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TickerAgentDrawer } from "../components/TickerAgentDrawer";

function mockFetch(responses: Record<string, unknown>) {
  (globalThis as any).fetch = vi.fn((url: string) => {
    const found = responses[String(url)];
    if (found) {
      return Promise.resolve(new Response(JSON.stringify(found)));
    }
    return Promise.resolve(new Response("{}", { status: 200 }));
  }) as any;
}

function renderDrawer(open = true) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onClose = vi.fn();
  const view = render(
    <QueryClientProvider client={qc}>
      <TickerAgentDrawer open={open} onClose={onClose} />
    </QueryClientProvider>
  );
  return { qc, onClose, view };
}

beforeEach(() => {
  mockFetch({
    "/api/ticker-agent/status": { status: "idle", last_run_at: null, next_scheduled_at: null, cycles_completed: 0, current_step: 0, current_step_name: "Idle" },
    "/api/ticker-agent/accuracy-leaderboard": { scores: {}, last_evaluated: null },
    "/api/ticker-agent/activity-log?limit=10": { entries: [] },
    "/api/ticker-agent/capabilities": { capabilities: [] },
    "/api/ticker-agent/missing-capabilities": { capabilities: [] },
  });
});

describe("TickerAgentDrawer", () => {
  it("renders all sections when open", async () => {
    renderDrawer(true);
    await waitFor(() => expect(screen.getByTestId("ticker-agent-drawer")).toBeInTheDocument());
    expect(screen.getByText("Ticker Accuracy Agent")).toBeInTheDocument();
    expect(screen.getByText(/Status & Controls/i)).toBeInTheDocument();
    expect(screen.getByText("Accuracy Leaderboard")).toBeInTheDocument();
    expect(screen.getByText("Activity Log")).toBeInTheDocument();
    expect(screen.getByText("Capabilities")).toBeInTheDocument();
  });

  it("does not render when closed", () => {
    renderDrawer(false);
    expect(screen.queryByTestId("ticker-agent-drawer")).not.toBeInTheDocument();
  });

  it("shows status bar with Run Now, Pause, Resume buttons", async () => {
    renderDrawer(true);
    await waitFor(() => expect(screen.getByText("Run Now")).toBeInTheDocument());
    expect(screen.getByText("Pause")).toBeInTheDocument();
    expect(screen.getByText("Resume")).toBeInTheDocument();
  });

  it("shows empty state for leaderboard when no scores exist", async () => {
    renderDrawer(true);
    await waitFor(() =>
      expect(screen.getByText(/No accuracy data yet/i)).toBeInTheDocument()
    );
  });

  it("renders accuracy leaderboard scores when present", async () => {
    mockFetch({
      "/api/ticker-agent/status": { status: "idle", cycles_completed: 0, current_step: 0, current_step_name: "Idle" },
      "/api/ticker-agent/accuracy-leaderboard": {
        scores: {
          NVDA: { accuracy_pct: 83.0, total_runs: 10, right: 8, wrong: 2 },
          AAPL: { accuracy_pct: 75.0, total_runs: 20, right: 15, wrong: 5 },
        },
        last_evaluated: "2026-06-18T12:00:00Z",
      },
      "/api/ticker-agent/activity-log?limit=10": { entries: [] },
      "/api/ticker-agent/capabilities": { capabilities: [] },
      "/api/ticker-agent/missing-capabilities": { capabilities: [] },
    });
    renderDrawer(true);
    await waitFor(() => expect(screen.getByText("NVDA")).toBeInTheDocument());
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("83.0%")).toBeInTheDocument();
    expect(screen.getByText("75.0%")).toBeInTheDocument();
  });

  it("shows activity log entries when present", async () => {
    mockFetch({
      "/api/ticker-agent/status": { status: "running", cycles_completed: 1, current_step: 0, current_step_name: "Idle" },
      "/api/ticker-agent/accuracy-leaderboard": { scores: {}, last_evaluated: null },
      "/api/ticker-agent/activity-log?limit=10": {
        entries: [
          { timestamp: "2026-06-18T12:00:00Z", message: "Cycle 1: Analysis completed" },
          { timestamp: "2026-06-18T06:00:00Z", message: "Cycle 2: Semi sector scan" },
        ],
      },
      "/api/ticker-agent/capabilities": { capabilities: [] },
      "/api/ticker-agent/missing-capabilities": { capabilities: [] },
      "/api/ticker-agent/live-events?since=0": { events: [], current_step: 0, current_step_name: "Idle" },
    });
    renderDrawer(true);
    await waitFor(() => expect(screen.getByText(/Cycle 1/i)).toBeInTheDocument());
    expect(screen.getByText(/Cycle 2/i)).toBeInTheDocument();
  });

  it("shows capabilities and missing capabilities", async () => {
    mockFetch({
      "/api/ticker-agent/status": { status: "idle", cycles_completed: 0, current_step: 0, current_step_name: "Idle" },
      "/api/ticker-agent/accuracy-leaderboard": { scores: {}, last_evaluated: null },
      "/api/ticker-agent/activity-log?limit=10": { entries: [] },
      "/api/ticker-agent/capabilities": {
        capabilities: [
          { name: "list-watchlist", path: "/api/watchlist", method: "GET", available: true },
          { name: "start-run", path: "/api/runs", method: "POST", available: true },
        ],
      },
      "/api/ticker-agent/missing-capabilities": {
        capabilities: [
          { name: "options-flow", description: "Track unusual options activity", logged_at: "2026-06-18T12:00:00Z" },
        ],
      },
    });
    renderDrawer(true);
    await waitFor(() => expect(screen.getByText("Missing")).toBeInTheDocument());
    expect(screen.getByText(/Track unusual options activity/i)).toBeInTheDocument();
    expect(screen.getByText("Implement →")).toBeInTheDocument();
  });

  it("calls onClose when close button is clicked", async () => {
    const { onClose } = renderDrawer(true);
    await waitFor(() => expect(screen.getByText("Close")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Close"));
    expect(onClose).toHaveBeenCalled();
  });

  it("triggers Run Now mutation when button clicked", async () => {
    let runNowCalled = false;
    const baseMock = {
      "/api/ticker-agent/status": { status: "idle", cycles_completed: 0, current_step: 0, current_step_name: "Idle" },
      "/api/ticker-agent/accuracy-leaderboard": { scores: {}, last_evaluated: null },
      "/api/ticker-agent/activity-log?limit=10": { entries: [] },
      "/api/ticker-agent/capabilities": { capabilities: [] },
      "/api/ticker-agent/missing-capabilities": { capabilities: [] },
    };
    (globalThis as any).fetch = vi.fn((url: string, opts?: RequestInit) => {
      if (String(url).endsWith("/api/ticker-agent/run-now")) {
        runNowCalled = true;
        return Promise.resolve(new Response(JSON.stringify({ status: "ok" })));
      }
      const found = (baseMock as any)[String(url)];
      if (found) return Promise.resolve(new Response(JSON.stringify(found)));
      return Promise.resolve(new Response("{}", { status: 200 }));
    }) as any;

    renderDrawer(true);
    await waitFor(() => {
      const buttons = screen.getAllByText("Run Now");
      return expect(buttons.length).toBeGreaterThan(0);
    });
    fireEvent.click(screen.getByText("Run Now"));
    await waitFor(() => expect(runNowCalled).toBe(true));
  });
});
