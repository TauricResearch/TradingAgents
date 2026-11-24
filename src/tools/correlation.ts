// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** Correlation between series, given or referenced, aligned on their dates. */
import { z } from "zod";
import { correlate } from "../compute/correlation.js";
import type { Series } from "../compute/series.js";
import { NAME_CHARS, referenceTo } from "./references.js";
import { basisNotes, labelOf, type Prepared, prepare } from "./series.js";
import { defineTool, refable, ToolRefusalError, wholeResult } from "./tool.js";

const GIVEN = z.object({
  label: z.string().min(1).max(NAME_CHARS).describe("A name for the series, such as its symbol"),
  values: refable(z.array(z.number().nullable())).describe(
    `The values, oldest first, or ${referenceTo("e7", "closes")}`,
  ),
  dates: refable(z.array(z.string()))
    .optional()
    .describe(
      `One date per value, or ${referenceTo("e7", "dates")}; with dates on every series they are aligned on shared dates`,
    ),
});
// A series referenced whole is read as returns_risk reads it: its closes on its dates.
const SERIES = z
  .union([GIVEN, wholeResult("A price_history result, named by its symbol unless labelled", { named: true })])
  .describe(
    `{label, values, dates}, or a price_history result referenced whole (${referenceTo("e7")}, or ${referenceTo("e7")} with a label)`,
  );

/** A series as correlate reads it, given or a price_history result's closes on its dates, with its caveats. */
function seriesOf(one: z.output<typeof SERIES>, of: "returns" | "levels"): Series & { prepared?: Prepared } {
  const given = GIVEN.safeParse(one);
  if (!given.success) {
    const prepared = prepare(one, { levels: of === "levels" });
    return { label: prepared.label, values: prepared.values, dates: prepared.dates, prepared };
  }
  const { label, values, dates } = given.data;
  return { label, values: values as (number | null)[], ...(dates ? { dates: dates as string[] } : {}) };
}

export function correlationTool() {
  return defineTool({
    name: "correlation",
    description:
      "Pearson correlation between 2 to 10 series: of their daily simple returns (the default) or their levels. " +
      "Give each series as {label, values, dates}, directly or as references to parts of earlier results (values: " +
      `${referenceTo("e7", "closes")}, dates: ${referenceTo("e7", "dates")}), or a price_history result referenced whole ` +
      `(${referenceTo("e7")}) for its closes; dated series are aligned on the dates they share.`,
    kind: "compute",
    parallelSafe: true,
    input: z.object({
      series: z.array(SERIES).min(2).max(10),
      of: z.enum(["returns", "levels"]).default("returns"),
    }),
    output: z.object({
      of: z.enum(["returns", "levels"]),
      observations: z.number().int(),
      from: z.string().optional(),
      to: z.string().optional(),
      labels: z.array(z.string()),
      matrix: z.array(z.array(z.number().nullable())),
      /** What the sources of series referenced whole say about them: their price basis and caveats. */
      notes: z.array(z.string()),
    }),
    label: ({ series, of }) => `${series.map((one) => labelOf(one)).join(", ")} (${of})`,
    async run({ series, of }) {
      const read = series.map((one) => seriesOf(one, of));
      const correlated = correlate(read, of);
      if ("error" in correlated) throw new ToolRefusalError(`correlation: ${correlated.error}`);
      const sources = read.flatMap((one) => (one.prepared ? [one.prepared] : []));
      const result = {
        ...correlated,
        notes: [...basisNotes(sources), ...sources.flatMap((one) => one.notes)],
      };
      const pair = result.matrix[0]?.[1];
      return {
        payload: result,
        provenance: {
          source: "computed",
          syncs: true,
          ...(result.to ? { as_of: result.to } : {}),
        },
        summary:
          result.labels.length === 2 && pair !== undefined
            ? `${result.labels.join(" / ")}: ${pair === null ? "no movement" : pair.toFixed(2)} over ${result.observations} ${of === "returns" ? "dates" : "values"}`
            : `${result.labels.length} series over ${result.observations} observations`,
      };
    },
  });
}
