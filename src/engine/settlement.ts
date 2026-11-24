// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Settling a recorded decision: how the instrument and the benchmark moved over a fixed number of
 * sessions after it. This is an observation of the first days, not a verdict on the decision's own
 * horizon. The benchmark's sessions are the calendar; the entry is the first session close after
 * the decision was made, the exit the close that many sessions later, and only final closes count.
 */
import { addDays, daysBetween, msOf } from "../contracts/index.js";
import { MEMORY } from "../contracts/limits.js";

/** Sessions observed after a decision. Stamped on each decision, so changing it reinterprets none. */
export const OBSERVATION_SESSIONS = 5;
/** The benchmark US decisions are compared with. */
export const BENCHMARK = "SPY";

/**
 * One session's close; `final` when the source says it will not change. A session the source lists
 * without a close keeps its place in the calendar with `close: null`.
 */
export type Close = { date: string; close: number | null; final: boolean };

/** One listing's daily closes between two dates (inclusive), oldest first, and the basis of its prices. */
type Closes = { closes: Close[]; basis: string };

/**
 * Daily closes of a listing and of its benchmark over one window, both from one source (a comparison
 * never mixes sources), and the source's name.
 */
export type ClosesSource = (
  symbols: readonly [string, string],
  from: string,
  to: string,
  signal?: AbortSignal,
) => Promise<{ stock: Closes; benchmark: Closes; source: string }>;

export type Settled = {
  state: "settled";
  sessions: number;
  benchmark: string;
  entry: { date: string; close: number; benchmark: number };
  exit: { date: string; close: number; benchmark: number };
  /** Returns as fractions over the window: the instrument's, the benchmark's, and the difference. */
  raw: number;
  benchmarkReturn: number;
  alpha: number;
  /** The exit session: when the outcome became known. */
  resolved: string;
};

type Unsettled =
  | { state: "immature"; reason: string }
  | { state: "gap"; reason: string }
  | { state: "unsettleable"; reason: string; resolved: string };

/**
 * The outcome of a decision made on `effective`, from the closes of the instrument and the
 * benchmark, as of `today`. It enters at the first close after the instant it was `decidedAt`, on the
 * benchmark's New York calendar. A gap is waited for from the exit session.
 */
export function settle(
  effective: string,
  stock: readonly Close[],
  benchmark: readonly Close[],
  today: string,
  {
    sessions = OBSERVATION_SESSIONS,
    benchmark: benchmarkSymbol = BENCHMARK,
    decidedAt,
  }: { sessions?: number; benchmark?: string; decidedAt: string },
): Settled | Unsettled {
  const after = msOf(decidedAt);
  const calendar = benchmark
    .filter((bar) => closeOf(bar.date) > after)
    .sort((a, b) => a.date.localeCompare(b.date));
  if (calendar.length < sessions + 1) {
    return {
      state: "immature",
      reason: `fewer than ${sessions + 1} sessions have traded since ${effective}`,
    };
  }
  const window = calendar.slice(0, sessions + 1);
  const exitDate = (window.at(-1) as Close).date;
  const priced = (bar: Close | undefined): bar is Close & { close: number } =>
    bar !== undefined && bar.close !== null && bar.close > 0;
  const byDate = new Map(stock.map((bar) => [bar.date, bar]));
  // A session without a close of the instrument or the benchmark is a gap, waited for and then given
  // up, whatever its status says; closes that are there but may still change are waited for.
  const missing = window.filter((bar) => !priced(bar) || !priced(byDate.get(bar.date)));
  if (missing.length) {
    const reason = `no close for ${missing.map((bar) => bar.date).join(", ")}`;
    return daysBetween(exitDate, today) > MEMORY.gapPatienceDays
      ? { state: "unsettleable", reason, resolved: today }
      : { state: "gap", reason };
  }
  if (window.some((bar) => !bar.final || !byDate.get(bar.date)?.final)) {
    return { state: "immature", reason: "closes in the window are not final yet" };
  }
  const first = window[0] as Close & { close: number };
  const last = window.at(-1) as Close & { close: number };
  const entry = byDate.get(first.date) as Close & { close: number };
  const exit = byDate.get(last.date) as Close & { close: number };
  const raw = exit.close / entry.close - 1;
  const benchmarkReturn = last.close / first.close - 1;
  return {
    state: "settled",
    sessions,
    benchmark: benchmarkSymbol,
    entry: { date: first.date, close: entry.close, benchmark: first.close },
    exit: { date: last.date, close: exit.close, benchmark: last.close },
    raw,
    benchmarkReturn,
    alpha: raw - benchmarkReturn,
    resolved: last.date,
  };
}

/** The range of closes settlement needs: the decision's day through enough calendar days for the window. */
export function closesRange(
  effective: string,
  today: string,
  sessions = OBSERVATION_SESSIONS,
): { from: string; to: string } {
  // Sessions take at most about 7/5 of their count in calendar days, plus holidays.
  const to = addDays(effective, Math.ceil(((sessions + 1) * 7) / 5) + 10);
  return { from: effective, to: to < today ? to : today };
}

/**
 * When a US session's regular trading ends, in milliseconds: 16:00 in New York, or 13:00 on the days
 * the exchange closes early (the day after Thanksgiving, July 3 and December 24, when they trade).
 */
function closeOf(date: string): number {
  const winter = Date.parse(`${date}T21:00:00Z`);
  const hour = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hour: "numeric",
    hourCycle: "h23",
  }).format(winter);
  // 21:00 UTC is 16:00 in New York in winter and 17:00 in summer.
  const close = hour === "16" ? winter : winter - 3_600_000;
  return closesEarly(date) ? close - 3 * 3_600_000 : close;
}

function closesEarly(date: string): boolean {
  const [year, month, day] = date.split("-").map(Number) as [number, number, number];
  if ((month === 7 && day === 3) || (month === 12 && day === 24)) return true;
  if (month !== 11) return false;
  // Thanksgiving is the fourth Thursday of November; the next day closes early.
  const firstThursday = 1 + ((4 - new Date(Date.UTC(year, 10, 1)).getUTCDay() + 7) % 7);
  return day === firstThursday + 22;
}
