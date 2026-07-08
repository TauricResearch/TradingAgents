# TradingAgents Pro — Dashboard Product Assessment

## UX improvements over the legacy single page

1. Single page → 6 routed modules; every run/trade/symbol/report has a URL.
2. Decision card → full Decision Center: gate waterfall with actual
   rejection reasons, team-laned debate timeline, confidence-weighted
   consensus bar with judge-override callout, evidence provenance
   popovers (DataRef name + raw value), persistent counterargument
   display, invalidation banner, quarantined-injection security badges.
3. Rejections promoted to first-class verdicts ("a refused trade is a
   decision too").
4. Hit-rate table → calibration reliability diagram (bubble size = n,
   hollow under n=10) + leaderboard with the calibration-gap honesty
   column.
5. One staleness pill → global LIVE/STALE/DISCONNECTED + per-widget
   freshness dots + a four-state (empty/degraded/error/locked) system.
6. 5s full-page polling → SSE push with heartbeats; polling relaxes to
   60s as a safety net; BTC ticks stream browser→Binance directly.
7. Static SVG equity → interactive Lightweight-Charts price/equity with
   levels, markers, Heikin-Ashi, Monte Carlo band.
8. New: command palette, vim chords, notification center with read
   state, watchlist-ready prefs store, drag/resize/save layouts with
   presets, CSV + print-PDF exports, PWA install, dark/light themes,
   mobile bottom-tab layout, "Since you left" diff panel.

## Premium feature matrix (if productized)

| Capability | Free | Pro (~$49/mo) | Desk (~$199/mo) |
|---|---|---|---|
| Decisions | 24h-delayed, latest only | Real-time + full history | + webhook/API push |
| Debate transcripts | Judge summary | Full 59-agent debate + provenance | + raw evidence export |
| Calibration | System-level | Per-team/per-agent | Custom cohorts |
| Charts | EOD | Intraday + levels + markers | Multi-seat sync |
| Alerts | Daily digest | Real-time PWA push | + Telegram/webhook |
| Exports | — | CSV/PDF | REST API + audit verification |
| Layouts | Presets | Full personalization | Shared team layouts |

Comparables: TradingView $14.95–59.95/mo, Coinglass ~$29–69/mo,
Glassnode $29–799/mo. Positioning: a *reasoning terminal*, not a
charting terminal — the calibration chart and explainable rejections
are the moat; charting is table stakes.

## Monetization readiness — honest blocker list

1. **Auth is a single static token.** Multi-tenant requires real
   identity (OIDC), per-user sessions, key management. Hard blocker.
2. No storage tenancy: runs/trades/memory are single-namespace.
3. Kill switch/loop control are global — needs per-tenant RBAC.
4. Billing (Stripe), plan gating, rate limiting, SLOs, status page.
5. Legal: not-investment-advice disclosures (present on the report
   footer; needed on every decision surface), jurisdiction gating, ToS.
6. Vendor licensing review before redistributing Binance/FRED/
   CoinMetrics-derived data to paying users.

Recommendation: sell nothing until the calibration chart has ≥3 months
of real outcomes — the product's pitch is its honesty metric, and the
honest metric needs data.

## Roadmap after this release

- OANDA gold intraday in production (token provisioned) → both symbols
  live at launch quality.
- Licensed TradingView Charting Library evaluation (drawing tools,
  replay) once the free tier proves demand.
- Paid feed integrations behind the existing locked-panel pattern:
  Coinglass liquidations, Glassnode whale flows, ETF flows.
- Watchlist UI over the existing watchlists API; alert rules
  (mute/threshold) over the notification store.
- Multi-tenant track per the blocker list above.

## Validation snapshot (2026-07-08)

- Python suite: 1000+ tests green including 60+ new dashboard-backend
  tests (auth matrix, SSE thread-safety, TTL/single-flight, prefs
  atomicity, exports, SPA fallback).
- Frontend: tsc strict clean, eslint clean, 16 vitest unit tests,
  Playwright E2E suite (desktop + mobile projects) against the seeded
  demo server with auth enabled.
- Live drills verified in-browser: token gate, LIVE↔STALE↔recovery via
  SSE heartbeats, real gold candles via yfinance, honest 503 +
  degraded states when Binance egress is blocked, halt banner, run
  pinning, layout edit mode, service-worker update-on-prompt.
- Initial bundle ≈166 KB gzip (budget 200 KB in CI); charts and grid
  lazy-loaded per route.
