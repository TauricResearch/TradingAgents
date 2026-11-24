// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * A list to choose one option from, as pure state: the keys move the selection (Up/Down, Home/End,
 * PgUp/PgDn), text typed filters the options by label in a list that filters (best match first, see match.ts), Enter chooses, Esc goes back, Ctrl+C cancels. At
 * most PICKER_ROWS options are shown, a window that keeps the selection in view.
 */

/**
 * One option: what is shown, with a dim detail line for the selected one and a note beside its label. A
 * group (a model's family) is named in a dim column before the first of its options in a row.
 */
export type PickerOption = { id: string; label: string; detail?: string; note?: string; group?: string };

import { ranked } from "../match.js";

export type PickerState = {
  options: readonly PickerOption[];
  /** What was typed to filter by. */
  query: string;
  /** The selected option's place among those matching, and the first one shown. */
  selected: number;
  offset: number;
  /** Whether text typed filters the options. */
  filters?: boolean;
  /** Whether Ctrl+D asks to delete the selected option, and the option it is asking about. */
  deletable?: boolean;
  confirming?: string;
};

/** The key fields a picker reads (Ink's key object has these and more). */
export type PickerKey = {
  upArrow?: boolean;
  downArrow?: boolean;
  home?: boolean;
  end?: boolean;
  pageUp?: boolean;
  pageDown?: boolean;
  return?: boolean;
  escape?: boolean;
  backspace?: boolean;
  delete?: boolean;
  ctrl?: boolean;
  meta?: boolean;
  tab?: boolean;
};

type PickerResult =
  | { kind: "state"; state: PickerState }
  | { kind: "chosen"; id: string }
  | { kind: "delete"; id: string }
  | { kind: "back" }
  | { kind: "cancel" };

export const PICKER_ROWS = 8;

/** A picker over `options`, on the one with id `start` when given (else the first). */
export function openPicker(
  options: readonly PickerOption[],
  start?: string,
  { deletable = false, filters = false }: { deletable?: boolean; filters?: boolean } = {},
): PickerState {
  const at = Math.max(
    0,
    options.findIndex((option) => option.id === start),
  );
  return within({
    options,
    query: "",
    selected: at,
    offset: 0,
    ...(deletable ? { deletable } : {}),
    ...(filters ? { filters } : {}),
  });
}

/** The options matching what was typed, best first; equal ones in their order. */
function matchingOptions(state: PickerState): PickerOption[] {
  return ranked(state.options, state.query, (option) => option.label).map(({ item }) => item);
}

/** The options shown now: the window of those matching. */
export function shownOptions(state: PickerState): PickerOption[] {
  return matchingOptions(state).slice(state.offset, state.offset + PICKER_ROWS);
}

/** The selected option, if any matches. */
export function selectedOption(state: PickerState): PickerOption | undefined {
  return matchingOptions(state)[state.selected];
}

export function pickerKey(
  state: PickerState,
  { input, key }: { input: string; key: PickerKey },
): PickerResult {
  if (key.ctrl && input === "c") return { kind: "cancel" };
  // Asking whether to delete: Enter deletes, Esc takes the question back, nothing else acts.
  if (state.confirming !== undefined) {
    if (key.return) return { kind: "delete", id: state.confirming };
    if (key.escape) {
      const { confirming: _, ...rest } = state;
      return { kind: "state", state: rest };
    }
    return { kind: "state", state };
  }
  if (state.deletable && key.ctrl && input === "d") {
    const chosen = selectedOption(state);
    return { kind: "state", state: chosen ? { ...state, confirming: chosen.id } : state };
  }
  if (key.escape) return { kind: "back" };
  const count = matchingOptions(state).length;
  if (key.return) {
    const chosen = selectedOption(state);
    return chosen ? { kind: "chosen", id: chosen.id } : { kind: "state", state };
  }
  const move = (to: number) => ({ kind: "state" as const, state: within({ ...state, selected: to }) });
  if (key.upArrow) return move(state.selected - 1);
  if (key.downArrow) return move(state.selected + 1);
  if (key.home) return move(0);
  if (key.end) return move(count - 1);
  if (key.pageUp) return move(state.selected - PICKER_ROWS);
  if (key.pageDown) return move(state.selected + PICKER_ROWS);
  // A list that does not filter takes no text.
  if (!state.filters) return { kind: "state", state };
  if (key.backspace || key.delete) {
    return { kind: "state", state: within({ ...state, query: state.query.slice(0, -1), selected: 0 }) };
  }
  // Text typed filters, from the first match.
  if (!key.ctrl && !key.meta && !key.tab && input && printableText(input)) {
    return { kind: "state", state: within({ ...state, query: state.query + input, selected: 0, offset: 0 }) };
  }
  return { kind: "state", state };
}

/** `state` with its selection among the matches and its window around the selection. */
function within(state: PickerState): PickerState {
  const count = matchingOptions(state).length;
  const selected = Math.max(0, Math.min(state.selected, count - 1));
  let offset = Math.min(state.offset, selected);
  if (selected >= offset + PICKER_ROWS) offset = selected - PICKER_ROWS + 1;
  offset = Math.max(0, Math.min(offset, Math.max(0, count - PICKER_ROWS)));
  return { ...state, selected, offset };
}

/** Text with no control character in it (a key such as Tab or Delete is not text to filter by). */
function printableText(text: string): boolean {
  return [...text].every((character) => {
    const code = character.codePointAt(0) ?? 0;
    return code >= 0x20 && code !== 0x7f;
  });
}
