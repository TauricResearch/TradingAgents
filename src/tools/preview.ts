// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * A result's preview for the person watching: a few rows of cells under its row in the transcript. Two
 * layers, and nothing else: a tool's declared hint (which list and fields, which record fields, which
 * date and value columns), checked against its output's type so a renamed field fails to compile; else
 * the first lines of the text the model reads. Previews read the tools' own typed payloads, never guess at
 * fields, and carry no width: the terminal aligns and fits them.
 */
import type { z } from "zod";
import type { Preview } from "../contracts/index.js";
import { displayNumber, displayPercent, oneLine, shortened } from "./tool-text.js";

/** Rows a preview carries at most; how many more there are is said. */
export const PREVIEW_ROWS = 3;

/** Characters a cell keeps at most: more than any row shows, so the terminal still cuts it to fit. */
export const PREVIEW_CELL_CHARS = 160;

/**
 * How a value is written: by its type when unset (numbers with displayNumber, ISO dates as "Nov 21").
 * `percent` and `signed` are percentages (signed with "+" for a gain), `level` a rate or yield in percent
 * (two decimals: "4.34%"), `unit` a number in its record's own unit (a list's `unit`: a level when it is
 * a percent, else as a number), `delta` a change in the value's
 * own units ("+0.13"), `instrument` an instrument's line without its key ("S&P 500 (series:...)" as "S&P 500").
 */
type Format = "number" | "percent" | "signed" | "level" | "unit" | "delta" | "date" | "text" | "instrument";

// Paths into a payload, checked by the compiler: a field, or a field of a nested record ("max_drawdown.depth_pct").
type Fields<T> = T extends unknown ? keyof T & string : never;
type Depth = [never, 0, 1];
type Nested<T, D extends number = 2> = [D] extends [never]
  ? never
  : T extends unknown
    ? {
        [K in keyof T & string]: NonNullable<T[K]> extends readonly unknown[]
          ? never
          : NonNullable<T[K]> extends Record<string, unknown>
            ? `${K}.${keyof NonNullable<T[K]> & string}` | `${K}.${Nested<NonNullable<T[K]>, Depth[D]>}`
            : never;
      }[keyof T & string]
    : never;
/** A field, or a field of a nested record up to two levels down ("summary.spot.price"). */
type Path<T> = Fields<T> | Nested<T>;

/** A cell: a field, a labelled field ("vol 48.2%"), or two fields as a range ("day 137.90 to 143.05"). */
type Cell<T> =
  | Path<T>
  | { field: Path<T>; label?: string; as?: Format }
  | { range: readonly [Path<T>, Path<T>]; label?: string; as?: Format };

type Lists<T> = {
  [K in keyof T & string]: NonNullable<T[K]> extends readonly (infer Item)[]
    ? Item extends object
      ? K
      : never
    : never;
}[keyof T & string];
type Columns<T> = {
  [K in keyof T & string]: NonNullable<T[K]> extends readonly unknown[] ? K : never;
}[keyof T & string];
type ItemOf<V> = NonNullable<V> extends readonly (infer Item)[] ? Item : never;
/** A list of records one record down ("content.bullets"). */
type NestedLists<T> = {
  [K in keyof T & string]: NonNullable<T[K]> extends readonly unknown[]
    ? never
    : NonNullable<T[K]> extends Record<string, unknown>
      ? `${K}.${Lists<NonNullable<T[K]>>}`
      : never;
}[keyof T & string];
type ListPaths<T> = Lists<T> | NestedLists<T>;
/** The record type of the list at `P`. */
type ItemAt<T, P extends string> = P extends `${infer K}.${infer Rest}`
  ? K extends keyof T
    ? ItemAt<NonNullable<T[K]>, Rest>
    : never
  : P extends keyof T
    ? ItemOf<T[P]>
    : never;

/**
 * What a tool's preview shows of a payload of type `T`. `replacesSummary`: the preview says all its
 * summary does, so the row leaves the summary out.
 * - `list`: one row per record of the list `list` (a field, or a list one record down: "content.bullets"),
 *   its `fields` as cells; a record holding `except` (a failure, say) is left out.
 * - `record`: one row, the payload's `fields`.
 * - `series`: one row of the dates and values columns: first to last date, first to last value, the change
 *   (in percent, or as a difference for rates), the low and the high.
 */
type PreviewHint<T> = { replacesSummary?: true } & (
  | {
      [K in ListPaths<T>]: {
        list: K;
        fields: readonly Cell<ItemAt<T, K>>[];
        except?: Fields<ItemAt<T, K>>;
        /** The field each record states its unit in (a unit's kind: "percent", "index_points", ...). */
        unit?: Path<ItemAt<T, K>>;
      };
    }[ListPaths<T>]
  | { record: readonly Cell<T>[] }
  | {
      series: {
        dates: Columns<T>;
        values: Columns<T>;
        change?: "percent" | "difference";
        /** The values are levels in percent (a yield): written "4.34%". */
        levels?: true;
      };
    }
);

