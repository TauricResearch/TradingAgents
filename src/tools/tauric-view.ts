// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Tauric AI's own research: news digests, a security's thesis, the week's themes and the daily research
 * report. It is a model's writing, not data, and is said to be wherever it is shown.
 */
import { z } from "zod";
import { message } from "../contracts/index.js";
import type { Syntheses, Synthesis } from "../data/capabilities.js";
import { hint } from "./preview.js";
import { referenceTo } from "./references.js";
import { defineTool, ToolRefusalError } from "./tool.js";
import { indented, instrumentLine, oneLine, provenanceOf, roomIn, shownOf, symbol } from "./tool-text.js";

const VIEWS = ["stock_digest", "market_digest", "thesis", "themes", "research"] as const;
const NEEDS_SYMBOL = new Set(["stock_digest", "thesis", "research"]);
/** Said with every result: whose writing it is, and how to weigh it. */
const LABEL =
  "Tauric AI's synthesis, written by a model from the news and data: weigh it as an informed opinion and check its figures against the data tools, not as data.";

const OUT = z.object({
  view: z.enum(VIEWS),
  subject: z.string(),
  for_date: z.string().nullable(),
  generated_at: z.string().nullable(),
  superseded: z.boolean().nullable(),
  stance: z.string().nullable(),
  content: z.unknown(),
});

export function tauricViewTool(syntheses: Syntheses) {
  return defineTool({
    name: "tauric_view",
    description:
      "Tauric AI's own research, written by a model (an opinion to weigh, not data): stock_digest (a security's " +
      "news digest, each point citing its articles), market_digest (the market's), thesis (a security's thesis with " +
      "its drivers and risks), themes (the week's themes across the news), research (the daily research report on a " +
      "covered security, with its stance). Use it as a second opinion beside the data tools.",
    kind: "data",
    parallelSafe: true,
    input: z.object({
      view: z.enum(VIEWS),
      symbol: symbol.optional().describe("For stock_digest, thesis and research"),
    }),
    output: OUT,
    // A digest's points, one row each with its polarity; the summary says whose writing it is.
    preview: [
      hint(
        OUT.extend({
          content: z.object({
            bullets: z.array(z.object({ polarity: z.string().nullable(), text: z.string() })),
          }),
        }),
        { list: "content.bullets", fields: ["polarity", "text"] },
      ),
    ],
    label: ({ view, symbol }) => `${view.replaceAll("_", " ")}${symbol ? ` ${symbol}` : ""}`,
    async run({ view, symbol }, { signal }) {
      if (NEEDS_SYMBOL.has(view) && !symbol) throw new ToolRefusalError(`${view} needs a symbol`);
      const call = { signal };
      const sourced =
        view === "stock_digest"
          ? await syntheses.digest(symbol, call)
          : view === "market_digest"
            ? await syntheses.digest(undefined, call)
            : view === "thesis"
              ? await syntheses.thesis(symbol as string, call)
              : view === "themes"
                ? await syntheses.themes(call)
                : await syntheses.research(symbol as string, call);
      const data: Synthesis = sourced.data;
      // A market-wide view is about the market, whatever symbol came with it.
      const forSymbol = NEEDS_SYMBOL.has(view) ? symbol : undefined;
      const subject = data.instrument ? instrumentLine(data.instrument) : (forSymbol ?? "the market");
      return {
        payload: {
          view,
          subject,
          for_date: data.for_date,
          generated_at: data.generated_at,
          superseded: data.superseded,
          stance: data.stance,
          content: data.content,
        },
        provenance: {
          ...provenanceOf(sourced, {
            subject: forSymbol ?? "market",
            as_of: data.for_date ?? data.generated_at?.slice(0, 10),
          }),
          notes: [...(sourced.notes ?? []), LABEL],
        },
        summary: message(
          "tool.tauricView",
          data.generated_at ? { written: data.generated_at.slice(0, 10) } : {},
        ),
      };
    },
    render(answer, { id, room }) {
      const head = [
        `${answer.view.replaceAll("_", " ")} of ${answer.subject}${answer.for_date ? ` for ${answer.for_date}` : ""}${answer.generated_at ? `, written ${answer.generated_at}` : ""}${answer.superseded ? " (a later version exists)" : ""}${answer.stance ? `; stance on the 12-month return: ${answer.stance}` : ""}`,
      ];
      return [
        ...head,
        ...shownOf(linesOf(answer.content), roomIn(room, head), id ? referenceTo(id, "content") : undefined),
      ];
    },
  });
}

/** Writing as lines: a report's own lines; points with their articles; themes with their members. */
function linesOf(content: unknown): string[] {
  if (typeof content === "string") return content.split(/\r?\n/).filter((line) => line.trim());
  if (content === null || typeof content !== "object") return [];
  const lines: string[] = [];
  for (const [key, value] of Object.entries(content)) {
    if (Array.isArray(value)) {
      lines.push(`${key.replaceAll("_", " ")}:`);
      for (const item of value) lines.push(itemLine(item));
    } else if (value !== null && typeof value === "object") {
      lines.push(`${key.replaceAll("_", " ")}: ${oneLine(JSON.stringify(value))}`);
    } else if (value !== null && value !== undefined) {
      lines.push(
        `${key.replaceAll("_", " ")}: ${typeof value === "string" ? indented(value, "").trim() : value}`,
      );
    }
  }
  return lines;
}

function itemLine(item: unknown): string {
  if (item === null || typeof item !== "object") return `- ${oneLine(String(item))}`;
  const one = item as {
    text?: string;
    name?: string;
    summary?: string;
    size?: number;
    members?: { name: string; mentions: number }[];
    article_ids?: string[];
    polarity?: string;
  };
  if (one.members) {
    const members = one.members
      .slice(0, 8)
      .map((member) => `${member.name} (${member.mentions})`)
      .join(", ");
    return `- ${one.size ?? one.members.length} entities, most mentioned: ${oneLine(members)}`;
  }
  const words = [one.name, one.text ?? one.summary].filter(Boolean).join(": ");
  const articles = one.article_ids?.length ? ` [articles ${one.article_ids.slice(0, 5).join(", ")}]` : "";
  return `- ${one.polarity ? `(${one.polarity}) ` : ""}${oneLine(words || JSON.stringify(item))}${articles}`;
}
