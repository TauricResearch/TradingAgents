// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** Daily price bars of one instrument, or a currency pair's reference rates. */
import { z } from "zod";
import { type Clock, dayOf, earlierDate, isCalendarDate, message, withWeekday } from "../contracts/index.js";
import { CALLS } from "../contracts/limits.js";
import type { DailyBars, PriceHistory } from "../data/capabilities.js";
import { parseInstrument } from "../data/instrument-key.js";
import { hint } from "./preview.js";
import { referenceTo } from "./references.js";
import { defineTool, type ToolAnswer, ToolRefusalError } from "./tool.js";
import { fieldNotes, instrument, instrumentLine, provenanceOf } from "./tool-text.js";

const PERIODS = ["5d", "1mo", "3mo", "6mo", "ytd", "1y"] as const;
/** Instrument types whose values are rates or yields. */
const RATES = new Set(["rate"]);
type Period = (typeof PERIODS)[number];

export const BARS = z.object({
  symbol: z.string(),
  instrument: z.string(),
  /** The currency the prices are quoted in, as the source states it. */
  currency: z.string().nullable(),
  interval: z.literal("daily"),
  price_basis: z.string().nullable(),
  from: z.string().nullable(),
  through: z.string().nullable(),
  complete: z.boolean().nullable(),
  incomplete_because: z.string().optional(),
  notes: z.array(z.string()),
  /** Whether the values are prices or rates (a yield, whose changes are differences, not returns). */
  quoted_as: z.enum(["price", "rate"]),
  earlier: z.string().optional(),
  dates: z.array(z.string()),
  opens: z.array(z.number().nullable()),
  highs: z.array(z.number().nullable()),
  lows: z.array(z.number().nullable()),
  closes: z.array(z.number().nullable()),
  volumes: z.array(z.number().nullable()),
  /** A bar not final yet, or a field the source flags, in words; null for a final bar. */
  states: z.array(z.string().nullable()),
});
/** A security's intraday bars: each with the UTC time it starts (times) and its session's date (dates). */
const INTRADAY = z.object({
  symbol: z.string(),
  instrument: z.string(),
  interval: z.enum(["1h", "15m"]),
  price_basis: z.string().nullable(),
  from: z.string().nullable(),
  through: z.string().nullable(),
  history_from: z.string().nullable(),
  notes: z.array(z.string()),
  earlier: z.string().optional(),
  times: z.array(z.string()),
  dates: z.array(z.string()),
  opens: z.array(z.number().nullable()),
  highs: z.array(z.number().nullable()),
  lows: z.array(z.number().nullable()),
  closes: z.array(z.number().nullable()),
  volumes: z.array(z.number().nullable()),
  states: z.array(z.string().nullable()),
});
export const RATES_OUT = z.object({
  pair: z.string(),
  instrument: z.string(),
  basis: z.string(),
  from: z.string().nullable(),
  through: z.string().nullable(),
  complete: z.boolean().nullable(),
  notes: z.array(z.string()),
  earlier: z.string().optional(),
  dates: z.array(z.string()),
  rates: z.array(z.number().nullable()),
});

