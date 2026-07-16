import { describe, expect, it } from "vitest";

import type { Notification } from "../api/types";
import { bySeverity, groupConsecutive } from "../bellGroups";

let counter = 0;
function note(event: string, severity = "info", read = false): Notification {
  counter += 1;
  return {
    id: `n${counter}`,
    severity,
    event,
    text: `${event} #${counter}`,
    time: `2026-07-16T1${counter % 10}:00:00+00:00`,
    read,
  };
}

describe("bell grouping (R2.5)", () => {
  it("collapses consecutive run_complete chatter, keeps warnings solo", () => {
    const rows = groupConsecutive([
      note("run_complete"),
      note("run_complete"),
      note("run_complete"),
      note("order_rejected", "warning"),
      note("run_complete"),
    ]);
    expect(rows.map((r) => r.kind)).toEqual(["group", "single", "single"]);
    const first = rows[0]!;
    expect(first.kind === "group" ? first.notes.length : 0).toBe(3);
  });

  it("a lone run_complete stays a single row", () => {
    const rows = groupConsecutive([note("run_complete"), note("daily_pnl")]);
    expect(rows.every((r) => r.kind === "single")).toBe(true);
  });

  it("warning-severity run notes never group", () => {
    const rows = groupConsecutive([
      note("run_complete", "warning"),
      note("run_complete", "warning"),
    ]);
    expect(rows.every((r) => r.kind === "single")).toBe(true);
  });
});

describe("bell severity filter (R2.5)", () => {
  it("important keeps warnings and criticals only", () => {
    const notes = [
      note("run_complete", "info"),
      note("order_rejected", "warning"),
      note("halt", "critical"),
    ];
    expect(bySeverity(notes, "important").map((n) => n.severity)).toEqual([
      "warning",
      "critical",
    ]);
    expect(bySeverity(notes, "all")).toHaveLength(3);
  });
});
