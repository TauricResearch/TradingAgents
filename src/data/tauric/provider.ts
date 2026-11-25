// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Tauric as a provider: every market-data capability, over the Tauric client. Tauric's own
 * conventions (instrument keys, bar status, units, its point-in-time block) stay here; answers are
 * translated into the capability contracts.
 */

import { addDays, errorText } from "../../contracts/index.js";
import { CALLS } from "../../contracts/limits.js";
import type {
  Capability,
  CrossSectionRow,
  DailyBar,
  DailyBars,
  DataProvider,
  FieldStates,
  FilingSectionName,
  InstrumentMatch,
  Quote,
  ReferenceRates,
  Registrant,
  SeriesObservations,
  Statement,
  Succession,
  TechnicalsAnswer,
} from "../capabilities.js";
import { DataError } from "../errors.js";
import { instrumentKey, parseInstrument } from "../instrument-key.js";
import type { Bars, FilingSection, TauricClient } from "./client.js";
import { compact } from "./compact.js";
import { marketView } from "./markets.js";
import { failureKind } from "./transport.js";

const NAME = "Tauric";

// The sections the capability offers are exactly the ones Tauric's pinned API serves.
const sameSections: [FilingSection["section"]] extends [FilingSectionName]
  ? [FilingSectionName] extends [FilingSection["section"]]
    ? true
    : false
  : false = true;
void sameSections;

type Answer<M extends keyof TauricClient> = TauricClient[M] extends (...args: never[]) => Promise<infer T>
  ? T
  : never;

