// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** A company's profile, analysts' estimates, and who owns and trades its shares. */
import { z } from "zod";
import { errorText, message } from "../contracts/index.js";
import { CALLS } from "../contracts/limits.js";
import { type Ownership, PROFILE_FIELDS, type Profiles } from "../data/capabilities.js";
import { hint } from "./preview.js";
import { referenceTo } from "./references.js";
import { defineTool } from "./tool.js";
import {
  amount,
  fieldNotes,
  instrumentLine,
  isoDate,
  oneLine,
  provenanceOf,
  roomIn,
  shownOf,
  symbol,
} from "./tool-text.js";

export const PROFILE = z.object({
  symbol: z.string(),
  instrument: z.string(),
  /** The listing's trading currency, which market values are stated in. */
  currency: z.string().nullable(),
  refreshed_at: z.string().nullable(),
  /** The company facts the profile names, in its order. */
  facts: z.record(z.string(), z.union([z.string(), z.number()])),
  /** What it does not give, and why. */
  not_given: z.string().optional(),
});

/** The facts a profile's preview shows, when the profile has them. */
const SHOWN_FACTS = z.looseObject({
  sector: z.string().optional(),
  industry: z.string().optional(),
  market_cap: z.number().optional(),
});

/** The profile's fields Tauric serves as fractions (0.2762 for 27.62%), stated as percents. */
const FRACTIONS = new Set([
  "profit_margin",
  "operating_margin",
  "return_on_assets",
  "return_on_equity",
  "revenue_growth",
  "earnings_growth",
  "dividend_yield",
  "payout_ratio",
]);

/** A fact as the profile states it: a fraction as a percent with the fraction its data holds beside it. */
function fact(field: string, value: string | number): string {
  if (typeof value !== "number") return clip(oneLine(value));
  if (!FRACTIONS.has(field)) return amount(value);
  return `${Number((value * 100).toFixed(2))}% (fraction ${value})`;
}

export function profileTool(profiles: Profiles) {
  return defineTool({
    name: "profile",
    description:
      "What a US-listed company is and its current key figures: sector and industry, country, market cap, valuation " +
      "ratios, margins, growth, cash and debt, with when they were refreshed.",
    kind: "data",
    parallelSafe: true,
    input: z.object({ symbol }),
    output: PROFILE,
    // One row: what the company is and how large; the summary (its sector) is in it.
    preview: [
      hint(PROFILE.extend({ facts: SHOWN_FACTS }), {
        record: ["facts.sector", "facts.industry", { field: "facts.market_cap", label: "cap" }],
        replacesSummary: true,
      }),
    ],
    async run({ symbol }, { signal }) {
      const sourced = await profiles.profile(symbol, { signal });
      const answer = sourced.data;
      // The company facts the profile names; nothing else a source sends is shown as a fact.
      const facts = Object.fromEntries(
        PROFILE_FIELDS.flatMap((field) => {
          const value = answer[field];
          return value === null || value === undefined ? [] : [[field, value]];
        }),
      );
      const withheld = fieldNotes(answer.field_states);
      const refreshed = answer.dataset_status?.refreshed_at ?? null;
      return {
        payload: {
          symbol,
          instrument: instrumentLine(answer.instrument),
          currency: answer.instrument?.currency ?? null,
          refreshed_at: refreshed,
          facts,
          ...(withheld ? { not_given: withheld } : {}),
        },
        provenance: provenanceOf(sourced, { subject: symbol, as_of: refreshed?.slice(0, 10) }),
        summary: message("tool.profile", answer.sector ? { sector: String(answer.sector) } : {}),
      };
    },
    render(profile, { id, room }) {
      const head = [
        `${profile.instrument}: profile${profile.refreshed_at ? ` as refreshed ${profile.refreshed_at}` : ""}`,
      ];
      const tail = profile.not_given ? [`not given: ${profile.not_given}`] : [];
      const facts = Object.entries(profile.facts).map(([field, value]) => `${field}: ${fact(field, value)}`);
      return [
        ...head,
        ...shownOf(facts, roomIn(room, head, tail), id ? referenceTo(id, "facts") : undefined),
        ...tail,
      ];
    },
  });
}

const PART = z.record(z.string(), z.unknown());

