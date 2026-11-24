// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The command menu under the input while a `/name` is being typed: the matching commands, best first, the
 * selected one marked in the accent and the typed characters marked in its name. It takes the footer's
 * place, so the frame keeps its height budget.
 */
import { Text } from "ink";
import { message } from "../contracts/index.js";
import { ChoiceList } from "./ChoiceList.js";
import type { Command } from "./commands.js";
import { matchText } from "./match.js";
import { useRoles } from "./theme-context.js";

/** Most commands listed at once. */
const MENU_ROWS = 8;

/** The rows the menu takes for `matches`: one even when nothing matches (it says so). */
export function menuHeight(matches: readonly Command[]): number {
  return Math.max(1, Math.min(MENU_ROWS, matches.length));
}

/** `typed`: the input, its slash included. */
export function CommandMenu({
  matches,
  selected,
  typed,
  rows = MENU_ROWS,
}: {
  matches: readonly Command[];
  selected: number;
  typed: string;
  /** The rows the frame has for it. */
  rows?: number;
}) {
  const roles = useRoles();
  if (!matches.length) {
    return (
      <Text {...roles.detail} wrap="truncate">
        {"  "}
        {message("app.noCommand")}
      </Text>
    );
  }
  const fit = Math.max(1, Math.min(rows, MENU_ROWS));
  const query = typed.replace(/^\//, "");
  const width = Math.max(...matches.map((command) => command.name.length)) + 3;
  return (
    <ChoiceList
      choices={matches.map((command) => ({
        key: command.name,
        label: `/${command.name}`,
        // After the slash.
        at: (matchText(query, command.name)?.at ?? []).map((index) => index + 1),
        note: command.summary,
      }))}
      selected={selected}
      rows={fit}
      noteColumn={width}
    />
  );
}
