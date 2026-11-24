// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Builds each capability from the routing table and the providers that implement it. A call goes to
 * the first provider in the chain; the next is asked only when one could not answer for reasons that
 * are not about the market (it does not cover the request, was unreachable, busy, out of quota, or
 * refused the key). An answer, even an empty or partial one, is returned as it came, and `no_data` or
 * `invalid` from any provider ends the call. Every answer names its provider and what failed before it.
 */
import { errorText, message, NOTICE } from "../contracts/index.js";
import {
  type Capabilities,
  type Capability,
  type DataProvider,
  METHODS,
  type QuoteBatch,
  type Sourced,
} from "./capabilities.js";
import { DataError, type DataErrorKind, LISTING_STATE_CODES } from "./errors.js";
import { type ProviderName, ROUTES } from "./routes.js";

/** Kinds after which the next provider is asked. */
const NEXT: ReadonlySet<DataErrorKind> = new Set([
  "unsupported",
  "unavailable",
  "rate_limited",
  "quota",
  "rejected",
  "not_configured",
]);

/**
 * Methods that answer for several instruments at once: an instrument the source could not answer for,
 * for a reason that sends one call on, is asked of the sources after it.
 */
const BATCHES: ReadonlySet<string> = new Set(["quotes.many"]);

/** Each capability's name as a sentence starts it. */
export const CAPABILITY_LABELS: { readonly [Name in Capability]: string } = {
  quotes: "Quotes",
  priceHistory: "Price history",
  statements: "Financial statements",
  filings: "SEC filings",
  news: "News",
  profiles: "Company profiles",
  ownership: "Insider and institutional ownership",
  corporateActions: "Corporate actions",
  syntheses: "Tauric AI's research",
  crossSections: "Sector screens",
  technicals: "Technical indicators",
  macroSeries: "Macro series",
  instruments: "Instrument search",
  markets: "Market overviews",
  predictionMarkets: "Prediction markets",
};

type Routed = {
  capabilities: Capabilities;
  /** The capabilities some configured provider serves. */
  available: ReadonlySet<Capability>;
};

type Method = (...args: unknown[]) => Promise<unknown>;
type Link = { source: string; implementation: Partial<Record<string, Method>>; syncs?: true };

/** The providers a setup has, by name. */
export type Providers = { readonly [Name in ProviderName]?: DataProvider };

/**
 * What adds a capability no source here serves: a Tauric key, for the capabilities named, run as
 * `app key tauric`. Without it (or for another capability) the answer only says it is not available.
 */
export type KeyFix = { app: string; capabilities: ReadonlySet<Capability> };

export function route(providers: Providers, { keyFix }: { keyFix?: KeyFix } = {}): Routed {
  const available = new Set<Capability>();
  const capabilities: Partial<Record<Capability, unknown>> = {};
  for (const capability of Object.keys(ROUTES) as Capability[]) {
    const chain: Link[] = ROUTES[capability].flatMap((name) => {
      const provider = providers[name];
      const implementation = provider?.capabilities[capability];
      return provider && implementation
        ? [
            {
              source: provider.name,
              implementation: implementation as unknown as Partial<Record<string, Method>>,
              ...(provider.syncs ? { syncs: true as const } : {}),
            },
          ]
        : [];
    });
    if (chain.length) available.add(capability);
    capabilities[capability] = chained(capability, chain, keyFix);
  }
  return { capabilities: capabilities as Capabilities, available };
}

/** The capability's methods, each tried along the chain. */
function chained(capability: Capability, chain: readonly Link[], keyFix: KeyFix | undefined): unknown {
  return Object.fromEntries(
    (METHODS[capability] as readonly string[]).map((method) => [
      method,
      (...args: unknown[]) => call(capability, chain, method, args, keyFix),
    ]),
  );
}