/** The parts of estimates a preview reads: the consensus and price targets, and the next earnings. */
const ESTIMATES_SHOWN = z.object({
  analyst: z
    .looseObject({
      recommendation: z.string().optional(),
      target_low_price: z.number().optional(),
      target_high_price: z.number().optional(),
    })
    .nullable(),
  calendar: z
    .looseObject({
      // The next earnings, or that none is announced yet (said in words), or none at all.
      earnings: z
        .union([
          z.looseObject({ earnings_date: z.string().optional(), eps_estimate: z.number().optional() }),
          z.string(),
        ])
        .nullish(),
    })
    .nullable(),
});

export function estimatesTool(profiles: Profiles) {
  return defineTool({
    name: "estimates",
    description:
      "What analysts expect of a US-listed company: the consensus rating, price targets, the ratings' distribution and " +
      "EPS estimates; and its calendar: the next announced earnings date with its EPS and revenue estimates (or that " +
      "none is announced yet) and the latest dividend. Each part says when its data was refreshed.",
    kind: "data",
    parallelSafe: true,
    input: z.object({ symbol }),
    output: z.object({
      symbol: z.string(),
      analyst: PART.nullable(),
      calendar: PART.nullable(),
      /** A part that could not be read, and why. */
      unavailable: z.array(z.string()),
    }),
    // One row: the consensus, the price targets' range, and the next earnings with its EPS estimate.
    preview: [
      hint(ESTIMATES_SHOWN, {
        record: [
          "analyst.recommendation",
          { range: ["analyst.target_low_price", "analyst.target_high_price"], label: "target" },
          { field: "calendar.earnings.earnings_date", label: "earnings", as: "date" },
          { field: "calendar.earnings.eps_estimate", label: "EPS est" },
        ],
        replacesSummary: true,
      }),
    ],
    async run({ symbol }, { signal }) {
      // Each part is its own read: one that fails is said, and the other stands.
      const [analyst, calendar] = await Promise.allSettled([
        profiles.analyst(symbol, { signal }),
        profiles.calendar(symbol, { signal }),
      ]);
      const read = [analyst, calendar].flatMap((part) => (part.status === "fulfilled" ? [part.value] : []));
      const first = read[0];
      // Both failing is the call's failure, with the first part's reason.
      if (!first) throw (analyst as PromiseRejectedResult).reason;
      const unavailable = (
        [
          ["analyst", analyst],
          ["calendar", calendar],
        ] as const
      ).flatMap(([name, part]) =>
        part.status === "rejected" ? [`${name}: not available (${oneLine(errorText(part.reason))})`] : [],
      );
      return {
        payload: {
          symbol,
          analyst: analyst.status === "fulfilled" ? analyst.value.data : null,
          calendar: calendar.status === "fulfilled" ? calendar.value.data : null,
          unavailable,
        },
        provenance: provenanceOf(
          {
            source: [...new Set(read.map((part) => part.source))].join(", "),
            after: [...new Set(read.flatMap((part) => part.after))],
            notes: read.flatMap((part) => part.notes),
            ...(read.every((part) => part.syncs) ? { syncs: true as const } : {}),
          },
          { subject: symbol },
        ),
        summary: message("tool.estimates"),
      };
    },
  });
}

const TRADE = z.object({
  date: z.string().nullable(),
  code: z.string().nullable(),
  shares: z.number().nullable(),
  security: z.string().nullable(),
  derivative: z.boolean(),
  exercise_price: z.number().nullable(),
  underlying_shares: z.number().nullable(),
  underlying: z.string().nullable(),
  price: z.number().nullable(),
  /** A (acquired) or D (disposed). */
  acquired_disposed: z.string().nullable(),
  holding_after: z.number().nullable(),
  /** The owners who filed, with their roles. */
  who: z.string(),
  form: z.string().nullable(),
  accession: z.string(),
  accepted_at: z.string().nullable(),
});
const INSIDERS = z.object({
  symbol: z.string(),
  instrument: z.string(),
  coverage: z
    .object({
      from: z.string().nullish(),
      through: z.string().nullish(),
      complete: z.boolean().nullish(),
      requested_before_window: z.boolean().nullish(),
      not_yet_served: z.number().nullish(),
      complete_after: z.string().nullish(),
    })
    .nullable(),
  /** The first date asked about: `start`, or failing one, `end`. */
  asked_from: z.string().nullable(),
  trades: z.array(TRADE),
  next_cursor: z.string().nullable(),
});

