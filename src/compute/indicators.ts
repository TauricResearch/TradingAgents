// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Technical indicators of daily bars, a value per session aligned with the bars, and what they did over a
 * window: the latest value, the start and end, the range with its dates, the direction of the
 * least-squares slope, and the dates of crossings. Where published definitions leave a choice (how a
 * smoothing is seeded, which deviation), TA-Lib's convention is used, so values match TA-Lib's
 * functions; each indicator's definition says which. A value is null until there are enough bars for it
 * (its warm-up), and where its formula is not defined (a range of zero).
 */

/** The indicators there are, as the tool names them. */
export const INDICATOR_NAMES = [
  "sma",
  "ema",
  "rsi",
  "macd",
  "bollinger",
  "atr",
  "adx",
  "stochastic",
  "roc",
] as const;
type IndicatorName = (typeof INDICATOR_NAMES)[number];

/** The periods each indicator takes, in order, with its defaults. */
export const PERIODS: { readonly [N in IndicatorName]: { names: string; defaults: readonly number[] } } = {
  sma: { names: "1 or 2 lengths (a fast and a slow line)", defaults: [50, 200] },
  ema: { names: "1 or 2 lengths (a fast and a slow line)", defaults: [20] },
  rsi: { names: "length", defaults: [14] },
  macd: { names: "fast, slow and signal lengths", defaults: [12, 26, 9] },
  bollinger: { names: "length (bands 2 standard deviations wide)", defaults: [20] },
  atr: { names: "length", defaults: [14] },
  adx: { names: "length", defaults: [14] },
  stochastic: { names: "%K length and smoothing", defaults: [14, 3] },
  roc: { names: "sessions", defaults: [20] },
};

/** Daily bars, oldest first: a close for every session, and its high and low where the source has them. */
export type Bars = {
  dates: readonly string[];
  highs: readonly (number | null)[];
  lows: readonly (number | null)[];
  closes: readonly number[];
};
/** Bars with the high and low of every session, which the range indicators need. */
type Ranged = Omit<Bars, "highs" | "lows"> & { highs: readonly number[]; lows: readonly number[] };

/** A value per session, null where there is none. */
export type Values = (number | null)[];

// Moving averages --------------------------------------------------------------------------------

/** The simple moving average: the mean of the last n values, from the n-th value. */
function sma(values: readonly number[], n: number): Values {
  const out: Values = values.map(() => null);
  let total = 0;
  values.forEach((value, i) => {
    total += value;
    if (i >= n) total -= values[i - n] as number;
    if (i >= n - 1) out[i] = total / n;
  });
  return out;
}

/**
 * The exponential moving average with alpha 2 / (n + 1), seeded with the simple mean of the n values
 * ending at `seedEnd` (the n-th value by default: TA-Lib's seeding), so its first value is there.
 */
function ema(values: readonly number[], n: number, seedEnd = n - 1): Values {
  return smoothed(values, n, 2 / (n + 1), seedEnd);
}

/** A series smoothed by alpha from a seed: the simple mean of the n values ending at `seedEnd`. */
function smoothed(values: readonly number[], n: number, alpha: number, seedEnd: number): Values {
  const out: Values = values.map(() => null);
  if (seedEnd >= values.length || seedEnd < n - 1) return out;
  let level = 0;
  for (let i = seedEnd - n + 1; i <= seedEnd; i++) level += values[i] as number;
  level /= n;
  out[seedEnd] = level;
  for (let i = seedEnd + 1; i < values.length; i++) {
    level = ((values[i] as number) - level) * alpha + level;
    out[i] = level;
  }
  return out;
}

// Momentum ---------------------------------------------------------------------------------------

/**
 * The relative strength index (Wilder, New Concepts in Technical Trading Systems, 1978): 100 times the
 * average gain over the average gain plus the average loss of the changes between closes. The averages
 * are seeded with the plain mean of the first n changes and then smoothed with alpha 1 / n (Wilder's
 * smoothing), as TA-Lib does; the first value is after n changes.
 */
