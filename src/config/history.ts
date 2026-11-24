// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The questions asked in the terminal, newest last, for Up/Down and Ctrl+R: kept in the home directory,
 * owner-only, the last ones only, and never sent anywhere (sync copies sessions, not this file).
 */
import { readPrivate, writePrivate } from "../store/index.js";
import type { Paths } from "./paths.js";

/** How many questions are kept. */
export const HISTORY_KEPT = 100;

/** The kept questions, oldest first; none when the file is missing or cannot be read. */
export async function loadHistory(paths: Paths): Promise<string[]> {
  let text: string | undefined;
  try {
    text = await readPrivate(paths.history);
  } catch {
    return [];
  }
  const entries: string[] = [];
  for (const line of (text ?? "").split("\n")) {
    try {
      const value: unknown = JSON.parse(line);
      if (typeof value === "string" && value.trim()) entries.push(value);
    } catch {
      // A line that is not one entry (a torn write) is skipped.
    }
  }
  return entries.slice(-HISTORY_KEPT);
}

/** The history with `question` added last (moved there if it was asked before), as kept. */
export function withQuestion(entries: readonly string[], question: string): string[] {
  return [...entries.filter((entry) => entry !== question), question].slice(-HISTORY_KEPT);
}

/** Keep `entries` as the history. */
export async function saveHistory(entries: readonly string[], paths: Paths): Promise<void> {
  const text = entries.map((entry) => JSON.stringify(entry)).join("\n");
  await writePrivate(paths.history, text ? `${text}\n` : "");
}

/**
 * Add `question` to the history as it is on disk now, so questions another session kept meanwhile stay.
 * Returns the history as kept.
 */
export async function addToHistory(question: string, paths: Paths): Promise<string[]> {
  const entries = withQuestion(await loadHistory(paths), question);
  await saveHistory(entries, paths);
  return entries;
}
