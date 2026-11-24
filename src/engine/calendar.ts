// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The dates a turn is about, written out with their weekdays, so the model reads them instead of
 * working them out (it gets weekdays wrong).
 */
import { withWeekday } from "../contracts/index.js";

const DAYS_BEFORE = 7;

function named(day: Date): string {
  return withWeekday(day.toISOString().slice(0, 10));
}

function before(day: Date): string {
  return Array.from({ length: DAYS_BEFORE }, (_, i) =>
    named(new Date(day.getTime() - (i + 1) * 86_400_000)),
  ).join(", ");
}

/** The calendar line for a turn run at `now` (UTC dates). */
export function calendarContext(now: Date): string {
  const today = new Date(`${now.toISOString().slice(0, 10)}T00:00:00Z`);
  return `Calendar (UTC): today is ${named(today)}. The ${DAYS_BEFORE} days before: ${before(today)}.`;
}
