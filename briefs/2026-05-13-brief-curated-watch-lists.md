# Brief: Curated Watch Lists

**Date:** 2026-05-13
**Status:** Open
**Epic ID:** WATCH-001

---

## Objective

Build an automated watchlist curation system that screens, enriches, and prioritises prospects based on configurable criteria — sector indices, geopolitical risk signals, fundamental screens, and analyst conviction lists. The system extends the existing `watchlist` table and `alerts` engine to support rule-based screening, automated enrichment, and structured output views in both the CLI and dashboard.

---

## Background

The current watchlist is a manual input system: tickers are added via the dashboard or seed data with a thesis, priority, and stage. There is no automated screening engine, no enrichment pipeline that fetches fundamental data, and no way to define screening rules (e.g. "flag tickers where P/S ratio is bottom decile in sector").

Separately, the `alerts` engine (`alerts-db.ts`, `alerts-engine.ts`) provides a condition-based matching system for price thresholds and percentage changes, but it evaluates against enabled alert rules — not against screening criteria across watchlist candidates.

**What exists today:**

| Component | File | Capability |
|-----------|------|------------|
| Watchlist table | `schema.sql` | `watchlist` table with ticker, thesis, priority, stage |
| Watchlist CLI | `src/cli/commands/watchlist.ts` | Lists prospects with priority/stage |
| Prospects data | `src/server/lib/prospects-data.ts` | CRUD for watchlist items |
| Alerts engine | `src/server/lib/alerts-engine.ts` | Condition-based price alert matching |
| Price data | `prices` table | Daily OHLCV per ticker |
| IG search | `src/cli/commands/ig-search.ts` | Market discovery by name/ticker |
| Dashboard views | `src/server/views/` | HTMX-rendered portfolio and alert views |

**What's missing:**

- A screening engine that evaluates candidates against configurable criteria (fundamental ratios, sector conditions, geopolitical flags)
- Automated enrichment that fetches fundamental data (forward P/E, EPS growth, operating margin, beta) for watchlist candidates via Yahoo Finance + IG API
- **Web-based enrichment** via `defuddle` (built-in web fetch) for analyst ratings, price targets, news sentiment, and geopolitical risk signals
- A CLI command to run screening and generate curated lists
- Dashboard views to review screening results and promote candidates through stages
- Scheduled screening runs (weekly cadence)
- News sentiment scoring for watchlist candidates

---

## Requirements

### R01: Screening Rule Definition

Define screening rules as JSON conditions, parallel to how `alerts` defines alert conditions but scoped to watchlist candidates rather than price triggers.

```typescript
type ScreenCondition = {
  field: "pe_forward" | "eps_growth_1y" | "operating_margin" | "beta_1y" | "price_to_sales" | "sector" | "region"
  operator: "gt" | "lt" | "eq" | "in" | "bottom_pct" | "top_pct"
  value: number | string | string[]
}
```

- [ ] **R01.1:** `screening_rules` table in schema with JSON column for rule definition
- [ ] **R01.2:** CLI command `trading screen create` to add a screening rule
- [ ] **R01.3:** CLI command `trading screen list` to show defined screening rules
- [ ] **R01.4:** CLI command `trading screen delete` to remove a screening rule

### R02: Data Enrichment Pipeline

Fetch fundamental data for watchlist candidates from Yahoo Finance (via existing `scripts/get_price.ts` infrastructure) and IG (via `IGClient`):

- [ ] **R02.1:** `screening-enrich.ts` script (or module) that fetches forward P/E, EPS growth, operating margin, 1Y beta, and price-to-sales for a given ticker
- [ ] **R02.2:** Store enriched fundamental data in a `watchlist_enrichment` table (keyed by ticker + date)
- [ ] **R02.3:** CLI command `trading screen enrich [--all | --ticker <ticker>]` to populate enrichment data
- [ ] **R02.4:** Use `defuddle` (web_fetch) to fetch analyst ratings and price targets from public financial sources (e.g., finviz, Yahoo Finance analyst page)
- [ ] **R02.5:** Cache enrichment results with TTL to avoid redundant fetches

> **Data model clarification:** Enrichment data is split into two tables:
> - `watchlist_enrichment` — one row per ticker per fetch date; columns: `ticker`, `fetch_date`, `pe_forward`, `eps_growth_1y`, `operating_margin`, `beta_1y`, `price_to_sales`, `sector`, `region`, `source`, `created_at`. Upsert on `(ticker, fetch_date)`.
> - `watchlist_news_sentiment` — one row per headline; columns: `id`, `ticker`, `published_date`, `headline_text`, `summary`, `sentiment_score` (-1 to 1), `source`, `enrichment_id` (FK to `watchlist_enrichment` on ticker+date). Foreign key ensures multi-headline writes (R07.2) are unambiguous: each headline references its parent enrichment row.
>
> **Why separate tables?** Aggregation (avg sentiment, headline count) is easier in a normalised schema. A single JSON field of multiple headlines would require parsing on every query and makes dedup/truncation hard.

### R03: Screening Engine

Evaluate screening rules against enriched data and produce a scored, prioritised list:

- [ ] **R03.1:** `screening-engine.ts` — pure function that takes screening rules + enrichment data, returns matched candidates with match reasons
- [ ] **R03.2:** Screening respects the watchlist stage progression: `researching → analyzed → candidate → approved → acquired`
- [ ] **R03.3:** CLI command `trading screen run` that runs all enabled screening rules and outputs a table of matched candidates
- [ ] **R03.4:** Support for `--json` flag for programmatic consumption

### R04: Curated List Output

Structured output in both CLI and dashboard:

