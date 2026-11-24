// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * How typed text matches a name, shared by the command menu and every picker: a name that starts with it
 * first, then one with a word that starts with it, then one holding its characters in order (fuzzy).
 * Case does not count. Each match says which characters matched, so they can be marked.
 */

/** How well a name matched (lower is better) and the indexes of the characters that matched. */
type Match = { rank: number; at: number[] };

/** Ranks: prefix, word start, fuzzy (a fuzzy match's spread is added, so a tighter one comes first). */
const PREFIX = 0;
const WORD = 1;
const FUZZY = 2;

const range = (from: number, length: number) => Array.from({ length }, (_, i) => from + i);

/** Where a word starts in `text`: its first character, and each letter or digit after one that is not. */
function wordStarts(text: string): number[] {
  const starts: number[] = [];
  for (let i = 0; i < text.length; i++) {
    const here = /[\p{L}\p{N}]/u.test(text[i] as string);
    const before = i > 0 && /[\p{L}\p{N}]/u.test(text[i - 1] as string);
    if (here && !before) starts.push(i);
  }
  return starts;
}

/** How `query` matches `text`, or undefined when it does not. An empty query matches everything. */
export function matchText(query: string, text: string): Match | undefined {
  const wanted = query.toLowerCase();
  const name = text.toLowerCase();
  if (!wanted) return { rank: PREFIX, at: [] };
  if (name.startsWith(wanted)) return { rank: PREFIX, at: range(0, wanted.length) };
  const word = wordStarts(name).find((start) => name.startsWith(wanted, start));
  if (word !== undefined) return { rank: WORD, at: range(word, wanted.length) };
  // Each character at its first place after the one before it; the spread between first and last ranks it.
  const at: number[] = [];
  let from = 0;
  for (const character of wanted) {
    const found = name.indexOf(character, from);
    if (found < 0) return undefined;
    at.push(found);
    from = found + 1;
  }
  const spread = (at.at(-1) as number) - (at[0] as number) + 1 - wanted.length;
  return { rank: FUZZY + spread / (name.length + 1), at };
}

/**
 * The items `query` matches, best first; items that match equally keep their order. `text` gives each
 * item's name to match.
 */
export function ranked<T>(
  items: readonly T[],
  query: string,
  text: (item: T) => string,
): { item: T; at: number[] }[] {
  return items
    .map((item, order) => ({ item, order, match: matchText(query, text(item)) }))
    .filter((entry): entry is { item: T; order: number; match: Match } => entry.match !== undefined)
    .sort((a, b) => a.match.rank - b.match.rank || a.order - b.order)
    .map(({ item, match }) => ({ item, at: match.at }));
}
