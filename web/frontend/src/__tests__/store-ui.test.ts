import { describe, it, expect, beforeEach, vi } from "vitest";
import { useUi } from "../store/ui";
import type { WsEvent } from "../lib/events";

function evt(
  id: number,
  runId: number,
  type: WsEvent["type"] = "analyst_thinking",
  data: unknown = {},
): WsEvent {
  return { v: 1, type, ts: `t${id}`, run_id: runId, data, id };
}

function resetState() {
  useUi.setState({
    focusedTicker: null,
    lastRunIdByTicker: {},
    activeRunIdByTicker: {},
    eventBuffer: [],
  });
}

beforeEach(() => {
  localStorage.clear();
  resetState();
});

describe("ui store — per-ticker cache", () => {
  it("preserves the event buffer when switching tickers", () => {
    useUi.setState({ eventBuffer: [evt(1, 42, "analyst_thinking", { node: "Market Analyst" })] });
    useUi.getState().setFocusedTicker("AAPL");
    useUi.getState().setFocusedTicker("NVDA");
    useUi.getState().setFocusedTicker("AAPL");
    expect(useUi.getState().eventBuffer).toHaveLength(1);
  });

  it("preserves lastRunIdByTicker when switching tickers", () => {
    useUi.getState().setLastRunIdForTicker("AAPL", 42);
    useUi.getState().setLastRunIdForTicker("NVDA", 99);
    useUi.getState().setFocusedTicker("AAPL");
    useUi.getState().setFocusedTicker("NVDA");
    expect(useUi.getState().lastRunIdByTicker).toEqual({ AAPL: 42, NVDA: 99 });
  });

  it("setLastRunIdForTicker overwrites when a new run starts for the same ticker", () => {
    useUi.getState().setLastRunIdForTicker("AAPL", 42);
    useUi.getState().setLastRunIdForTicker("AAPL", 100);
    expect(useUi.getState().lastRunIdByTicker.AAPL).toBe(100);
  });

  it("activeRunIdByTicker is set on start and cleared on terminal events", () => {
    useUi.getState().setActiveRunIdForTicker("AAPL", 42);
    expect(useUi.getState().activeRunIdByTicker.AAPL).toBe(42);
    useUi.getState().clearActiveRunForTicker("AAPL");
    expect(useUi.getState().activeRunIdByTicker.AAPL).toBeNull();
  });

  it("appendEvent keeps events from multiple runs in the same global buffer", () => {
    useUi.getState().appendEvent(evt(1, 42, "analyst_thinking"));
    useUi.getState().appendEvent(evt(2, 99, "analyst_thinking"));
    expect(useUi.getState().eventBuffer.map((e) => e.run_id)).toEqual([42, 99]);
  });
});

describe("ui store — persistence", () => {
  it("writes focusedTicker and lastRunIdByTicker to localStorage on change", async () => {
    useUi.getState().setFocusedTicker("AAPL");
    useUi.getState().setLastRunIdForTicker("AAPL", 42);
    useUi.setState({ eventBuffer: [evt(1, 42, "analyst_thinking")] });
    // Let the persist middleware flush.
    await new Promise((r) => setTimeout(r, 0));
    const raw = localStorage.getItem("tradingagents-ui");
    expect(raw).toBeTruthy();
    const parsed = JSON.parse(raw!);
    expect(parsed.state.focusedTicker).toBe("AAPL");
    expect(parsed.state.lastRunIdByTicker).toEqual({ AAPL: 42 });
    // Runtime-only: the live event buffer must NOT be persisted, since a
    // 1000-event JSON.stringify on every WS append would dominate the
    // main thread during a busy run. The buffer is the live stream's
    // working state; historical events are re-fetched from the server.
    expect(parsed.state.eventBuffer).toBeUndefined();
    // Active-run map is runtime-only and must not be persisted (it's
    // re-derived on hydration from server state).
    expect(parsed.state.activeRunIdByTicker).toBeUndefined();
  });

  it("hydrates a fresh store instance from localStorage on init", async () => {
    localStorage.setItem(
      "tradingagents-ui",
      JSON.stringify({
        state: {
          focusedTicker: "NVDA",
          lastRunIdByTicker: { NVDA: 7 },
        },
        version: 0,
      }),
    );
    vi.resetModules();
    const { useUi: Fresh } = await import("../store/ui");
    // Use waitFor so a future change to async hydration doesn't silently
    // regress this test the way a setTimeout(0) microtask would.
    await vi.waitFor(() => expect(Fresh.getState().focusedTicker).toBe("NVDA"));
    expect(Fresh.getState().lastRunIdByTicker).toEqual({ NVDA: 7 });
    // Fresh store has an empty buffer; nothing about a prior buffer is
    // recoverable from persistence.
    expect(Fresh.getState().eventBuffer).toEqual([]);
  });
});
