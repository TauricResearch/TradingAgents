// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Yahoo as a provider: quotes and daily price history only. Yahoo has no knowledge time for
 * statements, news or profiles (they are restated in place), so it offers none of those.
 *
 * Listings: a bare ticker is a US listing (share classes spelled the Yahoo way, BRK.B as BRK-B);
 * MIC:SYMBOL maps through a small table, and the listing Yahoo resolves must be on that venue, or
 * Yahoo is said not to cover it. Prices are adjusted for splits and dividends by Yahoo's adjusted
 * close; a bar without one is left out, never shown unadjusted. An unfinished session is never
 * returned, and a session is final once a later one has a bar.
 */

import YahooFinance from "yahoo-finance2";
import { addDays, errorText } from "../../contracts/index.js";
import { REQUEST_MS } from "../../contracts/limits.js";
import type { Call, DailyBar, DailyBars, DataProvider, Instrument, Quote } from "../capabilities.js";
import { DataError } from "../errors.js";
import { parseInstrument } from "../instrument-key.js";

const NAME = "Yahoo";

/** The venues of US listings, as Yahoo names them. */
const US = ["NMS", "NGM", "NCM", "NAS", "NYQ", "PCX", "BTS", "ASE"];

/** MIC -> how Yahoo spells a symbol there, and the venues it reports for it. */
const VENUES: Record<string, { spell: (symbol: string) => string; venues: readonly string[] }> = {
  XNAS: { spell: us, venues: ["NMS", "NGM", "NCM", "NAS"] },
  XNYS: { spell: us, venues: ["NYQ"] },
  ARCX: { spell: us, venues: ["PCX"] },
  BATS: { spell: us, venues: ["BTS"] },
  XASE: { spell: us, venues: ["ASE"] },
  // Hong Kong codes are four digits, with their leading zeros.
  XHKG: { spell: (s) => `${/^\d+$/.test(s) ? s.padStart(4, "0") : s}.HK`, venues: ["HKG"] },
  XLON: { spell: (s) => `${s.replaceAll(".", "-")}.L`, venues: ["LSE"] },
  XTKS: { spell: (s) => `${s}.T`, venues: ["JPX"] },
  XTSE: { spell: (s) => `${s.replaceAll(".", "-")}.TO`, venues: ["TOR"] },
  XNSE: { spell: (s) => `${s}.NS`, venues: ["NSI"] },
  XBOM: { spell: (s) => `${s}.BO`, venues: ["BSE"] },
  XETR: { spell: (s) => `${s}.DE`, venues: ["GER"] },
  XPAR: { spell: (s) => `${s}.PA`, venues: ["PAR"] },
  XASX: { spell: (s) => `${s}.AX`, venues: ["ASX"] },
};

function us(symbol: string): string {
  return symbol.replaceAll(".", "-");
}

/** The calls of yahoo-finance2 this provider uses, in the shapes it reads. */
export type YahooClient = {
  quote(symbol: string, options?: unknown, module?: { fetchOptions?: RequestInit }): Promise<YahooQuote>;
  chart(
    symbol: string,
    options: { period1: string; period2: string; interval: "1d" },
    module?: { fetchOptions?: RequestInit },
  ): Promise<YahooChart>;
};
type YahooQuote = {
  symbol: string;
  exchange?: string;
  fullExchangeName?: string;
  longName?: string;
  shortName?: string;
  currency?: string;
  marketState?: string;
  regularMarketPrice?: number;
  regularMarketChange?: number;
  regularMarketChangePercent?: number;
  regularMarketTime?: Date;
  regularMarketPreviousClose?: number;
  regularMarketOpen?: number;
  regularMarketDayHigh?: number;
  regularMarketDayLow?: number;
  regularMarketVolume?: number;
  fiftyTwoWeekLow?: number;
  fiftyTwoWeekHigh?: number;
  marketCap?: number;
  exchangeTimezoneName?: string;
};
type YahooChart = {
  meta: {
    symbol: string;
    currency?: string | null;
    exchangeName?: string;
    fullExchangeName?: string;
    longName?: string;
    shortName?: string;
    exchangeTimezoneName?: string;
    firstTradeDate?: Date | null;
    currentTradingPeriod?: { regular?: { start?: Date; end?: Date } };
  };
  quotes: {
    date: Date;
    open?: number | null;
    high?: number | null;
    low?: number | null;
    close?: number | null;
    volume?: number | null;
    adjclose?: number | null;
  }[];
};

