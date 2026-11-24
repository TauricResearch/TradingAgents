// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** One setup step while it is up, whichever screen shows it: what its keys do, and what it draws. */

import type { FormStep } from "./Form.js";
import type { FieldBuffer } from "./field-state.js";
import { BACK, type FieldStep, FlowCancelledError, type PickStep, type QuestionStep } from "./form-ui.js";
import type { PickerKey } from "./picker-state.js";
import { openPicker, type PickerState, pickerKey } from "./picker-state.js";
import {
  openQuestion,
  type QuestionAnswer,
  type QuestionState,
  questionKey,
  questionPaste,
} from "./question-state.js";

/** The step asked: a list, or a field with the buffer that holds what is typed. */
export type Ask =
  | { kind: "pick"; step: PickStep }
  | { kind: "field"; step: FieldStep; buffer: FieldBuffer }
  | { kind: "question"; step: QuestionStep };
/** How a step ended. */
export type Ended =
  | { kind: "chosen"; id: string }
  | { kind: "delete"; id: string }
  | { kind: "submit" }
  | { kind: "answered"; answer: QuestionAnswer }
  | { kind: "back" }
  | { kind: "cancel" };
export type OpenStep = { ask: Ask; picker?: PickerState; question?: QuestionState };

type StepKey = PickerKey & { leftArrow?: boolean; rightArrow?: boolean };

export function openStep(ask: Ask): OpenStep {
  if (ask.kind === "question") {
    return {
      ask,
      question: openQuestion(ask.step.options, {
        ...(ask.step.start !== undefined ? { start: ask.step.start } : {}),
        ...(ask.step.initial ? { initial: ask.step.initial } : {}),
      }),
    };
  }
  return ask.kind === "pick"
    ? {
        ask,
        picker: openPicker(ask.step.options, ask.step.start, {
          deletable: ask.step.deleteConfirm !== undefined,
          filters: ask.step.filter === true,
        }),
      }
    : { ask };
}

/** The step after one key, or how it ended. */
export function stepKey(open: OpenStep, input: string, key: StepKey): { open: OpenStep } | { ended: Ended } {
  const { ask } = open;
  if (ask.kind === "pick" && open.picker) {
    const result = pickerKey(open.picker, { input, key });
    return result.kind === "state" ? { open: { ask, picker: result.state } } : { ended: result };
  }
  if (ask.kind === "field") {
    const ended = ask.buffer.key(input, key);
    return ended ? { ended } : { open };
  }
  if (ask.kind === "question" && open.question) {
    const result = questionKey(open.question, { input, key });
    return result.kind === "state" ? { open: { ask, question: result.state } } : { ended: result };
  }
  return { open };
}

/** A paste into the step: kept by a field, ignored by a list. */
export function stepPaste(open: OpenStep, text: string): OpenStep {
  if (open.ask.kind === "field") open.ask.buffer.paste(text);
  if (open.ask.kind === "question" && open.question)
    return { ...open, question: questionPaste(open.question, text) };
  return open;
}

/** What the step draws: never a field's value, only what it shows. */
export function stepView(open: OpenStep): FormStep {
  const { ask } = open;
  if (ask.kind === "question" && open.question) {
    return {
      title: ask.step.title,
      kind: "question",
      question: open.question,
      own: ask.step.own,
      ...(ask.step.header ? { header: ask.step.header } : {}),
      ...(ask.step.position ? { position: ask.step.position } : {}),
      ...(ask.step.esc ? { esc: ask.step.esc } : {}),
    };
  }
  if (ask.kind === "pick" && open.picker) {
    return {
      title: ask.step.title,
      kind: "pick",
      picker: open.picker,
      ...(ask.step.subtitle ? { subtitle: ask.step.subtitle } : {}),
      ...(ask.step.deleteConfirm ? { deleteConfirm: ask.step.deleteConfirm } : {}),
      ...(ask.step.esc ? { esc: ask.step.esc } : {}),
    };
  }
  return {
    title: ask.step.title,
    kind: "field",
    shown: ask.kind === "field" ? ask.buffer.shown() : { text: "", cursor: 0 },
    ...(ask.kind === "field" && ask.step.hint ? { hint: ask.step.hint } : {}),
  };
}

/** What a question's step gives its flow: the answer, else BACK; a cancel throws FlowCancelledError. */
export function questionResult(ended: Ended): QuestionAnswer | typeof BACK {
  if (ended.kind === "cancel") throw new FlowCancelledError();
  return ended.kind === "answered" ? ended.answer : BACK;
}

/** What a list's step gives its flow: the id chosen, else BACK; a cancel throws FlowCancelledError. */
export function pickResult(ended: Ended): string | typeof BACK {
  if (ended.kind === "cancel") throw new FlowCancelledError();
  return ended.kind === "chosen" ? ended.id : BACK;
}

/**
 * What a field's step gives its flow: its buffer when submitted, else BACK; a cancel throws
 * FlowCancelledError. A field left without submitting is cleared.
 */
export function fieldResult(ended: Ended, buffer: FieldBuffer): FieldBuffer | typeof BACK {
  if (ended.kind === "submit") return buffer;
  buffer.clear();
  if (ended.kind === "cancel") throw new FlowCancelledError();
  return BACK;
}
