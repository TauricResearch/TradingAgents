// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** SEC filings of one company, and the text of a filing's sections. */

import { z } from "zod";
import { message } from "../contracts/index.js";
import { CALLS } from "../contracts/limits.js";
import { FILING_SECTIONS, type Filings } from "../data/capabilities.js";
import { referenceTo } from "./references.js";
import { defineTool } from "./tool.js";
import {
  fieldNotes,
  indented,
  instrumentLine,
  provenanceOf,
  roomIn,
  shownOf,
  successionNotes,
  symbol,
} from "./tool-text.js";

const form = z
  .string()
  .trim()
  .toUpperCase()
  .regex(/^[A-Z0-9][A-Z0-9 /-]{0,11}$/, "an SEC form type such as 10-K");

const FILING = z.object({
  form: z.string(),
  accession: z.string(),
  filed: z.string().nullable(),
  accepted_at: z.string(),
  report_date: z.string().nullable(),
  /** The predecessor's CIK, for a filing a predecessor made. */
  predecessor_cik: z.string().nullable(),
  /** The sections filing_section reads ("by reference" when the filing points elsewhere for the text). */
  sections: z.array(z.string()),
  url: z.string().nullable(),
});
const LIST = z.object({
  symbol: z.string(),
  instrument: z.string(),
  succession: z.array(z.string()),
  filings: z.array(FILING),
  next_cursor: z.string().nullable(),
});

export function filingsTool(filings: Filings) {
  return defineTool({
    name: "filings",
    description:
      "SEC filings of one US-listed company, newest first: form, dates, accession and which sections can be read " +
      "with filing_section. Filter by form types; page with `after`.",
    kind: "data",
    parallelSafe: true,
    input: z.object({
      symbol,
      forms: z.array(form).max(8).optional().describe("Form types to list, such as 10-K, 10-Q, 8-K"),
      limit: z.number().int().min(1).max(20).default(10),
      after: z
        .string()
        .min(1)
        .optional()
        .describe("The cursor a previous call returned, with the same filters"),
    }),
    output: LIST,
    async run({ symbol, forms, limit, after }, { signal }) {
      const sourced = await filings.list(
        symbol,
        { limit, ...(forms?.length ? { forms } : {}), ...(after ? { after } : {}) },
        { signal },
      );
      const answer = sourced.data;
      const listed = answer.data.map((filing) => ({
        form: filing.form,
        accession: filing.accession,
        filed: filing.filed ?? null,
        accepted_at: filing.accepted_at,
        report_date: filing.report_date ?? null,
        predecessor_cik: filing.predecessor ? filing.cik : null,
        // A section without a state has no text served.
        sections: (filing.sections ?? [])
          .filter((section) => section.state)
          .map((section) =>
            section.state === "by_reference" ? `${section.section} (by reference)` : section.section,
          ),
        url: filing.url ?? null,
      }));
      return {
        payload: {
          symbol,
          instrument: instrumentLine(answer.instrument),
          succession: successionNotes(answer.succession),
          filings: listed,
          next_cursor: answer.next_cursor ?? null,
        },
        provenance: provenanceOf(sourced, { subject: symbol }),
        summary: message("tool.filings", { count: listed.length }),
      };
    },
    render(answer, { id, room }) {
      const head = [`${answer.instrument}: filings`, ...answer.succession];
      if (!answer.filings.length) head.push("No filings match.");
      const rows = answer.filings.map((filing) => {
        // A predecessor's filing is listed under the company, but its sections are not read through the
        // company's symbol.
        const readable = filing.predecessor_cik
          ? "sections not readable here (a predecessor's filing; its text is at the link)"
          : filing.sections.length
            ? `sections: ${filing.sections.join(", ")}`
            : "no sections to read";
        return [
          `${filing.form} ${filing.accession} filed ${filing.filed} (accepted ${filing.accepted_at})${filing.report_date ? `, period ${filing.report_date}` : ""}${filing.predecessor_cik ? `, by predecessor CIK ${filing.predecessor_cik}` : ""}`,
          `  ${readable}; ${filing.url}`,
        ].join("\n");
      });
      const next = answer.next_cursor
        ? [`more filings: filings with after=${answer.next_cursor} and the same filters`]
        : [];
      return [
        ...head,
        ...shownOf(rows, roomIn(room, head, next), id ? referenceTo(id, "filings") : undefined),
        ...next,
      ];
    },
  });
}

