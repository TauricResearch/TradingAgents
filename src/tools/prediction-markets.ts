// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** Prediction-market odds on a topic, from Polymarket: open markets, by traded volume. */

import { z } from "zod";
import { type Clock, message, systemClock } from "../contracts/index.js";
import { CALLS } from "../contracts/limits.js";
import type { MarketOdds as Market, PredictionMarkets } from "../data/capabilities.js";
import { DataError } from "../data/errors.js";
import { referenceTo } from "./references.js";
import { defineTool } from "./tool.js";
import { oneLine, provenanceOf, roomIn, shownOf, sourceOf } from "./tool-text.js";

/** A probability as a whole percent, keeping two significant digits of the distance near 0 and 100. */
export function odds(price: number): string {
  const percent = price * 100;
  if (percent > 0 && percent < 1) return `${Number(percent.toPrecision(2))}%`;
  if (percent > 99 && percent < 100)
    return `${Number((100 - Number((100 - percent).toPrecision(2))).toFixed(4))}%`;
  return `${Math.round(percent)}%`;
}

const MARKET = z.object({
  question: z.string(),
  /** Outcomes and their prices (probabilities, 0 to 1), the leading one first. */
  outcomes: z.array(z.object({ name: z.string(), price: z.number() })),
  volume: z.number().nullable(),
  resolves: z.string(),
  /** The first outcome's change over a week, in probability (0.05 is 5 points). */
  week_change: z.number().nullable(),
  url: z.string().nullable(),
});
const OUT = z.object({
  topic: z.string(),
  as_of: z.string(),
  markets: z.array(MARKET),
  /** Matching markets left out because the source described them incompletely. */
  dropped: z.number(),
  more: z.boolean(),
});

export function predictionMarketsTool(markets: PredictionMarkets, now: Clock = systemClock) {
  return defineTool({
    name: "prediction_markets",
    description:
      "Market-implied odds on events (central bank decisions, elections, geopolitics, economic releases, crypto) from " +
      "open Polymarket markets, deepest first. Today only: the source keeps no history.",
    kind: "data",
    parallelSafe: true,
    input: z.object({
      topic: z.string().trim().min(2).max(100).describe('A short topic, such as "Fed rate cut December"'),
      limit: z.number().int().min(1).max(10).default(6),
    }),
    output: OUT,
    async run({ topic, limit }, { signal }) {
      const at = now();
      const sourced = await markets.search(topic, at, { signal });
      const { open, dropped, more } = sourced.data;
      // Deepest first among markets with live odds; odds pinned near 0 or 100 come after, and one event fills
      // at most a few rows (an event such as "how many cuts" lists a market per count).
      const pinned = (m: Market) => {
        const price = (m.outcomes[0] as { price: number }).price;
        return price <= 0.01 || price >= 0.99;
      };
      const perEvent = new Map<string, number>();
      const shown = [...open]
        .sort((a, b) => Number(pinned(a)) - Number(pinned(b)) || (b.volume ?? -1) - (a.volume ?? -1))
        .filter((m) => {
          const event = m.url ?? m.question;
          const count = (perEvent.get(event) ?? 0) + 1;
          perEvent.set(event, count);
          return count <= CALLS.marketsPerEvent;
        })
        .slice(0, limit);
      if (!shown.length && dropped) {
        throw new DataError(
          "unavailable",
          `${sourced.source} described ${dropped} matching markets in a form this client does not read, and listed no readable open one.`,
          { source: sourceOf(sourced) },
        );
      }
      return {
        payload: {
          topic,
          as_of: `${at.toISOString().slice(0, 16)}Z`,
          markets: shown.map((m) => ({
            question: m.question,
            outcomes: m.outcomes.map((o) => ({ name: o.name, price: o.price })),
            volume: m.volume ?? null,
            resolves: m.endDate.slice(0, 10),
            week_change: m.oneWeekChange ?? null,
            url: m.url ?? null,
          })),
          dropped: dropped ?? 0,
          more: Boolean(more),
        },
        provenance: provenanceOf(sourced, { subject: topic }),
        summary: message("tool.markets", { count: shown.length }),
      };
    },
    render({ topic, as_of, markets: found, dropped, more }, { id, room }) {
      const head = [
        `Open markets matching "${topic}" on the first page of its search, as of ${as_of} (the crowd's priced odds, not a forecast). Ranked by traded volume, with odds pinned below 1% or above 99% after the rest, at most ${CALLS.marketsPerEvent} markets per event:`,
      ];
      const caveats = [
        ...(dropped
          ? [
              `${dropped} matching market${dropped === 1 ? " was" : "s were"} left out because the source described ${dropped === 1 ? "it" : "them"} incompletely.`,
            ]
          : []),
        ...(more ? ["The search has more results than this page."] : []),
      ];
      if (!found.length) {
        return [
          ...head,
          more
            ? "No open markets on the first page of results; the search has more results."
            : "No open markets matched. Coverage is mostly macro, political, geopolitical and crypto events.",
        ];
      }
      const rows = found.map((m) => {
        const first = m.outcomes[0] as { name: string; price: number };
        const others = m.outcomes.slice(1, 3).map((o) => `${oneLine(o.name)} ${odds(o.price)}`);
        const week =
          m.week_change !== null && m.week_change !== 0
            ? `, ${oneLine(first.name)} ${m.week_change > 0 ? "+" : ""}${(m.week_change * 100).toFixed(1)} points over a week`
            : "";
        const volume =
          m.volume !== null ? `$${Math.round(m.volume).toLocaleString("en-US")} traded` : "volume not stated";
        return `- ${oneLine(m.question)}: ${oneLine(first.name)} ${odds(first.price)}${others.length ? ` (${others.join(", ")})` : ""}; ${volume}; resolves ${m.resolves}${week}${m.url ? `; ${oneLine(m.url)}` : ""}`;
      });
      return [
        ...head,
        ...shownOf(rows, roomIn(room, head, caveats), id ? referenceTo(id, "markets") : undefined),
        ...caveats,
      ];
    },
  });
}
