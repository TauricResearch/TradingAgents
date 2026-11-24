// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * What the tools can ask for, one interface per capability, with result types of our own. Providers
 * (data/tauric, data/yahoo, data/polymarket) implement the capabilities they offer; the router
 * (data/router.ts) picks among them by the routing table (data/routes.ts). Nothing above data/
 * knows which provider answered except through `source` and `notes` on each result.
 */

import type { DataErrorKind } from "../contracts/index.js";

/**
 * One capability's answer: the data, the provider that gave it, what a reader should know (a
 * fallback), the providers that failed before it, and whether the data may be copied with a synced
 * session (`syncs`, as its provider says).
 */
export type Sourced<T> = { data: T; source: string; notes: string[]; after: string[]; syncs?: true };

export type Call = { signal?: AbortSignal };

/** The listing a result is about, as its provider describes it. */
export type Instrument = {
  key?: string | null;
  name?: string | null;
  currency?: string | null;
  /** Quotation scale against the currency's main unit (London pence: 0.01). */
  price_scale?: number | null;
  venue?: string | null;
  listing?: { state?: string | null; delisted_at?: string | null } | null;
  /** How a continuous futures series is made, when the instrument is one (rolls are not marked). */
  continuous?: unknown;
  /** What the instrument is ("stock", "future", "rate", "index", ...), as the provider classifies it. */
  classification?: { instrument_type?: string | null } | null;
};

/** Why a value is missing or limited, by field: the source's reason and whether asking again can change it. */
export type FieldStates =
  | Record<string, { reason?: string | null; retry?: string | null } | undefined>
  | null
  | undefined;

// Quotes ---------------------------------------------------------------------------------------

export type Quote = {
  instrument?: Instrument | null;
  quote_kind?: string | null;
  price?: number | null;
  price_basis?: string | null;
  /** When the price traded, and whether the source calls it stale. */
  price_time?: string | null;
  stale?: boolean | null;
  session_date?: string | null;
  market_state?: string | null;
  /** The previous session's close, as the provider describes it (a value and its date). */
  previous_close?: unknown;
  /** The change against `change_basis` (the previous close, by default), in price units and percent. */
  change?: number | null;
  change_percent?: number | null;
  change_basis?: string | null;
  /** The session's (or the last 24 hours') range, open and volume. */
  day?: QuoteRange | null;
  range_52w?: QuoteRange | null;
  market_cap?: number | null;
  field_states?: FieldStates;
};
/** A quote's low and high (and, for its day, its open and volume), each null when the source has none. */
type QuoteRange = {
  low?: number | null;
  high?: number | null;
  open?: number | null;
  volume?: number | null;
  [field: string]: unknown;
};
/** Several instruments' quotes: each one asked for, with its quote or why it has none. */
export type QuoteBatch = {
  /** `source`: the source that answered this one, when a later source than the batch's did. */
  quotes: { instrument: string; quote: Quote; source?: string }[];
  /** `kind`: what the failure means, when known; the next source is asked as for one call. */
  errors: { instrument: string; message: string; kind?: DataErrorKind }[];
};
export interface Quotes {
  /** The latest quote of an instrument: a ticker, or a typed key (data/instrument-key.ts). */
  quote(instrument: string, call?: Call): Promise<Sourced<Quote>>;
  /** Several instruments' latest quotes at once; one that has none is said, not fatal. */
  many(instruments: readonly string[], call?: Call): Promise<Sourced<QuoteBatch>>;
}

// Price history --------------------------------------------------------------------------------

