// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** Arithmetic over figures and series, given or referenced, so the model never computes in its head. */
import { z } from "zod";
import { evaluate, type Value } from "../compute/expression.js";
import { referenceTo } from "./references.js";
import { defineTool, refable, ToolRefusalError } from "./tool.js";
import { displayNumber } from "./tool-text.js";

const VALUE = refable(z.union([z.number(), z.array(z.number().nullable())]));

export function calcTool() {
  return defineTool({
    name: "calc",
    description:
      "Evaluate an arithmetic expression over named values: numbers, + - * / ^, parentheses, lists of figures " +
      "([a / b * 100, c / d * 100] gives each), indexing (closes[-1] is the last), slices (closes[-20:] is the last 20), and abs sqrt ln log exp round min max sum mean stdev count first last pct_change, and the sample statistics var, median, " +
      "percentile(xs, p) (linear between the sorted values, p from 0 to 100), skew and kurt (excess kurtosis), as spreadsheets define them. Give each " +
      `value as a number, a list, or a reference to an earlier result (${referenceTo("e7", "closes")}, ${referenceTo("e7", "closes[-1]")}). Use it ` +
      "for any figure you derive instead of working it out yourself.",
    kind: "compute",
    parallelSafe: true,
    input: z.object({
      expression: z
        .string()
        .min(1)
        .max(2_000)
        .describe("Such as (b - a) / a * 100, mean(closes) or [(b - a) / a * 100, c / d * 100]"),
      values: z
        .record(z.string().regex(/^[A-Za-z_][A-Za-z0-9_]*$/), VALUE)
        .default({})
        .describe("The values the expression names"),
    }),
    output: z.object({
      expression: z.string(),
      value: z.union([z.number(), z.array(z.number().nullable())]),
    }),
    label: ({ expression }) => expression,
    async run({ expression, values }) {
      const result = evaluate(expression, values as Record<string, Value>);
      if ("error" in result) throw new ToolRefusalError(`calc: ${result.error}`);
      // The value is kept exact for later calculations; the text leaves out binary rounding noise.
      const { value } = result;
      return {
        payload: { expression, value: typeof value === "number" ? value : [...value] },
        provenance: { source: "computed", syncs: true },
        // The label shows the expression; the summary, its value at a glance.
        summary:
          typeof value === "number"
            ? displayNumber(value)
            : value.map((item) => (item === null ? "n/a" : displayNumber(item))).join(", "),
      };
    },
  });
}