export function tauricProvider(client: TauricClient) {
  // A window longer than Tauric serves at once is read in pieces, newest first, until it is covered or the
  // source's history starts within a piece (an older piece would have nothing).
  const daily = async (key: string, window: { from: string; to: string }, signal?: AbortSignal) => {
    const pieces: DailyBars[] = [];
    for (const piece of piecesOf(window)) {
      const answer = await dailyPiece(key, piece, signal);
      pieces.push(answer);
      const since = answer.coverage.history_from;
      if (since && since >= piece.from) break;
    }
    return joined(pieces);
  };
  const dailyPiece = async (key: string, window: { from: string; to: string }, signal?: AbortSignal) => {
    const { kind, id } = parseInstrument(key);
    const call = signal ? { signal } : {};
    const query = { interval: "1d" as const, start: window.from, end: window.to };
    const answer =
      kind === "security"
        ? await client.history(id, query, call)
        : kind === "future"
          ? await client.futuresHistory(id, query, call)
          : kind === "crypto"
            ? await client.cryptoHistory(id, query, call)
            : kind === "series"
              ? await client.seriesHistory(id, query, call)
              : refuse(`${key} is a currency pair: its history is reference rates, not daily bars`);
    return bars(answer, window);
  };
  return {
    name: NAME,
    // Tauric's own data is what a synced session carries.
    syncs: true,
    capabilities: {
      quotes: {
        quote: async (key, call?) => {
          const { kind, id } = parseInstrument(key);
          if (kind === "security") return quote(await client.quote(id, call));
          if (kind === "future") return quote(await client.futuresQuote(id, call));
          if (kind === "fx") return quote(await client.fxQuote(id, call));
          if (kind === "crypto") return quote(await client.cryptoQuote(id, call));
          const series = await client.seriesLatest(id, call);
          if ("quote" in series) return quote(series.quote);
          return refuse(`${key} is a series of values, not prices: macro_series reads it`);
        },
        many: async (keys, call?) => {
          // The batch route names a continuous future by its family and a security by its key.
          const sent = keys.map((key) => {
            const parsed = parseInstrument(key);
            return parsed.kind === "future" ? `${instrumentKey(parsed)}/continuous` : instrumentKey(parsed);
          });
          const answer = await client.quotes(sent, call);
          const asked = new Map(sent.map((key, i) => [key, keys[i] as string]));
          return {
            quotes: answer.data.map((item) => ({
              instrument: asked.get(item.key) ?? item.key,
              quote: quote(item as unknown as Answer<"quote">),
            })),
            errors: answer.errors.map((item) => ({
              instrument: asked.get(item.key) ?? item.key,
              message: item.error.message,
              kind: failureKind(0, item.error.code, item.error.retry ?? undefined),
            })),
          };
        },
      },
      priceHistory: {
        daily: (key, window, call?) => daily(key, window, call?.signal),
        referenceRates: async (key, window, call) => {
          const { kind, id } = parseInstrument(key);
          if (kind !== "fx") refuse(`${key} is not a currency pair; reference rates are for currency pairs`);
          return referenceRates(
            await client.fxReferenceRates(
              id,
              { start: window.from, end: window.to, limit: CALLS.referenceRates },
              call,
            ),
          );
        },
        intraday: async (key, { interval, start, end, limit }, call) => {
          const { kind, id } = parseInstrument(key);
          if (kind !== "security")
            refuse(`${key}: intraday bars are served for securities only; others have daily bars`);
          const answer = await client.history(id, { interval, start, ...(end ? { end } : {}), limit }, call);
          // Oldest first, whatever order they are served in.
          const sorted = [...answer.data].sort((a, b) =>
            (a.start ?? a.date).localeCompare(b.start ?? b.date),
          );
          const coverage = answer.coverage;
          return {
            instrument: answer.instrument,
            price_basis: answer.price_basis,
            missing_sessions: (coverage.missing ?? []).length,
            incomplete_because:
              coverage.complete === false ? (coverage.complete_reason ?? "not stated") : null,
            bars: sorted.map((bar) => ({
              start: bar.start ?? bar.date,
              date: bar.date,
              open: bar.open ?? null,
              high: bar.high ?? null,
              low: bar.low ?? null,
              close: bar.close ?? null,
              volume: bar.volume ?? null,
              revision: REVISION[bar.status],
              ...(Object.keys(bar.field_states).length ? { field_states: bar.field_states } : {}),
            })),
            history_from: coverage.history_from ?? null,
            // The bar just before the oldest one served; none at the start of the source's history.
            earlier_end: coverage.continue_end ?? null,
          };
        },
        // Both listings from this one source, or neither.
        dailyPair: async ([first, second], window, call?) => [
          await daily(first, window, call?.signal),
          await daily(second, window, call?.signal),
        ],
      },
      statements: {
        statement: async (symbol, { statement, periodType, limit, after }, call) =>
          statementOf(
            await client.statement(
              symbol,
              {
                statement,
                period_type: periodType,
                limit,
                ...(after ? { after } : {}),
              },
              call,
            ),
          ),
      },
      filings: {
        list: async (symbol, { limit, forms, after }, call) => {
          const answer = await client.filings(
            symbol,
            {
              limit,
              ...(forms?.length ? { form: forms.join(",") } : {}),
              ...(after ? { after } : {}),
            },
            call,
          );
          const succession = successionOf(answer.continuity_coverage);
          return {
            instrument: answer.instrument,
            succession,
            data: answer.data.map((row) => ({ ...row, predecessor: isPredecessor(succession, row.cik) })),
            next_cursor: answer.next_cursor,
          };
        },
        section: async (target, { after }, call) => {
          const answer = await client.filingSection(target, after ? { after } : {}, call);
          return {
            ...answer,
            field_states: answer.field_states ?? null,
          };
        },
      },
      news: {
        articles: async ({ symbol, query, ...filters }, call) => {
          const params = {
            limit: filters.limit,
            // Tauric attributes news to securities by instrument key; a venue-qualified symbol keeps its venue.
            ...(symbol ? { instrument: `security:${symbol}` } : {}),
            ...(filters.since ? { start: filters.since } : {}),
            ...(filters.until ? { end: filters.until } : {}),
            ...(filters.after ? { after: filters.after } : {}),
            ...(filters.topic ? { topic: filters.topic } : {}),
            ...(filters.eventType ? { event_type: filters.eventType } : {}),
            ...(filters.sentiment ? { sentiment: filters.sentiment } : {}),
            ...(filters.impact ? { impact: filters.impact } : {}),
          };
          // The latest news comes one article per story, not every outlet's copy of it.
          const page = query
            ? await client.searchNews({ q: query, ...params }, call)
            : await client.news({ ...params, collapse: "story" }, call);
          const items = page.data.map((item) => ("article" in item ? item.article : item));
          return {
            articles: items.map((article) => ({
              id: article.id,
              title: article.title,
              publisher: article.publisher,
              url: article.url,
              published_at: article.article_time,
              annotations: {
                summary: article.annotations.summary?.join(" ") ?? null,
                sentiment: article.annotations.sentiment,
                impact: article.annotations.impact,
              },
            })),
            next_cursor: page.next_cursor,
          };
        },
        article: async (id, call) => {
          const article = await client.newsArticle(id, call);
          const notes = article.annotations;
          return {
            id: article.id,
            title: article.title,
            publisher: article.publisher,
            url: article.url,
            published_at: article.article_time,
            available_at: article.available_at ?? null,
            time_kind: article.article_time_kind ?? null,
            word_count: article.word_count ?? null,
            annotations: {
              summary: notes.summary?.join(" ") ?? null,
              sentiment: notes.sentiment,
              impact: notes.impact,
            },
            topics: notes.topics ?? [],
            instruments: notes.instruments ?? [],
            events: (notes.events ?? []).map((event) => ({
              event_type: event.event_type,
              headline: event.headline,
              date_stated: event.date_stated ?? null,
              instruments: event.instruments ?? [],
            })),
            figures: (notes.figures ?? []).map((figure) => ({
              metric: figure.metric,
              value_stated: figure.value_stated,
              period_stated: figure.period_stated ?? null,
              instruments: figure.instruments ?? [],
            })),
            quotations: (notes.quotations ?? []).map((quote) => ({
              speaker: quote.speaker ?? null,
              text: quote.text,
            })),
          };
        },
      },
      profiles: {
        profile: async (symbol, call) => await client.profile(symbol, call),
        analyst: async (symbol, call) => shown(await client.securityAnalyst(symbol, call)),
        calendar: async (symbol, call) => shown(calendar(await client.securityCalendar(symbol, call))),
      },
      ownership: {
        transactions: async (symbol, { limit, start, end, codes, after }, call) => {
          const answer = await client.insider(
            symbol,
            {
              limit,
              ...(start ? { start } : {}),
              ...(end ? { end } : {}),
              ...(codes?.length ? { code: codes.join(",") } : {}),
              ...(after ? { after } : {}),
            },
            call,
          );
          return answer;
        },
        holders: async (symbol, { limit, quarter, after }, call) => {
          const answer = await client.institutionalHolders(
            symbol,
            { limit, ...(quarter ? { quarter } : {}), ...(after ? { after } : {}) },
            call,
          );
          const coverage = answer.coverage;
          const filings = answer.filings ?? {};
          const caveats = [
            ...(coverage.cusip_state && coverage.cusip_state !== "matched"
              ? [
                  `the security's CUSIP is ${coverage.cusip_state.replaceAll("_", " ")}: holdings filed under it may be missing`,
                ]
              : []),
            ...(coverage.ambiguous_cusips?.length
              ? ["holdings under CUSIPs shared with other share classes are left out"]
              : []),
            ...(coverage.historical_cusips?.complete === false
              ? ["holdings filed under the security's earlier CUSIPs are left out"]
              : []),
          ];
          return {
            instrument: answer.instrument,
            quarter: coverage.period ?? null,
            complete: coverage.period_complete ?? null,
            quarters: (coverage.periods ?? []).map((period) => period.period),
            caveats,
            holders: answer.data.map((row) => {
              const filing = filings[row.accession];
              return {
                manager: filing?.manager?.name ?? "manager not named",
                filed: filing?.filed ?? null,
                form: filing?.submission_type ?? null,
                value: row.value ?? null,
                value_unit:
                  filing?.value_unit === "dollars"
                    ? "dollars"
                    : filing?.value_unit
                      ? "thousands of dollars"
                      : null,
                shares: row.shares ?? null,
                shares_type: row.shares_type ?? null,
                put_call: row.put_call ?? null,
                discretion: row.investment_discretion ?? null,
                accession: row.accession,
              };
            }),
            next_cursor: answer.next_cursor ?? null,
          };
        },
      },
      syntheses: {
        digest: async (symbol, call) => {
          const answer = symbol ? await client.securityDigest(symbol, call) : await client.marketDigest(call);
          return {
            instrument: answer.instrument ?? null,
            for_date: answer.digest_date ?? null,
            generated_at: answer.generated_at ?? null,
            superseded: answer.superseded ?? null,
            stance: null,
            content: compact(answer.content),
          };
        },
        thesis: async (symbol, call) => {
          const answer = await client.thesis(symbol, call);
          return {
            instrument: answer.instrument ?? null,
            for_date: answer.evidence?.cutoff ?? null,
            generated_at: answer.generated_at ?? null,
            superseded: answer.superseded ?? null,
            stance: null,
            content: compact(answer.content),
          };
        },
        themes: async (call) => {
          const answer = await client.themes(call);
          return {
            for_date: null,
            generated_at: answer.generated_at ?? null,
            superseded: null,
            stance: null,
            content: { window_days: answer.window_days, themes: compact(answer.data) },
          };
        },
        research: async (symbol, call) => {
          const answer = await client.research(symbol, call);
          return {
            instrument: answer.instrument ?? null,
            for_date: answer.prepared_for ?? null,
            generated_at: answer.generated_at ?? null,
            superseded: null,
            stance: answer.stance ?? null,
            content: answer.report,
          };
        },
      },
      crossSections: {
        financials: async ({ sector, line, fiscalYear, knownAt, maxPages }, call) => {
          const rows: CrossSectionRow[] = [];
          let after: string | undefined;
          let pages = 0;
          let instant = knownAt ?? null;
          let because: string | null = null;
          // A sector is read to its end, page by page, as of the first page's instant.
          do {
            let page: Answer<"equityFinancials">;
            try {
              page = await client.equityFinancials(
                {
                  line,
                  sector,
                  period_type: "annual",
                  fiscal_year: fiscalYear,
                  limit: 25,
                  // The cursor holds the first page's instant: an instant is sent only when one was asked for.
                  ...(knownAt ? { known_at: knownAt } : {}),
                  ...(after ? { after } : {}),
                },
                call,
              );
            } catch (error) {
              // What was read stands, said to be partial; nothing read is the failure itself.
              if (!pages || call?.signal?.aborted) throw error;
              because = `the source stopped answering after ${pages} pages (${errorText(error)})`;
              break;
            }
            pages++;
            instant ??= page.point_in_time?.known_at ?? null;
            for (const row of page.data) {
              const unit = row.unit ?? null;
              const reason = row.field_states?.value?.reason;
              rows.push({
                ciks: row.ciks ?? [],
                name: row.name ?? null,
                symbols: row.symbols ?? [],
                value:
                  row.value === null || row.value === undefined ? null : row.value * (unit?.multiplier ?? 1),
                unit: unitOf(null, unit ? { ...unit, multiplier: 1 } : null),
                unit_group: unit ? [unit.kind, unit.currency ?? "", unit.per ?? ""].join("/") : null,
                period_start: row.period?.start ?? null,
                period_end: row.period?.end ?? null,
                derivation: row.derivation ?? null,
                // A value the source does not serve and gives no reason for is said so, not taken as zero.
                missing_because:
                  row.value === null || row.value === undefined ? (reason ?? "not served") : null,
                form: row.sources?.[0]?.form ?? null,
                accession: row.sources?.[0]?.accession ?? null,
              });
            }
            after = page.next_cursor ?? undefined;
          } while (after && pages < maxPages);
          if (!because && after) because = `the sector is longer than ${maxPages} pages`;
          return { rows, pages, complete: because === null, incomplete_because: because, known_at: instant };
        },
      },
      corporateActions: {
        list: async (symbol, call) => {
          const answer = await client.corporateActions(symbol, call);
          return {
            instrument: answer.instrument,
            actions: answer.data.map((action) => ({
              ex_date: action.ex_date,
              action_type: action.action_type,
              value: action.value ?? null,
              unit: unitOf(null, action.unit ?? null),
              cash_basis: action.cash_basis ?? null,
              revised: action.revised === true,
              field_states: action.field_states,
            })),
            through: answer.freshness?.through ?? null,
            stale: answer.freshness?.stale ?? null,
          };
        },
      },
      technicals: {
        latest: async (key, call) => {
          const { kind, id } = parseInstrument(key);
          if (kind === "security") return technicals(await client.technicals(id, call));
          if (kind === "future") return technicals(await client.futuresTechnicals(id, call));
          if (kind === "series") return technicals(await client.seriesTechnicals(id, call));
          return refuse(
            `${key}: technical indicators are served for securities, futures and price series only`,
          );
        },
      },
      markets: {
        view: async (view, call) => await marketView(client, view, call),
      },
      instruments: {
        search: async (query, kind, call) =>
          matches(
            await client.instruments(
              { q: query, limit: CALLS.instrumentMatches, ...(kind ? { kind: kind as never } : {}) },
              call,
            ),
          ),
      },
      macroSeries: {
        search: async (query, call) =>
          (await client.series({ q: query, limit: CALLS.seriesCandidates }, call)).data,
        observations: async (key, { limit, end }, call) =>
          observations(await client.observations(key, { limit, ...(end ? { end } : {}) }, call)),
      },
    },
  } satisfies DataProvider;
}

