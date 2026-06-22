import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useLogStream } from "../../hooks/useLogStream";
import { ResilientWs } from "../../lib/ws";

vi.mock("../../lib/ws", () => ({
  ResilientWs: vi.fn().mockImplementation(function(this: { start: ReturnType<typeof vi.fn>; stop: ReturnType<typeof vi.fn> }) {
    this.start = vi.fn();
    this.stop = vi.fn();
    return this;
  }),
  buildLogsUrl: vi.fn().mockReturnValue("ws://localhost/ws/logs"),
}));

describe("useLogStream", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns idle status when not connected", () => {
    const { result } = renderHook(() => useLogStream());
    expect(result.current.status).toBe("idle");
  });
});