import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "../App";
import { useUi } from "../store/ui";

function wrap(qc?: QueryClient) {
  const client = qc ?? new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><App /></QueryClientProvider>);
}

beforeEach(() => {
  useUi.setState({
    focusedTicker: null,
    lastRunIdByTicker: {},
    activeRunIdByTicker: {},
    eventBuffer: [],
  });
  (globalThis as any).fetch = vi.fn((url) => {
    if (String(url).endsWith("/api/watchlist")) {
      return Promise.resolve(new Response(JSON.stringify([])));
    }
    return Promise.resolve(new Response("{}", { status: 200 }));
  }) as any;
});

describe("App", () => {
  it("renders the shell with an empty-state message when the watchlist is empty", async () => {
    wrap();
    await waitFor(() => expect(screen.getByRole("button", { name: /add ticker/i })).toBeInTheDocument());
    expect(screen.getByText(/watchlist is empty/i)).toBeInTheDocument();
    expect(screen.queryByText(/Loading watchlist/i)).not.toBeInTheDocument();
  });

  it("auto-selects the first ticker when the watchlist is non-empty and no ticker is focused", async () => {
    (globalThis as any).fetch = vi.fn((url) => {
      if (String(url).endsWith("/api/watchlist")) {
        return Promise.resolve(new Response(JSON.stringify([
          { ticker: "NVDA", company_name: "NVIDIA", exchange: "NASDAQ", added_at: null, last_decision: null, last_decision_at: null },
        ])));
      }
      return Promise.resolve(new Response("{}", { status: 200 }));
    }) as any;

    wrap();
    await waitFor(() => expect(useUi.getState().focusedTicker).toBe("NVDA"));
  });

  it("clears focusedTicker when the watchlist refetches as empty", async () => {
    useUi.setState({ focusedTicker: "NVDA" });

    // Use staleTime: Infinity so the query serves cached data immediately
    // without fetching. Then we invalidate to trigger a refetch with the
    // empty mock.
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    qc.setQueryData(["watchlist"], [
      { ticker: "NVDA", company_name: "NVIDIA", exchange: "NASDAQ", added_at: null, last_decision: null, last_decision_at: null },
    ]);
    // Non-watchlist fetches (prices, etc.) return empty JSON
    (globalThis as any).fetch = vi.fn(() =>
      Promise.resolve(new Response("{}", { status: 200 })),
    ) as any;

    wrap(qc);
    await waitFor(() => expect(screen.getAllByText("NVDA").length).toBeGreaterThanOrEqual(1));

    // Swap the mock to return empty, then invalidate so the query refetches
    (globalThis as any).fetch = vi.fn((url) => {
      if (String(url).endsWith("/api/watchlist")) {
        return Promise.resolve(new Response(JSON.stringify([])));
      }
      return Promise.resolve(new Response("{}", { status: 200 }));
    }) as any;

    qc.invalidateQueries({ queryKey: ["watchlist"] });
    await waitFor(() => expect(useUi.getState().focusedTicker).toBeNull());
  });

  it("shows a stale-ticker banner with a Remove action when the price feed flags the symbol as unavailable", async () => {
    useUi.setState({ focusedTicker: "BADX" });
    (globalThis as any).fetch = vi.fn((url) => {
      if (String(url).endsWith("/api/watchlist")) {
        return Promise.resolve(new Response(JSON.stringify([
          { ticker: "BADX", company_name: "", exchange: "", added_at: null, last_decision: null, last_decision_at: null },
        ])));
      }
      if (String(url).endsWith("/api/prices")) {
        // Server flagged the ticker as stale (delisted / yfinance unreachable).
        return Promise.resolve(new Response(JSON.stringify({
          BADX: { price: 0, change_pct: 0, sparkline: [], stale: true },
        })));
      }
      // /api/runs, /api/tickers/.../runs, /api/runs/... — return empty
      return Promise.resolve(new Response("[]", { status: 200 }));
    }) as any;

    wrap();
    // TickerHeader shows "Price data unavailable"
    await waitFor(() =>
      expect(screen.getByTestId("ticker-header-unavailable")).toBeInTheDocument(),
    );
    // Stale banner is visible with a Remove button
    const banner = screen.getByTestId("stale-ticker-banner");
    expect(banner).toBeInTheDocument();
    expect(banner.textContent).toMatch(/BADX.*not available/i);
    expect(screen.getByTestId("stale-ticker-remove")).toBeInTheDocument();
  });

  it("dismissing the stale banner hides it for the current ticker", async () => {
    useUi.setState({ focusedTicker: "BADX" });
    (globalThis as any).fetch = vi.fn((url) => {
      if (String(url).endsWith("/api/watchlist")) {
        return Promise.resolve(new Response(JSON.stringify([
          { ticker: "BADX", company_name: "", exchange: "", added_at: null, last_decision: null, last_decision_at: null },
        ])));
      }
      if (String(url).endsWith("/api/prices")) {
        return Promise.resolve(new Response(JSON.stringify({
          BADX: { price: 0, change_pct: 0, sparkline: [], stale: true },
        })));
      }
      return Promise.resolve(new Response("[]", { status: 200 }));
    }) as any;

    wrap();
    await waitFor(() => expect(screen.getByTestId("stale-ticker-banner")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /dismiss/i }));
    await waitFor(() =>
      expect(screen.queryByTestId("stale-ticker-banner")).not.toBeInTheDocument(),
    );
  });
});