function rsi(closes: readonly number[], n: number): Values {
  const out: Values = closes.map(() => null);
  if (closes.length <= n) return out;
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= n; i++) {
    const change = (closes[i] as number) - (closes[i - 1] as number);
    if (change < 0) loss -= change;
    else gain += change;
  }
  gain /= n;
  loss /= n;
  out[n] = strength(gain, loss);
  for (let i = n + 1; i < closes.length; i++) {
    const change = (closes[i] as number) - (closes[i - 1] as number);
    gain *= n - 1;
    loss *= n - 1;
    if (change < 0) loss -= change;
    else gain += change;
    gain /= n;
    loss /= n;
    out[i] = strength(gain, loss);
  }
  return out;
}

/** RSI from the average gain and loss: undefined when price did not move at all. */
const strength = (gain: number, loss: number) => (gain + loss === 0 ? null : (100 * gain) / (gain + loss));

/**
 * MACD (Appel, The Moving Average Convergence-Divergence Trading Method, 1979): the fast EMA of closes
 * minus the slow one, its signal line the EMA of the MACD line, and the histogram the line minus the
 * signal. As in TA-Lib, both EMAs start on the slow one's first session (the fast one seeded with the
 * mean of its last n closes there), and the signal is seeded with the mean of the line's first values.
 */
function macd(
  closes: readonly number[],
  fast: number,
  slow: number,
  signal: number,
): { line: Values; signal: Values; histogram: Values } {
  const first = slow - 1;
  const slowLine = ema(closes, slow);
  const fastLine = ema(closes, fast, first);
  const line: Values = closes.map((_, i) =>
    i >= first ? (fastLine[i] as number) - (slowLine[i] as number) : null,
  );
  const signalLine: Values = [
    ...line.slice(0, first).map(() => null),
    ...ema(line.slice(first) as number[], signal),
  ];
  const histogram = line.map((value, i) => {
    const level = signalLine[i];
    return value === null || level === null || level === undefined ? null : value - level;
  });
  return { line, signal: signalLine, histogram };
}

/**
 * The rate of change: the percent change of the close over n sessions, 100 (close / close n sessions
 * earlier - 1), as TA-Lib's ROC.
 */
function roc(closes: readonly number[], n: number): Values {
  return closes.map((close, i) => {
    const before = closes[i - n];
    return i >= n && before !== undefined && before > 0 ? (close / before - 1) * 100 : null;
  });
}

/**
 * The slow stochastic oscillator (Lane): %K, where the close sits in the high-low range of the last n
 * sessions (0 at the low, 100 at the high), smoothed by a simple mean of `smooth` values; %D is the
 * simple mean of `smooth` values of that %K. TA-Lib's STOCH with simple means; undefined where the
 * range is zero.
 */
function stochastic(bars: Ranged, n: number, smooth: number): { k: Values; d: Values } {
  const { highs, lows, closes } = bars;
  const raw: Values = closes.map((close, i) => {
    if (i < n - 1) return null;
    const high = Math.max(...highs.slice(i - n + 1, i + 1));
    const low = Math.min(...lows.slice(i - n + 1, i + 1));
    return high === low ? null : ((close - low) / (high - low)) * 100;
  });
  const k = meanOfDefined(raw, smooth);
  return { k, d: meanOfDefined(k, smooth) };
}

/** The simple mean of the last n values, null where any of them is. */
function meanOfDefined(values: Values, n: number): Values {
  return values.map((_, i) => {
    if (i < n - 1) return null;
    const window = values.slice(i - n + 1, i + 1);
    return window.some((value) => value === null)
      ? null
      : (window as number[]).reduce((sum, value) => sum + value, 0) / n;
  });
}

// Volatility -------------------------------------------------------------------------------------