/** An answer shown whole, compacted; the instrument it names is the profile's, said there already. */
function shown({ instrument: _instrument, ...answer }: { instrument?: unknown } & Record<string, unknown>) {
  return (compact(answer) ?? {}) as Record<string, unknown>;
}

/**
 * A security's calendar. With no next earnings date announced, Tauric leaves `earnings` null and marks it
 * temporarily unavailable (a date may come later) while the earnings dataset itself is complete; that is
 * said as it is, not as an outage. An earnings dataset that is itself unavailable keeps its field state.
 */
function calendar(answer: Answer<"securityCalendar">): Record<string, unknown> {
  const { earnings: state, ...states } = answer.field_states ?? {};
  const unannounced =
    answer.earnings === null &&
    state?.reason === "temporarily_unavailable" &&
    answer.earnings_status?.complete === true;
  return unannounced ? { ...answer, earnings: "no next date announced yet", field_states: states } : answer;
}

/** A request this source cannot answer as asked: the model is told what to ask instead. */
function refuse(why: string): never {
  throw new DataError("invalid", `${NAME}: ${why}.`, { source: NAME });
}

function referenceRates(answer: Answer<"fxReferenceRates">): ReferenceRates {
  return {
    instrument: answer.instrument,
    basis: `reference rates in ${answer.quote_currency} per ${answer.base_currency} (${answer.derivation}${answer.formula ? `: ${answer.formula}` : ""})`,
    // Oldest first, as bars are, whatever order they are served in.
    rates: answer.data
      .map((rate) => ({ date: rate.date, value: rate.value }))
      .sort((a, b) => a.date.localeCompare(b.date)),
    complete: answer.coverage.complete ?? null,
    earlier_end: answer.coverage.continue_end ?? null,
  };
}

