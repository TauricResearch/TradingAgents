import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TickerHeader } from "../components/TickerHeader";
import { useUi } from "../store/ui";

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

describe("TickerHeader — action button", () => {
  it("shows 'Run analysis' on first visit (no prior history)", () => {
    mockFetch({});
    wrap(<TickerHeader ticker="NVDA" />);
    expect(screen.getByRole("button", { name: /run analysis/i })).toBeInTheDocument();
  });

  it("shows 'Re-run analysis' when prior history exists", () => {
    useUi.setState({ lastRunIdByTicker: { NVDA: 5 } });
    mockFetch({});
    wrap(<TickerHeader ticker="NVDA" />);
    expect(screen.getByRole("button", { name: /re-run analysis/i })).toBeInTheDocument();
  });

  it("'Run analysis' on first visit posts force=false", async () => {
    const fetchMock = mockFetch({
      "/api/runs": () => ({ run_id: 11 }),
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
    useUi.setState({ lastRunIdByTicker: { NVDA: 5 } });
    const fetchMock = mockFetch({
      "/api/runs": () => ({ run_id: 12 }),
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
    useUi.setState({ activeRunIdByTicker: { NVDA: 99 } });
    mockFetch({});
    wrap(<TickerHeader ticker="NVDA" />);
    const btn = screen.getByRole("button", { name: /run analysis/i });
    expect(btn).toBeDisabled();
  });
});

describe("TickerHeader — run history dropdown", () => {
  it("fetches /api/tickers/{ticker}/runs and lists the rows", async () => {
    useUi.setState({ lastRunIdByTicker: { NVDA: 5 } });
    mockFetch({
      "/api/tickers/NVDA/runs": () => [
        { id: 5, ticker: "NVDA", status: "done", started_at: "2026-06-01T00:00:00Z", finished_at: "2026-06-01T00:10:00Z" },
        { id: 3, ticker: "NVDA", status: "done", started_at: "2026-05-30T00:00:00Z", finished_at: "2026-05-30T00:10:00Z" },
      ],
    });
    wrap(<TickerHeader ticker="NVDA" />);
    await waitFor(() => {
      expect(screen.getByText(/2026-06-01/)).toBeInTheDocument();
      expect(screen.getByText(/2026-05-30/)).toBeInTheDocument();
    });
  });

  it("does not fetch the runs list for a ticker that has never been analyzed", () => {
    mockFetch({});
    wrap(<TickerHeader ticker="NVDA" />);
    // No 'NVDA' key in lastRunIdByTicker — the query should not fire.
    const fetchMock = (globalThis as any).fetch as ReturnType<typeof vi.fn>;
    const tickerRunsCall = fetchMock.mock.calls.find((c: unknown[]) =>
      String(c[0]).includes("/api/tickers/NVDA/runs"),
    );
    expect(tickerRunsCall).toBeUndefined();
  });

  it("selecting a row sets historicalRunIdByTicker[ticker]", async () => {
    useUi.setState({ lastRunIdByTicker: { NVDA: 5 } });
    mockFetch({
      "/api/tickers/NVDA/runs": () => [
        { id: 5, ticker: "NVDA", status: "done", started_at: "2026-06-01T00:00:00Z" },
        { id: 3, ticker: "NVDA", status: "done", started_at: "2026-05-30T00:00:00Z" },
      ],
    });
    wrap(<TickerHeader ticker="NVDA" />);
    await waitFor(() => {
      expect(screen.getByText(/2026-05-30/)).toBeInTheDocument();
    });
    // <select> in jsdom requires fireEvent.change on the element,
    // not fireEvent.click on the option text.
    const select = screen.getByLabelText(/run history/i) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "3" } });
    expect(useUi.getState().historicalRunIdByTicker["NVDA"]).toBe(3);
  });

  it("selecting 'Latest (live)' clears historicalRunIdByTicker[ticker]", async () => {
    useUi.setState({
      lastRunIdByTicker: { NVDA: 5 },
      historicalRunIdByTicker: { NVDA: 3 },
    });
    mockFetch({
      "/api/tickers/NVDA/runs": () => [
        { id: 5, ticker: "NVDA", status: "done", started_at: "2026-06-01T00:00:00Z" },
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
    useUi.setState({ lastRunIdByTicker: { NVDA: 5 } });
    const fetchMock = mockFetch({
      "/api/runs": () => ({ run_id: 7 }),
      "/api/tickers/NVDA/runs": () => [
        { id: 5, ticker: "NVDA", status: "done", started_at: "2026-06-01T00:00:00Z" },
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
    expect(useUi.getState().activeRunIdByTicker["NVDA"]).toBe(7);
    expect(useUi.getState().historicalRunIdByTicker["NVDA"]).toBeNull();
  });
});