/**
 * Bollinger bands (Bollinger, Bollinger on Bollinger Bands, 2001): the simple mean of the last n closes,
 * with bands k population standard deviations above and below, as TA-Lib's BBANDS; %B is where the close
 * sits between the bands (0 at the lower, 1 at the upper), and the bandwidth is the bands' distance apart
 * as a percent of the middle.
 */
function bollinger(
  closes: readonly number[],
  n: number,
  k: number,
): { upper: Values; middle: Values; lower: Values; percentB: Values; bandwidth: Values } {
  const middle = sma(closes, n);
  const width = middle.map((mean, i) => {
    if (mean === null) return null;
    const window = closes.slice(i - n + 1, i + 1);
    return k * Math.sqrt(window.reduce((sum, close) => sum + (close - mean) ** 2, 0) / n);
  });
  const upper = middle.map((mean, i) => (mean === null ? null : mean + (width[i] as number)));
  const lower = middle.map((mean, i) => (mean === null ? null : mean - (width[i] as number)));
  const percentB = closes.map((close, i) => {
    const spread = width[i];
    return spread === null || spread === undefined || spread === 0
      ? null
      : (close - (lower[i] as number)) / (2 * spread);
  });
  const bandwidth = middle.map((mean, i) =>
    mean === null || mean === 0 ? null : ((2 * (width[i] as number)) / mean) * 100,
  );
  return { upper, middle, lower, percentB, bandwidth };
}

/**
 * The true range of each session after the first (Wilder, 1978): the largest of its high less its low
 * and the distances of each from the prior close.
 */
function trueRange(bars: Ranged, i: number): number {
  const { highs, lows, closes } = bars;
  const high = highs[i] as number;
  const low = lows[i] as number;
  const prior = closes[i - 1] as number;
  return Math.max(high - low, Math.abs(high - prior), Math.abs(low - prior));
}

/**
 * The average true range (Wilder, 1978): the true range smoothed with alpha 1 / n, seeded with the mean
 * of the first n true ranges (from the second session, as each needs a prior close), as TA-Lib's ATR.
 */
function atr(bars: Ranged, n: number): Values {
  const out: Values = bars.closes.map(() => null);
  if (bars.closes.length <= n) return out;
  let level = 0;
  for (let i = 1; i <= n; i++) level += trueRange(bars, i);
  level /= n;
  out[n] = level;
  for (let i = n + 1; i < bars.closes.length; i++) {
    level = (level * (n - 1) + trueRange(bars, i)) / n;
    out[i] = level;
  }
  return out;
}

/**
 * The directional movement system (Wilder, 1978): +DI and -DI, the smoothed upward and downward moves
 * of the range as a percent of the smoothed true range, and ADX, the smoothed index of their spread
 * (100 |+DI - -DI| / (+DI + -DI)). Smoothing as in TA-Lib: the running sums start from the first n - 1
 * moves and go on by Wilder's rule (sum - sum / n + move), so the DIs start after n sessions; ADX starts
 * as the mean of the first n indexes, after 2n - 1 sessions, and goes on with alpha 1 / n.
 */
