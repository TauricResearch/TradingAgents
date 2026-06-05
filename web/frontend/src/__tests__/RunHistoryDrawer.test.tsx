import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RunHistoryDrawer } from "../components/RunHistoryDrawer";
import { useUi } from "../store/ui";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

function mockFetch(handlers: Record<string, (url: string) => unknown>) {
  (globalThis as any).fetch = vi.fn(async (url: string) => {
    for (const [suffix, handler] of Object.entries(handlers)) {
      if (String(url).endsWith(suffix)) {
        return new Response(JSON.stringify(handler(url)), { status: 200 });
      }
    }
    return new Response("{}", { status: 200 });
  });
}

beforeEach(() => {
  useUi.setState({
    focusedTicker: "NVDA",
    lastRunIdByTicker: { NVDA: "NVDA:1" },
    historicalRunIdByTicker: {},
    activeRunIdByTicker: {},
    eventBuffer: [],
  });
});

describe("RunHistoryDrawer", () => {
  it("fetches /api/tickers/{ticker}/runs and shows model + price + duration", async () => {
    mockFetch({
      "/runs?limit=50": (url) => url,
      "/api/tickers/NVDA/runs": () => [
        {
          id: "NVDA:1",
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
        },
      ],
    });
    wrap(<RunHistoryDrawer open onClose={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText(/gpt-5\.5/)).toBeInTheDocument();
    });
    expect(screen.getByText(/\$123\.45/)).toBeInTheDocument();
    expect(screen.getByText(/42\.0s|42s/)).toBeInTheDocument();
  });
});
