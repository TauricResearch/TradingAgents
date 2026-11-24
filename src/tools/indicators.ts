// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Technical indicators of one instrument's daily bars over time, from a price_history result referenced
 * whole: each indicator's values for every session, and what they did over a window.
 */
import { z } from "zod";
import {
  type Facts,
  INDICATOR_NAMES,
  type Indicator,
  indicatorsOf,
  type Line,
  PERIODS,
  type Values,
} from "../compute/indicators.js";
import { INDICATORS } from "../contracts/limits.js";
import { BARS } from "./price-history.js";
import { referenceTo } from "./references.js";
import { basisNotes, fromBars, labelOf } from "./series.js";
import { defineTool, ToolRefusalError, wholeResult } from "./tool.js";
import { isoDate, roomIn, shownOf } from "./tool-text.js";

/** An indicator that could not be computed, and why. */
type Failed = { label: string; error: string };

/** A value as the result lists it: six significant digits (the data keeps it exact). */
const num = (value: number) => String(Number(value.toPrecision(6)));
const signed = (value: number) => `${value > 0 ? "+" : ""}${num(value)}`;

export function indicatorsTool() {
  return defineTool({
    name: "indicators",
    description:
      `Technical indicators of one instrument over time from a daily price_history result referenced whole (${referenceTo("e7")}): ` +
      `1 to ${INDICATORS.perCall} of ${INDICATOR_NAMES.join(", ")}. Each gives its definition, latest value, path over the window ` +
      "from `from` (start and end, low and high with dates, slope direction), last values, and dated crossings (close vs moving " +
      "averages, 50/200-day golden and death crosses, MACD vs signal and zero, RSI 70 and 30, close outside the Bollinger bands, " +
      "ADX 25). Values need a warm-up (200 sessions for a 200-day average), so a year of bars suits most; every value is in its data for calc.",
    kind: "compute",
    parallelSafe: true,
    input: z.object({
      series: wholeResult("A price_history result of daily bars"),
      indicators: z
        .array(
          z.object({
            name: z.enum(INDICATOR_NAMES),
            periods: z
              .array(z.number().int().min(1).max(INDICATORS.maxPeriod))
              .min(1)
              .max(3)
              .optional()
              .describe(
                `Periods in sessions; defaults ${INDICATOR_NAMES.map((name) => `${name} ${PERIODS[name].defaults.join("/")}`).join(", ")}`,
              ),
          }),
        )
        .min(1)
        .max(INDICATORS.perCall),
      from: isoDate
        .optional()
        .describe("The first date the window's facts and crossings cover; values use the whole history"),
    }),
    output: z.object({
      symbol: z.string(),
      /** The first session of the window the facts cover. */
      facts_from: z.string(),
      notes: z.array(z.string()),
      dates: z.array(z.string()),
      closes: z.array(z.number()),
      /** Each indicator's lines, a value per date, by column name (such as rsi_14). */
      columns: z.record(z.string(), z.array(z.number().nullable())),
      results: z.array(
        z.union([
          z.custom<Indicator>((v) => !!v && typeof v === "object" && "lines" in v),
          z.object({ label: z.string(), error: z.string() }),
        ]),
      ),
    }),
    label: ({ series, indicators }) =>
      `${labelOf(series)} ${indicators.map((one) => (one.periods ? `${one.name} ${one.periods.join("/")}` : one.name)).join(", ")}`,
    async run({ series, indicators, from }) {
      const parsed = BARS.safeParse(series);
      if (!parsed.success) {
        const interval = (series as { interval?: unknown } | null)?.interval;
        throw new ToolRefusalError(
          interval === "1h" || interval === "15m"
            ? "indicators are computed from daily bars: ask price_history for daily bars"
            : `indicators read a price_history result of daily bars referenced whole (${referenceTo("e7")})`,
        );
      }
      const bars = parsed.data;
      if (bars.quoted_as === "rate") {
        throw new ToolRefusalError(
          `${bars.symbol} is quoted as a rate, not a price; use calc on its values instead`,
        );
      }
      const prepared = fromBars(bars);
      // Sessions without a close are left out with their date, as the other compute tools do.
      const kept = bars.closes.flatMap((close, i) => (close === null ? [] : [i]));
      const dates = kept.map((i) => bars.dates[i] as string);
      const closes = kept.map((i) => bars.closes[i] as number);
      const to = dates.at(-1);
      if (!to) throw new ToolRefusalError(`${bars.symbol}: the result has no closes`);
      if (from && from > to) {
        throw new ToolRefusalError(`from ${from} is after the last session, ${to}`);
      }
      const start = from ? dates.findIndex((date) => date >= from) : 0;
      const { columns, results } = indicatorsOf(
        {
          dates,
          highs: kept.map((i) => bars.highs[i] ?? null),
          lows: kept.map((i) => bars.lows[i] ?? null),
          closes,
        },
        indicators,
        start,
      );
      if (results.every((result) => "error" in result)) {
        throw new ToolRefusalError(
          `${results.map((result) => (result as Failed).error).join("; ")} (one price_history result covers up to a year: about 250 sessions)`,
        );
      }
      return {
        payload: {
          symbol: bars.symbol,
          facts_from: dates[start] as string,
          notes: [
            ...prepared.notes,
            ...basisNotes([prepared]),
            // technicals gives the source's stochastic, a different variant under the same name.
            ...(results.some((result) => "name" in result && result.name === "stochastic")
              ? [
                  "technicals' stochastic is the KDJ over 9 sessions, not this slow one, so their values differ",
                ]
              : []),
          ],
          dates,
          closes,
          columns,
          results,
        },
        provenance: { source: "computed", syncs: true, as_of: to },
        summary: `${bars.symbol}: ${results
          .map((result) => {
            if ("error" in result) return `${result.label} not computed`;
            const lead = result.lines[0];
            return `${lead?.label} ${lead?.latest ? num(lead.latest.value) : "n/a"}`;
          })
          .join(", ")}`,
      };
    },
    render(payload, { id, room }) {
      const { symbol, dates, facts_from, notes, columns, results } = payload;
      const head = [
        `${symbol}: ${dates.length} daily sessions, ${dates[0]} to ${dates.at(-1)}; window facts and crossings from ${facts_from}, values computed on the whole history`,
      ];
      const rows = results.flatMap((result) =>
        "error" in result
          ? [`${result.label}: not computed (${result.error})`]
          : indicatorLines(result, columns),
      );
      const tail = [
        ...notes.map((note) => `- note: ${note}`),
        ...(id
          ? [
              `every value is in ${referenceTo(id, "columns.<column>")} (columns: ${Object.keys(columns).join(", ")}), aligned with ${referenceTo(id, "dates")}`,
            ]
          : []),
      ];
      return [
        ...head,
        ...shownOf(rows, roomIn(room, head, tail), id ? referenceTo(id, "results") : undefined),
        ...tail,
      ];
    },
  });
}