export function priceHistoryTool(history: PriceHistory, clock: Clock) {
  return defineTool({
    name: "price_history",
    description:
      "Daily open, high, low, close and volume of one instrument (a US-listed security, a futures contract, a crypto " +
      "pair or a price series), oldest first; security prices are adjusted for splits and dividends. For a currency " +
      `pair, its daily reference rates instead. Reference the whole result (${referenceTo("e7")}) in returns_risk and beta for ` +
      `returns, volatility, drawdown, VaR and beta, or a column (${referenceTo("e7", "closes")}) in calc. Pages back with \`end\`.`,
    kind: "data",
    parallelSafe: true,
    input: z.object({
      symbol: instrument,
      interval: z
        .enum(["daily", "1h", "15m"])
        .default("daily")
        .describe("Bar length; 1h and 15m for securities, the newest 100 bars of the period"),
      period: z.enum(PERIODS).default("3mo").describe("How far back from `end`"),
      end: z
        .string()
        .regex(
          /^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?Z)?$/,
          "a date YYYY-MM-DD, or a UTC time for intraday paging",
        )
        .refine(
          (value) =>
            isCalendarDate(value.slice(0, 10)) && (value.length === 10 || !Number.isNaN(Date.parse(value))),
          "a day on the calendar",
        )
        .optional()
        .describe("The last session to include (default: the latest); for intraday, the earlier line's time"),
    }),
    output: z.union([BARS, RATES_OUT, INTRADAY]),
    // The span, the first and last close, the change, the low and the high; a rate's change is a difference.
    preview: [
      hint(BARS.extend({ quoted_as: z.literal("rate") }), {
        series: { dates: "dates", values: "closes", change: "difference", levels: true },
        replacesSummary: true,
      }),
      hint(BARS, { series: { dates: "dates", values: "closes" }, replacesSummary: true }),
      hint(RATES_OUT, { series: { dates: "dates", values: "rates" }, replacesSummary: true }),
      hint(INTRADAY, { series: { dates: "dates", values: "closes" }, replacesSummary: true }),
    ],
    table: ["times", "dates", "opens", "highs", "lows", "closes", "volumes", "states", "rates"],
    async run({ symbol, interval, period, end }, { signal }) {
      const to = earlierDate(end?.slice(0, 10), dayOf(clock())) as string;
      const { kind } = parseInstrument(symbol);
      if (interval !== "daily") {
        if (kind !== "security") {
          throw new ToolRefusalError(
            `${symbol}: intraday bars are for US-listed securities; ask for daily bars instead`,
          );
        }
        return intradayBars(history, symbol, interval, period, windowOf(period, to).from, end, signal);
      }
      if (kind === "fx") return referenceRates(history, symbol, period, windowOf(period, to), signal);
      const answer = await history.daily(symbol, windowOf(period, to), { signal });
      const { coverage, bars } = answer.data;
      const notes: string[] = [];
      // A continuous futures series follows the front month: a change across a roll compares two contracts.
      if (answer.data.instrument?.continuous) {
        notes.push(
          "A continuous front-month series: the roll dates are not marked, so a change across a roll compares different contracts.",
        );
      }
      if (coverage.missing_sessions)
        notes.push(`sessions the source flags as missing or not complete: ${coverage.missing_sessions}`);
      // A rate's moves are differences in percentage points, not returns.
      const rates = RATES.has(answer.data.instrument?.classification?.instrument_type ?? "");
      if (rates) {
        notes.push(
          "These values are rates: their changes are differences in percentage points, not returns.",
        );
      }
      const because = incompleteBecause(coverage);
      const payload: z.output<typeof BARS> = {
        symbol,
        instrument: instrumentLine(answer.data.instrument),
        currency: answer.data.instrument?.currency ?? null,
        interval: "daily",
        price_basis: answer.data.price_basis ?? null,
        from: coverage.from ?? null,
        through: coverage.through ?? null,
        complete: coverage.complete ?? null,
        ...(because ? { incomplete_because: because } : {}),
        notes,
        quoted_as: rates ? "rate" : "price",
        ...(answer.data.earlier_end
          ? { earlier: `price_history with end=${answer.data.earlier_end}, period=${period}` }
          : {}),
        ...columnsOf(bars),
      };
      return {
        payload,
        provenance: provenanceOf(answer, {
          subject: symbol,
          as_of: coverage.through,
        }),
        summary: message("tool.bars", {
          count: bars.length,
          through: coverage.through ? withWeekday(coverage.through) : "?",
        }),
      };
    },
  });
}

/** A security's newest intraday bars of the period, oldest first, and how to page back. */
async function intradayBars(
  history: PriceHistory,
  symbol: string,
  interval: "1h" | "15m",
  period: Period,
  start: string,
  end: string | undefined,
  signal: AbortSignal,
): Promise<ToolAnswer<z.output<typeof INTRADAY>>> {
  const answer = await history.intraday(
    symbol,
    { interval, start, ...(end ? { end } : {}), limit: CALLS.intradayBars },
    { signal },
  );
  const { bars } = answer.data;
  const through = bars.at(-1)?.date ?? null;
  return {
    payload: {
      symbol,
      instrument: instrumentLine(answer.data.instrument),
      interval,
      price_basis: answer.data.price_basis ?? null,
      from: bars[0]?.date ?? null,
      through,
      history_from: answer.data.history_from,
      notes: [
        "times are each bar's start in UTC; dates are its session's",
        ...(answer.data.missing_sessions
          ? [`sessions the source flags as missing or short: ${answer.data.missing_sessions}`]
          : []),
        ...(answer.data.incomplete_because ? [`incomplete: ${answer.data.incomplete_because}`] : []),
        ...(answer.data.history_from && start < answer.data.history_from
          ? [`the source's intraday history starts ${answer.data.history_from}`]
          : []),
      ],
      ...(answer.data.earlier_end
        ? {
            earlier: `price_history with interval=${interval}, period=${period}, end=${answer.data.earlier_end}`,
          }
        : {}),
      times: bars.map((bar) => bar.start),
      ...columnsOf(bars),
    },
    provenance: provenanceOf(answer, { subject: symbol, as_of: through }),
    summary: message("tool.bars", {
      count: bars.length,
      through: through ? withWeekday(through) : "?",
      interval,
    }),
  };
}

