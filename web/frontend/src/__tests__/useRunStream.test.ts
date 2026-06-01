import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { installMockWebSocket, MockWebSocket } from "./mocks/mockWs";
import { useRunStream } from "../hooks/useRunStream";
import { useUi } from "../store/ui";

describe("useRunStream", () => {
  beforeEach(() => {
    installMockWebSocket();
    useUi.setState({ eventBuffer: [] });
  });

  it("connects and pushes events to the buffer", () => {
    const { result } = renderHook(() => useRunStream(42));
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    act(() => ws.receive({ v: 1, type: "run_started", ts: "2026-06-01T00:00:00Z", run_id: 42, data: {}, id: 1 }));
    expect(useUi.getState().eventBuffer).toHaveLength(1);
    expect(result.current.status).toBe("open");
  });

  it("reconnects with ?since= after disconnect", () => {
    renderHook(() => useRunStream(42));
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    act(() => ws.receive({ v: 1, type: "analyst_thinking", ts: "t", run_id: 42, data: {}, id: 5 }));
    act(() => ws.failAndClose());
    return new Promise<void>((resolve) => {
      setTimeout(() => {
        const next = MockWebSocket.instances[MockWebSocket.instances.length - 1];
        expect(next.url).toContain("since=5");
        resolve();
      }, 1100);
    });
  });
});