/** One indicator's lines: its definition, each line's facts and last values, and its crossings. */
function indicatorLines(result: Indicator, columns: Record<string, Values>): string[] {
  return [
    `${result.label}: ${result.definition}; the first value needs ${result.needs} sessions`,
    ...result.lines.flatMap((line) => lineRows(line, columns[line.column] ?? [])),
    ...result.crossings.map(({ kind, since, side, total, events }) => {
      if (!since) return `- ${kind}: no sessions in the window with both values`;
      const now = side ? `; now ${side}` : "";
      if (!total) return `- ${kind}: no crossings from ${since}${now}`;
      const listed = events.slice(0, INDICATORS.events).map((one) => `${one.event} ${one.date}`);
      return `- ${kind}: ${total} crossing${total === 1 ? "" : "s"} from ${since}${total > listed.length ? `, the most recent ${listed.length}` : ""}: ${listed.join(", ")}${now}`;
    }),
  ];
}

function lineRows(line: Line, values: Values): string[] {
  const latest = line.latest ? `latest ${num(line.latest.value)} on ${line.latest.date}` : "no value";
  if (line.weight === "latest") return [`- ${line.label}: ${latest}`];
  const rows = [`- ${line.label}: ${latest}${line.facts ? `; ${factsText(line.facts)}` : ""}`];
  if (line.weight === "lead") {
    const last = values.slice(-INDICATORS.tail).filter((value): value is number => value !== null);
    if (last.length) rows.push(`  last ${last.length}: ${last.map(num).join(", ")}`);
  }
  return rows;
}

function factsText(facts: Facts): string {
  const direction =
    facts.slope === null ? "" : facts.slope > 0 ? "rising" : facts.slope < 0 ? "falling" : "flat";
  return [
    `${facts.start.date} to ${facts.end.date} (${facts.values} values): ${num(facts.start.value)} to ${num(facts.end.value)} (change ${signed(facts.change)})`,
    `low ${num(facts.min.value)} on ${facts.min.date}, high ${num(facts.max.value)} on ${facts.max.date}`,
    ...(facts.slope === null ? [] : [`least-squares slope ${signed(facts.slope)} a session (${direction})`]),
  ].join(", ");
}
