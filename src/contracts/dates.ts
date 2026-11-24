// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Dates, the same everywhere: a date is a UTC calendar day as YYYY-MM-DD. Every module that dates data
 * or decides which day it is uses these.
 */

/** What tells the time, so a run can be dated by a fixed clock. */
export type Clock = () => Date;

/** The system's clock. */
export const systemClock: Clock = () => new Date();

/** The UTC day of `instant`. */
export function dayOf(instant: Date): string {
  return instant.toISOString().slice(0, 10);
}

const WEEKDAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

/**
 * A calendar date with its weekday ("Thursday 2026-11-19"), so a model reads the weekday instead of working
 * it out (it gets weekdays wrong). Anything that is not a calendar date comes back as it is.
 */
export function withWeekday(date: string): string {
  if (!isCalendarDate(date)) return date;
  return `${WEEKDAY_NAMES[new Date(`${date}T00:00:00Z`).getUTCDay()]} ${date}`;
}

/** Whether `date` is a YYYY-MM-DD day on the calendar, not only shaped like one (2026-02-31 is not). */
export function isCalendarDate(date: string): boolean {
  const ms = /^\d{4}-\d{2}-\d{2}$/.test(date) ? Date.parse(`${date}T00:00:00Z`) : Number.NaN;
  return Number.isFinite(ms) && dayOf(new Date(ms)) === date;
}

/** `date` moved by `days` (back when negative). */
export function addDays(date: string, days: number): string {
  const day = new Date(`${date}T00:00:00Z`);
  day.setUTCDate(day.getUTCDate() + days);
  return dayOf(day);
}

/** Whole days from `from` to `to`. */
export function daysBetween(from: string, to: string): number {
  return (Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000;
}

/** The earlier of two dates; the bound a caller gave never moves later. */
export function earlierDate(a: string | undefined, b: string | undefined): string | undefined {
  if (a === undefined) return b;
  if (b === undefined) return a;
  return a <= b ? a : b;
}

/** Milliseconds of an ISO date or instant (a date is its midnight, UTC). */
export function msOf(value: string): number {
  return Date.parse(value.length === 10 ? `${value}T00:00:00Z` : value);
}
