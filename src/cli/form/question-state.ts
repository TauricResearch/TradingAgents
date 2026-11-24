// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * A question the agent asked, as pure state: its choices, numbered, then a last row to type an answer of
 * one's own. Up/Down move; a digit chooses that choice at once; Enter chooses the row the cursor is on.
 * On the last row, typing writes there directly (no Enter first) and Enter sends what was typed; on the
 * other rows, typing does nothing: a question's list is short and fixed, so nothing is filtered.
 */
import { type FieldKey, type FieldState, fieldKey, fieldPaste, openField } from "./field-state.js";
import type { PickerOption } from "./picker-state.js";

export type QuestionState = {
  options: readonly PickerOption[];
  /** The row the cursor is on: a choice's place, or `options.length` for the last row. */
  selected: number;
  /** What is typed on the last row, kept while the cursor moves away and back. */
  own: FieldState;
};

export type QuestionAnswer = { choice: number } | { own: string };

type QuestionResult =
  | { kind: "state"; state: QuestionState }
  | { kind: "answered"; answer: QuestionAnswer }
  | { kind: "back" }
  | { kind: "cancel" };

type QuestionKey = FieldKey & { upArrow?: boolean; downArrow?: boolean; home?: boolean; end?: boolean };

/** A question on its choice `start` (else the first), or on the last row with `initial` typed there. */
export function openQuestion(
  options: readonly PickerOption[],
  { start, initial }: { start?: number; initial?: string } = {},
): QuestionState {
  const selected = initial ? options.length : Math.max(0, Math.min(start ?? 0, options.length));
  return { options, selected, own: openField("text", initial ?? "") };
}

/** Whether the cursor is on the last row, where an answer of one's own is typed. */
export function onOwnRow(state: QuestionState): boolean {
  return state.selected === state.options.length;
}

export function questionKey(
  state: QuestionState,
  { input, key }: { input: string; key: QuestionKey },
): QuestionResult {
  if (key.ctrl && input === "c") return { kind: "cancel" };
  if (key.escape) return { kind: "back" };
  const last = state.options.length;
  const move = (to: number): QuestionResult => ({
    kind: "state",
    state: { ...state, selected: Math.max(0, Math.min(to, last)) },
  });
  if (key.upArrow) return move(state.selected - 1);
  if (key.downArrow) return move(state.selected + 1);
  if (onOwnRow(state)) {
    if (key.return) {
      const own = state.own.line.value.trim();
      return own ? { kind: "answered", answer: { own } } : { kind: "state", state };
    }
    const result = fieldKey(state.own, { input, key });
    return result.kind === "state"
      ? { kind: "state", state: { ...state, own: result.state } }
      : { kind: "state", state };
  }
  if (key.home) return move(0);
  if (key.end) return move(last);
  if (key.return) return { kind: "answered", answer: { choice: state.selected } };
  // A digit chooses its choice at once.
  if (!key.ctrl && !key.meta && /^[1-9]$/.test(input) && Number(input) <= last) {
    return { kind: "answered", answer: { choice: Number(input) - 1 } };
  }
  return { kind: "state", state };
}

/** A paste goes to the last row when the cursor is there; elsewhere it is not an answer. */
export function questionPaste(state: QuestionState, text: string): QuestionState {
  return onOwnRow(state) ? { ...state, own: fieldPaste(state.own, text) } : state;
}
