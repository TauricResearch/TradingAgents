// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Which fiscal quarter a quarter is, from the company's own annual periods: the fiscal year whose
 * span contains the quarter's end, counted from that year's start. A quarter after the latest annual
 * period (the year under way) is counted from that period's end, up to a year on. Anything else is
 * left unlabelled rather than guessed. The year is named by the month it ends in, not by the
 * company's own label, which follows conventions this data does not give.
 */

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];
const DAY = 86_400_000;
const QUARTER_DAYS = 365.25 / 4;
/** Days a 52/53-week year can run past 365. */
const YEAR_SLACK_DAYS = 10;

export type FiscalYear = { start: string; end: string };

const time = (date: string) => Date.parse(`${date}T00:00:00Z`);
const monthOf = (ms: number) => {
  const date = new Date(ms);
  return `${MONTHS[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
};

/** The quarter (1 to 4) a quarter ending `periodEnd` is, and when its fiscal year ends, from the annual periods given. */
export function fiscalQuarter(
  periodEnd: string,
  years: readonly FiscalYear[],
): { quarter: number; yearEnds: string } | undefined {
  const end = time(periodEnd);
  if (Number.isNaN(end)) return undefined;
  const count = (fromStart: number) => Math.round((end - fromStart) / DAY / QUARTER_DAYS);
  const containing = years.find((year) => time(year.start) <= end && end <= time(year.end));
  if (containing) {
    const quarter = count(time(containing.start));
    return quarter >= 1 && quarter <= 4 ? { quarter, yearEnds: monthOf(time(containing.end)) } : undefined;
  }
  const latest = [...years].sort((a, b) => time(b.end) - time(a.end))[0];
  if (!latest) return undefined;
  const after = time(latest.end);
  if (end <= after || end > after + (365 + YEAR_SLACK_DAYS) * DAY) return undefined;
  const quarter = count(after);
  return quarter >= 1 && quarter <= 4 ? { quarter, yearEnds: monthOf(after + 365 * DAY) } : undefined;
}

/** "fiscal Q2 of the year ending around January 2027", or "" when it cannot be told. */
export function fiscalLabel(periodEnd: string, years: readonly FiscalYear[]): string {
  const fiscal = fiscalQuarter(periodEnd, years);
  return fiscal ? `fiscal Q${fiscal.quarter} of the year ending around ${fiscal.yearEnds}` : "";
}