/** Instruments a search found, each with the capabilities its datasets serve here. */
function matches(answer: Answer<"instruments">): InstrumentMatch[] {
  return answer.data.map((row) => ({
    key: row.key,
    name: row.name,
    type: row.classification.instrument_type ?? null,
    listing_state: row.listing?.state ?? null,
    serves: [...new Set(row.datasets.flatMap((dataset) => SERVES[dataset] ?? []))],
  }));
}

/** Tauric's datasets, by the capabilities this provider serves from them. */
const SERVES: Record<string, Capability> = {
  "securities.quote": "quotes",
  "securities.history": "priceHistory",
  "securities.technicals": "technicals",
  "securities.profile": "profiles",
  "securities.financials": "statements",
  "securities.filings": "filings",
  "securities.insider_transactions": "ownership",
  "futures.quote": "quotes",
  "futures.history": "priceHistory",
  "futures.technicals": "technicals",
  "fx.quote": "quotes",
  "fx.reference_rates": "priceHistory",
  "crypto.quote": "quotes",
  "crypto.history": "priceHistory",
  "series.quote": "quotes",
  "series.history": "priceHistory",
  "series.technicals": "technicals",
  "series.observations": "macroSeries",
};

function quote(answer: Answer<"quote">): Quote {
  return {
    instrument: answer.instrument,
    quote_kind: answer.quote_kind,
    price: answer.price ?? null,
    price_basis: answer.price_basis ?? null,
    price_time: answer.price_time ?? null,
    stale: answer.stale ?? null,
    session_date: answer.session_date ?? null,
    market_state: answer.market_state ?? null,
    previous_close: answer.previous_close ?? null,
    change: answer.change?.absolute ?? null,
    change_percent: answer.change?.percent ?? null,
    change_basis: answer.change?.basis ?? null,
    day: answer.day ?? null,
    range_52w: answer.range_52w ?? null,
    market_cap: answer.market_cap ?? null,
    // The change's own states, under the names its values have here.
    field_states: {
      ...answer.field_states,
      ...renamed(answer.change?.field_states, { absolute: "change", percent: "change_percent" }),
    },
  };
}