export type DailyBar = {
  /** The session's exchange-local date. */
  date: string;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  close?: number | null;
  volume?: number | null;
  /** "final" once the source will not revise it; "provisional" before. */
  revision: "final" | "provisional";
  field_states?: FieldStates;
};
export type DailyBars = {
  instrument?: Instrument | null;
  /** How prices and volume are adjusted, as the provider states it. */
  price_basis: string | null;
  /** Completed sessions only, oldest first, within the window asked for. */
  bars: DailyBar[];
  coverage: {
    from: string | null;
    through: string | null;
    complete: boolean | null;
    /** Why the window is incomplete, as the source says it ("insufficient_history"). */
    complete_reason?: string | null;
    /** The first date the source has history for. */
    history_from?: string | null;
    /** Sessions in the window the source flags as missing or not complete. */
    missing_sessions: number;
  };
  /** `to` of the next older window when the source has bars before this one; null when it has none. */
  earlier_end: string | null;
};
/** A security's intraday bars, oldest first: each with the UTC time it starts and its session's date. */
type IntradayBars = {
  instrument?: Instrument | null;
  price_basis: string | null;
  bars: (Omit<DailyBar, "date"> & { start: string; date: string })[];
  /** Sessions in the window the source flags as missing or short, and why the window is incomplete. */
  missing_sessions: number;
  incomplete_because: string | null;
  /** The first date the source has intraday history for. */
  history_from: string | null;
  /** `end` of the next older page when the source has bars before these; null when it has none. */
  earlier_end: string | null;
};
/** A currency pair's daily reference rates (not market closes): one value per publication day. */
export type ReferenceRates = {
  instrument?: Instrument | null;
  /** Who sets the rates and how ("ECB reference rates, observed"). */
  basis: string;
  /** Oldest first, within the window asked for. */
  rates: { date: string; value: number | null }[];
  complete: boolean | null;
  /** `to` of the next older window when the source has rates before this one. */
  earlier_end: string | null;
};
export interface PriceHistory {
  /** Daily bars of completed sessions from `from` to `to`, both inclusive, of any instrument with bars. */
  daily(instrument: string, window: { from: string; to: string }, call?: Call): Promise<Sourced<DailyBars>>;
  /** A currency pair's daily reference rates from `from` to `to`, both inclusive. */
  referenceRates(
    pair: string,
    window: { from: string; to: string },
    call?: Call,
  ): Promise<Sourced<ReferenceRates>>;
  /**
   * A security's intraday bars from `start`, the newest `limit` of them, oldest first; `earlier_end` pages
   * back (pass it as the next `end`, inclusive) until it is null.
   */
  intraday(
    symbol: string,
    query: { interval: "15m" | "1h"; start: string; end?: string; limit: number },
    call?: Call,
  ): Promise<Sourced<IntradayBars>>;
  /** Two listings' bars over one window from one provider, for comparisons that must not mix sources. */
  dailyPair(
    symbols: readonly [string, string],
    window: { from: string; to: string },
    call?: Call,
  ): Promise<Sourced<[DailyBars, DailyBars]>>;
}

// Statements -----------------------------------------------------------------------------------

type StatementLine = {
  line: string;
  value?: number | null;
  /** The unit as filed ("USD", "shares", "USD/shares"). */
  unit?: string | null;
  period_start?: string | null;
  field_states?: FieldStates;
  /** The filings a value comes from, each with its filer and whether that filer is a predecessor. */
  sources?:
    | { accession: string; form: string; accepted_at: string; cik: string; predecessor: boolean }[]
    | null;
};
/** A filer's coverage: whether its filings are complete as held, and why not. */
export type Registrant = {
  cik: string;
  complete?: boolean | null;
  complete_reason?: string | null;
  /** For a predecessor: the day its successor took over (its filings come before then). */
  succeeded_on?: string | null;
};
/**
 * A company's filers across successions, the current one first, and the filers the source could not link
 * further back (their earlier history is not included).
 */
export type Succession = { registrants: Registrant[]; stopsAt: string[] };
export type Statement = {
  instrument?: Instrument | null;
  periods: { period_end: string; lines: StatementLine[] }[];
  succession: Succession;
  next_cursor?: string | null;
};
export interface Statements {
  statement(
    symbol: string,
    query: {
      statement: "income_statement" | "balance_sheet" | "cash_flow";
      periodType: "quarterly" | "annual";
      limit: number;
      after?: string;
    },
    call?: Call,
  ): Promise<Sourced<Statement>>;
}

// Filings --------------------------------------------------------------------------------------

