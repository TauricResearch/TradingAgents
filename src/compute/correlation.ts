// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Pearson correlation between series: of their simple returns (the default) or their levels, on the
 * dates every series has when each is dated, else position by position.
 */
import { align, type Series, simpleReturns } from "./series.js";

export type { Series } from "./series.js";

type Correlation = {
  of: "returns" | "levels";
  /** Aligned observations (dates, or positions) the figures come from; returns number one fewer. */
  observations: number;
  from?: string;
  to?: string;
  labels: string[];
  /** Row i, column j: the correlation of series i with series j; null when either does not move. */
  matrix: (number | null)[][];
};

const LEAST = 3;

export function correlate(
  series: readonly Series[],
  of: "returns" | "levels",
): Correlation | { error: string } {
  const aligned = align(series);
  if ("error" in aligned) return aligned;
  const { columns, dates } = aligned;
  const observations = columns[0]?.length ?? 0;
  // Returns are one fewer than the levels they come from, and two points always correlate at +1 or -1.
  const least = of === "returns" ? LEAST + 1 : LEAST;
  if (observations < least) {
    const who = series.length === 2 ? `${series[0]?.label} and ${series[1]?.label}` : "the series";
    return {
      error: `${who} share ${observations} ${dates ? "dates" : "values"}; ${of} need at least ${least}`,
    };
  }
  if (of === "returns") {
    const index = columns.findIndex((column) => column.some((value) => value <= 0));
    if (index >= 0) {
      return {
        error: `${series[index]?.label} has a value at or below zero, so its returns are not defined; correlate its levels instead`,
      };
    }
  }
  const prepared = of === "returns" ? columns.map(simpleReturns) : columns;
  return {
    of,
    observations,
    ...(dates ? { from: dates[0] as string, to: dates.at(-1) as string } : {}),
    labels: series.map((one) => one.label),
    matrix: prepared.map((row) => prepared.map((column) => pearson(row, column))),
  };
}

function pearson(xs: number[], ys: number[]): number | null {
  const mean = (values: number[]) => values.reduce((a, b) => a + b, 0) / values.length;
  const mx = mean(xs);
  const my = mean(ys);
  let cov = 0;
  let vx = 0;
  let vy = 0;
  xs.forEach((x, i) => {
    const dx = x - mx;
    const dy = (ys[i] as number) - my;
    cov += dx * dy;
    vx += dx * dx;
    vy += dy * dy;
  });
  if (vx === 0 || vy === 0) return null;
  // Rounding can put a series' correlation with itself a hair past 1.
  return Math.max(-1, Math.min(1, cov / Math.sqrt(vx * vy)));
}