/**
 * The company's filers across successions, the current one first: each link of the chain after the first
 * holds the predecessors a successor took over from on its `effective_date`.
 */
function successionOf(coverage: Answer<"filings">["continuity_coverage"]): Succession {
  return {
    registrants: coverage.chain.flatMap((link, index) =>
      link.registrants.map(
        (filer): Registrant => ({
          cik: filer.cik,
          complete: filer.complete,
          complete_reason: filer.complete_reason,
          ...(index > 0 ? { succeeded_on: link.effective_date } : {}),
        }),
      ),
    ),
    stopsAt: coverage.stopped_at?.ciks ?? [],
  };
}

/** Whether a filing's filer is one of the company's predecessors rather than its current registrant. */
function isPredecessor(succession: Succession, cik: string): boolean {
  return succession.registrants.some((filer) => filer.cik === cik && filer.succeeded_on !== undefined);
}

/** Field states with some fields renamed. */
function renamed(states: FieldStates, names: Record<string, string>): FieldStates {
  return Object.fromEntries(
    Object.entries(states ?? {}).map(([field, state]) => [names[field] ?? field, state]),
  );
}

type Unit = {
  kind: string;
  multiplier: number;
  currency: string | null;
  measure: string | null;
  per: string | null;
};

/**
 * A unit as filed, or else as Tauric states it: "USD/share", "thousands of barrel/day", "percent".
 */