function adx(bars: Ranged, n: number): { plus: Values; minus: Values; adx: Values } {
  const { highs, lows, closes } = bars;
  const plus: Values = closes.map(() => null);
  const minus: Values = closes.map(() => null);
  const index: Values = closes.map(() => null);
  let up = 0;
  let down = 0;
  let range = 0;
  let indexes = 0;
  let level = 0;
  for (let i = 1; i < closes.length; i++) {
    const rise = (highs[i] as number) - (highs[i - 1] as number);
    const fall = (lows[i - 1] as number) - (lows[i] as number);
    const upMove = rise > 0 && rise > fall ? rise : 0;
    const downMove = fall > 0 && fall > rise ? fall : 0;
    const tr = trueRange(bars, i);
    if (i < n) {
      up += upMove;
      down += downMove;
      range += tr;
      continue;
    }
    up = up - up / n + upMove;
    down = down - down / n + downMove;
    range = range - range / n + tr;
    const plusDI = range === 0 ? 0 : (100 * up) / range;
    const minusDI = range === 0 ? 0 : (100 * down) / range;
    plus[i] = plusDI;
    minus[i] = minusDI;
    const spread = plusDI + minusDI === 0 ? 0 : (100 * Math.abs(plusDI - minusDI)) / (plusDI + minusDI);
    if (i < 2 * n - 1) indexes += spread;
    else if (i === 2 * n - 1) level = (indexes + spread) / n;
    else level = (level * (n - 1) + spread) / n;
    if (i >= 2 * n - 1) index[i] = level;
  }
  return { plus, minus, adx: index };
}

// Facts over a window ----------------------------------------------------------------------------

/** A value on its date. */
type Dated = { date: string; value: number };

/** What a line did over the window: its values there, and the least-squares slope per session. */
export type Facts = {
  values: number;
  start: Dated;
  end: Dated;
  change: number;
  min: Dated;
  max: Dated;
  /** Null with a single value. */
  slope: number | null;
};

/** The facts of a line's values from session `from` on; null when it has none there. */
export function factsOf(dates: readonly string[], values: Values, from: number): Facts | null {
  const points: { i: number; value: number }[] = [];
  for (let i = from; i < values.length; i++) {
    const value = values[i];
    if (value !== null && value !== undefined) points.push({ i, value });
  }
  const [first] = points;
  const last = points.at(-1);
  if (!first || !last) return null;
  const at = (point: { i: number; value: number }) => ({
    date: dates[point.i] as string,
    value: point.value,
  });
  let min = first;
  let max = first;
  for (const point of points) {
    if (point.value < min.value) min = point;
    if (point.value > max.value) max = point;
  }
  const meanI = points.reduce((sum, point) => sum + point.i, 0) / points.length;
  const meanV = points.reduce((sum, point) => sum + point.value, 0) / points.length;
  const spread = points.reduce((sum, point) => sum + (point.i - meanI) ** 2, 0);
  const slope =
    spread === 0
      ? null
      : points.reduce((sum, point) => sum + (point.i - meanI) * (point.value - meanV), 0) / spread;
  return {
    values: points.length,
    start: at(first),
    end: at(last),
    change: last.value - first.value,
    min: at(min),
    max: at(max),
    slope,
  };
}

/** A crossing: the session a line closed on the other side of another (or of a level). */
type Crossing = { date: string; direction: "above" | "below" };

/**
 * The sessions from `from` on where line `a` moved to the other side of `b` (a line or a level): the
 * first session on the new side, after one on the other side (sessions where they are equal or either is
 * missing do not count as a side). With the first session from `from` on where both have a value, and
 * the side `a` is on at the end.
 */
export function crossingsOf(
  dates: readonly string[],
  a: Values | readonly number[],
  b: Values | readonly number[] | number,
  from: number,
): { since: string | null; side: "above" | "below" | null; crossings: Crossing[] } {
  const crossings: Crossing[] = [];
  let since: string | null = null;
  let side = 0;
  for (let i = 0; i < a.length; i++) {
    const x = a[i];
    const y = typeof b === "number" ? b : b[i];
    if (x === null || x === undefined || y === null || y === undefined) continue;
    if (i >= from) since ??= dates[i] as string;
    if (x === y) continue;
    const now = x > y ? 1 : -1;
    if (side !== 0 && now !== side && i >= from) {
      crossings.push({ date: dates[i] as string, direction: now > 0 ? "above" : "below" });
    }
    side = now;
  }
  return { since, side: side > 0 ? "above" : side < 0 ? "below" : null, crossings };
}

// Indicators as asked ----------------------------------------------------------------------------

