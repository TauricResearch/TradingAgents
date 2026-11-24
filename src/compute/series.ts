// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Series of values put side by side: on the dates every series has when each is dated, else position by
 * position; and the simple returns between neighbouring values.
 */

export type Series = {
  label: string;
  /** One ISO date per value; without dates, every series must have as many values. */
  dates?: readonly string[];
  /** A missing value (null) is left out with its date. */
  values: readonly (number | null)[];
};

/** The series' values on their shared dates (or positions), a column each; dates when they are dated. */
type Aligned = { columns: number[][]; dates?: string[] };

export function align(series: readonly Series[]): Aligned | { error: string } {
  for (const one of series) {
    if (one.dates && one.dates.length !== one.values.length) {
      return {
        error: `${one.label} has ${one.dates.length} dates and ${one.values.length} values; give one date per value`,
      };
    }
  }
  // Dates on some series only would pair values by position across different periods.
  const undated = series.find((one) => !one.dates);
  if (undated && series.some((one) => one.dates)) {
    return { error: `give dates for every series or for none: ${undated.label} has none` };
  }
  return undated ? byPosition(series) : byDate(series);
}

/** Simple returns between neighbouring values, one fewer than the values. */
export function simpleReturns(values: readonly number[]): number[] {
  return values.slice(1).map((value, i) => value / (values[i] as number) - 1);
}

function byDate(series: readonly Series[]): Aligned {
  const maps = series.map((one) => {
    const map = new Map<string, number>();
    one.values.forEach((value, i) => {
      if (value !== null && Number.isFinite(value))
        map.set((one.dates as readonly string[])[i] as string, value);
    });
    return map;
  });
  const [first, ...rest] = maps;
  const dates = [...(first?.keys() ?? [])].filter((date) => rest.every((map) => map.has(date))).sort();
  return { columns: maps.map((map) => dates.map((date) => map.get(date) as number)), dates };
}

function byPosition(series: readonly Series[]): Aligned | { error: string } {
  const lengths = new Set(series.map((one) => one.values.length));
  if (lengths.size > 1) {
    const counts = series.map((one) => `${one.label} has ${one.values.length}`).join(", ");
    return { error: `series without dates must have as many values each: ${counts}` };
  }
  const gap = series.find((one) => one.values.some((value) => value === null || !Number.isFinite(value)));
  if (gap) return { error: `${gap.label} has missing values; give dates so they can be left out` };
  return { columns: series.map((one) => one.values as number[]) };
}

/** `value` to `digits` decimals, as figures are reported. */
export function round(value: number, digits = 2): number {
  return Number(value.toFixed(digits));
}
