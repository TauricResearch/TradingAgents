// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Macro indicators and other reference series (CPI, unemployment, rates, GDP, ...), each value with when
 * it became known. A search picks a series only when the match is certain; otherwise it lists candidates
 * to choose from by key.
 */
import { z } from "zod";
import { message } from "../contracts/index.js";
import type { MacroSeries, SeriesMeta, SeriesObservation } from "../data/capabilities.js";
import { referenceTo } from "./references.js";
import { defineTool, ToolRefusalError } from "./tool.js";
import { fieldNotes, isoDate, oneLine, provenanceOf, roomIn, shownOf } from "./tool-text.js";

type Meta = SeriesMeta;
type Observation = SeriesObservation;
/**
 * How a change is written for each unit kind: a difference in percentage points for percents, a
 * difference in index points for index differences, and a percent change for levels.
 */
const DIFFERENCES: Record<string, string> = {
  percent: "percentage points",
  percentage_points: "percentage points",
  index_points: "index points",
};
/** Months between a period and the one before it, by period kind; others use the observation before. */
const PERIOD_MONTHS: Record<string, number> = { month: 1, quarter: 3, half_year: 6, year: 12 };

const bare = (key: string) => key.replace(/^series:/, "");

function describe(meta: Meta): string {
  const published = meta.as_published;
  return oneLine(
    [
      `${oneLine(meta.name)} (key ${bare(meta.key)})`,
      published?.unit ?? meta.unit?.kind ?? "unit not stated",
      published?.frequency ?? meta.frequency ?? "frequency not stated",
      published?.seasonal_adjustment ?? meta.seasonal_adjustment ?? "",
      meta.shape === "bars" ? "daily price bars" : "",
    ]
      .filter(Boolean)
      .join(", "),
  );
}

/** The first day of the period `months` before the one starting on `start`. */
function monthsBefore(start: string, months: number): string {
  const day = new Date(`${start}T00:00:00Z`);
  day.setUTCMonth(day.getUTCMonth() - months);
  return day.toISOString().slice(0, 10);
}

const CANDIDATES = z.object({
  query: z.string(),
  /** The series it may mean, each described with its key. */
  candidates: z.array(z.string()),
});
const PERIOD = z.object({
  label: z.string(),
  start: z.string().nullable(),
  value: z.number().nullable(),
  /** When the value became known. */
  known_from: z.string().nullable(),
  status: z.string().nullable(),
  evidence: z.string().nullable(),
  notes: z.string().optional(),
});
const OBSERVATIONS = z.object({
  key: z.string(),
  series: z.string(),
  empty_because: z.string().optional(),
  latest: z.string().optional(),
  missing: z.array(z.string()),
  /** Oldest first. */
  periods: z.array(PERIOD),
  /** `end` for the earlier periods, when there are more. */
  continue_end: z.string().nullable(),
});