- [ ] **R04.1:** CLI output shows: ticker, matched criteria, priority score, current price, sector, region
- [ ] **R04.2:** Dashboard tab showing curated watchlist with screening results (move/undeveloped into stage progression)
- [ ] **R04.3:** "Shock Stock" view: tickers where price has dropped >X% but fundamentals remain strong (operating margin > Y, P/S in bottom Z%)
- [ ] **R04.4:** Export curated list as markdown or JSON for review

### R05: Weekly Screening Cadence

- [ ] **R05.1:** `trading screen run --schedule weekly` runs every Friday at market close
- [ ] **R05.2:** Uses `just` recipe for cron wrapper (see `hledger.just` for cron pattern)
- [ ] **R05.3:** Output persists to `watchlist_screenings` table for history

### R06: Geopolitical Context Flags (Stretch)

- [ ] **R06.1:** Tag watchlist candidates with `geopolitical_risk` field (e.g. "hormuz-exposed", "supply-chain-secure")
- [ ] **R06.2:** CLI flag `--geopolitical` on `trading screen run` to include conflict-zone filters
- [ ] **R06.3:** Dashboard indicator showing which prospects have non-interdicted supply chains

### R07: News Sentiment Enrichment

Fetch recent news and analyst sentiment for watchlist candidates using `defuddle`:

- [x] **R07.1:** Fetch recent headlines for a ticker via Google News RSS (~20 headlines per ticker, 1s rate limit between tickers)
- [x] **R07.2:** Store each headline as a separate row in `watchlist_news_sentiment`
- [x] **R07.3:** CLI command `trading screen enrich --sentiment --ticker <ticker>` to fetch and score recent news
- [x] **R07.4:** Screening engine includes sentiment score in priority ranking
- [x] **R07.5:** Dashboard shows news sentiment indicator (bullish/neutral/bearish) per candidate

**Data model:** Headlines go to `watchlist_news_sentiment` (one row per headline, not aggregated JSON). The parent `watchlist_enrichment` row holds fundamentals. TTL: prune headlines older than 30 days via `DELETE FROM watchlist_news_sentiment WHERE published_date < date('now', '-30 days')`. The parent row is retained; only children are pruned.

**Implementation note:** Yahoo Finance blocks automated access (consent wall). Google News RSS (`news.google.com/rss/search?q=TICKER+stock`) provides 30+ headlines per ticker with title, publication date, source, and description — parsed with regex, no XML dependency needed. Rate limit: 1s delay between tickers. Headlines pruned after 30 days.

---

## How to Verify

| Requirement | Verification |
|-------------|-------------|
| R01.1 | `trading screen create` inserts a row; `trading screen list` shows it |
| R02.1–2 | `trading screen enrich --ticker AAPL` populates enrichment table |
| R02.4 | `trading screen enrich --ticker AAPL` triggers `defuddle` fetch; response includes `analyst_name`, `rating`, `price_target` fields |
| R02.5 | Second `trading screen enrich --ticker AAPL` within TTL returns cached data (no `defuddle` call); after TTL expires, triggers fresh fetch |
| R03.1–3 | `trading screen run` outputs matched candidates with match reasons |
| R04.1 | Output table matches format spec in R04.1 |
| R04.2 | Dashboard loads curated watchlist tab with screening results |
| R05.1–2 | `just screen-weekly` runs without error |
| R06.1–3 | `--geopolitical` flag filters candidates correctly |
| R07.1–5 | `trading screen enrich --sentiment --ticker AAPL` populates news + sentiment |
| R07.4–5 | Screening includes sentiment; dashboard shows indicator |

**End-to-end test:**
```bash
# Add a candidate
trading watchlist add AAPL --thesis "Strong cash flow, AI tailwinds"

# Enrich with fundamental data
trading screen enrich --ticker AAPL

# Fetch news sentiment
trading screen enrich --sentiment --ticker AAPL

# Run screening
trading screen run

# Expected: AAPL appears if it meets defined criteria
# Expected: priority score displayed
# Expected: sentiment indicator shows bullish/neutral/bearish
```

---

## Dependencies

- `src/server/lib/schema.sql` — add `screening_rules`, `watchlist_enrichment`, `watchlist_news_sentiment` tables
- `src/server/lib/prospects-data.ts` — extend for enrichment data access
- `src/server/lib/alerts-engine.ts` — pattern reference for condition matching
- `scripts/get_price.ts` — existing Yahoo Finance price fetch, can extend for fundamentals
- `defuddle` (web_fetch) — built-in web fetching for news and analyst data (see pi docs)
- `src/lib/ig-client.ts` — alternative data source for instrument metadata
- `src/server/lib/db.ts` — `DatabaseFactory` for all database access
- `src/cli/commands/` — new `screen.ts` command alongside existing `watchlist.ts`, `alerts-*.ts`
- `hledger.just` — cron scheduling pattern reference

---

## Exit Criteria

- Screening rules can be created, listed, and deleted via CLI
- Enrichment pipeline fetches fundamental data for any watchlist candidate
- News sentiment stores one row per headline with FK to enrichment
- Screening engine evaluates rules and produces a prioritised list
- Dashboard shows curated watchlist with screening results and sentiment indicator
- Weekly cadence is configurable and runnable via `just`
- Existing watchlist and alerts systems continue to work unchanged

---

## Not in Scope

- Real-time price streaming (existing daily OHLCV is sufficient)
- Machine learning model for candidate scoring (rule-based only)
- Web scraping of analyst research (manual input of conviction lists)
- Paid external APIs (Yahoo Finance, IG, defuddle are free/public only; paid data feeds not in scope)
- Allowed external sources: Yahoo Finance, IG, public web via defuddle
- Live account execution based on screening results (human approval required)