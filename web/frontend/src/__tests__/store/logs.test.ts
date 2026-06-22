import { describe, it, expect, beforeEach } from "vitest";
import { useLogStore } from "../../store/logs";

describe("useLogStore", () => {
  beforeEach(() => {
    useLogStore.getState().clear();
  });

  it("starts with empty entries", () => {
    expect(useLogStore.getState().entries).toEqual([]);
  });

  it("append adds entry to entries", () => {
    const entry = {
      id: "1",
      ts: "2026-06-22T10:00:00Z",
      level: "INFO" as const,
      logger: "test",
      message: "hello",
      source: "server" as const,
    };
    useLogStore.getState().append(entry);
    expect(useLogStore.getState().entries).toHaveLength(1);
    expect(useLogStore.getState().entries[0]).toEqual(entry);
  });

  it("clear removes all entries", () => {
    useLogStore.getState().append({ id: "1", ts: "", level: "INFO", logger: "", message: "", source: "server" });
    useLogStore.getState().append({ id: "2", ts: "", level: "ERROR", logger: "", message: "", source: "client" });
    useLogStore.getState().clear();
    expect(useLogStore.getState().entries).toHaveLength(0);
  });

  it("caps entries at 1000", () => {
    for (let i = 0; i < 1050; i++) {
      useLogStore.getState().append({ id: String(i), ts: "", level: "INFO", logger: "", message: "", source: "server" });
    }
    expect(useLogStore.getState().entries).toHaveLength(1000);
    expect(useLogStore.getState().entries[0].id).toBe("50");
  });
});