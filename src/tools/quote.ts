// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** The latest quotes of one listing or several, one row each. */
import { z } from "zod";
import { message, withWeekday } from "../contracts/index.js";
import type { Quote, Quotes } from "../data/capabilities.js";
import { hint } from "./preview.js";
import { referenceTo } from "./references.js";
import { defineTool } from "./tool.js";
import { instrument, instrumentLine, oneLine, provenanceOf, roomIn, shownOf } from "./tool-text.js";

const RANGE = z
  .object({ low: z.number().nullable().optional(), high: z.number().nullable().optional() })
  .nullable();
/** The fields a quote's preview shows; a quote has more (field_states, its basis, its times). */
const SHOWN = z.object({
  symbol: z.string(),
  price: z.number().nullable().optional(),
  change_percent: z.number().optional(),
  quote_kind: z.string().optional(),
  session_date: z.string().optional(),
  day: RANGE.optional(),
  range_52w: RANGE.optional(),
  market_cap: z.number().optional(),
});
const QUOTES = z.object({
  quotes: z.array(z.looseObject({ symbol: z.string(), price: z.number().nullable().optional() })),
  /** Instruments without a quote, and why. */
  errors: z.array(z.object({ symbol: z.string(), message: z.string() })),
});
/** The quote's figures, as one row; a last close says the session it closed. */
const FIGURES = [
  "price",
  { field: "change_percent", as: "signed" },
  { range: ["day.low", "day.high"], label: "day" },
  { range: ["range_52w.low", "range_52w.high"], label: "52w" },
  { field: "market_cap", label: "cap" },
] as const;

export function quoteTool(quotes: Quotes) {
  return defineTool({
    name: "quote",
    description:
      "Latest quotes of up to 20 instruments at once: a US-listed security (price, day " +
      "change, session state, 52-week range, market cap), a futures contract's front month, a currency pair, a " +
      "crypto pair (24-hour change) or a price series.",
    kind: "data",
    parallelSafe: true,
    input: z.object({
      symbols: z.array(instrument).min(1).max(20).describe("The instruments, one or several"),
    }),
    output: QUOTES,
    preview: [
      hint(z.object({ quotes: z.array(SHOWN) }), {
        list: "quotes",
        fields: ["symbol", ...FIGURES],
        replacesSummary: true,
      }),
    ],
    label: ({ symbols }) => symbols.join(", "),
    async run({ symbols }, { signal }) {
      const asked = [...new Set(symbols)];
      if (asked.length > 1) {
        const answer = await quotes.many(asked, { signal });
        const { quotes: found, errors } = answer.data;
        return {
          payload: {
            quotes: found.map((one) => ({
              symbol: one.instrument,
              ...(one.source ? { source: one.source } : {}),
              ...compact(one.quote),
            })),
            errors: errors.map((one) => ({ symbol: one.instrument, message: one.message })),
          },
          // As of the latest quote, as for a single quote; each quote carries its own date.
          provenance: provenanceOf(answer, { as_of: latestDate(found.map((one) => dateOf(one.quote))) }),
          summary: found.map((one) => headline(one.instrument, one.quote)).join("; "),
        };
      }
      const only = asked[0] as string;
      const answer = await quotes.quote(only, { signal });
      return {
        payload: { quotes: [{ symbol: only, ...compact(answer.data) }], errors: [] },
        provenance: provenanceOf(answer, {
          subject: only,
          as_of: dateOf(answer.data),
        }),
        // The label names the instrument; the summary is its quote.
        summary: headline(undefined, answer.data),
      };
    },
    render({ quotes: found, errors: missing }, { id, room }) {
      const rows = found.map((one) =>
        oneLine(
          Object.entries(one)
            .map(([key, value]) => `${key} ${shown(value)}`)
            .join("; "),
        ),
      );
      const errors = missing.map((one) => `${one.symbol}: no quote (${oneLine(one.message)})`);
      return [...shownOf(rows, roomIn(room, errors), id ? referenceTo(id, "quotes") : undefined), ...errors];
    },
  });
}

/** The day a quote is of: its session's, or for one quoted around the clock (FX, crypto), its time's. */
function dateOf(quote: Quote): string | undefined {
  return quote.session_date ?? quote.price_time?.slice(0, 10) ?? undefined;
}

/** The latest of ISO dates, if any. */
function latestDate(dates: readonly (string | null | undefined)[]): string | undefined {
  return dates
    .filter((date): date is string => typeof date === "string")
    .sort()
    .at(-1);
}

function shown(value: unknown): string {
  return value !== null && typeof value === "object" ? JSON.stringify(value) : String(value);
}

/** The fields worth the model's attention, without nulls; field_states says what is withheld and why. */
function compact(quote: Quote): Record<string, unknown> {
  const picked: Record<string, unknown> = {
    instrument: instrumentLine(quote.instrument),
    quote_kind: quote.quote_kind,
    price: quote.price,
    price_basis: quote.price_basis,
    price_time: quote.price_time,
    stale: quote.stale || undefined,
    // Dates carry their weekdays, so the model reads them instead of working them out.
    session_date: quote.session_date ? withWeekday(quote.session_date) : quote.session_date,
    market_state: quote.market_state,
    previous_close: withDate(quote.previous_close),
    change: quote.change,
    change_percent: quote.change_percent,
    change_basis: quote.change_basis,
    day: quote.day,
    range_52w: quote.range_52w,
    market_cap: quote.market_cap,
    field_states: Object.keys(quote.field_states ?? {}).length ? quote.field_states : undefined,
  };
  return Object.fromEntries(
    Object.entries(picked).filter(([, value]) => value !== null && value !== undefined),
  );
}

/** A dated value (a previous close) with its date's weekday. */
function withDate(value: unknown): unknown {
  const dated = value as { date?: unknown } | null | undefined;
  return typeof dated?.date === "string" ? { ...dated, date: withWeekday(dated.date) } : value;
}

/** "AAPL 342.37 -0.52% (close 2026-11-06)": what the quote says, at a glance. */
function headline(symbol: string | undefined, quote: Quote): string {
  const parts = symbol ? [symbol] : [];
  if (quote.price !== null && quote.price !== undefined) parts.push(String(quote.price));
  if (quote.change_percent !== null && quote.change_percent !== undefined) {
    parts.push(`${quote.change_percent > 0 ? "+" : ""}${quote.change_percent.toFixed(2)}%`);
  }
  if (quote.quote_kind === "last_close" && quote.session_date)
    parts.push(message("tool.quoteClose", { date: quote.session_date }));
  return parts.join(" ");
}
