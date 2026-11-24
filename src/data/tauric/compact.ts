// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Tauric answers compacted to what a reader needs, for answers shown whole (market snapshots, analyst
 * consensus, a security's calendar): instruments and series by name, key and unit; the reason a value
 * is missing; a row's freshness only when it is stale; dates with their weekdays; bookkeeping, nulls and
 * silent defaults left out.
 */

import { withWeekday } from "../../contracts/index.js";

/** Fields that describe how an answer was served, not the market. */
const BOOKKEEPING = new Set([
  "object",
  "next_cursor",
  "population",
  "classification",
  "listing",
  "refreshed_at",
  "price_age_seconds",
  "price_precision",
  "continuous",
  "venue",
]);

/** Values that say nothing a reader needs: a quote that is not stale, a unit not scaled. */
const SILENT: Json = { stale: false, multiplier: 1, quote_kind: "snapshot", value_kind: "observed" };

type Json = Record<string, unknown>;

/**
 * An instrument or series, by name and key with what its values are measured in: an instrument's
 * currency and any price scale (corn in cents), a series' unit as published or as stated.
 */
function named(kind: string, value: Json): string {
  const scale =
    typeof value.price_scale === "number" && value.price_scale !== 1 ? value.price_scale : undefined;
  const unit = value.unit as Json | null | undefined;
  const published = (value.as_published as Json | null | undefined)?.unit;
  const measure =
    kind === "series"
      ? ((published as string | undefined) ??
        (unit
          ? `${String(unit.kind)}${unit.multiplier && unit.multiplier !== 1 ? ` x${String(unit.multiplier)}` : ""}`
          : undefined))
      : [
          value.currency,
          scale ? `prices in units of ${scale} ${String(value.currency ?? "")}`.trim() : undefined,
        ]
          .filter(Boolean)
          .join(", ");
  return `${String(value.name ?? value.key)} (${String(value.key)}${measure ? `; ${measure}` : ""})`;
}

/** Fields whose null says something: an amount in a currency not stated, a completeness not known yet. */
const STATED_NULLS = new Set(["currency", "complete"]);

/**
 * `value` without bookkeeping, nulls and empty values: instruments and series by name, key and unit;
 * field states as the reason each field is null or limited; a row's freshness only when it is stale.
 * A dataset's status keeps when it was refreshed, so data refreshed long ago does not pass for today's.
 */
export function compact(value: unknown, inStatus = false): unknown {
  if (Array.isArray(value)) {
    const items = value.map((item) => compact(item)).filter((item) => item !== undefined);
    return items.length ? items : undefined;
  }
  if (value === null || value === undefined) return undefined;
  // A date carries its weekday, so the model reads it instead of working it out.
  if (typeof value === "string") return withWeekday(value);
  if (typeof value !== "object") return value;
  const kept = Object.entries(value as Json).flatMap(([key, inner]): [string, unknown][] => {
    if (inner === null && STATED_NULLS.has(key)) return [[key, "not stated"]];
    if (key === "from_value" && inner === null && isChange(value as Json))
      return [[key, noBase(value as Json)]];
    if (key === "refreshed_at" && inStatus && inner) return [[key, inner]];
    if (BOOKKEEPING.has(key) || SILENT[key] === inner) return [];
    if ((key === "instrument" || key === "series") && inner && typeof inner === "object")
      return [[key, named(key, inner as Json)]];
    if (key === "field_states" && inner && typeof inner === "object") {
      const reasons = Object.entries(inner as Record<string, { reason?: string } | undefined>).flatMap(
        ([field, state]) => (state?.reason ? [[field, state.reason]] : []),
      );
      return reasons.length ? [["why", Object.fromEntries(reasons)]] : [];
    }
    if (key === "freshness" && inner && typeof inner === "object") {
      const { stale, through } = inner as Json;
      return stale === true ? [["stale", through ? `through ${String(through)}` : true]] : [];
    }
    const shown = compact(inner, key.endsWith("status"));
    return shown === undefined ? [] : [[key, shown]];
  });
  return kept.length ? Object.fromEntries(kept) : undefined;
}

/** A change from one value to another, as Tauric gives it: one measured on a stated basis. */
function isChange(value: Json): boolean {
  return typeof value.basis === "string";
}

/**
 * A change without a base value (the earlier period was not published): said so, so the missing change
 * is not read as no change, nor worked out from another period.
 */
function noBase(change: Json): string {
  const period = (change.from_period as Json | null | undefined)?.label;
  return `no base value${period ? ` (${String(period)} not available)` : ""}`;
}