/** A cell as it is read once checked: paths as plain strings. */
type AnyCell =
  | string
  | { field: string; label?: string; as?: Format }
  | { range: readonly [string, string]; label?: string; as?: Format };

/** A hint as it is read once checked. */
type AnyHint = { replacesSummary?: true } & (
  | { list: string; fields: readonly AnyCell[]; except?: string; unit?: string }
  | { record: readonly AnyCell[] }
  | { series: { dates: string; values: string; change?: "percent" | "difference"; levels?: true } }
);

/** A hint as a tool keeps it: for payloads that fit `schema`, against whose type it was checked. */
export type PreviewSpec = { readonly schema: z.ZodType; readonly hint: AnyHint };

/** A preview hint for the payloads of `schema` (a tool's output, or one form of it). */
export function hint<S extends z.ZodType>(schema: S, spec: PreviewHint<z.output<S>>): PreviewSpec {
  return { schema, hint: spec as unknown as AnyHint };
}

/**
 * The preview of a result: from the first of `specs` whose schema the payload fits; for a tool without
 * hints, from the lines of `text` (the body the model reads, its head left out) that start a line and say
 * more than `summary`. Undefined when neither gives a row (the summary alone). `year`: the current year,
 * which dates in it leave out.
 */
export function previewOf(
  payload: unknown,
  {
    specs = [],
    text = "",
    summary = "",
    year,
  }: { specs?: readonly PreviewSpec[]; text?: string; summary?: string; year: number },
): Preview | undefined {
  for (const spec of specs) {
    if (!spec.schema.safeParse(payload).success) continue;
    const preview = fromHint(payload as Record<string, unknown>, spec.hint, year);
    if (preview) return capped(preview);
  }
  if (specs.length) return undefined;
  const fallback = fromText(text, summary);
  return fallback && capped(fallback);
}

/** Each cell within `PREVIEW_CELL_CHARS`, cut between characters as people see them. */
function capped(preview: Preview): Preview {
  return {
    ...preview,
    rows: preview.rows.map((row) => row.map((cell) => shortened(cell, PREVIEW_CELL_CHARS))),
  };
}

function fromHint(payload: Record<string, unknown>, spec: AnyHint, year: number): Preview | undefined {
  const replaces = spec.replacesSummary ? { replacesSummary: true as const } : {};
  if ("list" in spec) {
    const listed = at(payload, spec.list);
    const items = Array.isArray(listed) ? listed : [];
    const records = items.filter(
      (item): item is Record<string, unknown> =>
        !!item && typeof item === "object" && !(spec.except && spec.except in item),
    );
    if (!records.length) return undefined;
    const fields = spec.fields;
    const rows = records.slice(0, PREVIEW_ROWS).map((record) => {
      const unit = spec.unit === undefined ? undefined : at(record, spec.unit);
      return fields.map((cell) => cellText(record, cell, year, typeof unit === "string" ? unit : undefined));
    });
    return withMore({ rows, right: rightColumns(records, fields), ...replaces }, records.length);
  }
  if ("record" in spec) {
    const fields = spec.record;
    const row = fields.map((cell) => cellText(payload, cell, year)).filter(Boolean);
    return row.length ? { rows: [row], ...replaces } : undefined;
  }
  const shown = (value: number) =>
    spec.series.levels ? displayPercent(value, { level: true }) : displayNumber(value);
  const dates = payload[spec.series.dates] as unknown[];
  const values = payload[spec.series.values] as unknown[];
  const known = values.flatMap((value, index) =>
    typeof value === "number" && Number.isFinite(value) ? [{ value, date: dates[index] }] : [],
  );
  const first = known[0];
  const last = known.at(-1);
  if (!first || !last) return undefined;
  const numbers = known.map((one) => one.value);
  const change =
    spec.series.change === "difference"
      ? signed(last.value - first.value)
      : first.value !== 0
        ? displayPercent(((last.value - first.value) / Math.abs(first.value)) * 100, { signed: true })
        : "";
  const row = [
    `${dateText(first.date, year)} to ${dateText(last.date, year)}`,
    `${shown(first.value)} to ${shown(last.value)}`,
    change,
    `low ${shown(Math.min(...numbers))}`,
    `high ${shown(Math.max(...numbers))}`,
  ].filter(Boolean);
  return { rows: [row], ...replaces };
}