export function yahooProvider(
  options: { client?: YahooClient; fetch?: typeof globalThis.fetch; now?: () => Date } = {},
) {
  const client = options.client ?? defaultClient(options.fetch);
  const now = options.now ?? (() => new Date());
  const daily = async (symbol: string, window: { from: string; to: string }, signal?: AbortSignal) => {
    const listing = listingOf(symbol);
    // A week past `to` shows whether its last session is final (a later one exists).
    const answer = await called(() =>
      client.chart(
        listing.yahoo,
        { period1: window.from, period2: addDays(window.to, 8), interval: "1d" },
        { fetchOptions: signal ? { signal } : {} },
      ),
    );
    if (!listing.venues.includes(answer.meta.exchangeName ?? ""))
      throw elsewhere(symbol, answer.meta.fullExchangeName);
    return bars(answer, window, now());
  };
  const single = async (symbol: string, call?: Call): Promise<Quote> => {
    const listing = listingOf(symbol);
    const answer = await called(() =>
      client.quote(listing.yahoo, {}, { fetchOptions: call?.signal ? { signal: call.signal } : {} }),
    );
    // An empty answer is how Yahoo says it has no such listing.
    if (!answer) throw new DataError("no_data", `Yahoo has no quote for ${symbol}`, { source: NAME });
    if (!listing.venues.includes(answer.exchange ?? "")) throw elsewhere(symbol, answer.fullExchangeName);
    return quote(answer);
  };
  return {
    name: NAME,
    capabilities: {
      quotes: {
        quote: single,
        // One by one: a listing that has no quote is said, and the rest stand.
        many: async (keys, call?) => {
          const answers = await Promise.allSettled(keys.map((key) => single(key, call)));
          // None answered: the source's own failure is the answer, as for one quote.
          const first = answers[0];
          if (first?.status === "rejected" && answers.every((answer) => answer.status === "rejected")) {
            throw first.reason;
          }
          return {
            quotes: answers.flatMap((answer, i) =>
              answer.status === "fulfilled" ? [{ instrument: keys[i] as string, quote: answer.value }] : [],
            ),
            errors: answers.flatMap((answer, i) =>
              answer.status === "rejected"
                ? [
                    {
                      instrument: keys[i] as string,
                      message: errorText(answer.reason),
                      ...(answer.reason instanceof DataError ? { kind: answer.reason.kind } : {}),
                    },
                  ]
                : [],
            ),
          };
        },
      },
      priceHistory: {
        daily: (symbol, window, call?) => daily(symbol, window, call?.signal),
        // Both listings from Yahoo, or neither.
        dailyPair: async ([first, second], window, call?) => [
          await daily(first, window, call?.signal),
          await daily(second, window, call?.signal),
        ],
      },
    },
  } satisfies DataProvider;
}

function defaultClient(fetchImpl: typeof globalThis.fetch = fetch): YahooClient {
  const silent = { info() {}, warn() {}, error() {}, debug() {}, dir() {} };
  return new YahooFinance({
    suppressNotices: ["yahooSurvey", "ripHistorical"],
    logger: silent,
    fetch: answeredOrThrown(fetchImpl),
  } as never) as unknown as YahooClient;
}

/**
 * Every request to Yahoo ends within its time (the answer's body included), and Yahoo's API answers
 * that are not OK become errors carrying their status before the library reads them; the library
 * would otherwise print the request to the terminal.
 */
export function answeredOrThrown(
  fetchImpl: typeof globalThis.fetch,
  timeoutMs: number = REQUEST_MS.yahoo,
): typeof globalThis.fetch {
  // A wrapper lacks the `preconnect` that Bun's fetch type adds, so it is asserted to the fetch type.
  return (async (input, init) => {
    const deadline = AbortSignal.timeout(timeoutMs);
    const signal = init?.signal ? AbortSignal.any([init.signal, deadline]) : deadline;
    const response = await fetchImpl(input, { ...init, signal });
    const url = new URL(input instanceof Request ? input.url : String(input));
    if (!response.ok && /^query\d\.finance\.yahoo\.com$/.test(url.hostname)) {
      throw Object.assign(new Error(`HTTP ${response.status}`), { code: response.status });
    }
    return response;
  }) as typeof globalThis.fetch;
}

/** How Yahoo spells `symbol`, and the venues its listing may be on. */
function listingOf(key: string): { yahoo: string; venues: readonly string[] } {
  // Yahoo serves listed securities here; other kinds of instrument are another source's.
  const { kind, id: symbol } = parseInstrument(key);
  if (kind !== "security") {
    throw new DataError("unsupported", `Yahoo serves listed securities only, not ${key}`, { source: NAME });
  }
  const [mic, code] = symbol.includes(":") ? (symbol.split(":", 2) as [string, string]) : [undefined, symbol];
  if (!mic) return { yahoo: us(code), venues: US };
  const venue = VENUES[mic.toUpperCase()];
  if (!venue) {
    throw new DataError("unsupported", `Yahoo has no symbol for ${symbol}`, { source: NAME });
  }
  return { yahoo: venue.spell(code), venues: venue.venues };
}

function elsewhere(symbol: string, venue: string | undefined): DataError {
  return new DataError("unsupported", `Yahoo's ${symbol} is a listing on ${venue ?? "another venue"}`, {
    source: NAME,
  });
}

