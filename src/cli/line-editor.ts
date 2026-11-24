// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The input as pure state: what a key does to the text and its cursor, and which rows of it to draw so
 * the cursor is always in view. The text may hold line breaks (a paste, or a newline key); Home, End,
 * Ctrl+A/E/U/K act on the cursor's line. The app keeps this state in a ref, so keys that arrive faster
 * than the screen redraws each see the effect of the one before.
 */
import wrapAnsi from "wrap-ansi";
import { printable } from "../contracts/index.js";

export type LineState = { value: string; cursor: number };

/** The key fields this editor reads (Ink's key object has these and more). */
export type EditKey = {
  leftArrow?: boolean;
  rightArrow?: boolean;
  home?: boolean;
  end?: boolean;
  backspace?: boolean;
  delete?: boolean;
  ctrl?: boolean;
  meta?: boolean;
};

export const emptyLine: LineState = { value: "", cursor: 0 };

/**
 * One read of plain input as the keys it holds. A terminal can deliver typed text and its Enter in one
 * read (a fast typist, a slow link, tmux send-keys), and the input parser passes that on as one event: so
 * each CR (or CR LF) becomes an Enter of its own, each bare LF the Ctrl+J it is, and each other control
 * byte (a legacy Ctrl+R, say) its Ctrl key. Keys the parser named (Return, a modified key) and bracketed
 * pastes (their own channel) are left as they are.
 */
export function burstKeys<K extends { return?: boolean; ctrl?: boolean; meta?: boolean }>(
  input: string,
  key: K,
): [string, K][] {
  // Control bytes are below 0x20; a tab stays text.
  const control = (char: string) => char < " " && char !== "\t";
  if (input.length < 2 || key.return || key.ctrl || key.meta || ![...input].some(control))
    return [[input, key]];
  const keys: [string, K][] = [];
  let text = "";
  const flush = () => {
    if (text) keys.push([text, key]);
    text = "";
  };
  for (let index = 0; index < input.length; index++) {
    const char = input[index] as string;
    if (!control(char)) {
      text += char;
      continue;
    }
    flush();
    if (char === "\r") {
      keys.push(["\r", { ...key, return: true }]);
      if (input[index + 1] === "\n") index++;
    } else if (char === "\n") keys.push(["\n", key]);
    // Ctrl+A is 0x01, through Ctrl+Z at 0x1a; anything else is not a key here.
    else if (char >= "\u0001" && char <= "\u001a") {
      keys.push([String.fromCharCode((char.codePointAt(0) ?? 0) + 96), { ...key, ctrl: true }]);
    }
  }
  flush();
  return keys;
}

/** The line after one key; Enter and the app's own control keys are the caller's to handle first. */
export function editLine(state: LineState, input: string, key: EditKey): LineState {
  const { value, cursor } = state;
  if (key.leftArrow) return { value, cursor: cursor - before(value, cursor) };
  if (key.rightArrow) return { value, cursor: cursor + after(value, cursor) };
  const start = lineStart(value, cursor);
  const endAt = value.indexOf("\n", cursor);
  const end = endAt < 0 ? value.length : endAt;
  if (key.home || (key.ctrl && input === "a")) return { value, cursor: start };
  if (key.end || (key.ctrl && input === "e")) return { value, cursor: end };
  if (key.ctrl && input === "u") return { value: value.slice(0, start) + value.slice(cursor), cursor: start };
  if (key.ctrl && input === "k") return { value: value.slice(0, cursor) + value.slice(end), cursor };
  if (key.ctrl && input === "w") {
    // The word before the cursor, and the spaces after it, within the line.
    const before = value.slice(start, cursor).replace(/\S+\s*$/, "");
    return { value: value.slice(0, start) + before + value.slice(cursor), cursor: start + before.length };
  }
  // Terminals send DEL for the backspace key, which Ink reports as `delete`: both erase to the left.
  if (key.backspace || key.delete) {
    if (cursor === 0) return state;
    const start = cursor - before(value, cursor);
    return { value: value.slice(0, start) + value.slice(cursor), cursor: start };
  }
  if (key.ctrl || key.meta) return state;
  // Typed or pasted text: line breaks become spaces, tabs and anything else not printable are dropped.
  const text = printable(input.replace(/[\r\n]+/g, " ")).replaceAll("\t", "");
  if (!text) return state;
  return { value: value.slice(0, cursor) + text + value.slice(cursor), cursor: cursor + text.length };
}

/**
 * `text` put in at the cursor as it was written: line breaks kept (CR LF and CR become LF), tabs as two
 * spaces, anything else not printable dropped. For pastes and the newline keys.
 */
