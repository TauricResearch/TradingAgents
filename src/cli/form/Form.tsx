// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * One step of a setup in place of the input and footer: its title (the title role), then a list to choose from
 * (the selected option marked in the accent; a blank row, then the selected option's detail) or a one-line
 * field, or a question the agent asked (its choices numbered, a last row typed into), then a dim row of the
 * keys. It is drawn within the rows the frame grants it; a list shows fewer options when it must.
 */
import { Box, Text, useWindowSize } from "ink";
import stringWidth from "string-width";
import { message } from "../../contracts/index.js";
import { ChoiceList } from "../ChoiceList.js";
import { matchText } from "../match.js";
import { SEPARATOR } from "../rows.js";
import { useRoles } from "../theme-context.js";
import type { EscAction } from "./form-ui.js";
import { PICKER_ROWS, type PickerState, selectedOption, shownOptions } from "./picker-state.js";
import { onOwnRow, type QuestionState } from "./question-state.js";

/**
 * A step as it is drawn: a title, and a list or a field with a hint of its own. A field is given only what
 * it shows (a secret's dots), never its value.
 */
export type FormStep =
  | {
      title: string;
      kind: "pick";
      picker: PickerState;
      subtitle?: string;
      deleteConfirm?: string;
      esc?: EscAction;
    }
  | { title: string; kind: "field"; shown: { text: string; cursor: number }; hint?: string }
  | {
      title: string;
      kind: "question";
      question: QuestionState;
      /** The last row's words, shown until something is typed there. */
      own: string;
      header?: string;
      position?: string;
      esc?: EscAction;
    };

const PROMPT = "› ";

/** Labels wider than this (a session's question) do not push the notes' column further. */
const NOTE_COLUMN_MAX = 40;

/** The rows the step takes at most: title, body, hint (a list: a blank row and its detail before the hint). */
export function formHeight(step: FormStep, columns: number): number {
  if (step.kind === "field") return titleRows(step.title, columns) + 2;
  if (step.kind === "question") return 1 + (step.header ? 1 : 0) + step.question.options.length + 1 + 1 + 1;
  const shown = Math.max(1, Math.min(PICKER_ROWS, shownOptions(step.picker).length));
  const described = step.picker.options.some((option) => option.detail);
  return 1 + (step.subtitle ? 2 : 0) + shown + 1 + (described ? 1 : 0) + 1;
}

/** How many rows a field's title takes, wrapped at words in `columns` less its indent. */
function titleRows(title: string, columns: number): number {
  const width = Math.max(1, columns - 2);
  let rows = 1;
  let used = 0;
  for (const word of title.split(" ")) {
    const size = stringWidth(word);
    if (used && used + 1 + size > width) {
      rows += 1;
      used = size;
    } else used += (used ? 1 : 0) + size;
  }
  return rows;
}

export function Form({ step, rows }: { step: FormStep; rows: number }) {
  const roles = useRoles();
  const { columns } = useWindowSize();
  const separator = SEPARATOR;
  // Title and hints at the transcript's left edge (column 2), where the options' labels start; the title in
  // the title role, as every step's and list's heading is.
  const title = (
    <Text {...roles.title} wrap="truncate">
      {"  "}
      {step.title}
    </Text>
  );
  if (step.kind === "question") return <Question step={step} rows={rows} columns={columns} />;
  if (step.kind === "field") {
    const { text, cursor } = step.shown;
    return (
      <Box flexDirection="column">
        {rows >= 3 ? (
          // A field's title wraps rather than cut, so an address it ends with stays whole.
          <Box paddingLeft={2}>
            <Text {...roles.title}>{step.title}</Text>
          </Box>
        ) : null}
        <Text wrap="truncate">
          <Text {...roles.accent}>{PROMPT}</Text>
          {text.slice(0, cursor)}
          <Text inverse>{text.slice(cursor, cursor + 1) || " "}</Text>
          {text.slice(cursor + 1)}
        </Text>
        {rows >= 2 ? (
          <Text {...roles.detail} wrap="truncate">
            {"  "}
            {step.hint ?? message("form.fieldHint", { separator })}
          </Text>
        ) : null}
      </Box>
    );
  }
  const { picker } = step;
  const chosen = selectedOption(picker);
  // The hint first, then the detail, the blank row above it, the title; the options get the rows left.
  const hint = rows >= 2;
  // The detail row only when the list's options have details: a blank row, never two, above the keys.
  const described = picker.options.some((option) => option.detail);
  const detail = described && rows >= 3;
  const blank = rows >= (described ? 4 : 3);
  const titled = rows >= (described ? 5 : 4);
  // A subtitle under the title, and a blank row before the options.
  const subtitled = titled && step.subtitle !== undefined;
  const room = Math.max(1, rows - [hint, detail, blank, titled].filter(Boolean).length - (subtitled ? 2 : 0));
  const shown = shownOptions(picker);
  const at = chosen ? shown.indexOf(chosen) : -1;
  // Grouped options name their group before the first of each run shown, in a column wide enough for all.
  const groups = picker.options.map((option) => option.group ?? "");
  const groupColumn = groups.some(Boolean) ? Math.max(...groups.map((group) => group.length)) + 2 : 0;
  // Notes (a status such as ready or current) line up in a column after the widest label of all the
  // options, so it holds while typing filters them; a label too long for the column keeps its note close.
  const noteColumn = picker.options.some((option) => option.note)
    ? Math.min(NOTE_COLUMN_MAX, Math.max(...picker.options.map((option) => [...option.label].length))) + 2
    : undefined;
  return (
    <Box flexDirection="column">
      {titled ? title : null}
      {subtitled ? (
        <>
          <Text {...roles.detail} wrap="truncate">
            {"  "}
            {step.subtitle}
          </Text>
          <Text> </Text>
        </>
      ) : null}
      {shown.length === 0 ? (
        <Text {...roles.detail} wrap="truncate">
          {"  "}
          {message("form.noMatch", { query: picker.query })}
        </Text>
      ) : (
        <ChoiceList
          choices={shown.map((option) => ({
            key: option.id,
            label: option.label,
            at: matchText(picker.query, option.label)?.at ?? [],
            ...(option.note ? { note: option.note } : {}),
            ...(option.group ? { group: option.group } : {}),
            ...(picker.confirming === option.id ? { danger: true } : {}),
          }))}
          selected={at}
          rows={room}
          {...(groupColumn ? { groupColumn } : {})}
          {...(noteColumn !== undefined ? { noteColumn } : {})}
        />
      )}
      {blank ? <Text> </Text> : null}
      {detail ? (
        <Text {...roles.detail} wrap="truncate">
          {"  "}
          {chosen?.detail ?? ""}
        </Text>
      ) : null}
      {hint ? (
        picker.confirming !== undefined && step.deleteConfirm ? (
          <Text {...roles.error} wrap="truncate">
            {"  "}
            {step.deleteConfirm}
          </Text>
        ) : (
          <Text {...roles.detail} wrap="truncate">
            {"  "}
            {picker.query
              ? message("form.filtering", { query: picker.query, separator, esc: step.esc ?? "back" })
              : message("form.pickHint", {
                  separator,
                  filter: picker.filters === true,
                  deletes: step.deleteConfirm !== undefined,
                  esc: step.esc ?? "back",
                })}
          </Text>
        )
      ) : null}
    </Box>
  );
}

/**
 * A question the agent asked: the question (title role) with where it is among several at the right, its short
 * name under it, its choices numbered with their notes in a column, the last row to type an answer of one's
 * own (a cursor there when it is selected), a blank row, and the keys.
 */
function Question({
  step,
  rows,
  columns,
}: {
  step: Extract<FormStep, { kind: "question" }>;
  rows: number;
  columns: number;
}) {
  const roles = useRoles();
  const { question } = step;
  const own = onOwnRow(question);
  const count = question.options.length;
  // The hint first, the blank row above it, then the title and its header; the rows go to the choices.
  const hint = rows >= 2;
  const blank = rows >= 3;
  const titled = rows >= 4;
  const headed = Boolean(step.header) && rows >= 5;
  const width = Math.max(10, columns);
  const titleText = `  ${step.title}`;
  const gap = step.position ? Math.max(2, width - stringWidth(titleText) - stringWidth(step.position)) : 0;
  const labelWidth = Math.min(
    40,
    Math.max(0, ...question.options.map((option) => stringWidth(option.label))),
  );
  const number = (index: number) => `${String(index + 1).padStart(String(count + 1).length)}  `;
  const typed = question.own.line.value;
  const cursor = question.own.line.cursor;
  return (
    <Box flexDirection="column">
      {titled ? (
        <Text wrap="truncate">
          <Text {...roles.title}>{titleText}</Text>
          {step.position ? <Text {...roles.detail}>{`${" ".repeat(gap)}${step.position}`}</Text> : null}
        </Text>
      ) : null}
      {headed ? (
        <Text {...roles.detail} wrap="truncate">
          {"  "}
          {step.header}
        </Text>
      ) : null}
      {question.options.map((option, index) => {
        const selected = index === question.selected;
        return (
          <Text key={option.id} wrap="truncate">
            <Text {...(selected ? roles.accent : {})}>{selected ? PROMPT : "  "}</Text>
            <Text {...roles.detail}>{number(index)}</Text>
            <Text {...(selected ? roles.selected : {})}>{option.label}</Text>
            {option.note ? (
              <Text {...roles.detail}>
                {`${" ".repeat(Math.max(2, labelWidth - stringWidth(option.label) + 2))}${option.note}`}
              </Text>
            ) : null}
          </Text>
        );
      })}
      <Text wrap="truncate">
        <Text {...(own ? roles.accent : {})}>{own ? PROMPT : "  "}</Text>
        <Text {...roles.detail}>{number(count)}</Text>
        {own ? (
          <>
            {typed.slice(0, cursor)}
            <Text inverse>{typed.slice(cursor, cursor + 1) || " "}</Text>
            {typed.slice(cursor + 1)}
            {typed ? null : <Text {...roles.detail}>{step.own}</Text>}
          </>
        ) : typed ? (
          <Text>{typed}</Text>
        ) : (
          <Text {...roles.detail}>{step.own}</Text>
        )}
      </Text>
      {blank ? <Text> </Text> : null}
      {hint ? (
        <Text {...roles.detail} wrap="truncate">
          {"  "}
          {message("form.questionHint", { count, separator: SEPARATOR, esc: step.esc ?? "back" })}
        </Text>
      ) : null}
    </Box>
  );
}
