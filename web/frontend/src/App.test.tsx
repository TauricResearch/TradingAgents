/* eslint-disable @typescript-eslint/no-explicit-any */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { useUi } from "./store/ui";

beforeEach(() => {
  useUi.setState({
    focusedTicker: null,
    lastRunIdByTicker: {},
    activeRunIdByTicker: {},
    eventBuffer: [],
    backgroundRunsOpen: false,
  });
  (globalThis as any).fetch = vi.fn((url: string) => {
    if (String(url).endsWith("/api/watchlist")) {
      return Promise.resolve(new Response(JSON.stringify([])));
    }
    return Promise.resolve(new Response("{}", { status: 200 }));
  }) as any;
});

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>
  );
}

describe("App: Past Runs button", () => {
  it("renders the Past Runs button next to History", async () => {
    renderApp();
    expect(await screen.findByRole("button", { name: /past runs/i })).toBeInTheDocument();
  });

  it("clicking the button opens the BackgroundRunsDrawer", async () => {
    renderApp();
    await screen.findByRole("button", { name: /past runs/i });
    await userEvent.click(screen.getByRole("button", { name: /past runs/i }));
    await waitFor(() => expect(screen.getByTestId("background-runs-drawer")).toBeInTheDocument());
  });
});
