// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * A one-line field as pure state, for an address, a model id or a key: the line editor's keys on a single
 * line, Enter gives the value (trimmed), Esc goes back, Ctrl+C cancels. A secret field shows one dot per
 * character and never a character of it; a paste is kept up to its first line break.
 */
import { type EditKey, editLine, insertText, type LineState } from "../line-editor.js";

export type FieldState = { kind: "text" | "secret"; line: LineState };

export type FieldKey = EditKey & { return?: boolean; escape?: boolean };

type FieldResult =
  | { kind: "state"; state: FieldState }
  | { kind: "submit"; value: string }
  | { kind: "back" }
  | { kind: "cancel" };

const DOT = String.fromCodePoint(0x2022);

export function openField(kind: FieldState["kind"], value = ""): FieldState {
  return { kind, line: { value, cursor: value.length } };
}

export function fieldKey(state: FieldState, { input, key }: { input: string; key: FieldKey }): FieldResult {
  if (key.ctrl && input === "c") return { kind: "cancel" };
  if (key.escape) return { kind: "back" };
  if (key.return) return { kind: "submit", value: state.line.value.trim() };
  // A line break typed or read is not part of a one-line value.
  if (input === "\n" || input === "\r") return { kind: "state", state };
  return { kind: "state", state: { ...state, line: editLine(state.line, input, key) } };
}

export function fieldPaste(state: FieldState, text: string): FieldState {
  const [first = ""] = text.split(/\r\n|\r|\n/);
  return { ...state, line: insertText(state.line, first) };
}

/** What the field shows, and where its cursor is in that text. */
export function fieldShown(state: FieldState): { text: string; cursor: number } {
  const { value, cursor } = state.line;
  if (state.kind === "text") return { text: value, cursor };
  return { text: DOT.repeat([...value].length), cursor: [...value.slice(0, cursor)].length };
}

/**
 * A field whose value lives only in this closure: what holds it (an app's ref) sees the methods, and a
 * view is given `shown()`. `take()` hands the value on once and clears it; `clear()` drops it unused.
 */
export function fieldBuffer(kind: FieldState["kind"], value = "") {
  let state = openField(kind, value);
  return {
    key(
      input: string,
      key: FieldKey,
    ): Exclude<FieldResult, { kind: "state" | "submit" }> | { kind: "submit" } | undefined {
      const result = fieldKey(state, { input, key });
      if (result.kind === "state") {
        state = result.state;
        return undefined;
      }
      if (result.kind === "submit") return { kind: "submit" };
      return result;
    },
    paste(text: string) {
      state = fieldPaste(state, text);
    },
    shown: () => fieldShown(state),
    take(): string {
      const taken = state.line.value.trim();
      state = openField(kind);
      return taken;
    },
    clear() {
      state = openField(kind);
    },
  };
}

export type FieldBuffer = ReturnType<typeof fieldBuffer>;
