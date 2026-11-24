// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Return and risk figures of a dated price series, and of an asset against a benchmark, computed from
 * closes on the dates they share. Conventions: simple daily returns between neighbouring closes; period
 * returns are ratios of closes; volatility is the sample standard deviation of daily returns times the
 * square root of the sessions in a year; VaR and expected shortfall are historical, one day, stated as
 * positive losses; Sortino divides the annualized mean excess return by the downside deviation, the root
 * mean square of the daily shortfalls below the risk-free rate over every day, annualized; Calmar divides
 * the annualized return by the depth of the deepest drawdown, both over the whole series; a figure needs
 * enough returns to mean something, and is null with the reason otherwise.
 */
import { align, round, simpleReturns } from "./series.js";

/** A dated series of closes, oldest first, and the sessions in its year (252, or 365 for crypto). */
export type PriceSeries = {
  label: string;
  dates: readonly string[];
  values: readonly (number | null)[];
  perYear: number;
};

/** Returns needed: volatility, Sharpe and Sortino, VaR, expected shortfall without a caveat, beta. */
export const LEAST = { volatility: 20, var: 100, shortfall: 250, beta: 60 } as const;
/** Calendar days a window must span for its return to be annualized. */
const ANNUALIZED_DAYS = 90;
/** A daily fall this deep in adjusted closes is more likely an unadjusted split than a move. */
const SPLIT_LIKE = -0.45;

/** A return over a window ending at the last close. */
type WindowReturn = { window: string; from: string; return_pct: number };

export type Risk = {
  label: string;
  from: string;
  to: string;
  last_close: number;
  /** Daily returns the figures come from. */
  returns: number;
  windows: WindowReturn[];
  /** Over the whole series, and annualized (geometric) when it spans at least 90 days. */
  total_return_pct: number;
  annualized_return_pct: number | null;
  volatility_pct: number | null;
  volatility_20d_pct: number | null;
  max_drawdown: {
    depth_pct: number;
    peak: string;
    trough: string;
    /** The first close at or above the peak after the trough; null when it has not recovered. */
    recovered: string | null;
  } | null;
  var_95_1d_pct: number | null;
  shortfall_95_1d_pct: number | null;
  best_day: { date: string; return_pct: number } | null;
  worst_day: { date: string; return_pct: number } | null;
  sharpe: number | null;
  sortino: number | null;
  calmar: number | null;
  notes: string[];
};

export type Relative = {
  asset: string;
  benchmark: string;
  from: string;
  to: string;
  returns: number;
  beta: number;
  beta_se: number;
  correlation: number;
  r_squared: number;
  /** Annualized: Jensen's alpha against the risk-free rate given (excess return when it is 0). */
  alpha_pct: number;
  tracking_error_pct: number;
  information_ratio: number | null;
  /** The asset's return minus the benchmark's over each window, on the shared dates. */
  excess: { window: string; from: string; asset_pct: number; benchmark_pct: number; excess_pct: number }[];
  notes: string[];
};

/** Windows ending at the last date: the first day each starts on (calendar months, ytd from January 1). */
function windowStarts(to: string): [string, string][] {
  const [year, month, day] = to.split("-").map(Number) as [number, number, number];
  const back = (months: number) => {
    const lastDay = new Date(Date.UTC(year, month - 1 - months + 1, 0)).getUTCDate();
    return iso(new Date(Date.UTC(year, month - 1 - months, Math.min(day, lastDay))));
  };
  return [
    ["1 week", iso(new Date(Date.UTC(year, month - 1, day - 7)))],
    ["1 month", back(1)],
    ["3 months", back(3)],
    ["6 months", back(6)],
    ["year to date", iso(new Date(Date.UTC(year - 1, 11, 31)))],
    ["1 year", back(12)],
  ];
}

