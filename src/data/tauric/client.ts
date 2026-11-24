// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The Tauric market-data client. Requests and answers are typed from the pinned part of the data
 * document (schema.generated.ts from openapi.json); the shared transport checks each answer against it.
 */

import type { Client } from "openapi-fetch";
import { DataError } from "../errors.js";
import type { components, operations, paths } from "./schema.generated.js";
import { type Call, SOURCE, TauricTransport, type TransportOptions, within } from "./transport.js";

type Schemas = components["schemas"];
type Query<Id extends keyof operations> = NonNullable<operations[Id]["parameters"]["query"]>;

export type Quote = Schemas["Quote"];
export type Bars = Schemas["BarsResponse"];
export type Statement = Schemas["SecStatementContinuityResponse"];
type Profile = operations["get_security_profile"]["responses"]["200"]["content"]["application/json"];
export type Filings = Schemas["SecFilingsContinuityResponse"];
export type FilingSection =
  operations["get_security_filing_section"]["responses"]["200"]["content"]["application/json"];
type InsiderTransactions =
  operations["list_security_insider_transactions"]["responses"]["200"]["content"]["application/json"];
export type News = operations["list_news"]["responses"]["200"]["content"]["application/json"];
type NewsSearch = operations["search_news"]["responses"]["200"]["content"]["application/json"];
export type Technicals =
  operations["get_security_technicals"]["responses"]["200"]["content"]["application/json"];
type SeriesList = operations["list_series"]["responses"]["200"]["content"]["application/json"];
export type SeriesObservations =
  operations["get_series_observations"]["responses"]["200"]["content"]["application/json"];
export type ReferenceRates = Schemas["FxReferenceRatesResponse"];
type CryptoBars = Schemas["CryptoBarsResponse"];
type InstrumentList = Schemas["InstrumentList"];
type SeriesAnswer = Schemas["SeriesQuoteResponse"] | Schemas["SeriesLatestResponse"];

type TauricClientOptions = TransportOptions;

export class TauricClient {
  private readonly transport: TauricTransport;
  private readonly http: Client<paths>;

  constructor(options: TauricClientOptions) {
    this.transport = new TauricTransport(options);
    this.http = this.transport.client<paths>();
  }

  quote(symbol: string, call: Call = {}): Promise<Quote> {
    return this.get("/v1/securities/{symbol}/quote", { path: { symbol } }, call);
  }

  /** Up to 50 instruments' quotes in one request, each key's quote or why it has none, in the order sent. */
  quotes(instruments: string[], { signal }: Call = {}): Promise<Schemas["QuotesBatchResponse"]> {
    return this.transport.guarded(() =>
      this.transport.read("data", "post", "/v1/quotes", () =>
        this.http.POST("/v1/quotes", { body: { instruments }, ...within(signal) }),
      ),
    );
  }

  history(symbol: string, query: Query<"get_security_history"> = {}, call: Call = {}): Promise<Bars> {
    return this.get("/v1/securities/{symbol}/history", { path: { symbol }, query }, call);
  }

  technicals(symbol: string, call: Call = {}): Promise<Technicals> {
    return this.get("/v1/securities/{symbol}/technicals", { path: { symbol } }, call);
  }

  /** Reference series (macro indicators, rates, indices) matching a search, best match first. */
  series(query: Query<"list_series"> = {}, call: Call = {}): Promise<SeriesList> {
    return this.get("/v1/series", { query }, call);
  }

  /** A value series' ended periods, as known at `known_at` when given. */
  observations(
    key: string,
    query: Query<"get_series_observations"> = {},
    call: Call = {},
  ): Promise<SeriesObservations> {
    return this.get("/v1/series/{key}/observations", { path: { key }, query }, call);
  }

  /** Instruments matching a search by key, symbol, name or code, best match first. */
  instruments(query: Query<"list_instruments">, call: Call = {}): Promise<InstrumentList> {
    return this.get("/v1/instruments", { query }, call);
  }

