// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The price series the compute tools take: a price_history result referenced whole ({"ref": "e7"}) or a
 * series given directly, read into closes on their dates with what the source says about them.
 */
import { z } from "zod";
import type { PriceSeries } from "../compute/risk.js";
import { parseInstrument } from "../data/instrument-key.js";
import { BARS, RATES_OUT } from "./price-history.js";
import { NAME_CHARS, referenceTo } from "./references.js";
import { ToolRefusalError, wholeResult } from "./tool.js";
import { isoDate } from "./tool-text.js";

const GIVEN = z.object({
  label: z.string().min(1).max(NAME_CHARS).describe("A name for the series, such as its symbol"),
  dates: z.array(isoDate).describe("One date per value, oldest first"),
  values: z.array(z.number().nullable()).describe("Closes, oldest first"),
  periods_per_year: z
    .union([z.literal(252), z.literal(365)])
    .default(252)
    .describe("Sessions in a year: 252 for exchange trading, 365 for crypto"),
});
// A referenced result arrives as the record it is, checked when it is read.
export const SERIES = z
  .union([GIVEN, wholeResult("A price_history result, named by its symbol unless labelled", { named: true })])
  .describe(
    `A price_history result referenced whole (${referenceTo("e7")}, or ${referenceTo("e7")} with a label), or a series given as {label, dates, values}`,
  );
export const RISK_FREE = z
  .number()
  .min(0)
  .max(20)
  .default(0)
  .describe(
    "The risk-free rate in percent a year (4.5 is 4.5%), such as a Treasury bill yield; 0 by default",
  );

/** A series as the compute reads it, with what its source says about it (its currency: null when unstated). */
export type Prepared = PriceSeries & { notes: string[]; basis: string | null; currency: string | null };

/**
 * A series the tools take, ready to compute: its closes (or rates), calendar and caveats. A series quoted
 * as a rate (a yield) is refused unless `levels`: its changes are not returns.
 */
export function prepare(input: unknown, { levels = false }: { levels?: boolean } = {}): Prepared {
  const given = GIVEN.safeParse(input);
  if (given.success) {
    const { label, dates, values, periods_per_year } = given.data;
    return { label, dates, values, perYear: periods_per_year, notes: [], basis: null, currency: null };
  }
  // A referenced result labelled in the reference ({"ref": "e7", "label": "NVDA"}) is named by its label.
  const label = (input as { label?: unknown } | null)?.label;
  const named = typeof label === "string" ? { label } : {};
  const bars = BARS.safeParse(input);
  if (bars.success) {
    const { symbol, quoted_as } = bars.data;
    if (quoted_as === "rate" && !levels) {
      throw new ToolRefusalError(
        `${symbol} is quoted as a rate: its changes are differences in percentage points, not returns. Use calc on its values instead.`,
      );
    }
    return { ...fromBars(bars.data), ...named };
  }
  const interval = (input as { interval?: unknown } | null)?.interval;
  if (interval === "1h" || interval === "15m") {
    throw new ToolRefusalError(
      "returns and risk are computed from daily bars: ask price_history for daily bars",
    );
  }
  const rates = RATES_OUT.safeParse(input);
  if (!rates.success) {
    throw new ToolRefusalError(
      `a series is a price_history result referenced whole (${referenceTo("e7")}, optionally with a label), or a series given as {label, dates, values}`,
    );
  }
  const { pair, dates, basis, complete } = rates.data;
  return {
    label: pair,
    ...named,
    dates,
    values: rates.data.rates,
    perYear: 252,
    notes: [`${pair}: daily reference rates, not market closes`, ...incomplete(pair, complete)],
    basis,
    // A pair's rate is the base currency's price in the quote currency (EURUSD: dollars per euro).
    currency: pair.slice(3),
  };
}

/** A price_history result's closes as a series, with what its source says about them. */
export function fromBars(bars: z.output<typeof BARS>): Prepared {
  const { symbol, dates, closes, states, notes, price_basis, complete, incomplete_because, currency } = bars;
  const unsettled = dates.filter((_, i) => states[i]);
  return {
    label: symbol,
    dates,
    values: closes,
    perYear: parseInstrument(symbol).kind === "crypto" ? 365 : 252,
    notes: [
      ...notes.map((note) => `${symbol}: ${note}`),
      ...incomplete(symbol, complete, incomplete_because),
      ...(unsettled.length ? [`${symbol}: not final yet, so may still change: ${unsettled.join(", ")}`] : []),
    ],
    basis: price_basis,
    currency,
  };
}

/** That the source marks a series' history incomplete, and why when it says. */
function incomplete(label: string, complete: boolean | null, because?: string): string[] {
  return complete === false
    ? [`${label}: the source marks this history incomplete${because ? ` (${because})` : ""}`]
    : [];
}

/**
 * What the sources say about the basis of several series' closes: the one basis they share, or each
 * one's when they differ or some do not say.
 */
export function basisNotes(sources: readonly Prepared[]): string[] {
  const bases = new Set(sources.map((one) => one.basis));
  if (bases.size === 1) {
    const [only] = bases;
    return only ? [`price basis, as the sources state it: ${only}`] : [];
  }
  return [
    `the series are stated on different bases (${sources.map((one) => `${one.label} ${one.basis ?? "not stated"}`).join("; ")})`,
  ];
}

/**
 * Holdings in one currency, whose returns a portfolio can combine: refuses holdings quoted in different
 * currencies (their local returns leave out the exchange rate), and notes the ones whose currency the
 * source does not state.
 */
export function oneCurrency(tool: string, holdings: readonly Prepared[]): string[] {
  const stated = holdings.filter((one) => one.currency);
  if (new Set(stated.map((one) => one.currency)).size > 1) {
    throw new ToolRefusalError(
      `${tool}: the holdings are quoted in different currencies (${stated.map((one) => `${one.label} ${one.currency}`).join("; ")}); their returns combine only in one currency`,
    );
  }
  const unstated = holdings.filter((one) => !one.currency).map((one) => one.label);
  return unstated.length
    ? [`the currency of ${unstated.join(", ")} is not stated; the holdings are taken to be in one currency`]
    : [];
}

/** A result for one series, or why there is none. */

/** A series' name for the call's label: its given label, or the symbol or pair of the result it is. */
export function labelOf(series: unknown): string {
  const one = series as { label?: string; symbol?: string; pair?: string };
  return one.label ?? one.symbol ?? one.pair ?? "series";
}
