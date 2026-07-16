/** Bell list shaping (review R2.5): the hourly loop writes ~24 info-level
 * run_complete notes a day, which buries the four warnings that matter.
 * Consecutive notes of the same chatty event collapse into one group row;
 * warnings/criticals never group. */
import type { Notification } from "./api/types";

export type BellRow =
  | { kind: "single"; note: Notification }
  | { kind: "group"; event: string; notes: Notification[] };

const GROUPABLE = new Set(["run_complete"]);

export function groupConsecutive(notes: readonly Notification[]): BellRow[] {
  const rows: BellRow[] = [];
  let bucket: Notification[] = [];

  const flush = () => {
    if (bucket.length === 0) return;
    if (bucket.length === 1) rows.push({ kind: "single", note: bucket[0]! });
    else rows.push({ kind: "group", event: bucket[0]!.event, notes: bucket });
    bucket = [];
  };

  for (const note of notes) {
    const groupable = GROUPABLE.has(note.event) && note.severity === "info";
    if (groupable && (bucket.length === 0 || bucket[0]!.event === note.event)) {
      bucket.push(note);
      continue;
    }
    flush();
    if (groupable) bucket.push(note);
    else rows.push({ kind: "single", note });
  }
  flush();
  return rows;
}

/** "important" hides info-level chatter; warnings and criticals always show. */
export function bySeverity(
  notes: readonly Notification[],
  filter: "all" | "important",
): Notification[] {
  if (filter === "all") return [...notes];
  return notes.filter((n) => n.severity === "warning" || n.severity === "critical");
}
