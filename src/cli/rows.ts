// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The pieces of a transcript row: how long something took, the spinner's frame, and fitting a row's
 * fields into one line. A row is never more than one line; when it is too long, its secondary fields
 * give way first (cut with an ellipsis, by cells), and the ones that say what happened never do.
 */
import stringWidth from "string-width";
import { printable } from "../contracts/index.js";
import { APP } from "../contracts/limits.js";

/** A time as a row shows it: `0.4s` under ten seconds, `12s`, then `1m 05s`. */
export function shortDuration(ms: number): string {
  const seconds = Math.max(0, ms) / 1_000;
  if (seconds < 9.95) return `${seconds.toFixed(1)}s`;
  // Whole seconds from here; 59.6 s is a minute, not "60s".
  const whole = Math.round(seconds);
  if (whole < 60) return `${whole}s`;
  return `${Math.floor(whole / 60)}m ${String(whole % 60).padStart(2, "0")}s`;
}

/** A running time, in whole seconds so it ticks once a second: `12s`, then `1m 05s`. */
export function runningDuration(ms: number): string {
  const whole = Math.floor(Math.max(0, ms) / 1_000);
  return whole < 60 ? `${whole}s` : `${Math.floor(whole / 60)}m ${String(whole % 60).padStart(2, "0")}s`;
}

const BRAILLE = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
const ASCII = ["-", "\\", "|", "/"];
/** How often the spinner moves. */
export const SPINNER_MS = APP.spinnerMs;

/** The spinner's frame at `now`: braille, or ASCII where the terminal takes no UTF-8. */
export function spinnerFrame(now: number, unicode: boolean): string {
  const frames = unicode ? BRAILLE : ASCII;
  return frames[Math.floor(now / SPINNER_MS) % frames.length] as string;
}

/**
 * A field of a row; `shrink` says how soon it gives way when the row is too long (higher first, 0
 * only as a last resort); `gap` is what joins it to the field before (the separator unless set).
 */
export type Field = { text: string; shrink: number; gap?: string };

/** What separates the fields of a row and of the chrome lines. */
const SEPARATOR = " | ";

/**
 * The fields, each on one line, cut so that joined they fit `width` cells: the most shrinkable field
 * first, down to an ellipsis, then dropped (empty); when only fields that never shrink are left and they
 * still do not fit, the longest is cut. In the order given, one per field, so a caller can join them.
 */
export function fitFields(fields: readonly Field[], width: number): string[] {
  const all = fields.map((field) => ({ ...field, text: field.text.replace(/\s+/g, " ").trim() }));
  const kept = all.filter((field) => field.text !== "");
  const total = () =>
    kept.reduce(
      (sum, field, index) =>
        sum + stringWidth(field.text) + (index ? stringWidth(field.gap ?? SEPARATOR) : 0),
      0,
    );
  while (total() > width) {
    const candidates = kept.filter((field) => field.shrink > 0);
    const field = candidates.length
      ? candidates.reduce((most, next) => (next.shrink > most.shrink ? next : most))
      : kept.reduce((most, next) => (stringWidth(next.text) > stringWidth(most.text) ? next : most));
    const room = stringWidth(field.text) - (total() - width);
    if (room >= 4 || !candidates.length) {
      field.text = cut(field.text, Math.max(1, room));
      // A field that never shrinks is cut at most once; what is left over the window is truncated.
      if (!candidates.length) break;
      field.shrink = 0;
    } else kept.splice(kept.indexOf(field), 1);
  }
  return all.map((field) => (kept.includes(field) ? field.text : ""));
}

/** `text` cut to `cells` cells, the last of them an ellipsis; wide characters are kept whole. */
function cut(text: string, cells: number): string {
  let out = "";
  let used = 0;
  for (const { segment } of new Intl.Segmenter().segment(text)) {
    const width = stringWidth(segment);
    if (used + width > cells - 1) break;
    out += segment;
    used += width;
  }
  return `${out}…`;
}

