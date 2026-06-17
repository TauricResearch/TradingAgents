/* eslint-disable @typescript-eslint/no-explicit-any */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TickerHeader, runLabel } from "../components/TickerHeader";
import { useUi } from "../store/ui";
import type { RunRow, RunDetail } from "../lib/api";

// Compile-time assertions: a value with the new run-metadata fields is
// assignable to RunRow/RunDetail. Will fail tsc until those fields exist.
const _rowSample: RunRow = {
  id: "NVDA:2026-06-04T10:00:00.000000Z",
  slug: "2026-06-04_13-00-00_IDT",
  ticker: "NVDA",
  started_at: "2026-06-04T10:00:00.000000Z",
  finished_at: "2026-06-04T10:00:42.000000Z",
  status: "done",
  cancel_requested: false,
  decision_action: "HOLD",
  decision_target: null,
  decision_rationale: null,
  decision_confidence: null,
  llm_provider: "openai",
  deep_think_model: "gpt-5.5",
  quick_think_model: "gpt-5.4-mini",
  start_price: 123.45,
  start_price_at: "2026-06-04T10:00:00.000000Z",
  total_duration_s: 42.0,
  elapsed_s: null,
};
void _rowSample;

const _detailSample: RunDetail = {
  ..._rowSample,
  events: [],
  llm_calls: [],
  stages: [],
};
void _detailSample;

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

function mockFetch(handlers: Record<string, (req: { url: string; method?: string; body?: string }) => unknown>) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const body = typeof init?.body === "string" ? init.body : undefined;
    for (const [suffix, handler] of Object.entries(handlers)) {
      if (String(url).endsWith(suffix)) {
        const payload = await handler({ url, method, body });
        return new Response(JSON.stringify(payload), { status: 200 });
      }
    }
    return new Response("{}", { status: 200 });
  });
  (globalThis as any).fetch = fn;
  return fn;
}

beforeEach(() => {
  useUi.setState({
    focusedTicker: null,
    lastRunIdByTicker: {},
    historicalRunIdByTicker: {},
    activeRunIdByTicker: {},
    eventBuffer: [],
  });
});

const baseRow = (overrides: Record<string, unknown>): RunRow => ({
  id: "",
  slug: "2026-06-04T03-21-57Z",
  ticker: "NVDA",
  started_at: null,
  finished_at: null,
  status: "done",
  cancel_requested: false,
  decision_action: null,
  decision_target: null,
  decision_rationale: null,
  decision_confidence: null,
  llm_provider: null,
  deep_think_model: null,
  quick_think_model: null,
  start_price: null,
  start_price_at: null,
  total_duration_s: null,
  elapsed_s: null,
  ...overrides,
});

describe("TickerHeader — action button", () => {
  it("shows 'Run analysis' on first visit (no prior history)", () => {
    mockFetch({});
    wrap(<TickerHeader ticker="NVDA" />);
    expect(screen.getByRole("button", { name: /run analysis/i })).toBeInTheDocument();
  });

  it("shows 'Re-run analysis' when prior history exists", () => {
    useUi.setState({ lastRunIdByTicker: { NVDA: "NVDA:5" } });
    mockFetch({});
    wrap(<TickerHeader ticker="NVDA" />);
    expect(screen.getByRole("button", { name: /re-run analysis/i })).toBeInTheDocument();
  });

  it("'Run analysis' on first visit posts force=false", async () => {
    const fetchMock = mockFetch({
      "/api/runs": () => ({ run_id: "NVDA:11" }),
    });
    wrap(<TickerHeader ticker="NVDA" />);
    fireEvent.click(screen.getByRole("button", { name: /run analysis/i }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find((c: unknown[]) => c[0] === "/api/runs");
      expect(call).toBeDefined();
    });
    const [, init] = fetchMock.mock.calls.find((c: unknown[]) => c[0] === "/api/runs")!;
    expect(JSON.parse(init!.body as string)).toEqual({ ticker: "NVDA", force: false });
  });

  it("'Re-run analysis' when history exists posts force=true", async () => {
    useUi.setState({ lastRunIdByTicker: { NVDA: "NVDA:5" } });
    const fetchMock = mockFetch({
      "/api/runs": () => ({ run_id: "NVDA:12" }),
    });
    wrap(<TickerHeader ticker="NVDA" />);
    fireEvent.click(screen.getByRole("button", { name: /re-run analysis/i }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find((c: unknown[]) => c[0] === "/api/runs");
      expect(call).toBeDefined();
    });
    const [, init] = fetchMock.mock.calls.find((c: unknown[]) => c[0] === "/api/runs")!;
    expect(JSON.parse(init!.body as string)).toEqual({ ticker: "NVDA", force: true });
  });

  it("the action button is disabled while a run is active", () => {
    useUi.setState({ activeRunIdByTicker: { NVDA: "NVDA:99" } });
    mockFetch({});
    wrap(<TickerHeader ticker="NVDA" />);
    const btn = screen.getByRole("button", { name: /run analysis/i });
    expect(btn).toBeDisabled();
  });
});