/** One indicator as asked: its name and periods (its defaults when left out). */
type Request = { name: IndicatorName; periods?: readonly number[] | undefined };

/** How a line is shown: with its window facts and last values, its facts, or its latest value only. */
type Weight = "lead" | "facts" | "latest";

export type Line = {
  /** Its column in the payload, such as rsi_14. */
  column: string;
  label: string;
  weight: Weight;
  latest: Dated | null;
  facts: Facts | null;
};

/**
 * A kind of crossing: the first session of the window both sides have a value (null when none), the
 * side the first is on at the end, the crossings' total since then, and every one, newest first, in words.
 */
type Crossings = {
  kind: string;
  since: string | null;
  side: "above" | "below" | null;
  total: number;
  events: { date: string; event: string }[];
};

export type Indicator = {
  name: IndicatorName;
  periods: number[];
  /** Such as RSI(14). */
  label: string;
  definition: string;
  /** Sessions the first value needs. */
  needs: number;
  lines: Line[];
  crossings: Crossings[];
};

/** A line as computed, before its facts. */
type Computed = { column: string; label: string; weight: Weight; values: Values };
/** A crossing kind as computed: the lines, and the words for each direction. */
type Kind = {
  kind: string;
  a: Values | readonly number[];
  b: Values | readonly number[] | number;
  above: string;
  below: string;
};

/** The indicators asked, their columns aligned with the bars' dates, and facts from session `from` on. */
export function indicatorsOf(
  bars: Bars,
  requests: readonly Request[],
  from: number,
): { columns: Record<string, Values>; results: (Indicator | { label: string; error: string })[] } {
  const columns: Record<string, Values> = {};
  const seen = new Set<string>();
  const results: (Indicator | { label: string; error: string })[] = [];
  for (const request of requests) {
    const periods = [...(request.periods ?? PERIODS[request.name].defaults)];
    const label = `${request.name.toUpperCase()}(${periods.join(", ")})`;
    if (seen.has(label)) continue;
    seen.add(label);
    const built = build(bars, request.name, periods);
    if ("error" in built) {
      results.push({ label, error: built.error });
      continue;
    }
    if (bars.closes.length < built.needs) {
      results.push({
        label,
        error: `${built.label} needs ${built.needs} sessions for its first value; the series has ${bars.closes.length}`,
      });
      continue;
    }
    for (const line of built.lines) columns[line.column] = line.values;
    results.push({
      name: request.name,
      periods,
      label: built.label,
      definition: built.definition,
      needs: built.needs,
      lines: built.lines.map((line) => ({
        column: line.column,
        label: line.label,
        weight: line.weight,
        latest: latestOf(bars.dates, line.values),
        facts: line.weight === "latest" ? null : factsOf(bars.dates, line.values, from),
      })),
      crossings: built.kinds.map(({ kind, a, b, above, below }) => {
        const { since, side, crossings } = crossingsOf(bars.dates, a, b, from);
        const events = crossings.reverse();
        return {
          kind,
          since,
          side,
          total: events.length,
          events: events.map((one) => ({ date: one.date, event: one.direction === "above" ? above : below })),
        };
      }),
    });
  }
  return { columns, results };
}

/** The last value of a line, with its date. */
function latestOf(dates: readonly string[], values: Values): Dated | null {
  for (let i = values.length - 1; i >= 0; i--) {
    const value = values[i];
    if (value !== null && value !== undefined) return { date: dates[i] as string, value };
  }
  return null;
}

