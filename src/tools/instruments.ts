// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** Instruments by name or code: the keys the price tools take, and which tools serve each. */
import { z } from "zod";
import { message } from "../contracts/index.js";
import type { Capability, Instruments } from "../data/capabilities.js";
import { INSTRUMENT_KINDS } from "../data/instrument-key.js";
import { referenceTo } from "./references.js";
import { defineTool } from "./tool.js";
import { oneLine, provenanceOf, roomIn, shownOf } from "./tool-text.js";

/** The tool that reads each capability, for saying what an instrument can be asked. */
const TOOL_OF: Partial<Record<Capability, string>> = {
  quotes: "quote",
  priceHistory: "price_history",
  technicals: "technicals",
  profiles: "profile",
  statements: "statements",
  filings: "filings",
  ownership: "ownership",
  corporateActions: "corporate_actions",
  macroSeries: "macro_series",
};

const MATCH = z.object({
  key: z.string(),
  name: z.string().nullable(),
  type: z.string().nullable(),
  listing_state: z.string().nullable(),
  /** The tools that read it. */
  tools: z.array(z.string()),
});
const OUT = z.object({ query: z.string(), matches: z.array(MATCH) });

export function findInstrumentTool(instruments: Instruments) {
  return defineTool({
    name: "find_instrument",
    description:
      "Find instruments by name or code (gold, crude oil, S&P 500, euro dollar, bitcoin, CPI) and get their keys " +
      "for quote, price_history, technicals and macro_series, with the tools that serve each. A US stock's ticker " +
      "works in those tools as it is.",
    kind: "data",
    parallelSafe: true,
    input: z.object({
      query: z.string().trim().min(1).max(64).describe("A name, symbol or code"),
      kind: z.enum(INSTRUMENT_KINDS).optional().describe("Only instruments of this kind"),
    }),
    output: OUT,
    async run({ query, kind }, { signal }) {
      const sourced = await instruments.search(query, kind, { signal });
      const matches = sourced.data.map((match) => ({
        key: match.key,
        name: match.name ?? null,
        type: match.type ?? null,
        listing_state: match.listing_state ?? null,
        tools: match.serves.flatMap((capability) => TOOL_OF[capability] ?? []),
      }));
      return {
        payload: { query, matches },
        provenance: provenanceOf(sourced),
        summary: message("tool.instruments", { count: matches.length }),
      };
    },
    render({ query, matches }, { id, room }) {
      const head = matches.length
        ? `Instruments for "${oneLine(query)}", best match first:`
        : `No instrument matched "${oneLine(query)}".`;
      const rows = matches.map((match) => {
        const state =
          match.listing_state && match.listing_state !== "listed" ? `, ${match.listing_state}` : "";
        return oneLine(
          `- ${match.key}: ${match.name ?? "unnamed"} (${match.type ?? "type not stated"}${state})${match.tools.length ? `; ${match.tools.join(", ")}` : "; no tool here reads it"}`,
        );
      });
      return [head, ...shownOf(rows, roomIn(room, [head]), id ? referenceTo(id, "matches") : undefined)];
    },
  });
}