/** The sections a filing's text can be read by. */
export const FILING_SECTIONS = [
  "business",
  "risk_factors",
  "mdna",
  "market_risk",
  "financial_statements",
] as const;
export type FilingSectionName = (typeof FILING_SECTIONS)[number];

type FilingList = {
  instrument?: Instrument | null;
  succession: Succession;
  data: {
    form: string;
    accession: string;
    /** The filer, and whether it is a predecessor of the company's current registrant. */
    cik: string;
    predecessor: boolean;
    filed?: string | null;
    accepted_at: string;
    report_date?: string | null;
    url?: string | null;
    /** Each section the filing has: its text "available", or "by_reference" to another document. */
    sections?: { section: string; state?: string | null }[] | null;
  }[];
  next_cursor?: string | null;
};
type FilingSectionText = {
  form: string;
  accession: string;
  accepted_at: string;
  section: string;
  state?: string | null;
  /** Why no text is served (`content`), when the source says. */
  field_states?: FieldStates;
  content?: string | null;
  chars?: number | null;
  next_cursor?: string | null;
};
export interface Filings {
  list(
    symbol: string,
    query: { limit: number; forms?: string[]; after?: string },
    call?: Call,
  ): Promise<Sourced<FilingList>>;
  section(
    target: { symbol: string; accession: string; section: FilingSectionName },
    query: { after?: string },
    call?: Call,
  ): Promise<Sourced<FilingSectionText>>;
}

// News -----------------------------------------------------------------------------------------

type Article = {
  id: string;
  title: string | null;
  publisher?: string | null;
  url?: string | null;
  /** When it was published, or failing that listed or obtained: the time the source dates it by. */
  published_at?: string | null;
  annotations?: { summary?: string | null; sentiment?: string | null; impact?: string | null } | null;
};
type ArticlePage = { articles: Article[]; next_cursor?: string | null };
/** The filters articles can be asked for by, as the news source names them. */
export const NEWS_TOPICS = [
  "earnings",
  "revenue",
  "guidance",
  "ipo",
  "merger",
  "acquisition",
  "regulation",
  "lawsuit",
  "product_launch",
  "partnership",
  "supply_chain",
  "layoffs",
  "executive",
  "dividend",
  "buyback",
  "bankruptcy",
  "macro",
  "fed",
  "inflation",
  "rates",
  "employment",
  "gdp",
  "trade",
  "tariffs",
  "sanctions",
  "geopolitics",
  "technology",
  "ai",
  "semiconductor",
  "energy",
  "oil",
  "commodities",
  "real_estate",
  "healthcare",
  "pharma",
  "banking",
  "fintech",
  "crypto",
  "defi",
  "mining",
  "stablecoin",
] as const;
export const NEWS_EVENT_TYPES = [
  "earnings",
  "guidance",
  "analyst_rating",
  "m_and_a",
  "partnership",
  "product",
  "legal_regulatory",
  "macro",
  "insider_activity",
  "capital_return",
  "price_move",
  "other",
] as const;
export const NEWS_SENTIMENTS = ["bearish", "bullish", "mixed", "neutral"] as const;
export const NEWS_IMPACTS = ["high", "medium", "low"] as const;
/** One article read whole: its points, the events and figures it reports, and who it quotes. */
type ArticleDetail = Article & {
  /** When the source made the article available. */
  available_at: string | null;
  /** What `published_at` is: the publication time, or failing one, when it was listed or obtained. */
  time_kind: string | null;
  word_count?: number | null;
  topics: string[];
  instruments: string[];
  events: {
    event_type: string;
    headline: string | null;
    date_stated?: string | null;
    instruments: string[];
  }[];
  figures: {
    metric: string | null;
    value_stated: string | null;
    period_stated?: string | null;
    instruments: string[];
  }[];
  quotations: { speaker: string | null; text: string }[];
};
export interface News {
  /** Articles, newest first: market-wide, about one listing, matching a query, narrowed by the filters. */
  articles(
    query: {
      symbol?: string;
      query?: string;
      since?: string;
      until?: string;
      limit: number;
      after?: string;
      topic?: (typeof NEWS_TOPICS)[number];
      eventType?: (typeof NEWS_EVENT_TYPES)[number];
      sentiment?: (typeof NEWS_SENTIMENTS)[number];
      impact?: (typeof NEWS_IMPACTS)[number];
    },
    call?: Call,
  ): Promise<Sourced<ArticlePage>>;
  /** One article by its id. */
  article(id: string, call?: Call): Promise<Sourced<ArticleDetail>>;
}