/** One indicator's lines, crossings and definition, or why its periods do not fit it. */
function build(
  bars: Bars,
  name: IndicatorName,
  periods: number[],
):
  | { label: string; definition: string; needs: number; lines: Computed[]; kinds: Kind[] }
  | { error: string } {
  const { closes } = bars;
  const counts: { readonly [N in IndicatorName]: readonly number[] } = {
    sma: [1, 2],
    ema: [1, 2],
    rsi: [1],
    macd: [3],
    bollinger: [1],
    atr: [1],
    adx: [1],
    stochastic: [2],
    roc: [1],
  };
  if (!counts[name].includes(periods.length)) {
    return { error: `${name} takes ${PERIODS[name].names}; ${periods.length} given` };
  }
  const [n = 0, m = 0, s = 0] = periods;
  const ranged = name === "atr" || name === "adx" || name === "stochastic";
  const unranged = bars.closes.filter((_, i) => bars.highs[i] === null || bars.lows[i] === null).length;
  if (ranged && unranged) {
    return {
      error: `${name} needs the high and low of every session; the source does not give them for ${unranged} of ${bars.closes.length}`,
    };
  }
  const withRange = bars as Ranged;
  const close = (line: Values, label: string): Kind => ({
    kind: `close vs ${label}`,
    a: closes,
    b: line,
    above: "above",
    below: "below",
  });
  switch (name) {
    case "sma":
    case "ema": {
      if (periods.length === 2 && n >= m) {
        return { error: `${name} takes a fast length below the slow one; ${n} and ${m} given` };
      }
      const word = name.toUpperCase();
      const lines = periods.map((length) => ({
        column: `${name}_${length}`,
        label: `${word} ${length}`,
        weight: "lead" as const,
        values: name === "sma" ? sma(closes, length) : ema(closes, length),
      }));
      const [fast, slow] = lines;
      const golden = name === "sma" && n === 50 && m === 200;
      return {
        label: `${word}(${periods.join(", ")})`,
        definition:
          name === "sma"
            ? "simple moving average: the mean of the last n closes"
            : "exponential moving average of closes: alpha 2 / (n + 1), seeded with the simple mean of the first n closes (TA-Lib)",
        needs: Math.max(...periods),
        lines,
        kinds: [
          ...lines.map((line) => close(line.values, line.label)),
          ...(fast && slow
            ? [
                {
                  kind: `${fast.label} vs ${slow.label}${golden ? " (golden and death crosses)" : ""}`,
                  a: fast.values,
                  b: slow.values,
                  above: golden ? "golden cross" : "above",
                  below: golden ? "death cross" : "below",
                },
              ]
            : []),
        ],
      };
    }
    case "rsi": {
      const values = rsi(closes, n);
      return {
        label: `RSI(${n})`,
        definition: `Wilder's relative strength index: 100 x average gain / (average gain + average loss) of the changes between closes, each average seeded with the plain mean of the first ${n} changes, then smoothed with alpha 1/${n} (TA-Lib); 0 to 100, 70 and 30 the customary thresholds`,
        needs: n + 1,
        lines: [{ column: `rsi_${n}`, label: `RSI ${n}`, weight: "lead", values }],
        kinds: [
          { kind: "RSI vs 70", a: values, b: 70, above: "into above 70", below: "back below 70" },
          { kind: "RSI vs 30", a: values, b: 30, above: "back above 30", below: "into below 30" },
        ],
      };
    }
    case "macd": {
      if (n >= m) return { error: `macd takes a fast length below the slow one; ${n} and ${m} given` };
      const result = macd(closes, n, m, s);
      const suffix = periods.join("_");
      return {
        label: `MACD(${periods.join(", ")})`,
        definition: `Appel's MACD: EMA ${n} of closes minus EMA ${m} (both starting on the slow one's first session, TA-Lib); the signal is the EMA ${s} of the line; the histogram is the line minus the signal; in price units`,
        needs: m + s - 1,
        lines: [
          { column: `macd_${suffix}`, label: "MACD line", weight: "lead", values: result.line },
          { column: `macd_signal_${suffix}`, label: "signal", weight: "latest", values: result.signal },
          {
            column: `macd_histogram_${suffix}`,
            label: "histogram",
            weight: "lead",
            values: result.histogram,
          },
        ],
        kinds: [
          { kind: "MACD vs signal", a: result.line, b: result.signal, above: "above", below: "below" },
          { kind: "MACD vs zero", a: result.line, b: 0, above: "above", below: "below" },
        ],
      };
    }
    case "bollinger": {
      const bands = bollinger(closes, n, 2);
      return {
        label: `BOLLINGER(${n})`,
        definition: `Bollinger bands: the simple mean of the last ${n} closes, 2 population standard deviations above and below (TA-Lib); %B places the close between the bands (0 at the lower, 1 at the upper); bandwidth is the bands' distance apart as a percent of the middle`,
        needs: n,
        lines: [
          { column: `bb_upper_${n}`, label: "upper", weight: "latest", values: bands.upper },
          { column: `bb_middle_${n}`, label: "middle", weight: "latest", values: bands.middle },
          { column: `bb_lower_${n}`, label: "lower", weight: "latest", values: bands.lower },
          { column: `bb_percent_b_${n}`, label: "%B", weight: "lead", values: bands.percentB },
          { column: `bb_bandwidth_${n}`, label: "bandwidth %", weight: "lead", values: bands.bandwidth },
        ],
        kinds: [
          {
            kind: "close vs upper band",
            a: closes,
            b: bands.upper,
            above: "outside above",
            below: "back inside",
          },
          {
            kind: "close vs lower band",
            a: closes,
            b: bands.lower,
            above: "back inside",
            below: "outside below",
          },
        ],
      };
    }
    case "atr":
      return {
        label: `ATR(${n})`,
        definition: `Wilder's average true range: the true range (the largest of high - low, |high - prior close| and |low - prior close|) smoothed with alpha 1/${n}, seeded with the mean of the first ${n} (TA-Lib); in price units`,
        needs: n + 1,
        lines: [{ column: `atr_${n}`, label: `ATR ${n}`, weight: "lead", values: atr(withRange, n) }],
        kinds: [],
      };
    case "adx": {
      const result = adx(withRange, n);
      return {
        label: `ADX(${n})`,
        definition: `Wilder's directional movement: +DI and -DI are the smoothed upward and downward moves as a percent of the smoothed true range; ADX is the smoothed 100 |+DI - -DI| / (+DI + -DI); Wilder's smoothing over ${n}, as TA-Lib seeds it; ADX above 25 customarily reads as a trend`,
        needs: 2 * n,
        lines: [
          { column: `adx_${n}`, label: `ADX ${n}`, weight: "lead", values: result.adx },
          { column: `plus_di_${n}`, label: "+DI", weight: "facts", values: result.plus },
          { column: `minus_di_${n}`, label: "-DI", weight: "facts", values: result.minus },
        ],
        kinds: [{ kind: "ADX vs 25", a: result.adx, b: 25, above: "above", below: "below" }],
      };
    }
    case "stochastic": {
      const result = stochastic(withRange, n, m);
      return {
        label: `STOCHASTIC(${n}, ${m})`,
        definition: `Lane's slow stochastic: where the close sits in the high-low range of the last ${n} sessions (0 at the low, 100 at the high), %K its simple mean over ${m}, %D the simple mean of %K over ${m} (TA-Lib STOCH); 80 and 20 the customary thresholds`,
        needs: n + 2 * (m - 1),
        lines: [
          { column: `stoch_k_${n}_${m}`, label: "%K", weight: "lead", values: result.k },
          { column: `stoch_d_${n}_${m}`, label: "%D", weight: "facts", values: result.d },
        ],
        kinds: [],
      };
    }
    case "roc":
      return {
        label: `ROC(${n})`,
        definition: `rate of change: the percent change of the close over ${n} sessions, 100 (close / close ${n} sessions earlier - 1)`,
        needs: n + 1,
        lines: [{ column: `roc_${n}`, label: `ROC ${n}`, weight: "lead", values: roc(closes, n) }],
        kinds: [],
      };
  }
}
