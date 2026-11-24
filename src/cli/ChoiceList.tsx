// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * A list to choose from, as the command menu and every picker draw it: one row per choice, the selected one
 * behind the accent `›` in the selected role (the accent, bold), the characters that matched what was typed in the accent, a dim note
 * beside each label, and a dim column of group names before them where choices are grouped. A choice asked
 * about (for deletion) is drawn in red.
 */
import { Box, Text } from "ink";
import { useRef } from "react";
import { useRoles } from "./theme-context.js";

type Choice = {
  key: string;
  label: string;
  /** The label's characters that matched what was typed. */
  at?: readonly number[];
  note?: string;
  /** The choice's group: named before the first of a run of its choices in view. */
  group?: string;
  danger?: boolean;
};

const PROMPT = "› ";

/**
 * The window of `count` choices to show in `rows` with `selected` in view: from `first` when it already
 * holds it, else moved just enough.
 */
function windowStart(count: number, selected: number, rows: number, first: number): number {
  const fit = Math.max(1, rows);
  let start = Math.min(first, selected);
  if (selected >= start + fit) start = selected - fit + 1;
  return Math.max(0, Math.min(start, count - fit));
}

/**
 * `noteColumn`: where notes start (labels padded to it), else two cells after each label. `groupColumn`:
 * the width of the group names' column, when choices are grouped.
 */
export function ChoiceList({
  choices,
  selected,
  rows,
  noteColumn,
  groupColumn,
}: {
  choices: readonly Choice[];
  selected: number;
  rows: number;
  noteColumn?: number;
  groupColumn?: number;
}) {
  const roles = useRoles();
  // The window stays where it was while the selection is in it, so moving within it does not scroll.
  const start = useRef(0);
  start.current = windowStart(choices.length, Math.max(0, selected), rows, start.current);
  const first = start.current;
  const shown = choices.slice(first, first + Math.max(1, rows));
  return (
    <Box flexDirection="column">
      {shown.map((choice, index) => {
        const isSelected = first + index === selected;
        const at = new Set(choice.at ?? []);
        const label = [...choice.label];
        const pad = noteColumn !== undefined ? Math.max(2, noteColumn - label.length) : 2;
        return (
          <Text key={choice.key} wrap="truncate" {...(choice.danger ? roles.error : {})}>
            {groupColumn ? (
              <Text {...roles.detail}>
                {(index === 0 || shown[index - 1]?.group !== choice.group ? (choice.group ?? "") : "").padEnd(
                  groupColumn,
                )}
              </Text>
            ) : null}
            <Text {...(isSelected && !choice.danger ? roles.accent : {})}>{isSelected ? PROMPT : "  "}</Text>
            <Text {...(isSelected && !choice.danger ? roles.selected : {})}>
              {label.map((character, position) =>
                at.has(position) && !choice.danger ? (
                  // biome-ignore lint/suspicious/noArrayIndexKey: a fixed label's characters
                  <Text key={position} {...roles.accent} bold>
                    {character}
                  </Text>
                ) : (
                  character
                ),
              )}
            </Text>
            {choice.note ? <Text {...roles.detail}>{`${" ".repeat(pad)}${choice.note}`}</Text> : null}
          </Text>
        );
      })}
    </Box>
  );
}