// Profiles -------------------------------------------------------------------------------------

/** The company facts a profile shows, in this order. */
export const PROFILE_FIELDS = [
  "sector",
  "industry_group",
  "industry",
  "sub_industry",
  "country",
  "financial_currency",
  "market_cap",
  "market_cap_basis",
  "market_cap_price_date",
  "enterprise_value",
  "pe_ratio",
  "forward_pe",
  "peg_ratio",
  "price_to_book",
  "price_to_sales",
  "profit_margin",
  "operating_margin",
  "return_on_assets",
  "return_on_equity",
  "revenue_growth",
  "earnings_growth",
  "total_cash",
  "total_debt",
  "debt_to_equity",
  "current_ratio",
  "quick_ratio",
  "dividend_rate",
  "dividend_yield",
  "payout_ratio",
  "beta",
  "shares_outstanding",
  "float_shares",
  "employees",
  "website",
  "description",
  "shares_short",
  "days_to_cover",
  "short_interest_of_float",
  "institutional_ownership",
  "insider_ownership",
  "fund_yield",
  "nav_price",
  "five_year_avg_return",
  "beta_3y",
] as const;
type Profile = {
  instrument?: Instrument | null;
  field_states?: FieldStates;
  dataset_status?: { refreshed_at?: string | null } | null;
} & { [Field in (typeof PROFILE_FIELDS)[number]]?: string | number | null };
export interface Profiles {
  /** The company today. */
  profile(symbol: string, call?: Call): Promise<Sourced<Profile>>;
  /** Analysts' consensus: rating, price targets, the distribution of ratings, EPS estimates. */
  analyst(symbol: string, call?: Call): Promise<Sourced<Record<string, unknown>>>;
  /** The next stated earnings date (or the latest) with its estimates, and the latest dividend. */
  calendar(symbol: string, call?: Call): Promise<Sourced<Record<string, unknown>>>;
}

// Insider transactions -------------------------------------------------------------------------

type InsiderTransactions = {
  instrument?: Instrument | null;
  filings: Record<
    string,
    {
      form?: string | null;
      accepted_at?: string | null;
      owners?: {
        name?: string | null;
        officer_title?: string | null;
        is_director?: boolean | null;
        is_ten_percent_owner?: boolean | null;
      }[];
    }
  >;
  coverage?: {
    from?: string | null;
    through?: string | null;
    complete?: boolean | null;
    requested_before_window?: boolean | null;
    not_yet_served?: number | null;
    complete_after?: string | null;
  } | null;
  data: {
    accession: string;
    transaction_date?: string | null;
    code?: string | null;
    shares?: number | null;
    security_title?: string | null;
    derivative?: boolean | null;
    conversion_or_exercise_price?: number | null;
    underlying_shares?: number | null;
    underlying_title?: string | null;
    price?: number | null;
    acquired_disposed?: string | null;
    owned_following?: number | null;
  }[];
  next_cursor?: string | null;
};
export interface Ownership {
  transactions(
    symbol: string,
    query: {
      limit: number;
      start?: string;
      end?: string;
      codes?: string[];
      after?: string;
    },
    call?: Call,
  ): Promise<Sourced<InsiderTransactions>>;
  /** Institutional managers' 13F holdings of one quarter, largest first; each manager's report as filed. */
  holders(
    symbol: string,
    query: { limit: number; quarter?: string; after?: string },
    call?: Call,
  ): Promise<Sourced<InstitutionalHolders>>;
}

