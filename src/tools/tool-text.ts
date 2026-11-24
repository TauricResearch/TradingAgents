// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * How the data tools write for the model: one line naming the instrument, rows that fit the
 * budget whole (never a row cut in half), and notes for withheld values.
 */

import { z } from "zod";
import { isCalendarDate, message } from "../contracts/index.js";
import type { FieldStates, Instrument, Succession } from "../data/capabilities.js";
import { instrumentKey, isInstrumentKey, parseInstrument } from "../data/instrument-key.js";
import type { Provenance } from "./tool.js";

/** A control character: C0, DEL, C1, or a Unicode line or paragraph separator. */
function control(character: string): boolean {
  const code = character.codePointAt(0) ?? 0;
  return code < 0x20 || (code >= 0x7f && code <= 0x9f) || code === 0x2028 || code === 0x2029;
}

/**
 * Text a source wrote, on one line: its line breaks and other control characters become spaces, so
 * it cannot pass for a line of the tool's own (a paging line, a heading).
 */
export function oneLine(text: string): string {
  let out = "";
  for (const character of text) {
    if (!control(character)) out += character;
    else if (!out.endsWith(" ")) out += " ";
  }
  return out.trim();
}

/** Text a source wrote, over several lines, each indented under the line that names it. */
export function indented(text: string, indent = "  "): string {
  return text
    .split(/\r\n|[\r\n\u2028\u2029]/)
    .map(
      (line) =>
        `${indent}${[...line].map((character) => (control(character) && character !== "\t" ? " " : character)).join("")}`,
    )
    .join("\n");
}

/** A date as YYYY-MM-DD, on the calendar. */
export const isoDate = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/, "a date as YYYY-MM-DD")
  .refine(isCalendarDate, "a day on the calendar");

/**
 * An instrument: a US ticker, MIC:SYMBOL, or a typed key as find_instrument names it. Keys keep their
 * spelling (series keys are lower case); a bare ticker is upper-cased.
 */
export const instrument = z
  .string()
  .trim()
  .regex(/^[A-Za-z0-9.:_/-]{1,80}$/, "a ticker such as AAPL, or an instrument key such as fx:EURUSD")
  .refine(
    isInstrumentKey,
    "a ticker such as AAPL, or a key as find_instrument gives it (fx:EURUSD, crypto:BTC-USDT)",
  )
  .describe(
    "A US ticker such as AAPL, or an instrument key from find_instrument: future:XNYM:CL, fx:EURUSD, crypto:BTC-USDT, series:us.equity_index.sp500",
  )
  .transform((value) => {
    // A bare ticker stays a ticker; a typed key is written as answers name it.
    const parsed = parseInstrument(value);
    return parsed.kind === "security" && !/^security:/i.test(value) ? parsed.id : instrumentKey(parsed);
  });

/** The ticker as the API spells it; a security's instrument key ("security:AAPL") is read as its ticker. */
export const symbol = z
  .string()
  .trim()
  .transform((value) => value.replace(/^security:/i, ""))
  .pipe(z.string().regex(/^[A-Za-z0-9.:-]{1,32}$/, "a ticker such as AAPL, or MIC:SYMBOL"))
  .describe("A US ticker such as AAPL, or MIC:SYMBOL such as XNAS:AAPL when a ticker is ambiguous")
  .transform((value) => value.toUpperCase());

/** "Apple Inc. (security:AAPL, XNAS, USD)", with the listing's state when it is no longer listed. */
export function instrumentLine(instrument: Instrument | null | undefined): string {
  if (!instrument) return "an instrument the source did not describe";
  // Prices quoted in a minor unit (pence) say so, or they would read a hundred times too large.
  const currency =
    instrument.currency && typeof instrument.price_scale === "number" && instrument.price_scale !== 1
      ? `${instrument.currency}, prices in units of ${instrument.price_scale} ${instrument.currency}`
      : instrument.currency;
  const details = [instrument.key, instrument.venue, currency].filter(Boolean).join(", ");
  const state = instrument.listing?.state;
  const lifecycle =
    state && state !== "listed"
      ? `; ${state}${instrument.listing?.delisted_at ? ` since ${instrument.listing.delisted_at}` : ""}`
      : "";
  return `${oneLine(instrument.name ?? instrument.key ?? "?")} (${oneLine(details)}${lifecycle})`;
}

/** "volume: temporarily_unavailable, ask later": what a record does not carry or limits, and why. */
export function fieldNotes(states: FieldStates): string {
  const entries = Object.entries(states ?? {}).filter(([, state]) => state?.reason);
  if (!entries.length) return "";
  return entries
    .map(([field, state]) =>
      oneLine(
        `${field}: ${state?.reason}${state?.retry ? `, ${RETRY_WORDS[state.retry] ?? state.retry}` : ""}`,
      ),
    )
    .join("; ");
}

/**
 * What a company's filings span across successions: its filers when it has predecessors (the current
 * one first), any filer not known to be fully covered, and where the source stops linking further back.
 */
