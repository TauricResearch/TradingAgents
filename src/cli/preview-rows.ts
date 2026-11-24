// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * A result's preview as the transcript shows it: its cells in columns (two spaces apart, numbers set
 * right), each row cut to the width, and how many rows more there are on the last row shown.
 */
import stringWidth from "string-width";
import type { Preview } from "../contracts/index.js";
import { printable } from "../contracts/index.js";

/** Narrower than this, a call's preview is one row. */
export const PREVIEW_NARROW = 60;

/** The rows a call of its own shows of its preview at most. */
export const PREVIEW_ROWS = 3;

/** A row of a preview: its text, and "+N more" on the last one shown when rows are left out. */
type PreviewLine = { text: string; more?: string };

/**
 * `preview` in at most `rows` rows (3 for a call of its own, 1 when narrow or in a group), each within
 * `width` cells with room kept for "+N more".
 */
export function previewLines(
  preview: Preview,
  { width, rows }: { width: number; rows: number },
): PreviewLine[] {
  const shown = preview.rows.slice(0, Math.max(1, rows));
  const left = (preview.more ?? 0) + preview.rows.length - shown.length;
  const texts = alignRows(shown, new Set(preview.right ?? []));
  return texts.map((text, index) => {
    const more = index === texts.length - 1 && left > 0 ? `+${left} more` : undefined;
    const room = more ? width - stringWidth(more) - 2 : width;
    const fitted = cut(text, room);
    return more ? { text: fitted, more } : { text: fitted };
  });
}

/**
 * Rows of cells as lines: each column as wide as its widest cell, two spaces between, the columns in
 * `right` set right (a labelled number, "vol 4.1%", keeps its label at the left and its number at the right).
 */
export function alignRows(rows: readonly (readonly string[])[], right: ReadonlySet<number>): string[] {
  const cells = rows.map((row) => row.map((cell) => printable(cell).replace(/\s+/g, " ").trim()));
  const count = Math.max(0, ...cells.map((row) => row.length));
  const widths = Array.from({ length: count }, (_, column) =>
    Math.max(0, ...cells.map((row) => stringWidth(row[column] ?? ""))),
  );
  // A labelled column's labels, as wide as the widest, so its numbers line up too.
  const labels = widths.map((_, column) =>
    Math.max(0, ...cells.map((row) => stringWidth(labelOf(row[column] ?? "")))),
  );
  return cells.map((row) =>
    row
      .map((cell, column) => {
        const width = widths[column] ?? 0;
        if (!right.has(column)) return cell + " ".repeat(Math.max(0, width - stringWidth(cell)));
        const label = labelOf(cell);
        const value = label ? cell.slice(label.length + 1) : cell;
        const head = label ? `${label} `.padEnd((labels[column] ?? 0) + 1) : "";
        const inner = width - (labels[column] ? (labels[column] ?? 0) + 1 : 0);
        return head + " ".repeat(Math.max(0, inner - stringWidth(value))) + value;
      })
      .join("  ")
      .trimEnd(),
  );
}

/** The words before a cell's value ("max drawdown" of "max drawdown -14.3%"), or "" for a bare value. */
function labelOf(cell: string): string {
  const at = cell.lastIndexOf(" ");
  return at > 0 ? cell.slice(0, at) : "";
}

/** `text` within `width` cells, cut between characters as people see them, "…" where it was cut. */
function cut(text: string, width: number): string {
  if (stringWidth(text) <= width) return text;
  let out = "";
  for (const { segment } of new Intl.Segmenter().segment(text)) {
    if (stringWidth(out + segment) > Math.max(0, width - 1)) break;
    out += segment;
  }
  return `${out.trimEnd()}…`;
}
