import { describe, it, expect, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { useUi } from "../store/ui";
import { useFocusedRunEvents } from "../hooks/useFocusedRunEvents";
import type { WsEvent } from "../lib/events";

const evt = (runId: string, type: string, id: string): WsEvent => ({
  v: 1, type: type as any, ts: `t${id}`, run_id: runId, data: {}, id,
});

describe("useFocusedRunEvents", () => {
  beforeEach(() => {
    useUi.setState({
      eventBuffer: [],
      lastRunIdByTicker: {},
      activeRunIdByTicker: {},
      historicalRunIdByTicker: {},
      focusedTicker: null,
    });
  });

  it("returns events for the focused ticker only", () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: "NVDA:1" },
      eventBuffer: [evt("NVDA:1", "analyst_started", "1"), evt("AAPL:1", "analyst_started", "2")],
    });
    const { result } = renderHook(() => useFocusedRunEvents());
    expect(result.current).toHaveLength(1);
    expect(result.current[0].run_id).toBe("NVDA:1");
  });

  it("returns empty list when no ticker is focused", () => {
    useUi.setState({
      lastRunIdByTicker: { NVDA: "NVDA:1" },
      eventBuffer: [evt("NVDA:1", "analyst_started", "1")],
    });
    const { result } = renderHook(() => useFocusedRunEvents());
    expect(result.current).toEqual([]);
  });

  it("returns empty list when the focused ticker has no last run", () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: {},
      eventBuffer: [evt("NVDA:1", "analyst_started", "1")],
    });
    const { result } = renderHook(() => useFocusedRunEvents());
    expect(result.current).toEqual([]);
  });

  it("updates when focused changes", () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: "NVDA:1", AAPL: "AAPL:2" },
      eventBuffer: [evt("NVDA:1", "analyst_started", "1")],
    });
    const { result, rerender } = renderHook(() => useFocusedRunEvents());
    expect(result.current[0].run_id).toBe("NVDA:1");
    // Switching focus triggers the clearEventBuffer effect for the
    // new runId (preventing REST-replay + WS duplicates on the
    // handoff). Once the new run's events arrive (via REST replay or
    // WS), they appear in the filtered list.
    useUi.setState({ focusedTicker: "AAPL" });
    rerender();
    expect(result.current).toHaveLength(0);
    useUi.setState({
      eventBuffer: [evt("NVDA:1", "analyst_started", "1"), evt("AAPL:2", "analyst_started", "2")],
    });
    rerender();
    expect(result.current[0].run_id).toBe("AAPL:2");
  });

  it("prefers historicalRunIdByTicker over lastRunIdByTicker", () => {
    // The user picked an older run from the dropdown; the events must
    // come from that run, not the latest one.
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: "NVDA:99" },
      historicalRunIdByTicker: { NVDA: "NVDA:5" },
      eventBuffer: [
        evt("NVDA:99", "analyst_started", "1"),
        evt("NVDA:5", "analyst_started", "2"),
        evt("NVDA:5", "decision", "3"),
      ],
    });
    const { result } = renderHook(() => useFocusedRunEvents());
    expect(result.current).toHaveLength(2);
    expect(result.current.every((e) => e.run_id === "NVDA:5")).toBe(true);
  });

  it("falls back to lastRunIdByTicker when historical is not set", () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: "NVDA:7" },
      historicalRunIdByTicker: {},
      eventBuffer: [evt("NVDA:7", "analyst_started", "1")],
    });
    const { result } = renderHook(() => useFocusedRunEvents());
    expect(result.current).toHaveLength(1);
    expect(result.current[0].run_id).toBe("NVDA:7");
  });
});
