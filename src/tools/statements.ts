// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** Income statement, balance sheet or cash flow of one company, from its SEC filings. */
import { z } from "zod";
import { message } from "../contracts/index.js";
import type { Statements } from "../data/capabilities.js";
import { type FiscalYear, fiscalLabel } from "./fiscal.js";
import { referenceTo } from "./references.js";
import { defineTool } from "./tool.js";
import {
  amount,
  fieldNotes,
  fitting,
  instrumentLine,
  oneLine,
  provenanceOf,
  roomIn,
  shownOf,
  successionNotes,
  symbol,
} from "./tool-text.js";

const LINE = z.object({
  line: z.string(),
  value: z.number().nullable(),
  unit: z.string().nullable(),
  /** The predecessor that filed this value, in a period drawn from both filers. */
  predecessor_cik: z.string().optional(),
  /** What the value does not carry, and why. */
  notes: z.string().optional(),
});
const PERIOD = z.object({
  start: z.string().nullable(),
  end: z.string(),
  /** Its fiscal name ("fiscal Q3 2026"), when known. */
  label: z.string(),
  /** The filings its values come from. */
  filings: z.array(z.string()),
  /** A quarter whose values all come from an annual report: a fourth quarter is not filed on its own. */
  from_annual_report: z.boolean().default(false),
  lines: z.array(LINE),
});
export const STATEMENT = z.object({
  symbol: z.string(),
  instrument: z.string(),
  statement: z.string(),
  period_type: z.string(),
  succession: z.array(z.string()),
  periods: z.array(PERIOD),
  next_cursor: z.string().nullable(),
  /** How many periods were asked for, for the next page's call. */
  per_page: z.number(),
});

