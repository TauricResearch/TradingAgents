// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Citations in an answer: the model writes recorded results' ids in brackets after a claim ([e7], or
 * [e7, e12] for several); people read them numbered [1], [2], ... by first appearance, with a list of
 * sources. One function numbers the text, for every way an answer is shown.
 */
import { z } from "zod";

/** The main agent's tool that runs an agent; a call's label is the agent's name, its result the agent's report. */
export const AGENT_TOOL = "run_agent";

/** A cited source: its number in the answer and the recorded result it stands for. */
export const sourceSchema = z.object({
  n: z.number().int().positive(),
  id: z.string(),
  tool: z.string(),
  /** The call's arguments in a few words ("AAPL, 1y"). */
  label: z.string(),
  subject: z.string().optional(),
  /** Who answered ("Tauric"), or "computed" for a figure derived from other results. */
  source: z.string(),
  asOf: z.string().optional(),
});
export type Source = z.infer<typeof sourceSchema>;

/**
 * A source as one line of plain text: "[1] price_history AAPL, 1y (Tauric, as of 2026-11-19)"; an agent's
 * report by the agent: "[6] Quant Research report".
 */
export function sourceLine(source: Source): string {
  if (source.tool === AGENT_TOOL) return `[${source.n}] ${source.source} report`;
  const about = [source.source, ...(source.asOf ? [`as of ${source.asOf}`] : [])].join(", ");
  return `[${source.n}] ${source.tool}${source.label ? ` ${source.label}` : ""} (${about})`;
}

/** One cited id, or a range of them (e3-e6, with a hyphen or a dash). */
const ITEM = String.raw`e[1-9]\d*(?:\s*[-\u2013\u2014]\s*e[1-9]\d*)?`;
/** A bracket of one or more items, separated by commas or semicolons: [e7], [e7, e12], [e3-e6; e9]. */
const GROUP = new RegExp(String.raw`\[\s*(${ITEM}(?:\s*[,;]\s*${ITEM})*)\s*\]`, "g");

/**
 * A bracket's ids in the order written: each id as given, and a range's ids from one end to the other,
 * the ends as given and those between only where `exists` says there is such a result.
 */
function idsOf(group: string, exists: (id: string) => boolean): string[] {
  return group.split(/[,;]/).flatMap((item) => {
    const [from, to] = item.split(/[-\u2013\u2014]/).map((end) => end.trim());
    if (!from) return [];
    if (!to) return [from];
    const [a, b] = [Number(from.slice(1)), Number(to.slice(1))];
    const step = a <= b ? 1 : -1;
    const ids = [from];
    for (let n = a + step; n !== b; n += step) if (exists(`e${n}`)) ids.push(`e${n}`);
    if (b !== a) ids.push(to);
    return ids;
  });
}

/**
 * The ids an answer cites, each once, in the order they first appear; `exists` says which results
 * there are, for the ids inside a range.
 */
export function citedIds(text: string, exists: (id: string) => boolean): string[] {
  const ids = new Set<string>();
  for (const [, group] of text.matchAll(GROUP)) for (const id of idsOf(group as string, exists)) ids.add(id);
  return [...ids];
}

/**
 * The answer with each cited id written as its source's number ([e7, e12] as [1, 2], a range by each
 * of its sources); an id with no source is left out, and a bracket left empty goes with the space
 * before it.
 */
export function numberCitations(text: string, sources: readonly Pick<Source, "id" | "n">[]): string {
  const numbers = new Map(sources.map((source) => [source.id, source.n]));
  return text.replace(new RegExp(String.raw`\s?${GROUP.source}`, "g"), (whole, group: string) => {
    const known = [
      ...new Set(
        idsOf(group, (id) => numbers.has(id))
          .map((id) => numbers.get(id))
          .filter((n): n is number => n !== undefined),
      ),
    ];
    const space = whole.startsWith("[") ? "" : whole[0];
    return known.length ? `${space}[${known.join(", ")}]` : "";
  });
}
