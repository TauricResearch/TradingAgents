import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "../App";
import { useUi } from "../store/ui";

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><App /></QueryClientProvider>);
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
    // The rail and the add-ticker control are reachable so the user is
    // not stranded.
    await waitFor(() => expect(screen.getByRole("button", { name: /add ticker/i })).toBeInTheDocument());
    expect(screen.getByText(/watchlist is empty/i)).toBeInTheDocument();
    // Focused ticker UI must not appear when there is nothing to focus.
    expect(screen.queryByText(/Loading watchlist/i)).not.toBeInTheDocument();
  });
});
