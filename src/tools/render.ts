// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The text the model reads for a tool's result, written from its payload: the
 * result's id and where the data came from, then the payload's fields, its lists, and the lists the
 * tool declares as a table, a column each. A table too long to show keeps its newest rows; every row
 * stays reachable by reference.
 */
import { message, withWeekday } from "../contracts/index.js";
import { CALLS } from "../contracts/limits.js";
import { referenceTo } from "./references.js";
import type { Provenance } from "./tool.js";
import { fitting, sourceOf } from "./tool-text.js";

export function renderResult(result: {
  id?: string;
  tool: string;
  label: string;
  provenance: Provenance;
  payload: unknown;
  table?: readonly string[];
  /** The tool's own wording of the payload, under the head. */
  render?: (payload: never, at: { id?: string; room: number }) => string[];
  /** The characters the text may take; the model's own budget unless set. */
  room?: number;
}): string {
  const room = result.room ?? CALLS.textChars;
  const { id, provenance, payload } = result;
  const about = [
    ...(provenance.as_of ? [`as of ${withWeekday(provenance.as_of)}`] : []),
    ...(id ? [`reference its data as ${referenceTo(id, "<field>")}`] : []),
  ];
  const head = [
    `${id ? `[${id}] ` : ""}${result.tool}${result.label ? ` ${result.label}` : ""}${about.length ? ` (${about.join("; ")})` : ""}`,
    message("data.source", { source: sourceOf(provenance) }),
    ...(provenance.notes ?? []),
  ];
  if (result.render) {
    const used = head.join("\n").length + 1;
    return [...head, ...result.render(payload as never, { ...(id ? { id } : {}), room: room - used })].join(
      "\n",
    );
  }
  const record = payload !== null && typeof payload === "object" && !Array.isArray(payload);
  if (!record) return [...head, `value: ${JSON.stringify(payload)}`].join("\n");
  const fields = payload as Record<string, unknown>;
  const columns = (result.table ?? []).filter((name) => Array.isArray(fields[name]));
  for (const [key, value] of Object.entries(fields)) {
    if (value === undefined || columns.includes(key)) continue;
    if (Array.isArray(value) && value.every((item) => typeof item === "string")) {
      if (value.length) head.push(`${key}:`, ...value.map((item) => `- ${item}`));
    } else head.push(`${key}: ${scalar(value)}`);
  }
  if (!columns.length) return head.join("\n");
  const lists = columns.map((name) => fields[name] as unknown[]);
  const count = Math.max(...lists.map((list) => list.length));
  const newestFirst = Array.from({ length: count }, (_, i) =>
    lists.map((list) => cell(list[count - 1 - i])).join(","),
  );
  const header = columns.join(",");
  const note = (shown: number) =>
    `rows ${shown} of ${count} shown, the newest${id ? `; every row is in ${referenceTo(id, columns[0])}` : ""}`;
  let kept = fitting(newestFirst, room - [...head, header].join("\n").length - 1);
  if (kept < count) kept = fitting(newestFirst, room - [...head, header, note(count)].join("\n").length - 2);
  const rows = newestFirst.slice(0, kept).reverse();
  return [...head, header, ...rows, ...(kept < count ? [note(kept)] : [])].join("\n");
}

/** A number as people write it: binary rounding noise (4.0000000000000036) left out of the text only. */
function number(value: number): string {
  return Number.isFinite(value) && !Number.isInteger(value)
    ? String(Number(value.toPrecision(15)))
    : String(value);
}

function scalar(value: unknown): string {
  if (value === null) return "none";
  if (typeof value === "number") return number(value);
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean")
    return String(value);
  return JSON.stringify(value);
}

function cell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return number(value);
  return typeof value === "string" || typeof value === "number" || typeof value === "boolean"
    ? String(value)
    : JSON.stringify(value);
}
