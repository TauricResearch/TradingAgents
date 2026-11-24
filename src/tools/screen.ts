// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** A sector's companies ranked by one statement line, or by its change from the year before. */
import { z } from "zod";
import { type Screen, screenOf } from "../compute/screen.js";
import { type Clock, systemClock } from "../contracts/index.js";
import { CALLS } from "../contracts/limits.js";
import { type CrossSections, SECTORS } from "../data/capabilities.js";
import { referenceTo } from "./references.js";
import { defineTool } from "./tool.js";
import { displayNumber, oneLine, provenanceOf, roomIn, shownOf } from "./tool-text.js";

const OUT = z.object({
  sector: z.enum(SECTORS),
  line: z.string(),
  fiscal_year: z.number(),
  rank_by: z.enum(["value", "change"]),
  order: z.enum(["desc", "asc"]),
  known_at: z.string().nullable(),
  /** Whether every company of the sector was read, and why not. */
  complete: z.boolean(),
  incomplete_because: z.string().nullable(),
  screen: z.custom<Screen>(),
});

export function screenTool(sections: CrossSections, clock: Clock = systemClock) {
  return defineTool({
    name: "screen",
    description:
      "Rank a GICS sector's US-listed companies by one statement line for one fiscal year (Revenue, Net Income " +
      "(Loss), Operating Income (Loss), Total Assets, ... as statements names them), or by its change from the " +
      "year before: the top or bottom companies, how many have no value and why, and values in other units " +
      "apart. The fiscal year is the calendar year a company's fiscal year ends in.",
    kind: "data",
    parallelSafe: true,
    input: z.object({
      sector: z.enum(SECTORS),
      line: z
        .string()
        .trim()
        .min(2)
        .max(80)
        .describe("A statement line as statements names it, such as Revenue"),
      fiscal_year: z.number().int().min(2009).max(2100),
      rank_by: z
        .enum(["value", "change"])
        .default("value")
        .describe("change: against the year before, in percent"),
      order: z.enum(["desc", "asc"]).default("desc"),
      top: z.number().int().min(1).max(25).default(10),
    }),
    output: OUT,
    label: ({ sector, line, fiscal_year, rank_by }) =>
      `${sector.replaceAll("_", " ")} ${line} ${fiscal_year}${rank_by === "change" ? " change" : ""}`,
    async run({ sector, line, fiscal_year, rank_by, order, top }, { signal }) {
      // Both years are read as of one cutoff, set here, so a filing accepted between the reads is on neither or both.
      const query = { sector, line, maxPages: CALLS.screenPages, knownAt: clock().toISOString() };
      const current = await sections.financials({ ...query, fiscalYear: fiscal_year }, { signal });
      // The year before is read as of the same instant, so both years are what was known then.
      const prior =
        rank_by === "change"
          ? await sections.financials({ ...query, fiscalYear: fiscal_year - 1 }, { signal })
          : undefined;
      const screen = screenOf({
        current: current.data.rows,
        ...(prior ? { prior: prior.data.rows } : {}),
        rankBy: rank_by,
        order,
        top,
      });
      const incomplete = [current, prior].flatMap((read) =>
        read && !read.data.complete ? [read.data.incomplete_because ?? "not read to its end"] : [],
      );
      return {
        payload: {
          sector,
          line,
          fiscal_year,
          rank_by,
          order,
          known_at: current.data.known_at,
          complete: incomplete.length === 0,
          incomplete_because: incomplete.length ? incomplete.join("; ") : null,
          screen,
        },
        provenance: provenanceOf(current, { subject: sector, as_of: screen.last_end }),
        summary: `${screen.ranked.length} of ${screen.with_value} with a value${incomplete.length ? ", sector not read whole" : ""}`,
      };
    },
    render(answer, { id, room }) {
      const { screen } = answer;
      const by = answer.rank_by === "change" ? "change from the year before" : "value";
      const head = [
        `${answer.sector.replaceAll("_", " ")}: ${answer.line}, fiscal years ending in ${answer.fiscal_year}, ranked by ${by} (${answer.order === "desc" ? "highest" : "lowest"} first), in ${screen.unit ?? "the main unit"}; as known at ${answer.known_at ?? "now"}`,
        ...(answer.complete
          ? []
          : [`incomplete: ${answer.incomplete_because}; this is not a ranking of the whole sector`]),
        `${screen.read} companies read, ${screen.with_value} with a value, ${screen.in_unit} of them in ${screen.unit ?? "the main unit"}${answer.rank_by === "change" ? `, ${screen.eligible} with a change to rank${screen.not_eligible.length ? ` (not: ${screen.not_eligible.map((n) => `${n.companies} ${n.reason}`).join(", ")})` : ""}` : " and ranked"}${screen.without_value.length ? `; without: ${screen.without_value.map((w) => `${w.companies} ${w.reason.replaceAll("_", " ")}`).join(", ")}` : ""}`,
        `fiscal years end ${screen.first_end ?? "?"} to ${screen.last_end ?? "?"}, most in ${screen.usual_end ?? "?"}${screen.off_calendar ? `; ${screen.off_calendar} far from that, marked` : ""}${screen.derived ? `; ${screen.derived} values derived rather than filed, marked` : ""}`,
      ];
      const rows = screen.ranked.map((r, i) => {
        const change =
          answer.rank_by === "change" || r.prior !== null
            ? r.change_pct !== null
              ? `, ${r.change_pct > 0 ? "+" : ""}${r.change_pct.toFixed(2)}% from ${displayNumber(r.prior as number)}`
              : r.no_change_because
                ? ` (no change: ${r.no_change_because})`
                : ""
            : "";
        const marks = [
          r.off_calendar ? "off the sector's calendar" : "",
          r.derived ? `derived: ${r.derived}` : "",
        ].filter(Boolean);
        return oneLine(
          `${i + 1}. ${r.name}${r.symbol ? ` (${r.symbol})` : ""}: ${displayNumber(r.value)}${change}, year ending ${r.period_end ?? "?"}${marks.length ? ` [${marks.join("; ")}]` : ""}; ${r.accession ?? ""}`,
        );
      });
      const tail = screen.other_units.map(
        (group) =>
          `in ${group.unit}, not ranked with these: ${group.companies} companies, such as ${group.examples.join(", ")}`,
      );
      return [
        ...head,
        ...shownOf(rows, roomIn(room, head, tail), id ? referenceTo(id, "screen.ranked") : undefined),
        ...tail,
      ];
    },
  });
}