describe("TickerHeader — run history dropdown", () => {
  it("fetches /api/tickers/{ticker}/runs and lists the rows", async () => {
    useUi.setState({ lastRunIdByTicker: { NVDA: "NVDA:5" } });
    mockFetch({
      "/api/tickers/NVDA/runs": () => [
        baseRow({ id: "NVDA:5", started_at: "2026-06-01T00:00:00Z", finished_at: "2026-06-01T00:10:00Z" }),
        baseRow({ id: "NVDA:3", started_at: "2026-05-30T00:00:00Z", finished_at: "2026-05-30T00:10:00Z" }),
      ],
    });
    wrap(<TickerHeader ticker="NVDA" />);
    await waitFor(() => {
      expect(screen.getByText(/2026-06-01/)).toBeInTheDocument();
      expect(screen.getByText(/2026-05-30/)).toBeInTheDocument();
    });
  });

  it("does not show the dropdown when there are no runs", async () => {
    mockFetch({});
    wrap(<TickerHeader ticker="NVDA" />);
    // Always fetches to check for runs (background runs may exist).
    await waitFor(() => {
      const fetchMock = (globalThis as any).fetch as ReturnType<typeof vi.fn>;
      expect(fetchMock.mock.calls.some((c: unknown[]) =>
        String(c[0]).includes("/api/tickers/NVDA/runs"),
      )).toBe(true);
    });
    // No 'NVDA' key in lastRunIdByTicker and the response was empty — dropdown hidden.
    await waitFor(() => {
      expect(screen.queryByRole("combobox", { name: /run history/i })).not.toBeInTheDocument();
    });
  });

  it("selecting a row sets historicalRunIdByTicker[ticker]", async () => {
    useUi.setState({ lastRunIdByTicker: { NVDA: "NVDA:5" } });
    mockFetch({
      "/api/tickers/NVDA/runs": () => [
        baseRow({ id: "NVDA:5", started_at: "2026-06-01T00:00:00Z" }),
        baseRow({ id: "NVDA:3", started_at: "2026-05-30T00:00:00Z" }),
      ],
    });
    wrap(<TickerHeader ticker="NVDA" />);
    await waitFor(() => {
      expect(screen.getByText(/2026-05-30/)).toBeInTheDocument();
    });
    // <select> in jsdom requires fireEvent.change on the element,
    // not fireEvent.click on the option text.
    const select = screen.getByLabelText(/run history/i) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "NVDA:3" } });
    expect(useUi.getState().historicalRunIdByTicker["NVDA"]).toBe("NVDA:3");
  });

  it("selecting 'Latest (live)' clears historicalRunIdByTicker[ticker]", async () => {
    useUi.setState({
      lastRunIdByTicker: { NVDA: "NVDA:5" },
      historicalRunIdByTicker: { NVDA: "NVDA:3" },
    });
    mockFetch({
      "/api/tickers/NVDA/runs": () => [
        baseRow({ id: "NVDA:5", started_at: "2026-06-01T00:00:00Z" }),
      ],
    });
    wrap(<TickerHeader ticker="NVDA" />);
    await waitFor(() => {
      expect(screen.getByText(/latest \(live\)/i)).toBeInTheDocument();
    });
    const select = screen.getByLabelText(/run history/i) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "latest" } });
    expect(useUi.getState().historicalRunIdByTicker["NVDA"]).toBeNull();
  });
});

describe("TickerHeader — successful start", () => {
  it("on rerun, invalidates the ['ticker-runs', ticker] query cache", async () => {
    useUi.setState({ lastRunIdByTicker: { NVDA: "NVDA:5" } });
    const fetchMock = mockFetch({
      "/api/runs": () => ({ run_id: "NVDA:7" }),
      "/api/tickers/NVDA/runs": () => [
        baseRow({ id: "NVDA:5", started_at: "2026-06-01T00:00:00Z" }),
      ],
    });
    wrap(<TickerHeader ticker="NVDA" />);
    fireEvent.click(screen.getByRole("button", { name: /re-run analysis/i }));
    await waitFor(() => {
      const post = fetchMock.mock.calls.find((c: unknown[]) => c[0] === "/api/runs");
      expect(post).toBeDefined();
    });
    // The new run id is stored as the active run; the historical
    // selection is cleared so the user sees the new run live.
    expect(useUi.getState().activeRunIdByTicker["NVDA"]).toBe("NVDA:7");
    expect(useUi.getState().historicalRunIdByTicker["NVDA"]).toBeNull();
  });

describe("runLabel", () => {
  it("formats a full run", () => {
    expect(
      runLabel({
        ...baseRow({}),
        started_at: "2026-06-04T10:00:00.000000Z",
        decision_action: "HOLD",
        llm_provider: "openai",
        deep_think_model: "gpt-5.5",
        start_price: 123.45,
        total_duration_s: 42.0,
      })
    ).toContain("gpt-5.5");
    expect(runLabel({
      ...baseRow({}),
      started_at: "2026-06-04T10:00:00.000000Z",
      decision_action: "HOLD",
      llm_provider: "openai",
      deep_think_model: "gpt-5.5",
      start_price: 123.45,
      total_duration_s: 42.0,
    })).toContain("$123.45");
  });

  it("omits missing fields cleanly", () => {
    const out = runLabel(baseRow({ started_at: "2026-06-04T10:00:00.000000Z" }));
    // No model/price/duration present → label is just the timestamp.
    expect(out).toBe("2026-06-04 10:00");
  });

  it("uses deep_think_model when present even if quick is also set", () => {
    const out = runLabel(baseRow({
      started_at: "2026-06-04T10:00:00.000000Z",
      deep_think_model: "gpt-5.5",
      quick_think_model: "gpt-5.4-mini",
    }));
    expect(out).toContain("gpt-5.5");
    expect(out).not.toContain("gpt-5.4-mini");
  });
});
});