  /** A futures root's continuous front-month series ("XNYM:CL" or "CL"). */
  futuresQuote(root: string, call: Call = {}): Promise<Quote> {
    return this.get("/v1/futures/{root}/continuous/quote", { path: { root } }, call);
  }

  futuresHistory(root: string, query: Query<"get_futures_history">, call: Call = {}): Promise<Bars> {
    return this.get("/v1/futures/{root}/continuous/history", { path: { root }, query }, call);
  }

  futuresTechnicals(root: string, call: Call = {}): Promise<Technicals> {
    return this.get("/v1/futures/{root}/continuous/technicals", { path: { root } }, call);
  }

  fxQuote(pair: string, call: Call = {}): Promise<Quote> {
    return this.get("/v1/fx/{pair}/quote", { path: { pair } }, call);
  }

  /** ECB reference rates of a currency pair, by publication day. */
  fxReferenceRates(
    pair: string,
    query: Query<"get_fx_reference_rates">,
    call: Call = {},
  ): Promise<ReferenceRates> {
    return this.get("/v1/fx/{pair}/reference-rates", { path: { pair }, query }, call);
  }

  cryptoQuote(pair: string, call: Call = {}): Promise<Quote> {
    return this.get("/v1/crypto/pairs/{pair}/quote", { path: { pair } }, call);
  }

  cryptoHistory(pair: string, query: Query<"get_crypto_history">, call: Call = {}): Promise<CryptoBars> {
    return this.get("/v1/crypto/pairs/{pair}/history", { path: { pair }, query }, call);
  }

  /** A reference series' definition with its latest quote (a price series) or value (a value series). */
  seriesLatest(key: string, call: Call = {}): Promise<SeriesAnswer> {
    return this.get("/v1/series/{key}", { path: { key } }, call);
  }

  seriesHistory(key: string, query: Query<"get_series_history">, call: Call = {}): Promise<Bars> {
    return this.get("/v1/series/{key}/history", { path: { key }, query }, call);
  }

  seriesTechnicals(key: string, call: Call = {}): Promise<Technicals> {
    return this.get("/v1/series/{key}/technicals", { path: { key } }, call);
  }

  /** One market view's answer, checked against the pinned document for its route. */
  marketView(path: keyof paths, query: Record<string, string | number>, call: Call = {}): Promise<unknown> {
    return this.get(path, { query }, call);
  }

  securityAnalyst(symbol: string, call: Call = {}): Promise<Schemas["AnalystConsensus"]> {
    return this.get("/v1/securities/{symbol}/analyst", { path: { symbol } }, call);
  }

  securityCalendar(symbol: string, call: Call = {}): Promise<Schemas["SecurityCalendar"]> {
    return this.get("/v1/securities/{symbol}/calendar", { path: { symbol } }, call);
  }

  institutionalHolders(
    symbol: string,
    query: { limit: number; quarter?: string; after?: string },
    call: Call = {},
  ): Promise<Schemas["InstitutionalHoldersResponse"]> {
    return this.get("/v1/securities/{symbol}/institutional-holders", { path: { symbol }, query }, call);
  }

  securityDigest(symbol: string, call: Call = {}): Promise<Schemas["DigestResponse"]> {
    return this.get("/v1/securities/{symbol}/digest", { path: { symbol } }, call);
  }

  marketDigest(call: Call = {}): Promise<Schemas["DigestResponse"]> {
    return this.get("/v1/digests/market", {}, call);
  }

  thesis(symbol: string, call: Call = {}): Promise<Schemas["ThesisResponse"]> {
    return this.get("/v1/securities/{symbol}/thesis", { path: { symbol } }, call);
  }

  themes(call: Call = {}): Promise<Schemas["ThemesResponse"]> {
    return this.get("/v1/themes", { query: { limit: 10 } }, call);
  }

