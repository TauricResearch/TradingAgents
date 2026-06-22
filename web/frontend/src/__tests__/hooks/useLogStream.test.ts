import { describe, it, expect, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useLogStream } from "../../hooks/useLogStream";

describe("useLogStream", () => {
  it("returns idle status when not connected", () => {
    const { result } = renderHook(() => useLogStream());
    expect(result.current.status).toBe("idle");
  });
});