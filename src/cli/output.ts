// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * What this process writes for a person, made printable: settings problems, errors and titles can carry
 * text from files, the model or a data source.
 */
import { homedir } from "node:os";
import stringWidth from "string-width";
import wrapAnsi from "wrap-ansi";
import { printable } from "../contracts/index.js";

export function toOut(text: string): boolean {
  return process.stdout.write(printable(text));
}

export function toErr(text: string): boolean {
  return process.stderr.write(printable(text));
}

/** Print `text` as a line; the command's exit code, 0. */
export function print(text: string): number {
  toOut(`${text}\n`);
  return 0;
}

/** A path as it is shown: the home folder as `~`. */
export function homePath(path: string, home = homedir()): string {
  return home && (path === home || path.startsWith(`${home}/`)) ? `~${path.slice(home.length)}` : path;
}

/** `text` in rows at most `width` wide: broken between words, and inside a word only one wider than a row. */
function rowsOf(text: string, width: number): string[] {
  return wrapAnsi(text, Math.max(1, width), { hard: false })
    .split("\n")
    .flatMap((row) =>
      stringWidth(row) > width ? wrapAnsi(row, Math.max(1, width), { hard: true }).split("\n") : [row],
    );
}

/**
 * `text` fitted to a window `columns` wide, each line in rows as `rowsOf` breaks it, the rows after a line's
 * first indented by `hang`. Unchanged when the width is not known (not a terminal).
 */
export function fitted(text: string, columns: number | undefined, hang = 0): string {
  if (!columns) return text;
  return text
    .split("\n")
    .flatMap((line) => {
      const [first = "", ...more] = rowsOf(line, columns);
      if (!more.length || !hang) return [first, ...more];
      // The rest of the line again, at the width left beside the indent.
      const rest = line.slice(first.length).trimStart();
      return [first, ...rowsOf(rest, columns - hang).map((row) => `${" ".repeat(hang)}${row}`)];
    })
    .join("\n");
}