async function call(
  capability: Capability,
  chain: readonly Link[],
  method: string,
  args: unknown[],
  keyFix: KeyFix | undefined,
): Promise<Sourced<unknown>> {
  // The providers that serve this method: one may serve a capability's other methods only.
  const serving = chain.filter((link) => link.implementation[method]);
  if (!serving.length) {
    throw new DataError(
      "not_configured",
      keyFix?.capabilities.has(capability)
        ? message("data.needsKey", { capability: CAPABILITY_LABELS[capability], app: keyFix.app })
        : message("data.notAvailable", { capability: CAPABILITY_LABELS[capability] }),
      {
        source: CAPABILITY_LABELS[capability],
        code: NOTICE.capabilityUnavailable,
      },
    );
  }
  const signal = (args.at(-1) as { signal?: AbortSignal } | undefined)?.signal;
  const failed: { source: string; error: DataError }[] = [];
  for (const [index, { source, implementation, syncs }] of serving.entries()) {
    const fn = implementation[method] as Method;
    let data: unknown;
    try {
      data = await fn.apply(implementation, args);
    } catch (error) {
      // A cancelled call goes no further down the chain.
      if (!(error instanceof DataError) || !NEXT.has(error.kind) || signal?.aborted) {
        throw failed.length && error instanceof DataError ? after(failed, error) : error;
      }
      failed.push({ source, error });
      continue;
    }
    const answer: Sourced<unknown> = {
      data,
      source,
      notes: failed.length ? [fellBack(failed, source)] : [],
      after: failed.map((f) => f.source),
      ...(syncs ? { syncs } : {}),
    };
    return BATCHES.has(`${capability}.${method}`)
      ? await completed(
          answer as Sourced<QuoteBatch>,
          (rest) => call(capability, serving.slice(index + 1), method, [rest, ...args.slice(1)], keyFix),
          signal,
        )
      : answer;
  }
  // Every provider failed for reasons of its own: all of them are said, the last one's kind decides.
  const last = failed.at(-1) as { source: string; error: DataError };
  if (failed.length === 1) throw last.error;
  throw new DataError(last.error.kind, failed.map(attempt).join("; "), {
    ...last.error.details,
    source: failed.map((f) => f.source).join(" and "),
    code: "every_source_failed",
  });
}

/**
 * A batch with the instruments its source could not answer for asked of the sources after it. What
 * they answer joins the batch, named by its source; what none could answer keeps every reason.
 */
async function completed(
  answer: Sourced<QuoteBatch>,
  later: (instruments: string[]) => Promise<Sourced<unknown>>,
  signal: AbortSignal | undefined,
): Promise<Sourced<QuoteBatch>> {
  const passed = answer.data.errors.filter((error) => error.kind && NEXT.has(error.kind));
  // A cancelled call goes no further down the chain.
  if (!passed.length || signal?.aborted) return answer;
  const first = new Map(passed.map((error) => [error.instrument, error]));
  const reasons = (said: string) => (error: QuoteBatch["errors"][number]) => ({
    ...error,
    message: `${answer.source}: ${first.get(error.instrument)?.message}; ${said}`,
  });
  let next: Sourced<QuoteBatch>;
  try {
    next = (await later([...first.keys()])) as Sourced<QuoteBatch>;
  } catch (error) {
    if (signal?.aborted) throw error;
    // No later source answered for any of them: each keeps its own reason and theirs, the last one's kind.
    const kind = error instanceof DataError ? { kind: error.kind } : {};
    const kept = answer.data.errors.filter((one) => !first.has(one.instrument));
    return {
      ...answer,
      data: {
        quotes: answer.data.quotes,
        errors: [...kept, ...passed.map((one) => ({ ...reasons(errorText(error))(one), ...kind }))],
      },
    };
  }
  const found = next.data.quotes.map((one) => ({ ...one, source: one.source ?? next.source }));
  const errors = [
    ...answer.data.errors.filter((one) => !first.has(one.instrument)),
    ...next.data.errors.map((one) => reasons(`${next.source}: ${one.message}`)(one)),
  ];
  if (!found.length) return { ...answer, data: { quotes: answer.data.quotes, errors } };
  const own = answer.data.quotes;
  // The sources that gave a quote, and only those, are named; the first source's are named too, once mixed.
  const sources = [...new Set([...(own.length ? [answer.source] : []), ...found.map((one) => one.source)])];
  return {
    data: {
      quotes: [...own.map((one) => ({ ...one, source: one.source ?? answer.source })), ...found],
      errors,
    },
    source: sources.join(" and "),
    notes: [
      ...answer.notes,
      message("data.batchFellBack", {
        instruments: found.map((one) => one.instrument).join(", "),
        source: next.source,
        failed: answer.source,
      }),
    ],
    after: answer.after,
    // The complete data is copied only when every source that gave a quote allows it.
    ...((!own.length || answer.syncs) && next.syncs ? { syncs: true as const } : {}),
  };
}

/**
 * One failed attempt, said in a note or a combined failure. A source's words about the state of a
 * listing now are left out: the note may reach a question about an earlier date.
 */
function attempt({ source, error }: { source: string; error: DataError }): string {
  const detail = LISTING_STATE_CODES.has(error.details.code ?? "")
    ? message("data.listingNotServed")
    : error.message;
  return message("data.attempt", { source, outcome: error.kind, detail });
}

function fellBack(failed: readonly { source: string; error: DataError }[], source: string): string {
  return message("data.fellBack", { failed: failed.map(attempt).join("; "), source });
}

/** A final answer from a later provider (no data, an invalid request) after earlier ones failed. */
function after(failed: readonly { source: string; error: DataError }[], error: DataError): DataError {
  return new DataError(error.kind, `${failed.map(attempt).join("; ")}; ${error.message}`, error.details);
}
