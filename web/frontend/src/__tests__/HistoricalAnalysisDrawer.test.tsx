import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HistoricalAnalysisDrawer } from "../components/HistoricalAnalysisDrawer";

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("HistoricalAnalysisDrawer", () => {
  it("renders the drawer with ticker title when open", () => {
    const onClose = vi.fn();
    render(
      <Wrapper>
        <HistoricalAnalysisDrawer ticker="NVDA" onClose={onClose} />
      </Wrapper>,
    );
    expect(screen.getByText(/NVDA/)).toBeInTheDocument();
  });

  it("renders without crashing for different tickers", () => {
    const onClose = vi.fn();
    const { rerender } = render(
      <Wrapper>
        <HistoricalAnalysisDrawer ticker="AAPL" onClose={onClose} />
      </Wrapper>,
    );
    expect(screen.getByText(/AAPL/)).toBeInTheDocument();

    rerender(
      <Wrapper>
        <HistoricalAnalysisDrawer ticker="TSLA" onClose={onClose} />
      </Wrapper>,
    );
    expect(screen.getByText(/TSLA/)).toBeInTheDocument();
  });

  it("renders the close button", () => {
    const onClose = vi.fn();
    render(
      <Wrapper>
        <HistoricalAnalysisDrawer ticker="NVDA" onClose={onClose} />
      </Wrapper>,
    );
    expect(screen.getByRole("button", { name: /close/i })).toBeInTheDocument();
  });
});
