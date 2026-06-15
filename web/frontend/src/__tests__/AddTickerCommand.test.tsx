import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode } from "react";
import { AddTickerCommand } from "../components/AddTickerCommand";
import * as api from "../lib/api";

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("AddTickerCommand", () => {
  it("shows a clear 'not found' message when the backend rejects the ticker", async () => {
    const { ApiError } = await import("../lib/api");
    vi.spyOn(api, "addToWatchlist").mockRejectedValueOnce(
      new ApiError("add 400", 400, {
        detail: { error: "ticker_not_found", ticker: "BADX", reason: "KeyError" },
      }),
    );
    render(<AddTickerCommand />, { wrapper: createWrapper() });
    fireEvent.click(screen.getByText("Add ticker"));
    const input = screen.getByPlaceholderText(/Ticker symbol/i);
    fireEvent.change(input, { target: { value: "BADX" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => {
      expect(
        screen.getByText(/BADX.*not found.*Yahoo Finance/i),
      ).toBeInTheDocument();
    });
  });

  it("shows a 'duplicate' message on 409", async () => {
    const { ApiError } = await import("../lib/api");
    vi.spyOn(api, "addToWatchlist").mockRejectedValueOnce(
      new ApiError("add 409", 409, { detail: { error: "already_in_watchlist" } }),
    );
    render(<AddTickerCommand />, { wrapper: createWrapper() });
    fireEvent.click(screen.getByText("Add ticker"));
    const input = screen.getByPlaceholderText(/Ticker symbol/i);
    fireEvent.change(input, { target: { value: "NVDA" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => {
      expect(screen.getByText(/NVDA.*already in your watchlist/i)).toBeInTheDocument();
    });
  });

  it("falls back to a generic message for unknown errors", async () => {
    vi.spyOn(api, "addToWatchlist").mockRejectedValueOnce(new Error("network down"));
    render(<AddTickerCommand />, { wrapper: createWrapper() });
    fireEvent.click(screen.getByText("Add ticker"));
    const input = screen.getByPlaceholderText(/Ticker symbol/i);
    fireEvent.change(input, { target: { value: "NVDA" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => {
      expect(screen.getByText(/Could not add "NVDA"/i)).toBeInTheDocument();
    });
  });

  it("closes the form and clears the error on a successful add", async () => {
    vi.spyOn(api, "addToWatchlist").mockResolvedValueOnce(undefined);
    const { container } = render(<AddTickerCommand />, { wrapper: createWrapper() });
    fireEvent.click(screen.getByText("Add ticker"));
    const input = screen.getByPlaceholderText(/Ticker symbol/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "NVDA" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => {
      expect(container.querySelector('input[placeholder*="Ticker"]')).toBeNull();
    });
  });
});