export function unitOf(asFiled: string | null, unit: Unit | null): string | null {
  if (asFiled) return asFiled;
  if (!unit) return null;
  const base = `${unit.currency ?? unit.measure ?? unit.kind}${unit.per ? `/${unit.per}` : ""}`;
  return unit.multiplier === 1 ? base : `${unit.multiplier.toLocaleString("en-US")} ${base}`;
}

function statementOf(answer: Answer<"statement">): Statement {
  const succession = successionOf(answer.continuity_coverage);
  return {
    instrument: answer.instrument,
    succession,
    periods: answer.data.map((period) => ({
      period_end: period.end,
      lines: period.lines.map((line) => ({
        line: line.line,
        value: line.value,
        unit: unitOf(line.unit_as_filed, line.unit),
        period_start: line.period?.start ?? null,
        field_states: line.field_states ?? null,
        sources: line.sources.map(({ accession, form, accepted_at, cik }) => ({
          accession,
          form,
          accepted_at,
          cik,
          predecessor: isPredecessor(succession, cik),
        })),
      })),
    })),
    next_cursor: answer.next_cursor,
  };
}

/** Tauric's bar status as a revision: an `unsettled` bar may still be revised. */
const REVISION = { settled: "final", unsettled: "provisional" } as const satisfies Record<
  Bars["data"][number]["status"],
  DailyBar["revision"]