/** A currency pair's reference rates: values a central bank sets each day, not market prices. */
async function referenceRates(
  history: PriceHistory,
  pair: string,
  period: Period,
  window: { from: string; to: string },
  signal: AbortSignal,
): Promise<ToolAnswer<z.output<typeof RATES_OUT>>> {
  const answer = await history.referenceRates(pair, window, { signal });
  const { rates } = answer.data;
  const valued = rates.filter((rate): rate is { date: string; value: number } => rate.value !== null);
  const first = valued[0];
  const last = valued.at(-1);
  const through = rates.at(-1)?.date ?? null;
  return {
    payload: {
      pair,
      instrument: instrumentLine(answer.data.instrument),
      basis: answer.data.basis,
      from: rates[0]?.date ?? null,
      through,
      complete: answer.data.complete ?? null,
      notes: [
        "These are reference rates set once a day, not market prices: there is no open, high, low or volume, and they are not closes.",
        ...(first && last && valued.length > 1
          ? [
              `change over these days: ${((last.value / first.value - 1) * 100).toFixed(2)}% (${first.value} on ${first.date} to ${last.value} on ${last.date})`,
            ]
          : []),
      ],
      ...(answer.data.earlier_end
        ? { earlier: `price_history with end=${answer.data.earlier_end}, period=${period}` }
        : {}),
      dates: rates.map((rate) => rate.date),
      rates: rates.map((rate) => rate.value),
    },
    provenance: provenanceOf(answer, { subject: pair, as_of: through }),
    summary: message("tool.rates", { count: rates.length, through: through ? withWeekday(through) : "?" }),
  };
}

/**
 * The dates a period covers, ending at `to` (both inclusive), so every provider answers the same
 * window: 5d is the 7 calendar days ending at `to`, months and a year count back by calendar, ytd
 * starts on January 1 of `to`'s year.
 */
export function windowOf(period: Period, to: string): { from: string; to: string } {
  if (period === "ytd") return { from: `${to.slice(0, 4)}-01-01`, to };
  const [year, month, date] = to.split("-").map(Number) as [number, number, number];
  if (period === "5d") {
    return { from: new Date(Date.UTC(year, month - 1, date - 6)).toISOString().slice(0, 10), to };
  }
  // The same day of an earlier month, or that month's last day when it is shorter (March 31 -> February 28).
  const back = { "1mo": 1, "3mo": 3, "6mo": 6, "1y": 12 }[period];
  const lastDay = new Date(Date.UTC(year, month - 1 - back + 1, 0)).getUTCDate();
  const from = new Date(Date.UTC(year, month - 1 - back, Math.min(date, lastDay)));
  return { from: from.toISOString().slice(0, 10), to };
}

/** Why a window of bars is incomplete, when the source says: a history that starts later is said with its start. */
function incompleteBecause(coverage: DailyBars["coverage"]): string {
  if (coverage.complete_reason === "insufficient_history" && coverage.history_from)
    return `the source's history starts ${coverage.history_from}`;
  return coverage.complete_reason ?? "";
}

/** Bars as columns, oldest first: each field a list, and each bar's state (not final, a field's note). */
function columnsOf(
  bars: readonly {
    date: string;
    open?: number | null;
    high?: number | null;
    low?: number | null;
    close?: number | null;
    volume?: number | null;
    revision: string;
    field_states?: Parameters<typeof fieldNotes>[0];
  }[],
) {
  return {
    dates: bars.map((bar) => bar.date),
    opens: bars.map((bar) => bar.open ?? null),
    highs: bars.map((bar) => bar.high ?? null),
    lows: bars.map((bar) => bar.low ?? null),
    closes: bars.map((bar) => bar.close ?? null),
    volumes: bars.map((bar) => bar.volume ?? null),
    states: bars.map((bar) => {
      const words = [bar.revision !== "final" ? bar.revision : "", fieldNotes(bar.field_states)].filter(
        Boolean,
      );
      return words.length ? words.join("; ") : null;
    }),
  };
}
