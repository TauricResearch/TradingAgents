// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** Today's market at a glance: one view per call (indices and sectors, movers, rates, commodities, ...). */
import { z } from "zod";
import { message } from "../contracts/index.js";
import { MARKET_VIEWS, type Markets } from "../data/capabilities.js";
import { hint } from "./preview.js";
import { referenceTo } from "./references.js";
import { defineTool } from "./tool.js";
import { oneLine, provenanceOf, roomIn, shownOf } from "./tool-text.js";

const OUT = z.object({
  view: z.enum(MARKET_VIEWS),
  through: z.string().nullable(),
  stale: z.boolean(),
  summary: z.record(z.string(), z.unknown()),
  coverage: z
    .object({
      requested: z.number().nullable(),
      measured: z.number().nullable(),
      byReason: z.array(z.object({ reason: z.string().nullable(), count: z.number() })),
    })
    .nullable(),
  missing: z.array(z.object({ key: z.string(), reason: z.string().nullish() })),
  rows: z.array(z.record(z.string(), z.unknown())),
  more: z.boolean(),
});

/** The fields a preview reads of the views' common shapes; the rows hold more (their basis, times). */
const NUMBER = z.number().nullable().optional();
/** A quoted instrument (an index, a sector, a yield, a future, a pair): most views' rows. */
const UNIT = z.object({ kind: z.string() }).nullable().optional();
/**
 * A quoted instrument (an index, a sector, a yield, a future, a pair): most views' rows. A change's unit is
 * stated when it is not the instrument's money: percentage points say the price is a percent (a yield).
 */
const QUOTED = z.object({
  instrument: z.string(),
  price: NUMBER,
  change: z.object({ absolute: NUMBER, percent: NUMBER, absolute_unit: UNIT }).nullable().optional(),
});
/** A point of the yield curve, in its unit. */
const POINT = z.object({ maturity: z.string(), unit: UNIT, latest: z.object({ value: NUMBER }) });
/** The VIX term structure: a snapshot, all in its summary. */
const TERM = z.object({ price: NUMBER }).nullable().optional();
const VOLATILITY = z.object({
  view: z.literal("volatility"),
  summary: z.object({
    spot: TERM,
    vix_9d: TERM,
    vix_3m: TERM,
    vix_6m: TERM,
    vix_1y: TERM,
    structure: z.string().nullable().optional(),
  }),
});

export function marketsTool(markets: Markets) {
  return defineTool({
    name: "markets",
    description:
      "Today's market, one view per call: equity_summary (major indices, sectors, breadth), sectors (the sector " +
      "ETFs ranked), gainers, losers, most_active, volatility (the VIX term structure), yield_curve, central_banks, " +
      "credit_spreads, energy, metals, agriculture (front-month futures), fx (major pairs), cross_asset (yields, " +
      "VIX, dollar, gold, oil), crypto (largest assets), macro (latest indicators and their changes), indices (the " +
      "major US indices), sector_rotation (leading and lagging sectors), tips_breakevens (market-implied inflation), " +
      "rate_indicators (fed funds, SOFR, the MOVE index), commodity_benchmarks (commodity volatility and benchmark " +
      "indices), livestock (cattle and hog futures).",
    kind: "data",
    parallelSafe: true,
    input: z.object({ view: z.enum(MARKET_VIEWS) }),
    output: OUT,
    // The view's newest rows as people read them; a view of another shape shows its summary alone.
    preview: [
      hint(z.object({ rows: z.array(POINT).min(1) }), {
        list: "rows",
        fields: ["maturity", { field: "latest.value", as: "unit" }],
        unit: "unit.kind",
      }),
      hint(z.object({ rows: z.array(QUOTED).min(1) }), {
        list: "rows",
        fields: [
          { field: "instrument", as: "instrument" },
          { field: "price", as: "unit" },
          { field: "change.absolute", as: "delta" },
          { field: "change.percent", as: "signed" },
        ],
        unit: "change.absolute_unit.kind",
      }),
      hint(VOLATILITY, {
        record: [
          { field: "summary.spot.price", label: "VIX" },
          { field: "summary.vix_9d.price", label: "9 day" },
          { field: "summary.vix_3m.price", label: "3 month" },
          { field: "summary.vix_6m.price", label: "6 month" },
          { field: "summary.vix_1y.price", label: "1 year" },
          { field: "summary.structure", as: "text" },
        ],
      }),
    ],
    async run({ view }, { signal }) {
      const sourced = await markets.view(view, { signal });
      const answer = sourced.data;
      return {
        payload: {
          view,
          through: answer.through ?? null,
          stale: answer.stale === true,
          summary: answer.summary,
          coverage: answer.coverage,
          missing: answer.missing,
          rows: answer.rows,
          more: answer.more,
        },
        provenance: provenanceOf(sourced, { as_of: answer.through }),
        // A snapshot (the VIX term structure) is its summary, with no rows.
        summary: message("tool.market", answer.rows.length ? { count: answer.rows.length } : {}),
      };
    },
    render(answer, { id, room }) {
      const head = [
        `${answer.view.replaceAll("_", " ")}, through ${answer.through ?? "?"}${answer.stale ? " (the source calls it stale)" : ""}`,
        ...(Object.keys(answer.summary).length ? [oneLine(JSON.stringify(answer.summary))] : []),
      ];
      const coverage = answer.coverage;
      const counted =
        coverage &&
        coverage.requested !== null &&
        coverage.measured !== null &&
        coverage.measured < coverage.requested
          ? [
              `covers ${coverage.measured} of ${coverage.requested}${coverage.byReason.length ? ` (left out: ${coverage.byReason.map((r) => `${r.count} ${r.reason ?? "without a stated reason"}`).join(", ")})` : ""}`,
            ]
          : [];
      const missing = answer.missing.length
        ? [
            `${counted.length ? "some of those left out" : "not included"}: ${answer.missing.map((m) => oneLine(`${m.key}${m.reason ? ` (${m.reason})` : ""}`)).join(", ")}`,
          ]
        : [];
      const tail = [
        ...counted,
        ...missing,
        ...(answer.more ? ["(the source has more rows than these)"] : []),
      ];
      const rows = answer.rows.map((row) => oneLine(JSON.stringify(row)));
      return [
        ...head,
        ...shownOf(rows, roomIn(room, head, tail), id ? referenceTo(id, "rows") : undefined),
        ...tail,
      ];
    },
  });
}