export function riskOf(series: PriceSeries, riskFreePct = 0): Risk | { error: string } {
  const aligned = align([series]);
  if ("error" in aligned) return aligned;
  const closes = aligned.columns[0] as number[];
  const dates = aligned.dates as string[];
  if (closes.length < 2)
    return { error: `${series.label} has ${closes.length} closes; returns need at least 2` };
  if (closes.some((close) => close <= 0)) {
    return { error: `${series.label} has a close at or below zero, so its returns are not defined` };
  }
  const notes: string[] = [];
  const daily = simpleReturns(closes);
  const n = daily.length;
  const first = closes[0] as number;
  const last = closes.at(-1) as number;
  const from = dates[0] as string;
  const to = dates.at(-1) as string;
  const span = days(from, to);
  const total = last / first - 1;

  const windows = windowReturns(dates, closes);
  const volatility = n >= LEAST.volatility ? deviation(daily) * Math.sqrt(series.perYear) : null;
  const recent = daily.slice(-20);
  const volatility20 =
    recent.length >= LEAST.volatility ? deviation(recent) * Math.sqrt(series.perYear) : null;
  if (volatility === null)
    notes.push(
      `volatility, Sharpe and Sortino need at least ${LEAST.volatility} daily returns; there are ${n}`,
    );

  // Historical one-day VaR at 95%: the loss at the k-th worst return, k = ceil(5% of n); expected
  // shortfall is the mean loss over those k worst.
  const sorted = [...daily].sort((a, b) => a - b);
  const k = Math.ceil(0.05 * n);
  const tail = sorted.slice(0, k);
  const valueAtRisk = n >= LEAST.var ? -(sorted[k - 1] as number) : null;
  const shortfall = n >= LEAST.var ? -mean(tail) : null;
  if (n < LEAST.var)
    notes.push(`VaR and expected shortfall need at least ${LEAST.var} daily returns; there are ${n}`);
  else if (n < LEAST.shortfall) notes.push(`expected shortfall rests on ${k} worst days only`);

  const rfDaily = riskFreePct / 100 / series.perYear;
  const sharpe =
    volatility !== null && volatility > 0
      ? (mean(daily.map((r) => r - rfDaily)) * series.perYear) / volatility
      : null;

  const shortfalls = daily.map((r) => Math.min(0, r - rfDaily) ** 2);
  const downside = Math.sqrt(mean(shortfalls) * series.perYear);
  const sortino =
    volatility !== null && downside > 0
      ? (mean(daily.map((r) => r - rfDaily)) * series.perYear) / downside
      : null;
  const annualized = span >= ANNUALIZED_DAYS ? (1 + total) ** (365 / span) - 1 : null;
  const deepest = drawdown(dates, closes);
  const calmar = annualized !== null && deepest ? annualized / -deepest.depth : null;

  let best = 0;
  let worst = 0;
  daily.forEach((r, i) => {
    if (r > (daily[best] as number)) best = i;
    if (r < (daily[worst] as number)) worst = i;
    if (r <= SPLIT_LIKE) {
      notes.push(
        `the ${pct(r)} move on ${dates[i + 1]} looks like an unadjusted split or a data error; check it before relying on these figures`,
      );
    }
  });

  return {
    label: series.label,
    from,
    to,
    last_close: last,
    returns: n,
    windows,
    total_return_pct: round(total * 100),
    annualized_return_pct: annualized === null ? null : round(annualized * 100),
    volatility_pct: volatility === null ? null : round(volatility * 100),
    volatility_20d_pct: volatility20 === null ? null : round(volatility20 * 100),
    max_drawdown: deepest && {
      depth_pct: round(deepest.depth * 100),
      peak: deepest.peak,
      trough: deepest.trough,
      recovered: deepest.recovered,
    },
    var_95_1d_pct: valueAtRisk === null ? null : round(valueAtRisk * 100),
    shortfall_95_1d_pct: shortfall === null ? null : round(shortfall * 100),
    best_day:
      (daily[best] as number) > 0
        ? { date: dates[best + 1] as string, return_pct: round((daily[best] as number) * 100) }
        : null,
    worst_day:
      (daily[worst] as number) < 0
        ? { date: dates[worst + 1] as string, return_pct: round((daily[worst] as number) * 100) }
        : null,
    sharpe: sharpe === null ? null : round(sharpe, 3),
    sortino: sortino === null ? null : round(sortino, 3),
    calmar: calmar === null ? null : round(calmar, 3),
    notes,
  };
}

