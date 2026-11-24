// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Tauric's market snapshots as market views: each view's route, and its answer compacted to what a
 * reader needs. Every row names its instrument by key and name only; the bookkeeping a snapshot
 * repeats on each row (classification, listing, refresh times, precision) is left out.
 */

import type { MarketView, MarketViewName } from "../capabilities.js";
import type { TauricClient } from "./client.js";
import { compact } from "./compact.js";
import type { paths } from "./schema.generated.js";

type Json = Record<string, unknown>;

/** Each view's route and query. */
const VIEWS: {
  readonly [View in MarketViewName]: { path: keyof paths; query?: Record<string, string | number> };
} = {
  equity_summary: { path: "/v1/markets/equity/summary" },
  sectors: { path: "/v1/markets/equity/sectors" },
  gainers: { path: "/v1/markets/equity/movers", query: { type: "gainers", limit: 10 } },
  losers: { path: "/v1/markets/equity/movers", query: { type: "losers", limit: 10 } },
  most_active: { path: "/v1/markets/equity/movers", query: { type: "active", limit: 10 } },
  volatility: { path: "/v1/markets/equity/volatility-term-structure" },
  yield_curve: { path: "/v1/markets/rates/yield-curve" },
  central_banks: { path: "/v1/markets/rates/central-bank-rates" },
  credit_spreads: { path: "/v1/markets/credit/spreads" },
  energy: { path: "/v1/markets/commodity/energy" },
  metals: { path: "/v1/markets/commodity/metals" },
  agriculture: { path: "/v1/markets/commodity/agriculture" },
  fx: { path: "/v1/markets/fx/pairs", query: { limit: 25 } },
  cross_asset: { path: "/v1/markets/cross-asset" },
  crypto: { path: "/v1/markets/crypto/assets", query: { limit: 20 } },
  macro: { path: "/v1/markets/macro/snapshot", query: { limit: 25 } },
  indices: { path: "/v1/markets/equity/indices" },
  sector_rotation: { path: "/v1/markets/equity/sectors/rotation" },
  tips_breakevens: { path: "/v1/markets/rates/tips-breakevens" },
  rate_indicators: { path: "/v1/markets/rates/market-indicators" },
  commodity_benchmarks: { path: "/v1/markets/commodity/benchmarks" },
  livestock: { path: "/v1/markets/commodity/livestock" },
};

export async function marketView(client: TauricClient, view: MarketViewName, call = {}): Promise<MarketView> {
  const { path, query = {} } = VIEWS[view];
  const answer = (await client.marketView(path, query, call)) as Json;
  const population = answer.population as
    | {
        requested?: number;
        measured?: number;
        missing?: { key: string; reason?: string | null }[];
        missing_by_reason?: { reason?: string | null; count: number }[];
      }
    | undefined;
  const freshness = answer.freshness as { through?: string | null; stale?: boolean | null } | undefined;
  // A list view's rows are its data; a single snapshot (the VIX term structure) is all summary.
  const rows = Array.isArray(answer.data) ? (answer.data as unknown[]) : [];
  // The macro snapshot lists every group's members beside its rows; the groups' names are enough.
  const { data: _data, groups, freshness: _freshness, ...rest } = answer;
  if (Array.isArray(groups)) rest.groups = groups.map((group) => (group as Json).key);
  return {
    rows: rows.map((row) => (compact(row) ?? {}) as Json),
    summary: (compact(rest) ?? {}) as Json,
    coverage: population
      ? {
          requested: population.requested ?? null,
          measured: population.measured ?? null,
          byReason: (population.missing_by_reason ?? []).map(({ reason, count }) => ({
            reason: reason ?? null,
            count,
          })),
        }
      : null,
    missing: (population?.missing ?? []).map(({ key, reason }) => ({ key, reason: reason ?? null })),
    through: freshness?.through ?? null,
    stale: freshness?.stale ?? null,
    more: typeof answer.next_cursor === "string",
  };
}