type InstitutionalHolders = {
  instrument?: Instrument | null;
  /** The quarter served, whether its filings are all in, and the quarters there are. */
  quarter: string | null;
  complete: boolean | null;
  quarters: string[];
  /** Why holdings may be missing: CUSIPs not matched, or other share classes' left out. */
  caveats: string[];
  holders: {
    manager: string;
    filed: string | null;
    form: string | null;
    value: number | null;
    /** "dollars" for filings since 2023, "thousands of dollars" before. */
    value_unit: string | null;
    shares: number | null;
    shares_type: string | null;
    put_call: string | null;
    discretion: string | null;
    accession: string;
  }[];
  next_cursor: string | null;
};

// Corporate actions ----------------------------------------------------------------------------

type CorporateAction = {
  /** The first session the action is effective in. */
  ex_date: string;
  /** "split" or "dividend" (a special dividend reads as a dividend). */
  action_type: string;
  /** A split: shares after over shares before (4 for 4:1); a cash action: the amount per share. */
  value: number | null;
  /** "ratio" for a split; for cash, the currency per share. */
  unit: string | null;
  /** Cash: whether the amount is per share as of today's share count (split adjusted). */
  cash_basis: string | null;
  /** An earlier report of this action had a different value. */
  revised: boolean;
  field_states?: FieldStates;
};
type CorporateActionList = {
  instrument?: Instrument | null;
  actions: CorporateAction[];
  /** The newest session the listing's daily bars hold, and whether an update is overdue. */
  through: string | null;
  stale: boolean | null;
};
export interface CorporateActions {
  /** A listing's reported splits and cash distributions; an empty list does not establish that there were none. */
  list(symbol: string, call?: Call): Promise<Sourced<CorporateActionList>>;
}

// Cross section ---------------------------------------------------------------------------------

/** The GICS sectors a cross section is read by. */
export const SECTORS = [
  "energy",
  "materials",
  "industrials",
  "consumer_discretionary",
  "consumer_staples",
  "health_care",
  "financials",
  "information_technology",
  "communication_services",
  "utilities",
  "real_estate",
] as const;
/** One company's value of a line for one fiscal year, as filed (or derived, when the source says so). */
export type CrossSectionRow = {
  ciks: string[];
  name: string | null;
  symbols: string[];
  /** The value in base units (the unit's multiplier applied). */
  value: number | null;
  /** The unit as people read it ("USD"), and the group values are compared within (kind, currency, per). */
  unit: string | null;
  unit_group: string | null;
  period_start: string | null;
  period_end: string | null;
  /** "filed", or how the value was derived from what was filed. */
  derivation: string | null;
  /** Why there is no value, when there is none. */
  missing_because: string | null;
  form: string | null;
  accession: string | null;
};
type CrossSection = {
  rows: CrossSectionRow[];
  pages: number;
  /** Whether the sector was read to its end; why not, when it was not. */
  complete: boolean;
  incomplete_because: string | null;
  /** The instant every page was read as of, to read another year as of too. */
  known_at: string | null;
};
export interface CrossSections {
  /**
   * Every company of a sector with its value of one statement line for one fiscal year, read page by
   * page up to `maxPages`, all as of one instant; a read cut short (by a limit or the source) says so.
   */
  financials(
    query: {
      sector: (typeof SECTORS)[number];
      line: string;
      /** The calendar year each company's fiscal year ends in. */
      fiscalYear: number;
      knownAt?: string;
      maxPages: number;
    },
    call?: Call,
  ): Promise<Sourced<CrossSection>>;
}

// Tauric AI's synthesis -----------------------------------------------------------------------

/** A piece of Tauric AI's writing: when it was written, whether a later version replaced it, and the content. */
export type Synthesis = {
  instrument?: Instrument | null;
  /** The session or date it is for, when it says. */
  for_date: string | null;
  generated_at: string | null;
  superseded: boolean | null;
  /** The research report's stance on the expected 12-month return, when it has one. */
  stance: string | null;
  content: unknown;
};
export interface Syntheses {
  /** One security's news digest, or the market's when no symbol is given. */
  digest(symbol: string | undefined, call?: Call): Promise<Sourced<Synthesis>>;
  thesis(symbol: string, call?: Call): Promise<Sourced<Synthesis>>;
  /** The latest weekly themes across the news, largest first. */
  themes(call?: Call): Promise<Sourced<Synthesis>>;
  /** The latest daily research report on a covered security. */
  research(symbol: string, call?: Call): Promise<Sourced<Synthesis>>;
}

