import { describe, it, expect } from "vitest";
import { EventType, ALL_EVENT_TYPES } from "../lib/events";

// Mirror the Python expected set
const PYTHON_EXPECTED = new Set([
  "run_started", "run_finished", "run_failed",
  "analyst_started", "analyst_thinking", "analyst_completed",
  "tool_call", "tool_result", "tool_call_warning",
  "debate_message", "risk_message", "decision",
  "price_update", "server_notice",
]);

describe("events protocol", () => {
  it("TS mirror matches Python expected set", () => {
    const ts = new Set(ALL_EVENT_TYPES);
    expect(ts).toEqual(PYTHON_EXPECTED);
  });

  it("no empty type values", () => {
    for (const v of ALL_EVENT_TYPES) {
      expect(v).toBeTruthy();
      expect(typeof v).toBe("string");
    }
  });

  it("EventType keys are unique", () => {
    const values = Object.values(EventType);
    expect(new Set(values).size).toBe(values.length);
  });
});
