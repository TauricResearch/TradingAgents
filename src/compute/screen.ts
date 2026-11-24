// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * A sector's companies ranked by one statement line: by its value, or by its change from the year before.
 * Values are compared only within one unit (the sector's most common), companies are matched across years
 * by CIK, and a change is given only between years of about the same length with a positive base.
 */
import { daysBetween } from "../contracts/index.js";
import { SCREEN } from "../contracts/limits.js";

/** One company's value of a line for one fiscal year, as a sector screen reads it. */
type ScreenRow = {
  ciks: string[];
  name: string | null;
  symbols: string[];
  value: number | null;
  unit: string | null;
  unit_group: string | null;
  period_start: string | null;
  period_end: string | null;
  derivation: string | null;
  missing_because: string | null;
  accession: string | null;
};

type Ranked = {
  name: string;
  symbol: string | null;
  value: number;
  period_end: string | null;
  /** Its fiscal year ends far from the sector's usual end. */
  off_calendar: boolean;
  /** How the value was derived, when it was not filed as such. */
  derived: string | null;
  prior: number | null;
  change: number | null;
  change_pct: number | null;
  /** Why there is no change in percent. */
  no_change_because: string | null;
  accession: string | null;
};

export type Screen = {
  unit: string | null;
  /** Companies with a value in the main unit. */
  in_unit: number;
  /** Those the ranking is drawn from (for a change, those with one), and why the others are not. */
  eligible: number;
  not_eligible: { reason: string; companies: number }[];
  ranked: Ranked[];
  /** Companies whose values are in another unit, apart from the ranking. */
  other_units: { unit: string; companies: number; examples: string[] }[];
  read: number;
  with_value: number;
  without_value: { reason: string; companies: number }[];
  derived: number;
  off_calendar: number;
  /** The sector's usual fiscal year end (a month), and the range of period ends read. */
  usual_end: string | null;
  first_end: string | null;
  last_end: string | null;
};

export function screenOf(input: {
  current: readonly ScreenRow[];
  prior?: readonly ScreenRow[];
  rankBy: "value" | "change";
  order: "desc" | "asc";
  top: number;
}): Screen {
  const { current } = input;
  const valued = current.filter((row) => row.value !== null);
  // The unit most of the sector reports in is the one ranked; the others are listed apart.
  const groups = new Map<string, ScreenRow[]>();
  for (const row of valued) {
    const key = row.unit_group ?? "unknown";
    groups.set(key, [...(groups.get(key) ?? []), row]);
  }
  const [main, ...others] = [...groups.entries()].sort((a, b) => b[1].length - a[1].length);
  const ends = valued.flatMap((row) => (row.period_end ? [row.period_end] : [])).sort();
  const usual = mostCommon(ends.map((end) => end.slice(0, 7)));
  const priorBy = new Map<string, ScreenRow>();
  for (const row of input.prior ?? []) for (const cik of row.ciks) priorBy.set(cik, row);
  const rows = (main?.[1] ?? []).map((row): Ranked => {
    const before = row.ciks.map((cik) => priorBy.get(cik)).find(Boolean);
    const change = changeOf(row, before, main?.[0] ?? "");
    return {
      name: row.name ?? "unnamed",
      symbol: row.symbols[0]
        ? `${row.symbols[0]}${row.symbols.length > 1 ? ` +${row.symbols.length - 1}` : ""}`
        : null,
      value: row.value as number,
      period_end: row.period_end,
      off_calendar: Boolean(
        usual && row.period_end && Math.abs(days(`${usual}-15`, row.period_end)) > SCREEN.offCalendarDays,
      ),
      derived: row.derivation && row.derivation !== "filed" ? row.derivation : null,
      ...change,
      accession: row.accession,
    };
  });
  const key = (row: Ranked) => (input.rankBy === "change" ? row.change_pct : row.value);
  const pool = rows.filter((row) => key(row) !== null);
  const excluded = new Map<string, number>();
  for (const row of rows) {
    if (key(row) === null)
      excluded.set(
        row.no_change_because ?? "no change",
        (excluded.get(row.no_change_because ?? "no change") ?? 0) + 1,
      );
  }
  const ranked = pool
    .sort((a, b) => ((key(a) as number) - (key(b) as number)) * (input.order === "desc" ? -1 : 1))
    .slice(0, input.top);
  const missing = new Map<string, number>();
  for (const row of current) {
    if (row.value === null)
      missing.set(
        row.missing_because ?? "not served",
        (missing.get(row.missing_because ?? "not served") ?? 0) + 1,
      );
  }
  return {
    unit: main?.[1][0]?.unit ?? null,
    in_unit: rows.length,
    eligible: pool.length,
    not_eligible: [...excluded.entries()].map(([reason, companies]) => ({ reason, companies })),
    ranked,
    other_units: others.slice(0, 5).map(([, members]) => ({
      unit: members[0]?.unit ?? "unknown",
      companies: members.length,
      examples: members.slice(0, 3).map((row) => row.name ?? "unnamed"),
    })),
    read: current.length,
    with_value: valued.length,
    without_value: [...missing.entries()].map(([reason, companies]) => ({ reason, companies })),
    derived: rows.filter((row) => row.derived).length,
    off_calendar: rows.filter((row) => row.off_calendar).length,
    usual_end: usual,
    first_end: ends[0] ?? null,
    last_end: ends.at(-1) ?? null,
  };
}

function changeOf(
  row: ScreenRow,
  before: ScreenRow | undefined,
  group: string,
): Pick<Ranked, "prior" | "change" | "change_pct" | "no_change_because"> {
  const none = (why: string, prior: number | null = null) => ({
    prior,
    change: null,
    change_pct: null,
    no_change_because: why,
  });
  if (!before || before.value === null) return none("prior year missing");
  if (before.unit_group !== group) return none("prior year in another unit");
  // A balance-sheet value is a date's, with no span: two year ends compare as they are.
  const instants = !row.period_start && !before.period_start;
  const length = (r: ScreenRow) =>
    r.period_start && r.period_end ? days(r.period_start, r.period_end) : undefined;
  const now = length(row);
  const then = length(before);
  if (!instants && (now === undefined || then === undefined || Math.abs(now - then) > SCREEN.lengthDays)) {
    return none("the two years are not of the same length", before.value);
  }
  const change = (row.value as number) - before.value;
  if (before.value <= 0)
    return { prior: before.value, change, change_pct: null, no_change_because: "prior year not positive" };
  return {
    prior: before.value,
    change,
    change_pct: Number(((change / before.value) * 100).toFixed(2)),
    no_change_because: null,
  };
}

function mostCommon(values: readonly string[]): string | null {
  const counts = new Map<string, number>();
  for (const value of values) counts.set(value, (counts.get(value) ?? 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
}

function days(from: string, to: string): number {
  return daysBetween(from.slice(0, 10), to.slice(0, 10));
}