// Technicals -----------------------------------------------------------------------------------

/**
 * The indicators, with the definitions the technicals tool states (RSI 14 Wilder, MACD 12/26/9,
 * Bollinger 20/2, ATR 14 and 5, ...): a provider of this capability computes them that way.
 */
export const INDICATORS = [
  "rsi",
  "macd",
  "macd_signal",
  "macd_histogram",
  "sma_50",
  "sma_200",
  "ema_10",
  "ema_50",
  "bb_upper",
  "bb_middle",
  "bb_lower",
  "atr",
  "atr_5",
  "stochastic_k",
  "stochastic_d",
  "cci",
  "adx",
  "z_score_75",
  "roc",
  "mfi",
  "vwma",
  "pvo",
] as const;
export type TechnicalsAnswer = {
  instrument?: Instrument | null;
  through?: string | null;
  last_value?: { value?: number | null; date?: string | null } | null;
  window?: {
    bars?: number | null;
    /** Sessions left out of the computation, with the source's reason. */
    missing?: { date: string; reason?: string | null }[] | null;
    /** The last session no longer expected to change; later ones may still be revised. */
    settled_through?: string | null;
  } | null;
  price_basis?: string | null;
  /** Whether volume is available, so the volume-based indicators could be computed. */
  volume_available?: boolean | null;
  field_states?: FieldStates;
  history_rows?: number | null;
  rows_needed?: number | null;
  /** Where the close and the averages stand against each other: "above" or "below". */
  price_vs_sma50?: string | null;
  price_vs_sma200?: string | null;
  sma50_vs_sma200?: string | null;
} & { [Indicator in (typeof INDICATORS)[number]]?: number | null };
export interface Technicals {
  /** Indicators of an instrument with daily bars at its latest session. */
  latest(instrument: string, call?: Call): Promise<Sourced<TechnicalsAnswer>>;
}

// Macro series ---------------------------------------------------------------------------------

export type SeriesMeta = {
  key: string;
  name: string;
  shape?: string | null;
  frequency?: string | null;
  seasonal_adjustment?: string | null;
  unit?: { kind?: string | null; [detail: string]: unknown } | null;
  as_published?: {
    unit?: string | null;
    frequency?: string | null;
    seasonal_adjustment?: string | null;
  } | null;
  field_states?: FieldStates;
};
export type SeriesObservation = {
  value?: number | null;
  status?: string | null;
  known_from?: string | null;
  evidence?: string | null;
  field_states?: FieldStates;
  period: { kind: string; start: string; label: string };
};
export type SeriesObservations = {
  series: SeriesMeta;
  coverage?: {
    missing?: { period: { label: string }; reason?: string | null }[] | null;
    continue_end?: string | null;
    complete_reason?: string | null;
  } | null;
  observations: SeriesObservation[];
};
export interface MacroSeries {
  search(query: string, call?: Call): Promise<Sourced<SeriesMeta[]>>;
  observations(
    key: string,
    query: { limit: number; end?: string },
    call?: Call,
  ): Promise<Sourced<SeriesObservations>>;
}

// Instruments ----------------------------------------------------------------------------------

/** An instrument a search found: its key, what it is, and the capabilities that serve it. */
export type InstrumentMatch = {
  key: string;
  name?: string | null;
  /** What it is: "stock", "etf", "future", "spot", "index", "economic", ... */
  type?: string | null;
  listing_state?: string | null;
  serves: Capability[];
};
export interface Instruments {
  /** Instruments matching a name, symbol or code, best match first; of one kind when `kind` is given. */
  search(query: string, kind: string | undefined, call?: Call): Promise<Sourced<InstrumentMatch[]>>;
}

// Markets ----------------------------------------------------------------------------------------

