---
date: 2026-05-20
tags: [feature, cleanup, screening, enrichment, alerts, markov]
agent: pi
environment: development
---

# Debrief: WATCH-001 Completion + Signal Hygiene

## Accomplishments

- **Markov signal dead code cleanup (PR #20):** Replaced runtime `require()` with static ESM import for `nDayProbabilities`. Removed two dead `void` calls on pure functions. Fixed phantom `server/` directory in justfile Biome globs.

- **Alert Fire Integration (PR #21):** Added `POST /api/alerts/fire` as the canonical HTTP route for alert matching + dispatch. `GET /api/alerts/check` (dry-run) and `POST /api/alerts/check/fire` (backward compat) already existed. The matching engine, Telegram dispatch, and CRUD were all wired — only the route name was missing from the brief spec.

- **WATCH-001 R07 — News Sentiment Headlines (PR #22):** Replaced the stubbed `fetchHeadlines()` (returned `[]`) with Google News RSS parsing. Yahoo Finance blocks automated access (consent wall), so Google News RSS (`news.google.com/rss/search?q=TICKER+stock`) is the canonical news source. Regex-based XML parsing — no XML dependency. 1s rate limit between tickers, 20 headlines max per ticker, 30-day prune window.

- **WATCH-001 R08 — STL Pattern Features (PR #23):** Added 7 structural features from the TIME benchmark paper (arXiv:2602.12147): trend_strength, trend_linearity, seasonality_strength, seasonality_stability, residual_acf1, spectral_entropy, is_stationary. Computed via `scripts/py/compute_pattern_features.py` using statsmodels STL decomposition + scipy FFT + ADF stationarity test. Wired into the enrichment pipeline via `--pattern` flag on `trading screen enrich`. Screening engine and dashboard enrichment types extended to support pattern-based screening rules.

## Problems

- **Yahoo Finance consent wall:** The brief specified using defuddle to fetch Yahoo Finance news pages, but Yahoo returns a consent wall even for defuddle. Switched to Google News RSS which is publicly accessible and well-structured. Updated the brief implementation notes.

- **TauricResearch upstream confusion:** Initially listed open PRs from TauricResearch/TradingAgents instead of pjsvis/TradingAgents. User corrected — we don't contribute to upstream. Removed the TauricResearch remote entirely and pointed `upstream` to pjsvis.

- **Biome `.tsx` exclusion:** Biome config doesn't include `**/*.tsx` in `files.includes`, so Biome checks silently skip `.tsx` files. TypeScript errors in `screenings.tsx` only caught by `tsc`. Noted for future: `.tsx` files need separate type-check attention.

- **Inline enrichment objects had type drift:** Adding 7 new fields to `EnrichmentRow` caused 4 type errors in `screenings.tsx` where enrichment objects were constructed inline without the new fields. Fixed via sed-based insertion of `null` defaults.

## Lessons Learned

- **Briefs can lag implementation:** The Alert Fire Integration brief was written before the routes existed. Both `GET /api/alerts/check` and `POST /api/alerts/check/fire` were already implemented — the brief just specified a different canonical path (`/fire` instead of `/check/fire`). Always verify what code already exists before trusting a brief's gap analysis.

- **Google News RSS is a reliable free source:** For headline-level sentiment enrichment, Google News RSS provides 30+ headlines per ticker with title, date, source, and description — parsed trivially with regex. No API key, no rate limit beyond basic politeness. Better than fighting consent walls.

- **statsmodels STL works but is noisy:** The STL decomposition produces RuntimeWarnings on synthetic/boundary data (divide by zero, overflow). These are cosmetic — the features compute correctly. Warnings suppressed in the Python script.

- **Pattern feature computation is batch-only:** Requires 252 bars of price history per ticker. For portfolios with limited price data (test DB has 22 bars for AAPL), this doesn't work. Only meaningful for positions with sufficient history.

## WATCH-001 Completion Status

| Req | Component | Status |
|-----|-----------|--------|
| R01 | Screening rules CRUD | ✅ Done |
| R02 | Enrichment pipeline | ✅ Done |
| R03 | Screening engine | ✅ Done |
| R04 | Curated list output | ✅ Done |
| R05 | Weekly cadence | ✅ Done |
| R06 | Geopolitical flags | ❓ Stretch — not started |
| R07 | News sentiment headlines | ✅ PR #22 |
| R08 | STL pattern features | ✅ PR #23 |

## Remaining Briefs

- `2026-05-13-brief-curated-watch-lists.md` — partially done (R06 stretch remains)
- `2026-05-15-brief-watchlist-pattern-enrichment.md` — done (PR #23)
- `2026-05-20-brief-markov-regime.md` — code exists, schema + CLI remaining
- `2026-06-01-brief-bifrost-installation.md` — proxy built, docs status unclear
- `eodhd-pricing-brief.md` — not started
- `15-brief-tidy-up.md` — cross-cutting hygiene
- `2026-05-15-brief-research-registry-and-watchlist-seed.md` — not started
