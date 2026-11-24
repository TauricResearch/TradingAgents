// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * What a setup flow asks of the screen it runs on: one step at a time, a list to choose from or a field
 * to fill. The setup before the chat and the chat itself each provide it, so a flow runs the same in both.
 */
import type { FieldBuffer } from "./field-state.js";
import type { PickerOption } from "./picker-state.js";
import type { QuestionAnswer } from "./question-state.js";

/** Esc on a step: the flow goes back one step. */
export const BACK = Symbol("back");

/** Ctrl+C on a step (or the app leaving): the flow ends, keeping only what it saved already. */
export class FlowCancelledError extends Error {
  override readonly name = "FlowCancelledError";
}

/** A list; with `deleteConfirm`, Ctrl+D on an option asks that question before it is deleted. */
/**
 * A list to choose from. `filter`: typing filters the options, for a long list (models, sessions); a short
 * fixed choice leaves it off and typing does nothing. `esc`: what Esc does there, as its key row says it:
 * back to the step before (the default), skip a question, or close a menu or a flow at its first step.
 */
export type PickStep = {
  title: string;
  /** A line under the title, when the question needs one. */
  subtitle?: string;
  options: PickerOption[];
  start?: string;
  deleteConfirm?: string;
  filter?: boolean;
  esc?: EscAction;
};
export type EscAction = "back" | "skip" | "close";
export type FieldStep = { title: string; kind: "text" | "secret"; hint?: string; initial?: string };
/**
 * A question the agent asked: `title` the question, `header` its short name ("Ticker"), `position` where it is
 * among several ("1/2"), its choices (numbered) and `own`, the last row's words for typing an answer. `start`
 * and `initial` open it on an answer given before (a choice's place, or what was typed).
 */
export type QuestionStep = {
  title: string;
  header?: string;
  position?: string;
  options: PickerOption[];
  own: string;
  start?: number;
  initial?: string;
  /** What Esc does there, as its key row says it (see PickStep). */
  esc?: EscAction;
};

export type FormUI = {
  /** The chosen option's id, or BACK; rejects with FlowCancelledError. */
  pick(step: PickStep): Promise<string | typeof BACK>;
  /** The field holding what was entered (its value taken by whoever saves it), or BACK. */
  field(step: FieldStep): Promise<FieldBuffer | typeof BACK>;
  /** The choice made or the answer typed, or BACK; rejects with FlowCancelledError. */
  question(step: QuestionStep): Promise<QuestionAnswer | typeof BACK>;
};