export function insertText(state: LineState, text: string): LineState {
  const clean = text
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .map((line) => printable(line.replaceAll("\t", "  ")))
    .join("\n");
  if (!clean) return state;
  const { value, cursor } = state;
  return { value: value.slice(0, cursor) + clean + value.slice(cursor), cursor: cursor + clean.length };
}

/**
 * The cursor one line up or down, at the same column where the line is long enough; undefined when it
 * is already on the first or last line (the caller's history takes the key).
 */
export function moveLine(state: LineState, direction: "up" | "down"): LineState | undefined {
  const { value, cursor } = state;
  const start = lineStart(value, cursor);
  const column = cursor - start;
  let target: number;
  if (direction === "up") {
    if (start === 0) return undefined;
    const above = lineStart(value, start - 1);
    target = Math.min(above + column, start - 1);
  } else {
    const endAt = value.indexOf("\n", cursor);
    if (endAt < 0) return undefined;
    const nextEnd = value.indexOf("\n", endAt + 1);
    target = Math.min(endAt + 1 + column, nextEnd < 0 ? value.length : nextEnd);
  }
  // Never inside a character outside the basic plane: back to its start.
  return { value, cursor: target - (isLowSurrogate(value, target) ? 1 : 0) };
}

/** Where the line holding `cursor` starts. */
function lineStart(value: string, cursor: number): number {
  return cursor === 0 ? 0 : value.lastIndexOf("\n", cursor - 1) + 1;
}

/** Whether `index` falls between the two halves of a surrogate pair. */
function isLowSurrogate(value: string, index: number): boolean {
  const unit = value.charCodeAt(index);
  const before = value.charCodeAt(index - 1);
  return unit >= 0xdc00 && unit <= 0xdfff && before >= 0xd800 && before <= 0xdbff;
}

// The cursor is an index into the string's UTF-16 units that always sits between whole code points.

/** Units in the code point before `cursor`: 0 at the start. */
function before(value: string, cursor: number): number {
  if (cursor === 0) return 0;
  const low = value.charCodeAt(cursor - 1);
  const high = value.charCodeAt(cursor - 2);
  return low >= 0xdc00 && low <= 0xdfff && high >= 0xd800 && high <= 0xdbff ? 2 : 1;
}

/** Units in the code point at `cursor`: 0 at the end. */
function after(value: string, cursor: number): number {
  const point = value.codePointAt(cursor);
  return point === undefined ? 0 : point > 0xffff ? 2 : 1;
}

type EditorRow = { before: string; cursor?: string; after: string };

/**
 * The rows to draw for `prompt` + the text, each line wrapped at `columns` (lines after the first indented
 * under the prompt), at most `maxRows` of them, always including the cursor's row (the last rows when the
 * cursor is at the end).
 */
export function editorRows(prompt: string, state: LineState, columns: number, maxRows: number): EditorRow[] {
  const width = Math.max(1, columns);
  const indent = " ".repeat(prompt.length);
  const rows: string[] = [];
  let cursorRow = 0;
  let cursorColumn = 0;
  let offset = 0;
  // Every row of the text sits under the prompt: the prompt on the first, its width of spaces on the rest.
  const room = Math.max(1, width - prompt.length);
  for (const [index, line] of state.value.split("\n").entries()) {
    const onLine = state.cursor >= offset && state.cursor <= offset + line.length;
    // A trailing space gives the cursor a cell when it sits after the line's last character.
    const text = `${line}${onLine && state.cursor === offset + line.length ? " " : ""}`;
    const wrapped = wrapAnsi(text, room, { hard: true, wordWrap: false, trim: false }).split("\n");
    if (onLine) {
      let position = state.cursor - offset;
      cursorRow = rows.length + wrapped.length - 1;
      cursorColumn = prompt.length;
      for (const [at, row] of wrapped.entries()) {
        if (position < row.length) {
          cursorRow = rows.length + at;
          cursorColumn = prompt.length + position;
          break;
        }
        position -= row.length;
      }
    }
    for (const [at, row] of wrapped.entries())
      rows.push(`${index === 0 && at === 0 ? prompt : indent}${row}`);
    offset += line.length + 1;
  }
  const first = Math.max(0, cursorRow - Math.max(1, maxRows) + 1);
  return rows.slice(first, first + Math.max(1, maxRows)).map((row, index) => {
    if (first + index !== cursorRow) return { before: row, after: "" };
    const end = cursorColumn + Math.max(1, after(row, cursorColumn));
    return {
      before: row.slice(0, cursorColumn),
      cursor: row.slice(cursorColumn, end) || " ",
      after: row.slice(end),
    };
  });
}