/**
 * A row's fields fitted beside its right-aligned `meta` (source and time, say) in `width` cells: the fields
 * as fitted, the meta (dropped when the row is too narrow for both), and the spaces between them.
 */
export function besideMeta(
  fields: readonly Field[],
  meta: string,
  width: number,
): { fields: string[]; meta: string; gap: number } {
  const metaWidth = meta ? stringWidth(meta) : 0;
  // Room for the meta only when the fields keep a useful width beside it.
  const keepMeta = meta !== "" && width - metaWidth - 1 >= 12;
  const room = keepMeta ? width - metaWidth - 1 : width;
  const fitted = fitFields(fields, room);
  const used = fitted.reduce(
    (sum, text, index) =>
      text
        ? sum + stringWidth(text) + (index && sum ? stringWidth(fields[index]?.gap ?? SEPARATOR) : 0)
        : sum,
    0,
  );
  return keepMeta
    ? { fields: fitted, meta, gap: Math.max(1, width - used - metaWidth) }
    : { fields: fitted, meta: "", gap: 0 };
}

/** A row's name, with its label after a space when there is one. */
export function named(name: string, label: string): string {
  return label ? `${name} ${label}` : name;
}

/** The fields after a row's name, joined, with the separator before them; empty when there are none. */
export function after(fields: readonly string[]): string {
  const shown = fields.filter(Boolean);
  return shown.length ? `${SEPARATOR}${shown.join(SEPARATOR)}` : "";
}

export { cut, SEPARATOR };

/**
 * A column of a table: at most `cap` cells wide, cut no narrower than `min` before it is dropped; under
 * pressure the column with the highest `shrink` gives way first, and `right` aligns its cells right.
 */
export type Column = { cap: number; min: number; shrink: number; right?: boolean };

/** What separates a table's columns. */
export const TABLE_GAP = "  ";

/**
 * The widths of a table's columns: each as wide as its widest cell (capped), an empty column 0; then, while
 * they do not fit `width` with the gaps between them, the most shrinkable column is cut toward its minimum,
 * and dropped (0) once it is there.
 */
export function tableWidths(
  rows: readonly (readonly string[])[],
  columns: readonly Column[],
  width: number,
): number[] {
  const widths = columns.map((column, index) =>
    Math.min(column.cap, Math.max(0, ...rows.map((row) => stringWidth(row[index] ?? "")))),
  );
  const total = () => {
    const shown = widths.filter((cells) => cells > 0);
    return shown.reduce((sum, cells) => sum + cells, 0) + Math.max(0, shown.length - 1) * TABLE_GAP.length;
  };
  const order = columns
    .map((column, index) => ({ ...column, index }))
    .filter((column) => column.shrink > 0)
    .sort((a, b) => b.shrink - a.shrink);
  for (const column of order) {
    if (total() <= width) break;
    const over = total() - width;
    const cells = widths[column.index] ?? 0;
    if (cells - over >= column.min) widths[column.index] = cells - over;
    else widths[column.index] = 0;
  }
  return widths;
}

/** `text` in a cell `cells` wide: cut with an ellipsis when longer, padded (on the left when `right`). */
export function tableCell(text: string, cells: number, right = false): string {
  const flat = text.replace(/\s+/g, " ").trim();
  const fitted = stringWidth(flat) > cells ? cut(flat, cells) : flat;
  const pad = " ".repeat(Math.max(0, cells - stringWidth(fitted)));
  return right ? `${pad}${fitted}` : `${fitted}${pad}`;
}

/** A table's row: its cells in their widths, dropped columns left out, joined by the gap. */
export function tableRow(
  cells: readonly string[],
  widths: readonly number[],
  columns: readonly Column[],
): string[] {
  return cells.flatMap((text, index) => {
    const cellsWide = widths[index] ?? 0;
    return cellsWide > 0 ? [tableCell(text, cellsWide, columns[index]?.right)] : [];
  });
}

/** Text on one line, printable: runs of whitespace, line breaks included, become one space. */
export function oneLine(text: string): string {
  return printable(text).replace(/\s+/g, " ").trim();
}
