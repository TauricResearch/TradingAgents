// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The input: the `›` and the text being typed, between two rules, in the accent while it waits and grey
 * while a question runs. It stays mounted while a question runs, so nothing below the answer moves. In a
 * window too small for the rules it is a bare `›` line.
 */
import { Box, Text } from "ink";
import { message } from "../contracts/index.js";
import { editorRows, type LineState } from "./line-editor.js";
import { useRoles, useTheme } from "./theme-context.js";

const PROMPT = "› ";
/** Smaller than this and the rules would crowd the answer out: a bare prompt instead. */
const BOX_MIN = { columns: 24, rows: 10 };

/** The rows the input takes at this size: the rules count. */
export function composerHeight(line: LineState, columns: number, rows: number): number {
  const boxed = columns >= BOX_MIN.columns && rows >= BOX_MIN.rows;
  return contentRows(line, columns, rows).length + (boxed ? 2 : 0);
}

/** The most rows the typed text may take: eight, or less in a short window. */
function maxRows(rows: number): number {
  return Math.max(1, Math.min(8, Math.floor(rows * 0.3)));
}

function contentRows(line: LineState, columns: number, rows: number) {
  const width = Math.max(1, columns);
  if (line.value === "") {
    const placeholder = message("app.placeholder");
    return [
      { before: PROMPT, cursor: placeholder.slice(0, 1), after: placeholder.slice(1), placeholder: true },
    ];
  }
  return editorRows(PROMPT, line, width, maxRows(rows)).map((row) => ({ ...row, placeholder: false }));
}

/** `busy`: a question is running. */
export function Composer({
  line,
  columns,
  rows,
  busy = false,
}: {
  line: LineState;
  columns: number;
  rows: number;
  busy?: boolean;
}) {
  const { unicode } = useTheme();
  const roles = useRoles();
  const boxed = columns >= BOX_MIN.columns && rows >= BOX_MIN.rows;
  const shown = contentRows(line, columns, rows);
  // The chrome: in the accent while it waits for a question; secondary while one runs or without colour.
  const chrome = !busy && roles.accent.color ? roles.accent : roles.detail;
  const body = (
    <Box flexDirection="column">
      {shown.map((row, index) => {
        // The prompt is drawn in the chrome's colour; it is only ever at the start of the first row.
        const prompt = index === 0 && row.before.startsWith(PROMPT);
        const before = prompt ? row.before.slice(PROMPT.length) : row.before;
        return (
          // biome-ignore lint/suspicious/noArrayIndexKey: each row is a position in the box
          <Text key={index} wrap="truncate">
            {prompt ? <Text {...chrome}>{PROMPT}</Text> : null}
            {before}
            {row.cursor !== undefined ? <Text inverse>{row.cursor}</Text> : null}
            <Text {...(row.placeholder ? roles.detail : {})}>{row.after}</Text>
          </Text>
        );
      })}
    </Box>
  );
  if (!boxed) return body;
  // Cut, never wrapped: a resize can draw this frame once more at the new width before it is redone.
  const rule = (
    <Text {...chrome} wrap="truncate">
      {(unicode ? "─" : "-").repeat(columns)}
    </Text>
  );
  return (
    <Box flexDirection="column">
      {rule}
      {body}
      {rule}
    </Box>
  );
}