/** The asset against the benchmark on the dates both have; `perYear` is the shared calendar's. */
export function relativeOf(
  asset: PriceSeries,
  benchmark: PriceSeries,
  riskFreePct = 0,
): Relative | { error: string } {
  const aligned = align([asset, benchmark]);
  if ("error" in aligned) return aligned;
  const [a, b] = aligned.columns as [number[], number[]];
  const dates = aligned.dates as string[];
  if ([...a, ...b].some((close) => close <= 0)) {
    return { error: "a close at or below zero leaves returns undefined" };
  }
  const ra = simpleReturns(a);
  const rb = simpleReturns(b);
  const n = ra.length;
  if (n < LEAST.beta) {
    return {
      error: `${asset.label} and ${benchmark.label} share ${n} daily returns; beta needs at least ${LEAST.beta} (a longer period)`,
    };
  }
  // Two calendars (crypto against a stock) meet on the stock's sessions.
  const perYear = Math.min(asset.perYear, benchmark.perYear);
  const notes: string[] = [];
  if (asset.perYear !== benchmark.perYear) {
    notes.push(
      `aligned on the ${perYear}-session calendar both trade on; a return across a gap spans several days`,
    );
  }
  const ma = mean(ra);
  const mb = mean(rb);
  let cov = 0;
  let vb = 0;
  let va = 0;
  ra.forEach((x, i) => {
    const y = rb[i] as number;
    cov += (x - ma) * (y - mb);
    vb += (y - mb) ** 2;
    va += (x - ma) ** 2;
  });
  if (vb === 0) return { error: `${benchmark.label} does not move over these dates` };
  const beta = cov / vb;
  const residuals = ra.map((x, i) => x - ma - beta * ((rb[i] as number) - mb));
  const se = Math.sqrt(residuals.reduce((sum, e) => sum + e * e, 0) / (n - 2) / vb);
  const correlation = va === 0 ? 0 : cov / Math.sqrt(va * vb);
  const rf = riskFreePct / 100 / perYear;
  const alpha = (ma - rf - beta * (mb - rf)) * perYear;
  const active = ra.map((x, i) => x - (rb[i] as number));
  const trackingError = deviation(active) * Math.sqrt(perYear);
  const excess = windowStarts(dates.at(-1) as string).flatMap(([window, start]) => {
    const at = baseIndex(dates, start);
    if (at === undefined) return [];
    const assetReturn = (a.at(-1) as number) / (a[at] as number) - 1;
    const benchmarkReturn = (b.at(-1) as number) / (b[at] as number) - 1;
    return [
      {
        window,
        from: dates[at] as string,
        asset_pct: round(assetReturn * 100),
        benchmark_pct: round(benchmarkReturn * 100),
        excess_pct: round((assetReturn - benchmarkReturn) * 100),
      },
    ];
  });
  if (riskFreePct === 0)
    notes.push(
      "with a risk-free rate of 0, alpha is the return in excess of what beta explains, not Jensen's alpha against cash",
    );
  return {
    asset: asset.label,
    benchmark: benchmark.label,
    from: dates[0] as string,
    to: dates.at(-1) as string,
    returns: n,
    beta: round(beta, 4),
    beta_se: round(se, 4),
    correlation: round(correlation, 4),
    r_squared: round(correlation ** 2, 4),
    alpha_pct: round(alpha * 100),
    tracking_error_pct: round(trackingError * 100),
    information_ratio: trackingError > 0 ? round((mean(active) * perYear) / trackingError, 3) : null,
    excess,
    notes,
  };
}

/** Returns over the windows the series reaches: from the last close on or before each window's start. */
function windowReturns(dates: readonly string[], closes: readonly number[]): WindowReturn[] {
  const last = closes.at(-1) as number;
  return windowStarts(dates.at(-1) as string).flatMap(([window, start]) => {
    const at = baseIndex(dates, start);
    return at === undefined
      ? []
      : [{ window, from: dates[at] as string, return_pct: round((last / (closes[at] as number) - 1) * 100) }];
  });
}

/** The last date on or before `start`; none when the series starts after it. */
function baseIndex(dates: readonly string[], start: string): number | undefined {
  for (let i = dates.length - 1; i >= 0; i--) if ((dates[i] as string) <= start) return i;
  return undefined;
}

/** The deepest fall from a running peak (a negative fraction), and the first close back at or above that peak. */
function drawdown(
  dates: readonly string[],
  closes: readonly number[],
): { depth: number; peak: string; trough: string; recovered: string | null } | null {
  let peak = 0;
  let worst = { depth: 0, peak: 0, trough: 0 };
  closes.forEach((close, i) => {
    if (close > (closes[peak] as number)) peak = i;
    const depth = close / (closes[peak] as number) - 1;
    if (depth < worst.depth) worst = { depth, peak, trough: i };
  });
  if (worst.depth >= 0) return null;
  const level = closes[worst.peak] as number;
  const back = closes.findIndex((close, i) => i > worst.trough && close >= level);
  return {
    depth: worst.depth,
    peak: dates[worst.peak] as string,
    trough: dates[worst.trough] as string,
    recovered: back < 0 ? null : (dates[back] as string),
  };
}

function mean(values: readonly number[]): number {
  return values.reduce((a, b) => a + b, 0) / values.length;
}

function deviation(values: readonly number[]): number {
  const m = mean(values);
  return Math.sqrt(values.reduce((a, b) => a + (b - m) ** 2, 0) / (values.length - 1));
}

function days(from: string, to: string): number {
  return (Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000;
}

function iso(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}