/** The first lines of `text` that start at its margin, without the summary's line; then how many more. */
function fromText(text: string, summary: string): Preview | undefined {
  const said = oneLine(summary);
  const lines = text
    .split("\n")
    .filter((line) => line.trim() !== "" && !/^\s/.test(line) && !JSONISH.test(line))
    .map((line) => oneLine(line))
    .filter((line) => line !== said);
  if (!lines.length) return undefined;
  return withMore({ rows: lines.slice(0, PREVIEW_ROWS).map((line) => [line]) }, lines.length);
}

/**
 * A line of data written for the model as JSON ({"maturity":"1M",...}, or a field holding it): no preview
 * for people. A result whose text is all such lines shows its summary alone.
 */
const JSONISH = /^(?:-\s*)?(?:\([\w ]+\)\s*)?(?:[A-Za-z_][\w .-]*:\s*)?(?:\{"|\{\}|\[\{|\["|\[\]|\[-?\d)/;

function withMore(preview: Preview, total: number): Preview {
  return total > preview.rows.length ? { ...preview, more: total - preview.rows.length } : preview;
}

/** The columns written as numbers in every record that has them: right-aligned. */
function rightColumns(records: readonly Record<string, unknown>[], cells: readonly AnyCell[]) {
  const right = cells.flatMap((cell, index) => {
    // A range ("day 137.90 to 143.05") reads from the left; so do dates and text.
    if (typeof cell !== "string" && ("range" in cell || cell.as === "date" || cell.as === "text")) return [];
    const path = typeof cell === "string" ? cell : cell.field;
    const values = records
      .map((record) => at(record, path))
      .filter((value) => value !== null && value !== undefined);
    return values.length && values.every((value) => typeof value === "number") ? [index] : [];
  });
  return right.length ? right : undefined;
}

/** `unit`: the kind of unit the record states its values in, when it does. */
function cellText(record: Record<string, unknown>, cell: AnyCell, year: number, unit?: string): string {
  if (typeof cell === "string") return valueText(at(record, cell), undefined, year);
  const label = cell.label ? `${cell.label} ` : "";
  if ("range" in cell) {
    const [from, to] = cell.range.map((path) => valueText(at(record, path), cell.as, year, unit));
    return from && to ? `${label}${from} to ${to}` : "";
  }
  const value = valueText(at(record, cell.field), cell.as, year, unit);
  return value ? `${label}${value}` : "";
}

/** The value at `path`: a field, or a field of a nested record. */
function at(record: Record<string, unknown>, path: string): unknown {
  return path
    .split(".")
    .reduce<unknown>(
      (value, key) =>
        value && typeof value === "object" ? (value as Record<string, unknown>)[key] : undefined,
      record,
    );
}

/** A date as payloads give it: ISO, a time after it or not, its weekday before it or not ("Friday 2026-11-06"). */
const ISO_DATE = /^(?:[A-Z][a-z]+ )?(\d{4})-(\d{2})-(\d{2})/;

/**
 * Units in which a value is a percent: the value's own, or the unit its change is stated in (percentage
 * points are the change of a percent value).
 */
const PERCENT_UNITS = new Set(["percent", "percentage_points"]);

function valueText(value: unknown, as: Format | undefined, year: number, unit?: string): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "";
    if (as === "percent") return displayPercent(value);
    if (as === "signed") return displayPercent(value, { signed: true });
    if (as === "level" || (as === "unit" && unit !== undefined && PERCENT_UNITS.has(unit)))
      return displayPercent(value, { level: true });
    if (as === "delta") return `${value > 0 ? "+" : ""}${displayNumber(value)}`;
    return displayNumber(value);
  }
  if (typeof value === "string") {
    // Our instrument lines name it, then its key and venue in parentheses: the name says enough here.
    if (as === "instrument") return oneLine(value.replace(/\s*\([^()]*\)\s*$/, ""));
    if (as === "date" || (as === undefined && ISO_DATE.test(value))) return dateText(value, year);
    return oneLine(value);
  }
  if (typeof value === "boolean") return value ? "yes" : "no";
  return "";
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** An ISO date as "Nov 21", with its year when it is not `year`'s. */
export function dateText(value: unknown, year: number): string {
  const match = typeof value === "string" ? ISO_DATE.exec(value) : null;
  if (!match) return typeof value === "string" ? oneLine(value) : "";
  const [, y, m, d] = match;
  const day = `${MONTHS[Number(m) - 1]} ${Number(d)}`;
  return Number(y) === year ? day : `${day} ${y}`;
}

/** A difference with its sign: "+0.13", "-0.13" (a rate's change, in its own units). */
function signed(value: number): string {
  const shown = displayNumber(value);
  return value > 0 ? `+${shown}` : shown;
}