const HOLDERS = z.object({
  symbol: z.string(),
  instrument: z.string(),
  quarter: z.string().nullable(),
  complete: z.boolean().nullable(),
  quarters: z.array(z.string()),
  caveats: z.array(z.string()),
  holders: z.array(
    z.object({
      manager: z.string(),
      filed: z.string().nullable(),
      form: z.string().nullable(),
      value: z.number().nullable(),
      value_unit: z.string().nullable(),
      shares: z.number().nullable(),
      shares_type: z.string().nullable(),
      put_call: z.string().nullable(),
      discretion: z.string().nullable(),
      accession: z.string(),
    }),
  ),
  next_cursor: z.string().nullable(),
});

export function ownershipTool(ownership: Ownership) {
  return defineTool({
    name: "ownership",
    description:
      "Who trades and holds a US-listed company's shares. view insider (the default): trades by its officers, " +
      "directors and large holders from SEC Form 4 filings, newest first: date, code (P purchase, S sale, A award, " +
      "M exercise, F tax withholding), shares, price, holding after, and who. view institutional: institutional " +
      "managers' 13F holdings for one quarter (the latest complete one by default), largest first, each manager's " +
      "report as filed.",
    kind: "data",
    parallelSafe: true,
    input: z.object({
      symbol,
      view: z.enum(["insider", "institutional"]).default("insider"),
      quarter: isoDate.optional().describe("institutional: the quarter's end, such as 2026-06-30"),
      start: isoDate.optional().describe("Earliest transaction date"),
      end: isoDate.optional().describe("Latest transaction date"),
      codes: z
        .array(
          z
            .string()
            .regex(/^[A-Za-z]$/, "a one-letter SEC transaction code")
            .transform((code) => code.toUpperCase()),
        )
        .max(10)
        .optional()
        .describe("Only these transaction codes, such as P and S for open-market trades"),
      limit: z.number().int().min(1).max(25).default(14),
      after: z
        .string()
        .min(1)
        .optional()
        .describe("The cursor a previous call returned, with the same filters"),
    }),
    output: z.union([INSIDERS, HOLDERS]),
    async run({ symbol, view, quarter, start, end, codes, limit, after }, { signal }) {
      if (view === "institutional") {
        const sourced = await ownership.holders(
          symbol,
          { limit, ...(quarter ? { quarter } : {}), ...(after ? { after } : {}) },
          { signal },
        );
        const { instrument: described, ...rest } = sourced.data;
        return {
          payload: { symbol, instrument: instrumentLine(described), ...rest },
          provenance: provenanceOf(sourced, { subject: symbol, as_of: rest.quarter }),
          summary: message("tool.holders", {
            count: rest.holders.length,
            quarter: rest.quarter ?? "?",
          }),
        };
      }
      const sourced = await ownership.transactions(
        symbol,
        {
          limit,
          ...(start ? { start } : {}),
          ...(end ? { end } : {}),
          ...(codes?.length ? { codes } : {}),
          ...(after ? { after } : {}),
        },
        { signal },
      );
      const answer = sourced.data;
      const filings = answer.filings ?? {};
      const trades = answer.data.map((row) => {
        const filing = filings[row.accession];
        const who = (filing?.owners ?? [])
          .map((owner) => {
            const role =
              owner.officer_title ??
              (owner.is_director ? "director" : owner.is_ten_percent_owner ? "10% owner" : "");
            return `${oneLine(owner.name ?? "?")}${role ? ` (${oneLine(role)})` : ""}`;
          })
          .join(", ");
        return {
          date: row.transaction_date ?? null,
          code: row.code ?? null,
          shares: row.shares ?? null,
          security: row.security_title ?? null,
          derivative: row.derivative === true,
          exercise_price: row.conversion_or_exercise_price ?? null,
          underlying_shares: row.underlying_shares ?? null,
          underlying: row.underlying_title ?? null,
          price: row.price ?? null,
          acquired_disposed: row.acquired_disposed ?? null,
          holding_after: row.owned_following ?? null,
          who,
          form: filing?.form ?? null,
          accession: row.accession,
          accepted_at: filing?.accepted_at ?? null,
        };
      });
      return {
        payload: {
          symbol,
          instrument: instrumentLine(answer.instrument),
          coverage: answer.coverage ?? null,
          asked_from: start ?? end ?? null,
          trades,
          next_cursor: answer.next_cursor ?? null,
        },
        provenance: provenanceOf(sourced, { subject: symbol, as_of: answer.coverage?.through }),
        summary: message("tool.insider", { count: trades.length, more: Boolean(answer.next_cursor) }),
      };
    },
    render(answer, { id, room }) {
      if ("holders" in answer) return holderLines(answer, id, room);
      const { trades, coverage } = answer;
      const head = [`${answer.instrument}: insider transactions`];
      // An empty page means "none found" only when the source says it covered the dates asked about.
      if (coverage) {
        head.push(`covered: ${coverage.from ?? "?"} to ${coverage.through ?? "?"}`);
        // Said once: when the dates asked start before the coverage, the line below says so.
        if (coverage.requested_before_window && trades.length)
          head.push("part of the dates asked about is before what the source covers");
        if (coverage.not_yet_served)
          head.push(`${coverage.not_yet_served} filings received but not yet processed`);
        if (coverage.complete_after) head.push(`complete only after ${coverage.complete_after}`);
      }
      // "None" is said only of dates the source covers: before its coverage nothing is known either way.
      const asked = answer.asked_from;
      if (!trades.length) {
        head.push(
          coverage?.from && asked && coverage.from > asked
            ? `Insider filings are not available from this source before ${coverage.from}, so none can be shown or ruled out for the dates asked.`
            : coverage?.complete === false
              ? "None found, but the source's coverage of these dates is incomplete."
              : "No transactions found in what is covered.",
        );
      }
      const rows = trades.map((row) => {
        const price = row.price === null ? "" : ` @ ${row.price}`;
        const derivative = row.derivative
          ? ` [derivative${row.exercise_price !== null ? `, exercise ${row.exercise_price}` : ""}${row.underlying_shares !== null ? `, ${amount(row.underlying_shares)} ${oneLine(row.underlying ?? "underlying")}` : ""}]`
          : "";
        return `${row.date ?? "?"} ${row.code ?? "?"} ${amount(row.shares)} ${oneLine(row.security ?? "units")}${derivative}${price} (${row.acquired_disposed === "A" ? "acquired" : row.acquired_disposed === "D" ? "disposed" : "?"}), holding after ${amount(row.holding_after)}; ${row.who || "owner not named"}; ${row.form ?? "?"} ${row.accession}${row.accepted_at ? ` accepted ${row.accepted_at}` : ""}`;
      });
      const next = answer.next_cursor
        ? [`more: ownership with after=${answer.next_cursor} and the same filters`]
        : [];
      return [
        ...head,
        ...shownOf(rows, roomIn(room, head, next), id ? referenceTo(id, "trades") : undefined),
        ...next,
      ];
    },
  });
}