/** Characters of section text one call shows. */
const PART = CALLS.textChars - CALLS.sectionHeadroomChars;

const SECTION = z.object({
  symbol: z.string(),
  form: z.string(),
  accession: z.string(),
  accepted_at: z.string(),
  section: z.string(),
  state: z.string().nullable(),
  /** The page's length in characters, as the source counts it. */
  chars: z.number().nullable(),
  /** The part of the page this call read: characters `from` to `to`. */
  from: z.number(),
  to: z.number(),
  text: z.string(),
  /** Why there is no text, when there is none. */
  not_given: z.string().optional(),
  /** The call that reads on, or "end of section". */
  next: z.string(),
});

/**
 * Where a part starts, as one value the tool names and reads back: characters into the section's
 * first page (`8302`), or into a later page, after that page's cursor (`<cursor>:8302`). One value
 * the model copies leaves nothing for it to fill in.
 */
const FROM = /^(?:([^\s:]+):)?(\d+)$/;

function continueFrom(after: string | undefined, skip: number): string {
  return after ? `${after}:${skip}` : String(skip);
}

function position(from: string | undefined): { after?: string; skip: number } {
  const [, after, skip] = FROM.exec(from ?? "0") ?? [];
  return { ...(after ? { after } : {}), skip: Number(skip ?? 0) };
}

export function filingSectionTool(filings: Filings) {
  return defineTool({
    name: "filing_section",
    description:
      "The text of one section of an SEC filing (accession and section as filings lists them), part by part. " +
      "Continue with the `from` value the previous part names.",
    kind: "data",
    parallelSafe: true,
    input: z
      .object({
        symbol,
        accession: z.string().regex(/^\d{10}-\d{2}-\d{6}$/, "an accession such as 0000320193-26-000026"),
        section: z.enum(FILING_SECTIONS).describe("A section filings lists for this filing"),
        from: z
          .string()
          .regex(FROM, "the value a part names after `continue: filing_section with from=`")
          .optional()
          .describe("Where the previous part said to continue; the section's start when left out"),
      })
      .strict(),
    output: SECTION,
    label: ({ symbol, section, from }, part) =>
      `${symbol}${part ? ` ${part.form}` : ""} ${section.replaceAll("_", " ")}${part?.accepted_at ? `, ${part.accepted_at.slice(0, 10)}` : ""}${from ? ", more" : ""}`,
    async run({ symbol, accession, section, from }, { signal }) {
      const { after, skip } = position(from);
      const sourced = await filings.section({ symbol, accession, section }, after ? { after } : {}, {
        signal,
      });
      const answer = sourced.data;
      const content = answer.content ?? "";
      // As much text as fits the part once indented (two characters a line).
      let end = Math.min(content.length, skip + PART);
      while (end > skip + 1 && indented(content.slice(skip, end)).length > PART) {
        end = skip + Math.floor(((end - skip) * PART) / indented(content.slice(skip, end)).length);
      }
      const part = content.slice(skip, end);
      const why = fieldNotes(answer.field_states);
      const state = answer.state ?? "state not stated";
      return {
        payload: {
          symbol,
          form: answer.form,
          accession: answer.accession,
          accepted_at: answer.accepted_at,
          section: answer.section,
          state: answer.state ?? null,
          chars: answer.chars ?? null,
          from: content ? skip : 0,
          to: content ? end : 0,
          text: part,
          ...(!content && why ? { not_given: why } : {}),
          next:
            content && end < content.length
              ? `continue: filing_section with from=${continueFrom(after, end)}`
              : content && answer.next_cursor
                ? `continue: filing_section with from=${continueFrom(answer.next_cursor, 0)}`
                : "end of section",
        },
        provenance: provenanceOf(sourced, { subject: symbol }),
        summary: content
          ? message("tool.sectionPart", { chars: part.length })
          : message("tool.section", { state }),
      };
    },
    render(part) {
      const head = `${part.form} ${part.accession} (accepted ${part.accepted_at}), section ${part.section}: ${part.state ?? "state not stated"}`;
      // A by_reference section's content is the filing's own pointer to where the text is.
      if (!part.text) return [`${head}; no text to read${part.not_given ? ` (${part.not_given})` : ""}.`];
      return [
        `${head}; ${part.chars ?? "?"} characters in all; this part ${part.from}-${part.to} of this page`,
        indented(part.text),
        part.next,
      ];
    },
  });
}
