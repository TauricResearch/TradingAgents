// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Risk of a portfolio of price series held at constant weights, rebalanced daily, on the dates every
 * holding shares. The portfolio's daily return is the weighted sum of its holdings' simple returns; its
 * value from 100 goes through riskOf, so its figures read as returns_risk's do. Covariance is the sample
 * covariance of daily returns; a holding's share of variance is w_i (Sigma w)_i / w' Sigma w, and the
 * shares sum to 1; the effective number of holdings is 1 / sum of squares, of the weights and of those
 * shares.
 */
import { PORTFOLIO } from "../contracts/limits.js";
import { LEAST, type PriceSeries, type Relative, type Risk, relativeOf, riskOf } from "./risk.js";
import { align, round, simpleReturns } from "./series.js";

type Holding = { series: PriceSeries; weight: number };

export type PortfolioRisk = {
  /**
   * The holdings, their weights as given and as used (summing to 1), and each one's share of variance:
   * null when the portfolio does not move.
   */
  holdings: { label: string; given: number; weight: number; variance_share_pct: number | null }[];
  /** The portfolio's figures, its value starting at 100. */
  risk: Risk;
  sessions_per_year: number;
  correlation: { labels: string[]; matrix: (number | null)[][] };
  /** By risk: null when the portfolio does not move. */
  effective_holdings: { by_weight: number; by_risk: number | null };
  benchmark: Relative | null;
  notes: string[];
};

/** Returns aligned on shared dates, as columns, with the dates they end on. */
type Returns = { labels: string[]; dates: string[]; columns: number[][]; perYear: number };

/** The holdings' daily simple returns on the dates all of them share. */
export function sharedReturns(series: readonly PriceSeries[]): Returns | { error: string } {
  const aligned = align(series);
  if ("error" in aligned) return aligned;
  const dates = aligned.dates as string[];
  const index = aligned.columns.findIndex((column) => column.some((close) => close <= 0));
  if (index >= 0) {
    return { error: `${series[index]?.label} has a close at or below zero, so its returns are not defined` };
  }
  const returns = Math.max(0, dates.length - 1);
  if (returns < LEAST.volatility) {
    return {
      error: `the series share ${returns} daily returns; a covariance needs at least ${LEAST.volatility} (a longer period, or series that trade on the same dates)`,
    };
  }
  return {
    labels: series.map((one) => one.label),
    dates,
    columns: aligned.columns.map(simpleReturns),
    // Two calendars (crypto with stocks) meet on the stocks' sessions.
    perYear: Math.min(...series.map((one) => one.perYear)),
  };
}

/** The sample covariance matrix of the columns (deviations from each mean, over n - 1). */
export function covariance(columns: readonly (readonly number[])[]): number[][] {
  const n = columns[0]?.length ?? 0;
  const centred = columns.map((column) => {
    const mean = column.reduce((a, b) => a + b, 0) / n;
    return column.map((x) => x - mean);
  });
  return centred.map((x) =>
    centred.map((y) => x.reduce((sum, value, t) => sum + value * (y[t] as number), 0) / (n - 1)),
  );
}

/** The matrix times the vector. */
export function times(matrix: readonly (readonly number[])[], vector: readonly number[]): number[] {
  return matrix.map((row) => row.reduce((sum, value, j) => sum + value * (vector[j] as number), 0));
}

/**
 * Each weight's share of the variance w' Sigma w: w_i (Sigma w)_i over the variance; empty when it is 0,
 * that is within rounding of the variance the weights would have uncorrelated.
 */
export function varianceShares(sigma: readonly (readonly number[])[], weights: readonly number[]): number[] {
  const marginal = times(sigma, weights);
  const variance = weights.reduce((sum, w, i) => sum + w * (marginal[i] as number), 0);
  const apart = weights.reduce((sum, w, i) => sum + w * w * ((sigma[i] as number[])[i] as number), 0);
  return variance > PORTFOLIO.varianceTolerance * apart
    ? weights.map((w, i) => (w * (marginal[i] as number)) / variance)
    : [];
}

export function portfolioRiskOf(
  holdings: readonly Holding[],
  options: { benchmark?: PriceSeries; riskFreePct?: number } = {},
): PortfolioRisk | { error: string } {
  const negative = holdings.filter((holding) => holding.weight < 0);
  if (negative.length) {
    return {
      error: `${negative.map((holding) => holding.series.label).join(", ")} has a negative weight; short positions are outside this long-only measure`,
    };
  }
  const total = holdings.reduce((sum, holding) => sum + holding.weight, 0);
  if (!(total > 0)) return { error: "the weights sum to 0; give each holding's weight" };
  const notes: string[] = [];
  if (Math.abs(total - 1) > PORTFOLIO.weightSumTolerance) {
    notes.push(`the weights given sum to ${round(total, 6)}; each is divided by that sum`);
  }
  const weights = holdings.map((holding) => holding.weight / total);
  const returns = sharedReturns(holdings.map((holding) => holding.series));
  if ("error" in returns) return returns;
  const { dates, columns, perYear } = returns;
  if (holdings.some((holding) => holding.series.perYear !== perYear)) {
    notes.push(
      `aligned on the ${perYear}-session calendar all holdings trade on; a return across a gap spans several days`,
    );
  }

  const daily = dates
    .slice(1)
    .map((_, t) => weights.reduce((sum, w, i) => sum + w * ((columns[i] as number[])[t] as number), 0));
  const values = [100];
  for (const r of daily) values.push((values.at(-1) as number) * (1 + r));
  const series: PriceSeries = { label: "portfolio", dates, values, perYear };
  const risk = riskOf(series, options.riskFreePct ?? 0);
  if ("error" in risk) return risk;

  const sigma = covariance(columns);
  const shares = varianceShares(sigma, weights);
  const deviations = sigma.map((row, i) => Math.sqrt(row[i] as number));
  const matrix = sigma.map((row, i) =>
    row.map((value, j) => {
      const scale = (deviations[i] as number) * (deviations[j] as number);
      return scale > 0 ? round(Math.max(-1, Math.min(1, value / scale)), 4) : null;
    }),
  );

  let benchmark: Relative | null = null;
  if (options.benchmark) {
    const relative = relativeOf(series, options.benchmark, options.riskFreePct ?? 0);
    if ("error" in relative) notes.push(`no beta: ${relative.error}`);
    else benchmark = relative;
  }

  return {
    holdings: holdings.map((holding, i) => ({
      label: holding.series.label,
      given: holding.weight,
      weight: round(weights[i] as number, 4),
      variance_share_pct: shares.length ? round((shares[i] as number) * 100) : null,
    })),
    risk,
    sessions_per_year: perYear,
    correlation: { labels: returns.labels, matrix },
    effective_holdings: {
      by_weight: round(1 / weights.reduce((sum, w) => sum + w * w, 0)),
      by_risk: shares.length ? round(1 / shares.reduce((sum, s) => sum + s * s, 0)) : null,
    },
    benchmark,
    notes,
  };
}