export function statementsTool(statements: Statements) {
  return defineTool({
    name: "statements",
    description:
      "One financial statement of a US-listed company from its SEC filings, newest period first, each value with the " +
      "filing it comes from. Up to 3 periods per call; page with `after`. Every line can be referenced, such as " +
      `${referenceTo("e4", "periods[0].lines")}. For trailing twelve months, add the last four quarters with calc.`,
    kind: "data",
    parallelSafe: true,
    input: z.object({
      symbol,
      statement: z.enum(["income_statement", "balance_sheet", "cash_flow"]),
      period_type: z.enum(["quarterly", "annual"]).default("quarterly"),
      periods: z.number().int().min(1).max(3).default(3).describe("How many periods, newest first"),
      after: z
        .string()
        .min(1)
        .optional()
        .describe("The cursor a previous call returned, for the next periods"),
    }),
    output: STATEMENT,
    label: ({ symbol, statement, period_type, after }) =>
      `${symbol} ${statement.replaceAll("_", " ")}, ${period_type}${after ? ", more" : ""}`,
    async run({ symbol, statement, period_type, periods, after }, { signal }) {
      const sourced = await statements.statement(
        symbol,
        { statement, periodType: period_type, limit: periods, ...(after ? { after } : {}) },
        { signal },
      );
      const answer = sourced.data;
      // Quarters are labelled by their fiscal quarter, from the annual periods around them (one more read,
      // left out if it fails). The three latest fiscal years label the latest quarters; older quarters keep
      // their dates only.
      let years: FiscalYear[] = [];
      if (period_type === "quarterly" && answer.periods.length) {
        const annual = await statements
          .statement(symbol, { statement, periodType: "annual", limit: 3 }, { signal })
          .catch(() => undefined);
        years = (annual?.data.periods ?? []).flatMap((period) => {
          const start = period.lines.find((line) => line.period_start)?.period_start;
          return start ? [{ start, end: period.period_end }] : [];
        });
      }
      const labelOf = (periodEnd: string) =>
        period_type === "annual" ? `fiscal year ending ${periodEnd}` : fiscalLabel(periodEnd, years);
      const shown = answer.periods.map((period) => {
        const filings = new Map<string, string>();
        // A period drawn from both a predecessor's and the current filer's filings says, line by line,
        // which values the predecessor filed.
        const sources = period.lines.flatMap((line) => line.sources ?? []);
        const mixed =
          sources.some((source) => source.predecessor) && sources.some((source) => !source.predecessor);
        const lines = period.lines.map((line) => {
          for (const source of line.sources ?? []) {
            filings.set(
              source.accession,
              `${source.form} ${source.accession} accepted ${source.accepted_at}${source.predecessor ? ` (predecessor CIK ${source.cik})` : ""}`,
            );
          }
          const notes = fieldNotes(line.field_states);
          const predecessor = mixed ? (line.sources ?? []).find((source) => source.predecessor) : undefined;
          return {
            line: oneLine(line.line),
            value: line.value ?? null,
            unit: line.unit ? oneLine(line.unit) : null,
            ...(predecessor ? { predecessor_cik: String(predecessor.cik) } : {}),
            ...(notes ? { notes } : {}),
          };
        });
        return {
          start: period.lines.find((line) => line.period_start)?.period_start ?? null,
          end: period.period_end,
          label: labelOf(period.period_end),
          filings: [...filings.values()],
          from_annual_report:
            period_type === "quarterly" &&
            sources.length > 0 &&
            sources.every((source) => /^10-K/.test(source.form ?? "")),
          lines,
        };
      });
      return {
        payload: {
          symbol,
          instrument: instrumentLine(answer.instrument),
          statement,
          period_type,
          succession: successionNotes(answer.succession),
          periods: shown,
          next_cursor: answer.next_cursor ?? null,
          per_page: periods,
        },
        provenance: provenanceOf(sourced, { subject: symbol, as_of: shown[0]?.end }),
        summary: message("tool.statement", { count: shown.length }),
      };
    },
    render(answer, { id, room }) {
      const head = [
        `${answer.instrument}: ${answer.statement.replaceAll("_", " ")}, ${answer.period_type}, ${answer.periods.length} periods`,
        ...answer.succession,
        ...(answer.periods.length ? [] : ["No periods in this range."]),
      ];
      const more = answer.next_cursor
        ? [`next periods: statements with after=${answer.next_cursor}, periods=${answer.per_page}`]
        : [];
      const blocks = answer.periods.map((period) => {
        const span = period.start ? `${period.start} to ${period.end}` : `at ${period.end}`;
        const title = `${span}${period.label ? `, ${period.label}` : ""} (from ${period.filings.join("; ") || "no filing named"})${period.from_annual_report ? "; this quarter's values come from the annual report (10-K), as a fourth quarter is not filed on its own: say so when you cite them" : ""}`;
        const lines = period.lines.map((line) => {
          const value =
            line.value === null ? "no value" : `${amount(line.value)} ${line.unit ?? ""}`.trimEnd();
          const filer = line.predecessor_cik ? ` [predecessor CIK ${line.predecessor_cik}]` : "";
          return `  ${line.line}: ${value}${filer}${line.notes ? ` (${line.notes})` : ""}`;
        });
        return { title, lines };
      });
      const whole = blocks.map((block) => [block.title, ...block.lines].join("\n"));
      const left = (kept: number) =>
        kept < blocks.length
          ? [
              `(${blocks.length - kept} later periods not shown${id ? `; each is in ${referenceTo(id, "periods")}` : ""})`,
            ]
          : [];
      const kept = fitting(whole, roomIn(room, head, more, left(0)));
      const body = whole.slice(0, kept);
      // A period too large to show whole: its first lines, and where all of them are.
      const cut = blocks[kept];
      if (cut) {
        const rest = id ? referenceTo(id, `periods[${kept}].lines`) : undefined;
        const lines = shownOf(cut.lines, roomIn(room, head, body, [cut.title], left(kept + 1), more), rest);
        // Shown only when some of its lines fit, beside the note.
        if (lines.length > 1) return [...head, ...body, cut.title, ...lines, ...left(kept + 1), ...more];
      }
      return [...head, ...body, ...left(kept), ...more];
    },
  });
}
