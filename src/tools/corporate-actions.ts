// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** A listing's splits and cash distributions, as reported. */
import { z } from "zod";
import { message } from "../contracts/index.js";
import type { CorporateActions } from "../data/capabilities.js";
import { referenceTo } from "./references.js";
import { defineTool } from "./tool.js";
import { fieldNotes, instrumentLine, provenanceOf, roomIn, shownOf, symbol } from "./tool-text.js";

const ACTION = z.object({
  ex_date: z.string(),
  action_type: z.string(),
  value: z.number().nullable(),
  unit: z.string().nullable(),
  cash_basis: z.string().nullable(),
  revised: z.boolean(),
  notes: z.string().optional(),
});
const OUT = z.object({
  symbol: z.string(),
  instrument: z.string(),
  /** Newest first. */
  actions: z.array(ACTION),
  through: z.string().nullable(),
  stale: z.boolean().nullable(),
});

export function corporateActionsTool(actions: CorporateActions) {
  return defineTool({
    name: "corporate_actions",
    description:
      "A US-listed security's reported splits (with their ratio) and cash distributions (amount per share, ex-date), " +
      "newest first: for dividend history, yield over a period, and total return. An empty list does not establish " +
      "that there were none.",
    kind: "data",
    parallelSafe: true,
    input: z.object({ symbol }),
    output: OUT,
    async run({ symbol }, { signal }) {
      const sourced = await actions.list(symbol, { signal });
      const answer = sourced.data;
      const listed = [...answer.actions]
        .sort((a, b) => b.ex_date.localeCompare(a.ex_date))
        .map((action) => {
          const notes = fieldNotes(action.field_states);
          return {
            ex_date: action.ex_date,
            action_type: action.action_type,
            value: action.value,
            unit: action.unit,
            cash_basis: action.cash_basis,
            revised: action.revised,
            ...(notes ? { notes } : {}),
          };
        });
      return {
        payload: {
          symbol,
          instrument: instrumentLine(answer.instrument),
          actions: listed,
          through: answer.through,
          stale: answer.stale,
        },
        provenance: provenanceOf(sourced, { subject: symbol, as_of: answer.through }),
        summary: message("tool.corporateActions", { count: listed.length }),
      };
    },
    render(answer, { id, room }) {
      const head = [
        `${answer.instrument}: splits and cash distributions, newest first${answer.through ? `, through ${answer.through}` : ""}${answer.stale ? " (the source calls it stale)" : ""}`,
        ...(answer.actions.length ? [] : ["None reported. That does not establish that there were none."]),
      ];
      const rows = answer.actions.map((action) => {
        const what =
          action.action_type === "split"
            ? `split ${action.value === null ? "ratio not given" : `${action.value} shares for each 1`}`
            : `${action.action_type} ${action.value === null ? "amount not given" : `${action.value} ${action.unit ?? ""}`.trimEnd()}${action.cash_basis ? ` (${action.cash_basis.replaceAll("_", " ")})` : ""}`;
        return `${action.ex_date}: ${what}${action.revised ? "; revised since first reported" : ""}${action.notes ? `; ${action.notes}` : ""}`;
      });
      return [...head, ...shownOf(rows, roomIn(room, head), id ? referenceTo(id, "actions") : undefined)];
    },
  });
}