  research(symbol: string, call: Call = {}): Promise<Schemas["SharedResearchReport"]> {
    return this.get("/v1/securities/{symbol}/research", { path: { symbol } }, call);
  }

  equityFinancials(
    query: Query<"list_equity_financials">,
    call: Call = {},
  ): Promise<Schemas["CrossSectionFinancialsResponse"]> {
    return this.get("/v1/markets/equity/financials", { query }, call);
  }

  corporateActions(symbol: string, call: Call = {}): Promise<Schemas["CorporateActions"]> {
    return this.get("/v1/securities/{symbol}/corporate-actions", { path: { symbol } }, call);
  }

  /** One statement's lines per period (`statement=`, strict view, latest assertions). */
  async statement(
    symbol: string,
    query: Query<"list_security_financials"> & {
      statement: NonNullable<Query<"list_security_financials">["statement"]>;
    },
    call: Call = {},
  ): Promise<Statement> {
    const answer = await this.get<Record<string, unknown>>(
      "/v1/securities/{symbol}/financials",
      { path: { symbol }, query: { ...query, view: "continuity" } },
      call,
    );
    // The route answers concept reads in other forms; a statement read must come back as one, across
    // successions (the continuity view).
    if (!("statement" in answer) || answer.view !== "continuity") {
      throw new DataError("unavailable", "Tauric answered the statement request in another form.", {
        source: SOURCE,
      });
    }
    return answer as unknown as Statement;
  }

  profile(symbol: string, call: Call = {}): Promise<Profile> {
    return this.get("/v1/securities/{symbol}/profile", { path: { symbol } }, call);
  }

  async filings(
    symbol: string,
    query: Query<"list_security_filings"> = {},
    call: Call = {},
  ): Promise<Filings> {
    const answer = await this.get<Filings>(
      "/v1/securities/{symbol}/filings",
      { path: { symbol }, query: { ...query, view: "continuity" } },
      call,
    );
    // Filings are read across successions (the continuity view): a successor's history includes its
    // predecessors' filings, each with its own filer.
    if (answer.view !== "continuity") {
      throw new DataError("unavailable", "Tauric answered the filings request in another form.", {
        source: SOURCE,
      });
    }
    return answer;
  }

  filingSection(
    path: { symbol: string; accession: string; section: string },
    query: Query<"get_security_filing_section"> = {},
    call: Call = {},
  ): Promise<FilingSection> {
    return this.get("/v1/securities/{symbol}/filings/{accession}/sections/{section}", { path, query }, call);
  }

  insider(
    symbol: string,
    query: Query<"list_security_insider_transactions"> = {},
    call: Call = {},
  ): Promise<InsiderTransactions> {
    return this.get("/v1/securities/{symbol}/insider-transactions", { path: { symbol }, query }, call);
  }

  news(query: Query<"list_news"> = {}, call: Call = {}): Promise<News> {
    return this.get("/v1/news", { query }, call);
  }

  newsArticle(id: string, call: Call = {}): Promise<Schemas["ArticleDetail"]> {
    return this.get("/v1/news/{article_id}", { path: { article_id: id } }, call);
  }

  searchNews(query: Query<"search_news">, call: Call = {}): Promise<NewsSearch> {
    return this.get("/v1/news/search", { query }, call);
  }

  /**
   * One published GET, with path and query parameters as the route names them. The answer is checked
   * against the pinned document for that route, so its declared type is what it holds.
   */
  private get<T>(
    path: keyof paths,
    params: { path?: Record<string, string>; query?: object },
    { signal }: Call,
  ): Promise<T> {
    return this.transport.guarded(() =>
      this.transport.read<T>(
        "data",
        "get",
        path,
        () =>
          this.http.GET(path as never, { params, ...within(signal) } as never) as Promise<{
            data?: T;
            error?: unknown;
            response: Response;
          }>,
      ),
    );
  }
}
