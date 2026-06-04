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

const evt = (runId: string, type: string, id: string): WsEvent => ({
  v: 1, type: type as any, ts: `t${id}`, run_id: runId, data: {}, id,
});

const row = (id: string, status: "running" | "done" | "failed" | "queued" | "cancelled" | "superseded" = "done") => ({
  id,
  slug: id,
  ticker: "NVDA",
  started_at: null,
  finished_at: null,
  status,
  cancel_requested: false,
  decision_action: null,
  decision_target: null,
  decision_rationale: null,
  decision_confidence: null,
});

beforeEach(() => {
  useUi.setState({
    eventBuffer: [],
    lastRunIdByTicker: {},
    historicalRunIdByTicker: {},
    activeRunIdByTicker: {},
    focusedTicker: null,
  });
  vi.restoreAllMocks();
});

describe("useRestoredRunEvents", () => {
  it("hydrates event buffer from /api/runs/{id} on mount", async () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: "NVDA:7" },
    });
    vi.spyOn(api, "fetchRunDetail").mockResolvedValue({
      ...row("NVDA:7"),
      events: [evt("NVDA:7", "analyst_thinking", "1"), evt("NVDA:7", "analyst_completed", "2")],
      llm_calls: [],
      stages: [],
    });
    renderHook(() => useRestoredRunEvents("NVDA"), { wrapper: createWrapper() });
    await waitFor(() => {
      const buf = useUi.getState().eventBuffer;
      expect(buf).toHaveLength(2);
      expect(buf.every((e) => e.run_id === "NVDA:7")).toBe(true);
    });
  });

  it("skips the fetch for active runs", async () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: "NVDA:7" },
    });
    const fetchSpy = vi.spyOn(api, "fetchRunDetail").mockResolvedValue({
      ...row("NVDA:7", "running"),
      events: [evt("NVDA:7", "analyst_thinking", "1")],
      llm_calls: [],
      stages: [],
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
      lastRunIdByTicker: { NVDA: "NVDA:7" },
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
      lastRunIdByTicker: { NVDA: "NVDA:7", AAPL: "AAPL:8" },
    });
    const fetchSpy = vi.spyOn(api, "fetchRunDetail").mockImplementation(async (id) => ({
      ...row(id),
      ticker: "X",
      events: [evt(id, "analyst_thinking", "1")],
      llm_calls: [],
      stages: [],
    }));
    const { rerender } = renderHook(({ focused }: { focused: string }) => useRestoredRunEvents(focused), {
      initialProps: { focused: "NVDA" },
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledWith("NVDA:7"));
    rerender({ focused: "AAPL" });
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledWith("AAPL:8"));
  });

  it("fetches the historical run, not the latest, when both are set", async () => {
    // Regression: useRestoredRunEvents used to key on lastRunIdByTicker
    // only, so picking a historical run from the dropdown left the
    // timeline empty (useFocusedRunEvents displayed historical events
    // but the hook never fetched them from the DB).
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: "NVDA:11" },
      historicalRunIdByTicker: { NVDA: "NVDA:5" },
    });
    const fetchSpy = vi.spyOn(api, "fetchRunDetail").mockImplementation(async (id) => ({
      ...row(id),
      ticker: "NVDA",
      events: [evt(id, "analyst_thinking", "1"), evt(id, "analyst_completed", "2")],
      llm_calls: [],
      stages: [],
    }));
    renderHook(() => useRestoredRunEvents("NVDA"), { wrapper: createWrapper() });
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledWith("NVDA:5"));
    await waitFor(() => {
      const buf = useUi.getState().eventBuffer;
      expect(buf).toHaveLength(2);
      expect(buf.every((e) => e.run_id === "NVDA:5")).toBe(true);
    });
    expect(fetchSpy).not.toHaveBeenCalledWith("NVDA:11");
  });

  it("refetches when the user picks a different historical run", async () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: "NVDA:11" },
      historicalRunIdByTicker: { NVDA: "NVDA:5" },
    });
    const fetchSpy = vi.spyOn(api, "fetchRunDetail").mockImplementation(async (id) => ({
      ...row(id),
      ticker: "NVDA",
      events: [evt(id, "analyst_thinking", "1")],
      llm_calls: [],
      stages: [],
    }));
    renderHook(() => useRestoredRunEvents("NVDA"), { wrapper: createWrapper() });
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledWith("NVDA:5"));
    // User picks a different historical run from the dropdown.
    useUi.getState().setHistoricalRunForTicker?.("NVDA", "NVDA:7");
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledWith("NVDA:7"));
  });

  it("clears the historical run id on 404", async () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: "NVDA:11" },
      historicalRunIdByTicker: { NVDA: "NVDA:5" },
    });
    vi.spyOn(api, "fetchRunDetail").mockRejectedValue(new Error("run 404"));
    renderHook(() => useRestoredRunEvents("NVDA"), { wrapper: createWrapper() });
    await waitFor(() => {
      expect(useUi.getState().historicalRunIdByTicker.NVDA ?? null).toBeNull();
    });
  });
});