/** A yahoo-finance2 failure as a DataError: unknown symbols are no data; anything else is the source's. */
async function called<T>(work: () => Promise<T>): Promise<T> {
  try {
    return await work();
  } catch (cause) {
    const error = cause as { name?: string; message?: string; code?: number | string };
    const text = String(error?.message ?? cause);
    const status = typeof error?.code === "number" ? error.code : undefined;
    // The HTTP status decides when there is one; the text only when there is not.
    if (status === 429 || (status === undefined && /too many requests/i.test(text))) {
      throw new DataError("rate_limited", "Yahoo is limiting requests", { source: NAME });
    }
    if (status === 404 || (status === undefined && /no data found|delisted|invalid symbol/i.test(text))) {
      throw new DataError("no_data", `Yahoo: ${text}`, { source: NAME });
    }
    const what = error?.name === "AbortError" ? "the request was cancelled" : text;
    throw new DataError("unavailable", `Yahoo could not be read (${what})`, { source: NAME });
  }
}

/** Currencies Yahoo quotes in a minor unit, and the major unit with its scale. */
const MINOR: Record<string, { currency: string; scale: number }> = {
  GBp: { currency: "GBP", scale: 0.01 },
  GBX: { currency: "GBP", scale: 0.01 },
  ZAc: { currency: "ZAR", scale: 0.01 },
  ILA: { currency: "ILS", scale: 0.01 },
};

function instrumentOf(raw: {
  symbol: string;
  longName?: string | undefined;
  shortName?: string | undefined;
  fullExchangeName?: string | undefined;
  currency?: string | null | undefined;
}): Instrument {
  const minor = raw.currency ? MINOR[raw.currency] : undefined;
  return {
    key: raw.symbol,
    name: raw.longName ?? raw.shortName ?? raw.symbol,
    venue: raw.fullExchangeName ?? null,
    currency: minor?.currency ?? raw.currency ?? null,
    ...(minor ? { price_scale: minor.scale } : {}),
  };
}

function quote(raw: YahooQuote): Quote {
  const date = raw.regularMarketTime ? localDate(raw.regularMarketTime, raw.exchangeTimezoneName) : null;
  return {
    instrument: instrumentOf(raw),
    quote_kind: raw.marketState === "REGULAR" ? "last" : "last_close",
    price: raw.regularMarketPrice ?? null,
    price_basis: "as traded",
    price_time: raw.regularMarketTime?.toISOString() ?? null,
    session_date: date,
    market_state: raw.marketState?.toLowerCase() ?? null,
    previous_close: raw.regularMarketPreviousClose ?? null,
    change: raw.regularMarketChange ?? null,
    change_percent: raw.regularMarketChangePercent ?? null,
    day: {
      open: raw.regularMarketOpen ?? null,
      high: raw.regularMarketDayHigh ?? null,
      low: raw.regularMarketDayLow ?? null,
      volume: raw.regularMarketVolume ?? null,
    },
    range_52w: { low: raw.fiftyTwoWeekLow ?? null, high: raw.fiftyTwoWeekHigh ?? null },
    market_cap: raw.marketCap ?? null,
  };
}

function bars(answer: YahooChart, { from, to }: { from: string; to: string }, now: Date): DailyBars {
  const zone = answer.meta.exchangeTimezoneName;
  const sessionEnd = answer.meta.currentTradingPeriod?.regular?.end;
  const today = localDate(now, zone);
  const all = answer.quotes
    .map((row) => ({ row, date: localDate(row.date, zone) }))
    // The session under way is not a daily bar yet.
    .filter(({ date }) => !(date === today && (!sessionEnd || now < sessionEnd)));
  const latest = all.at(-1)?.date;
  let left = 0;
  const shown: DailyBar[] = [];
  for (const { row, date } of all) {
    if (date < from || date > to) continue;
    const { close, adjclose } = row;
    if (!Number.isFinite(close) || !Number.isFinite(adjclose) || close === 0) {
      left++;
      continue;
    }
    const factor = (adjclose as number) / (close as number);
    const scaled = (value: number | null | undefined) =>
      typeof value === "number" && Number.isFinite(value) ? value * factor : null;
    shown.push({
      date,
      open: scaled(row.open),
      high: scaled(row.high),
      low: scaled(row.low),
      close: adjclose as number,
      volume: row.volume ?? null,
      // Yahoo does not say when a bar is final; one with a later completed session after it is taken as final.
      revision: latest !== undefined && date < latest ? "final" : "provisional",
    });
  }
  const first = answer.meta.firstTradeDate ? localDate(answer.meta.firstTradeDate, zone) : undefined;
  return {
    instrument: instrumentOf(answer.meta),
    price_basis: "split_dividend_adjusted",
    bars: shown,
    coverage: {
      from: shown[0]?.date ?? null,
      through: shown.at(-1)?.date ?? null,
      // Yahoo does not say whether every session is accounted for.
      complete: null,
      missing_sessions: left,
    },
    earlier_end: first !== undefined && first < from ? addDays(from, -1) : null,
  };
}

/** The date of `instant` at the exchange (UTC when the zone is unknown). */
function localDate(instant: Date, zone: string | undefined): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: zone ?? "UTC" }).format(instant);
}