/** A quarter's 13F holders, largest first, each as its manager filed it. */
function holderLines(answer: z.output<typeof HOLDERS>, id: string | undefined, room: number): string[] {
  const head = [
    `${answer.instrument}: institutional holders (13F) for the quarter ending ${answer.quarter ?? "?"}; each line is one manager's report as filed, never summed across managers`,
    // What the source covers of the quarter's filing days decides what an empty or short list means.
    ...(answer.complete === null
      ? [
          "the source covers none of this quarter's filing days, so holdings can be neither shown nor ruled out",
        ]
      : answer.complete === false
        ? ["the source covers this quarter's filings in part: more holders may report"]
        : []),
    ...(answer.quarters.length ? [`quarters served: ${answer.quarters.join(", ")}`] : []),
    ...answer.caveats,
    ...(answer.holders.length || answer.complete === null
      ? []
      : ["No holdings reported for this quarter in what is covered."]),
  ];
  const rows = answer.holders.map(
    (row) =>
      `${oneLine(row.manager)}: ${
        row.put_call
          ? // An option line's quantity and value are its underlying's: a notional, not the options' worth.
            `${row.put_call.toLowerCase()} options on ${amount(row.shares)} underlying shares, notional value ${amount(row.value)}`
          : `${amount(row.shares)} ${row.shares_type === "PRN" ? "principal" : "shares"}, value ${amount(row.value)}`
      }${row.value_unit ? ` ${row.value_unit}` : ""}${row.discretion ? `; discretion ${row.discretion}` : ""}; ${row.form ?? "13F"} ${row.accession}${row.filed ? ` filed ${row.filed}` : ""}`,
  );
  const next = answer.next_cursor
    ? [`more: ownership with view=institutional, after=${answer.next_cursor} and the same quarter`]
    : [];
  return [
    ...head,
    ...shownOf(rows, roomIn(room, head, next), id ? referenceTo(id, "holders") : undefined),
    ...next,
  ];
}

/** A long field cut to a readable length, saying how much was left out. */
function clip(text: string, limit: number = CALLS.longFieldChars): string {
  return text.length <= limit ? text : `${text.slice(0, limit)}… (${text.length - limit} more characters)`;
}
