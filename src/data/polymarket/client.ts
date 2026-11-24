// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Polymarket's public market search (no key). It serves live odds of open markets and keeps no history,
 * so it can answer only about today. Markets the source describes incompletely are counted, not
 * guessed at, and a malformed answer is the source being unavailable, never an empty search.
 */

import { z } from "zod";
import { message } from "../../contracts/index.js";
import { ANSWER_BYTES, CALLS, REQUEST_MS } from "../../contracts/limits.js";
import { bounded } from "../bounded.js";
import type { MarketOdds, MarketSearch } from "../capabilities.js";
import { DataError } from "../errors.js";

const SOURCE = "Polymarket";
const BASE = "https://gamma-api.polymarket.com";

/** A JSON-encoded list of strings, as the search answers outcomes and prices. */
const stringList = z.string().transform((text, context) => {
  try {
    const value = JSON.parse(text);
    if (Array.isArray(value) && value.every((item) => typeof item === "string" && item.trim() !== "")) {
      return value as string[];
    }
  } catch {
    // reported below
  }
  context.addIssue({ code: "custom", message: "not a list of strings" });
  return z.NEVER;
});

const marketSchema = z.object({
  question: z.string().min(1),
  outcomes: stringList,
  outcomePrices: stringList,
  volumeNum: z.number().nonnegative().optional(),
  endDate: z.string().refine((value) => !Number.isNaN(Date.parse(value))),
  closed: z.boolean(),
  active: z.boolean().optional(),
  archived: z.boolean().optional(),
  oneWeekPriceChange: z.number().min(-1).max(1).optional(),
});
const answerSchema = z.object({
  events: z
    .array(z.object({ slug: z.string().optional(), markets: z.array(z.unknown()).optional() }))
    .optional(),
  pagination: z.object({ hasMore: z.boolean().optional() }).optional(),
});

export class PolymarketClient {
  constructor(private readonly fetchImpl: typeof globalThis.fetch = fetch) {}

  /** The open markets on the first page of results for `topic`. */
  async search(topic: string, now: Date, { signal }: { signal?: AbortSignal } = {}): Promise<MarketSearch> {
    const url = `${BASE}/public-search?${new URLSearchParams({ q: topic, limit_per_type: String(CALLS.marketSearchPage) })}`;
    let response: Response;
    try {
      response = await this.fetchImpl(url, {
        signal: AbortSignal.any([AbortSignal.timeout(REQUEST_MS.polymarket), ...(signal ? [signal] : [])]),
      });
    } catch (error) {
      if (signal?.aborted) throw error;
      throw new DataError("unavailable", "Polymarket could not be reached.", { source: SOURCE });
    }
    if (response.status === 429) {
      throw new DataError("rate_limited", "Polymarket is limiting requests.", {
        source: SOURCE,
        status: 429,
      });
    }
    if (!response.ok) {
      throw new DataError("unavailable", `Polymarket answered ${response.status}.`, {
        source: SOURCE,
        status: response.status,
      });
    }
    const body = await bounded(
      response,
      ANSWER_BYTES,
      () =>
        new DataError("unavailable", message("data.answerTooLong", { source: SOURCE, bytes: ANSWER_BYTES }), {
          source: SOURCE,
        }),
    )
      .json()
      .catch((error: unknown) => {
        if (error instanceof DataError) throw error;
        return undefined;
      });
    const parsed = answerSchema.safeParse(body);
    if (!parsed.success) {
      throw new DataError("unavailable", "Polymarket answered in a form this client does not read.", {
        source: SOURCE,
      });
    }
    const open: MarketOdds[] = [];
    let dropped = 0;
    for (const event of parsed.data.events ?? []) {
      for (const raw of event.markets ?? []) {
        const market = marketSchema.safeParse(raw);
        const prices = market.success ? market.data.outcomePrices.map(Number) : [];
        if (
          !market.success ||
          !prices.length ||
          market.data.outcomes.length !== prices.length ||
          prices.some((price) => !Number.isFinite(price) || price < 0 || price > 1)
        ) {
          dropped++;
          continue;
        }
        const m = market.data;
        if (m.closed || m.archived === true || m.active === false || Date.parse(m.endDate) <= now.getTime()) {
          continue;
        }
        open.push({
          question: m.question,
          outcomes: m.outcomes.map((name, i) => ({ name, price: prices[i] as number })),
          endDate: m.endDate,
          ...(m.volumeNum !== undefined ? { volume: m.volumeNum } : {}),
          ...(m.oneWeekPriceChange !== undefined ? { oneWeekChange: m.oneWeekPriceChange } : {}),
          ...(event.slug ? { url: `https://polymarket.com/event/${event.slug}` } : {}),
        });
      }
    }
    return { open, dropped, more: parsed.data.pagination?.hasMore === true };
  }
}