>;

/** `window` as windows Tauric serves, newest first, each ending the day before the one after it starts. */
function piecesOf({ from, to }: { from: string; to: string }): { from: string; to: string }[] {
  const pieces: { from: string; to: string }[] = [];
  for (let end = to; end >= from; ) {
    const earliest = addDays(end, 1 - CALLS.dailyWindowDays);
    const start = earliest > from ? earliest : from;
    pieces.push({ from: start, to: end });
    end = addDays(start, -1);
  }
  // A window that ends before it starts is asked as it is, for the source to answer.
  return pieces.length ? pieces : [{ from, to }];
}

/**
 * Pieces of one window, newest first, as one: their bars oldest first, the newest piece's instrument and
 * basis, complete only when every piece is, and older bars continuing where the oldest piece says.
 */
function joined(pieces: readonly DailyBars[]): DailyBars {
  const newest = pieces[0] as DailyBars;
  if (pieces.length === 1) return newest;
  const all = [...pieces].reverse();
  const oldest = all[0] as DailyBars;
  const dated = all.flatMap((piece) => piece.bars);
  const completes = all.map((piece) => piece.coverage.complete);
  return {
    ...newest,
    bars: dated,
    coverage: {
      from: dated[0]?.date ?? null,
      through: dated.at(-1)?.date ?? null,
      complete: completes.includes(false) ? false : completes.includes(null) ? null : true,
      complete_reason: all.find((piece) => piece.coverage.complete_reason)?.coverage.complete_reason ?? null,
      history_from: all.find((piece) => piece.coverage.history_from)?.coverage.history_from ?? null,
      missing_sessions: all.reduce((sum, piece) => sum + piece.coverage.missing_sessions, 0),
    },
    earlier_end: oldest.earlier_end,
  };
}

/** Tauric's answer for the window asked: the bars in it and whether every session there is accounted for. */
function bars(answer: Bars, { from, to }: { from: string; to: string }): DailyBars {
  const within = (date: string) => date >= from && date <= to;
  const inWindow = answer.data.filter((bar) => within(bar.date));
  const coverage = answer.coverage;
  return {
    instrument: answer.instrument,
    price_basis: answer.price_basis,
    bars: inWindow.map((bar) => ({
      date: bar.date,
      open: bar.open ?? null,
      high: bar.high ?? null,
      low: bar.low ?? null,
      close: bar.close ?? null,
      volume: bar.volume ?? null,
      revision: REVISION[bar.status],
      ...(Object.keys(bar.field_states).length ? { field_states: bar.field_states } : {}),
    })),
    coverage: {
      from: inWindow[0]?.date ?? null,
      through: inWindow.at(-1)?.date ?? null,
      complete: coverage.complete ?? null,
      complete_reason: coverage.complete_reason ?? null,
      history_from: coverage.history_from ?? null,
      missing_sessions: (coverage.missing ?? []).filter((m) => within(m.start)).length,
    },
    earlier_end: coverage.continue_end ?? null,
  };
}

function technicals(answer: Answer<"technicals">): TechnicalsAnswer {
  const { window, volume_available, ichimoku: _ichimoku, ...rest } = answer;
  return {
    ...rest,
    volume_available: volume_available ?? null,
    window: {
      bars: window.bars ?? null,
      missing: (window.missing ?? []).map((m) => ({ date: m.start, reason: m.reason })),
      settled_through: window.settled_through ?? null,
    },
  };
}

function observations(answer: Answer<"observations">): SeriesObservations {
  return {
    series: answer.series,
    coverage: {
      missing: (answer.coverage.missing ?? []).map((m) => ({ period: { label: m.start }, reason: m.reason })),
      continue_end: answer.coverage.continue_end ?? null,
      complete_reason: answer.coverage.complete_reason ?? null,
    },
    observations: answer.data,
  };
}
