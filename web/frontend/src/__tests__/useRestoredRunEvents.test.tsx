import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode } from "react";
import { useUi } from "../store/ui";
import { useRestoredRunEvents } from "../hooks/useRestoredRunEvents";
import * as api from "../lib/api";
import type { WsEvent } from "../lib/events";

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

const evt = (runId: number, type: string, id: number): WsEvent => ({
  v: 1, type: type as any, ts: `t${id}`, run_id: runId, data: {}, id,
});

beforeEach(() => {
  useUi.setState({
    eventBuffer: [],
    lastRunIdByTicker: {},
    activeRunIdByTicker: {},
    focusedTicker: null,
  });
  vi.restoreAllMocks();
});

describe("useRestoredRunEvents", () => {
  it("hydrates event buffer from /api/runs/{id} on mount", async () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: 7 },
    });
    vi.spyOn(api, "fetchRunDetail").mockResolvedValue({
      run: { id: 7, ticker: "NVDA", started_at: null, finished_at: null,
             status: "done", decision_action: null, decision_target: null,
             decision_rationale: null, decision_confidence: null },
      events: [evt(7, "analyst_thinking", 1), evt(7, "analyst_completed", 2)],
    });
    renderHook(() => useRestoredRunEvents("NVDA"), { wrapper: createWrapper() });
    await waitFor(() => {
      const buf = useUi.getState().eventBuffer;
      expect(buf).toHaveLength(2);
      expect(buf.every((e) => e.run_id === 7)).toBe(true);
    });
  });

  it("skips the fetch for active runs", async () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: 7 },
    });
    const fetchSpy = vi.spyOn(api, "fetchRunDetail").mockResolvedValue({
      run: { id: 7, ticker: "NVDA", started_at: null, finished_at: null,
             status: "running", decision_action: null, decision_target: null,
             decision_rationale: null, decision_confidence: null },
      events: [evt(7, "analyst_thinking", 1)],
    });
    renderHook(() => useRestoredRunEvents("NVDA"), { wrapper: createWrapper() });
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled();
    });
    // Wait an additional tick to let the effect run.
    await new Promise((r) => setTimeout(r, 50));
    expect(useUi.getState().eventBuffer).toEqual([]);
  });

  it("clears the stale run id on 404", async () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: 7 },
    });
    vi.spyOn(api, "fetchRunDetail").mockRejectedValue(new Error("run 404"));
    renderHook(() => useRestoredRunEvents("NVDA"), { wrapper: createWrapper() });
    await waitFor(() => {
      expect(useUi.getState().lastRunIdByTicker.NVDA ?? null).toBeNull();
    });
  });

  it("refetches when focused changes", async () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: 7, AAPL: 8 },
    });
    const fetchSpy = vi.spyOn(api, "fetchRunDetail").mockImplementation(async (id) => ({
      run: { id, ticker: "X", started_at: null, finished_at: null,
             status: "done", decision_action: null, decision_target: null,
             decision_rationale: null, decision_confidence: null },
      events: [evt(id, "analyst_thinking", 1)],
    }));
    const { rerender } = renderHook(({ focused }: { focused: string }) => useRestoredRunEvents(focused), {
      initialProps: { focused: "NVDA" },
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledWith(7));
    rerender({ focused: "AAPL" });
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledWith(8));
  });
});