export function successionNotes(succession: Succession): string[] {
  const { registrants, stopsAt } = succession;
  const filers =
    registrants.length > 1
      ? [
          oneLine(
            `filers: ${registrants
              .map((filer) =>
                filer.succeeded_on === undefined
                  ? `CIK ${filer.cik} (current)`
                  : `CIK ${filer.cik} (predecessor${filer.succeeded_on ? `, until ${filer.succeeded_on}` : ""})`,
              )
              .join("; ")}`,
          ),
        ]
      : [];
  const coverage = registrants
    .filter((filer) => filer.complete !== true)
    .map((filer) =>
      oneLine(
        `filer ${filer.cik}: ${filer.complete === false ? "coverage incomplete" : "coverage not known"}${filer.complete_reason ? ` (${filer.complete_reason})` : ""}`,
      ),
    );
  const stops = stopsAt.length
    ? [
        oneLine(
          `history before CIK ${stopsAt.join(", ")} is not linked by the source, so any earlier predecessor's filings are not included`,
        ),
      ]
    : [];
  return [...filers, ...coverage, ...stops];
}

/** What the source's retry advice means for whoever reads the note. */
const RETRY_WORDS: Record<string, string> = {
  later: "may change if asked later",
  never: "settled",
  change_request: "another request may serve it",
};

/**
 * A number as a person glances at it: billions and up compact (1.93T), others to two decimals with
 * separators, and small fractions to three significant digits. For summaries; results keep the exact value.
 */
export function displayNumber(value: number): string {
  if (!Number.isFinite(value)) return String(value);
  const size = Math.abs(value);
  if (size >= 1e9)
    return new Intl.NumberFormat("en-US", { notation: "compact", maximumSignificantDigits: 3 }).format(value);
  if (size >= 1 || size === 0) return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
  return String(Number(value.toPrecision(3)));
}

/**
 * A percentage as people read it, its decimals fixed so a column of them lines up: a change or a return
 * with one ("-14.0%", "+2.4%", "51.1%"); a rate or a yield, a level, with two ("4.34%"). `signed` puts "+"
 * before a gain.
 */
export function displayPercent(
  value: number,
  { signed = false, level = false }: { signed?: boolean; level?: boolean } = {},
): string {
  if (!Number.isFinite(value)) return String(value);
  const digits = level ? 2 : 1;
  const text = value.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  // Rounded to nothing, a value has no sign.
  const zero = Number(text.replaceAll(",", "")) === 0;
  const shown = zero ? text.replace(/^-/, "") : text;
  return `${signed && !zero && value > 0 ? "+" : ""}${shown}%`;
}

/** A number with thousands separators, as given (no rounding); "no value" for null. */
export function amount(value: number | null | undefined): string {
  if (value === null || value === undefined) return "no value";
  return value.toLocaleString("en-US", { maximumFractionDigits: 20 });
}

/** How many of `rows`, in the order given (most wanted first), fit in `room` characters, whole. */
export function fitting(rows: readonly string[], room: number): number {
  let used = 0;
  let count = 0;
  for (const row of rows) {
    if (used + row.length + 1 > room) break;
    used += row.length + 1;
    count++;
  }
  return count;
}

/**
 * The rows that fit in `room` characters, whole and in order (most wanted first), and when some do not,
 * a last line saying how many are shown and where every row is (`rest`, such as {"ref": "e4", "path": "articles"}).
 */
export function shownOf(rows: readonly string[], room: number, rest?: string): string[] {
  if (fitting(rows, room) === rows.length) return [...rows];
  const note = (shown: number) =>
    `(${shown} of ${rows.length} shown${rest ? `; every one is in ${rest}` : ""})`;
  const kept = fitting(rows, room - note(rows.length).length - 1);
  return [...rows.slice(0, kept), note(kept)];
}

/** The room left in `room` characters for rows once the fixed lines are written. */
export function roomIn(room: number, ...fixed: string[][]): number {
  return room - fixed.flat().join("\n").length - 1;
}

/** A sourced answer's provenance: the source, those that failed before it, its notes, and what it describes. */
export function provenanceOf(
  answer: { source: string; after: readonly string[]; notes: readonly string[]; syncs?: true },
  about: {
    [K in Exclude<keyof Provenance, "source" | "after" | "notes" | "syncs">]?:
      | Provenance[K]
      | null
      | undefined;
  } = {},
): Provenance {
  return {
    source: answer.source,
    ...(answer.after.length ? { after: [...answer.after] } : {}),
    ...(answer.notes.length ? { notes: [...answer.notes] } : {}),
    ...(answer.syncs ? { syncs: true as const } : {}),
    ...Object.fromEntries(Object.entries(about).filter(([, value]) => value !== undefined && value !== null)),
  };
}

/** Where an answer came from, as the transcript shows it: the source, and any that failed before it. */
export function sourceOf(answer: { source: string; after?: readonly string[] | undefined }): string {
  return answer.after?.length
    ? message("data.sourceAfter", { source: answer.source, failed: answer.after.join(", ") })
    : answer.source;
}

/** `text` within `chars` characters, cut between characters as people see them (never inside one) with "…". */
export function shortened(text: string, chars: number): string {
  if (text.length <= chars) return text;
  let out = "";
  for (const { segment } of new Intl.Segmenter().segment(text)) {
    if (out.length + segment.length > chars - 1) break;
    out += segment;
  }
  return `${out}…`;
}
