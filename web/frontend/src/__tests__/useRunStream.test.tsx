/* eslint-disable @typescript-eslint/no-explicit-any */
import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { installMockWebSocket, MockWebSocket } from "./mocks/mockWs";
import { useRunStream } from "../hooks/useRunStream";
import { useUi } from "../store/ui";
import type { WsEvent } from "../lib/events";
import type { ReactNode } from "react";

const evt = (runId: string, type: string, id: string): WsEvent => ({
  v: 1, type: type as any, ts: `t${id}`, run_id: runId, data: {}, id,
});

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>;
}

describe("useRunStream", () => {
  beforeEach(() => {
    installMockWebSocket();
    useUi.setState({ eventBuffer: [] });
  });

  it("connects and pushes events to the buffer", () => {
    const { result } = renderHook(() => useRunStream("NVDA:42"), { wrapper });
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    act(() => ws.receive({ v: 1, type: "run_started", ts: "2026-06-01T00:00:00Z", run_id: "NVDA:42", data: {}, id: "1" }));
    expect(useUi.getState().eventBuffer).toHaveLength(1);
    expect(result.current.status).toBe("open");
  });

  it("reconnects with ?since= after disconnect", () => {
    renderHook(() => useRunStream("NVDA:42"), { wrapper });
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    act(() => ws.receive({ v: 1, type: "analyst_thinking", ts: "t", run_id: "NVDA:42", data: {}, id: "NVDA:42:5" }));
    act(() => ws.failAndClose());
    return new Promise<void>((resolve) => {
      setTimeout(() => {
        const next = MockWebSocket.instances[MockWebSocket.instances.length - 1];
        expect(next.url).toContain("since=NVDA%3A42%3A5");
        resolve();
      }, 1100);
    });
  });

  it("clears buffered events for its runId before opening the WS", () => {
    useUi.setState({
      eventBuffer: [evt("NVDA:42", "analyst_started", "1"), evt("AAPL:1", "analyst_started", "2")],
    });
    renderHook(() => useRunStream("NVDA:42"), { wrapper });
    expect(useUi.getState().eventBuffer.map((e) => e.id)).toEqual(["2"]);
  });
});