/** The market views, each one snapshot of today's market. */
export const MARKET_VIEWS = [
  "equity_summary",
  "sectors",
  "gainers",
  "losers",
  "most_active",
  "volatility",
  "yield_curve",
  "central_banks",
  "credit_spreads",
  "energy",
  "metals",
  "agriculture",
  "fx",
  "cross_asset",
  "crypto",
  "macro",
  "indices",
  "sector_rotation",
  "tips_breakevens",
  "rate_indicators",
  "commodity_benchmarks",
  "livestock",
] as const;
export type MarketViewName = (typeof MARKET_VIEWS)[number];
/** One view: its rows, figures about the whole (breadth, the curve's date), and what it could not include. */
export type MarketView = {
  rows: Record<string, unknown>[];
  summary: Record<string, unknown>;
  /** Some of what it could not include (the source lists a sample), with the counts of all of it. */
  missing: { key: string; reason?: string | null }[];
  coverage: {
    requested: number | null;
    measured: number | null;
    byReason: { reason: string | null; count: number }[];
  } | null;
  /** The latest day the data reaches, and whether the source calls it stale. */
  through?: string | null;
  stale?: boolean | null;
  /** Whether the view has more rows than these. */
  more: boolean;
};
export interface Markets {
  /** One view of today's market. */
  view(view: MarketViewName, call?: Call): Promise<Sourced<MarketView>>;
}

// Prediction markets ---------------------------------------------------------------------------

export type MarketOdds = {
  question: string;
  /** Outcome names and their prices (probabilities, 0 to 1), paired. */
  outcomes: { name: string; price: number }[];
  /** Traded volume in dollars, when the source says. */
  volume?: number;
  endDate: string;
  /** The first outcome's price change over a week (-1 to 1), when the source gives it. */
  oneWeekChange?: number;
  url?: string;
};
export type MarketSearch = {
  /** Markets open now: not closed, not archived, active, and ending after `now`. */
  open: MarketOdds[];
  /** Markets left out because the source described them incompletely or malformedly. */
  dropped: number;
  /** Whether the source has more results than this one page. */
  more: boolean;
};
export interface PredictionMarkets {
  search(topic: string, now: Date, call?: Call): Promise<Sourced<MarketSearch>>;
}

// The whole set --------------------------------------------------------------------------------

export type Capabilities = {
  quotes: Quotes;
  priceHistory: PriceHistory;
  statements: Statements;
  filings: Filings;
  news: News;
  profiles: Profiles;
  ownership: Ownership;
  corporateActions: CorporateActions;
  syntheses: Syntheses;
  crossSections: CrossSections;
  technicals: Technicals;
  macroSeries: MacroSeries;
  instruments: Instruments;
  markets: Markets;
  predictionMarkets: PredictionMarkets;
};
export type Capability = keyof Capabilities;

/** Each capability's methods, so a capability is a plain object with exactly these. */
export const METHODS: { readonly [Name in Capability]: readonly (keyof Capabilities[Name])[] } = {
  quotes: ["quote", "many"],
  priceHistory: ["daily", "dailyPair", "referenceRates", "intraday"],
  statements: ["statement"],
  filings: ["list", "section"],
  news: ["articles", "article"],
  profiles: ["profile", "analyst", "calendar"],
  ownership: ["transactions", "holders"],
  corporateActions: ["list"],
  syntheses: ["digest", "thesis", "themes", "research"],
  crossSections: ["financials"],
  technicals: ["latest"],
  macroSeries: ["search", "observations"],
  instruments: ["search"],
  markets: ["view"],
  predictionMarkets: ["search"],
};

/** A capability as a provider implements it: the same methods, answering the data alone (the router adds the rest). */
export type Implementation<C> = {
  [Method in keyof C]?: C[Method] extends (...args: infer Args) => Promise<Sourced<infer Data>>
    ? (...args: Args) => Promise<Data>
    : never;
};

/** A source of data: its name as people read it, and the capabilities it implements. */
export type DataProvider = {
  name: string;
  /** Its data may be copied with a synced session; another's stays on this computer. */
  syncs?: true;
  capabilities: { [Name in Capability]?: Implementation<Capabilities[Name]> };
};
