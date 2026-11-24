// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * A list a command shows (/help, /status, /agents, /skills, /changelog): sections, each a heading with where its
 * items come from beside it, then rows of a name and what it is, aligned, or items said in a sentence each. Drawn with the theme's roles (the heading in
 * the title role, names in the name role, descriptions dim, a reason an item is unavailable as a warning),
 * and written to the transcript's Markdown as plain lines.
 */

/** One row: its name, what it is, and a short reason it cannot be used here. */
type ListRow = { name: string; text?: string; warn?: string };

/**
 * A section: a heading (none for a list of one section that needs no name), `aside` beside it (where its items
 * come from), its rows, its `items` (a sentence each, as a bullet), and a dim `note` under them. `labels`: the
 * names are labels (dim) and the text is the value (as /status shows them), not names (in the name role) with
 * dim descriptions.
 */
export type ListSection = {
  heading?: string;
  aside?: string;
  rows?: ListRow[];
  items?: string[];
  note?: string;
  labels?: true;
};

/** A list: its sections; `oneLine`: each row's text cut to one row with an ellipsis (the full text elsewhere). */
export type List = { sections: ListSection[]; oneLine?: true };

/** Names wider than this do not push the text column further. */
const LIST_NAME_COLUMN_MAX = 24;

/** The column the rows' text starts at, the same in every section: after the widest name, capped. */
export function listColumn(list: List, width: (text: string) => number): number {
  const widest = Math.max(
    0,
    ...list.sections.flatMap((section) => (section.rows ?? []).map((row) => width(row.name))),
  );
  return Math.min(widest, LIST_NAME_COLUMN_MAX) + 2;
}

/** The list as Markdown lines: a heading in bold with its aside, then a line per row and per item. */
export function listMarkdown(list: List): string[] {
  return list.sections.flatMap((section, index) => [
    ...(index > 0 ? [""] : []),
    ...(section.heading ? [`**${section.heading}**${section.aside ? ` ${section.aside}` : ""}`, ""] : []),
    ...(section.rows ?? []).map(
      (row) => `- ${row.name}${row.text ? `: ${row.text}` : ""}${row.warn ? ` (${row.warn})` : ""}`,
    ),
    ...(section.items ?? []).map((item) => `- ${item}`),
    ...(section.note ? ["", section.note] : []),
  ]);
}
