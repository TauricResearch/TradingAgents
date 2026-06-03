import { describe, it, expect, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { useUi } from "../store/ui";
import { useFocusedRunEvents } from "../hooks/useFocusedRunEvents";
import type { WsEvent } from "../lib/events";

const evt = (runId: number, type: string, id: number): WsEvent => ({
  v: 1, type: type as any, ts: `t${id}`, run_id: runId, data: {}, id,
});

describe("useFocusedRunEvents", () => {
  beforeEach(() => {
    useUi.setState({
      eventBuffer: [],
      lastRunIdByTicker: {},
      activeRunIdByTicker: {},
      focusedTicker: null,
    });
  });

  it("returns events for the focused ticker only", () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: 1 },
      eventBuffer: [evt(1, "analyst_started", 1), evt(2, "analyst_started", 2)],
    });
    const { result } = renderHook(() => useFocusedRunEvents());
    expect(result.current).toHaveLength(1);
    expect(result.current[0].run_id).toBe(1);
  });

  it("returns empty list when no ticker is focused", () => {
    useUi.setState({
      lastRunIdByTicker: { NVDA: 1 },
      eventBuffer: [evt(1, "analyst_started", 1)],
    });
    const { result } = renderHook(() => useFocusedRunEvents());
    expect(result.current).toEqual([]);
  });

  it("returns empty list when the focused ticker has no last run", () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: {},
      eventBuffer: [evt(1, "analyst_started", 1)],
    });
    const { result } = renderHook(() => useFocusedRunEvents());
    expect(result.current).toEqual([]);
  });

  it("updates when focused changes", () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: 1, AAPL: 2 },
      eventBuffer: [evt(1, "analyst_started", 1), evt(2, "analyst_started", 2)],
    });
    const { result, rerender } = renderHook(() => useFocusedRunEvents());
    expect(result.current[0].run_id).toBe(1);
    useUi.setState({ focusedTicker: "AAPL" });
    rerender();
    expect(result.current[0].run_id).toBe(2);
  });
});