export function macroSeriesTool(macro: MacroSeries) {
  return defineTool({
    name: "macro_series",
    description:
      "A macro indicator or reference series (inflation, employment, rates, growth, money, sentiment, housing): its " +
      'latest periods, each value with when it became known. Name it ("CPI", "unemployment rate", ' +
      '"10-year Treasury yield") or give its key from an earlier answer.',
    kind: "data",
    parallelSafe: true,
    input: z.object({
      series: z.string().trim().min(2).max(120).describe("A name, an external code such as UNRATE, or a key"),
      periods: z
        .number()
        .int()
        .min(1)
        .max(36)
        .default(13)
        .describe("Latest periods to read (13 covers a year earlier for monthly data)"),
      end: isoDate.optional().describe("The latest period to include, by its first day; for paging back"),
    }),
    output: z.union([OBSERVATIONS, CANDIDATES]),
    async run({ series, periods, end }, { signal }) {
      // Resolve the series: a key is used as given; a search must give one certain match.
      let key: string;
      if (/^(series:)?[a-z0-9_]+(\.[a-z0-9_]+)+$/.test(series)) key = bare(series);
      else {
        const search = await macro.search(series, { signal });
        const found = search.data;
        const wanted = series.toLowerCase();
        const exact = found.filter((meta) => meta.name.toLowerCase() === wanted || bare(meta.key) === wanted);
        // Only an exact name or key is certain; a lone fuzzy result is offered, not assumed.
        const chosen = exact.length === 1 ? exact[0] : undefined;
        if (!found.length)
          throw new ToolRefusalError(`No series matched "${series}". Try another name or a broader term.`);
        if (!chosen) {
          return {
            payload: { query: series, candidates: found.map(describe) },
            provenance: provenanceOf(search),
            summary: message("tool.seriesCandidates", { count: found.length }),
          };
        }
        if (chosen.shape === "bars") {
          throw new ToolRefusalError(
            `${describe(chosen)} is a price series with daily bars, which this tool does not read.`,
          );
        }
        key = bare(chosen.key);
      }

      const sourced = await macro.observations(key, { limit: periods, ...(end ? { end } : {}) }, { signal });
      const answer = sourced.data;
      const meta = answer.series;
      const coverage = answer.coverage;
      const observations = answer.observations ?? [];
      const base = {
        key,
        series: describe(meta),
        missing: (coverage?.missing ?? []).map(
          (m) => `${m.period?.label ?? "?"}${m.reason ? ` (${m.reason})` : ""}`,
        ),
        periods: observations.map((o) => {
          const notes = fieldNotes(o.field_states);
          return {
            label: o.period.label,
            start: o.period.start ?? null,
            value: typeof o.value === "number" ? o.value : null,
            known_from: o.known_from ?? null,
            status: o.status ?? null,
            evidence: o.evidence ?? null,
            ...(notes ? { notes } : {}),
          };
        }),
        continue_end: coverage?.continue_end ?? null,
      };
      const provenance = provenanceOf(sourced, {
        subject: key,
        as_of: observations.at(-1)?.period.start,
      });
      if (!observations.length) {
        return {
          payload: {
            ...base,
            empty_because: `No periods are served${coverage?.complete_reason ? ` (${coverage.complete_reason})` : ""}.`,
          },
          provenance,
          summary: message("tool.seriesEmpty"),
        };
      }
      return {
        payload: { ...base, latest: latestLine(observations, String(meta.unit?.kind ?? "")) },
        provenance,
        summary: message("tool.series", {
          count: observations.length,
          latest: (observations.at(-1) as Observation).period.label,
        }),
      };
    },
    render(answer, { id, room }) {
      if ("candidates" in answer) {
        return [
          `"${answer.query}" is not certain to mean one series; call macro_series again with the key of the one you mean:`,
          ...answer.candidates.map((line) => `- ${line}`),
        ];
      }
      const head = [answer.series, ...(answer.empty_because ? [answer.empty_because] : [])];
      if (!answer.periods.length) return head;
      head.push(answer.latest ?? "", "periods, newest first:");
      const rows = [...answer.periods].reverse().map((o) => {
        const known = o.known_from ? `, known from ${o.known_from.slice(0, 10)}` : "";
        const value = o.value !== null ? String(o.value) : `no value${o.status ? ` (${o.status})` : ""}`;
        return `${o.label}: ${value}${known}${o.evidence ? ` (${o.evidence})` : ""}${o.notes && o.value === null ? `; ${o.notes}` : ""}`;
      });
      const tail = [
        ...(answer.missing.length ? [`missing periods: ${answer.missing.join(", ")}`] : []),
        ...(answer.continue_end
          ? [`earlier periods: macro_series with series=${answer.key}, end=${answer.continue_end}`]
          : []),
      ];
      return [
        ...head,
        ...shownOf(rows, roomIn(room, head, tail), id ? referenceTo(id, "periods") : undefined),
        ...tail,
      ];
    },
  });
}

/**
 * The latest period against the one before it and the same period a year earlier, chosen by date first;
 * a period that is missing or has no value makes that comparison unavailable.
 */
function latestLine(observations: Observation[], kind: string): string {
  const latest = observations.at(-1) as Observation;
  const months = PERIOD_MONTHS[latest.period.kind ?? ""];
  const start = latest.period.start ?? "";
  const previous =
    months && start
      ? observations.find((o) => o.period.start === monthsBefore(start, months))
      : observations.at(-2);
  const yearEarlier = start
    ? observations.find((o) => o.period.start === monthsBefore(start, 12))
    : undefined;
  const change = (from: Observation | undefined, label: string) => {
    if (typeof latest.value !== "number")
      return `${label}: not available (no value for ${latest.period.label})`;
    if (!from) return `${label}: not available (that period is not in this answer)`;
    if (typeof from.value !== "number") return `${label}: not available (no value for ${from.period.label})`;
    const difference = latest.value - from.value;
    const sign = (value: number) => (value >= 0 ? "+" : "");
    if (DIFFERENCES[kind]) {
      return `${label}: ${sign(difference)}${difference.toFixed(2)} ${DIFFERENCES[kind]} (from ${from.value} in ${from.period.label})`;
    }
    if (from.value === 0) return `${label}: not available (the earlier value is 0)`;
    const percent = (difference / Math.abs(from.value)) * 100;
    return `${label}: ${sign(percent)}${percent.toFixed(2)}% (from ${from.value} in ${from.period.label})`;
  };
  return `Latest: ${typeof latest.value === "number" ? latest.value : "no value"} for ${latest.period.label}; ${change(previous, "change from the period before")}; ${change(yearEarlier, "change from a year earlier")}`;
}
