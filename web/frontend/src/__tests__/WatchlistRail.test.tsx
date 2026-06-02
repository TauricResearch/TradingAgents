import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WatchlistRail } from "../components/WatchlistRail";
import { useUi } from "../store/ui";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  useUi.setState({ focusedTicker: null });
  (globalThis as any).fetch = vi.fn((url) => {
    if (String(url).endsWith("/api/watchlist")) {
      return Promise.resolve(new Response(JSON.stringify([
        { ticker: "NVDA", company_name: "NVIDIA", exchange: "NASDAQ", added_at: null, last_decision: null, last_decision_at: null },
        { ticker: "AAPL", company_name: "Apple", exchange: "NASDAQ", added_at: null, last_decision: null, last_decision_at: null },
      ])));
    }
    return Promise.resolve(new Response("{}", { status: 200 }));
  }) as any;
});

describe("WatchlistRail", () => {
  it("renders rows and clicking sets focus", async () => {
    wrap(<WatchlistRail />);
    await waitFor(() => expect(screen.getByText("NVDA")).toBeInTheDocument());
    fireEvent.click(screen.getByText("NVDA"));
    expect(useUi.getState().focusedTicker).toBe("NVDA");
  });

  it("shows an Add button", async () => {
    wrap(<WatchlistRail />);
    await waitFor(() => expect(screen.getByText(/add/i)).toBeInTheDocument());
  });
});
