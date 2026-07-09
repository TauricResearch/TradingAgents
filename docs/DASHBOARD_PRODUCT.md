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

## Final Production Validation Report (2026-07-08, v2)

**Feature completeness vs spec** — shipped across v1+v2: 5 modules +
settings + print-report; SSE push with heartbeats + Binance WS +
polling fallback; Lightweight Charts with candles/Heikin-Ashi/OHLC
bars/line/area, indicator overlays and oscillator panes from the
deterministic engine, volume pane, recommendation price lines, trade
markers, full-screen, synchronized compare charts (separate scales),
client-side market replay with REPLAY badge and tick isolation;
watchlists (persisted CRUD); journal filters + Sharpe/Sortino/max-DD +
drawdown pane; saved views; alert mute rules (hide, never delete);
cross-asset correlation matrix (server-side Pearson on daily log
returns, gaps disclosed); command palette + vim chords; personalizable
layouts with presets; notification center; CSV/print-PDF exports; PWA;
Storybook; dark/light themes.

**Test evidence**
- Python: 1008 tests + 69 subtests green (includes ~80 dashboard-backend
  tests: auth matrix, SSE thread-safety + replay dedupe, TTL/
  single-flight, prefs atomicity under concurrent writers, correlation
  symmetry/disclosure, exports, SPA fallback).
- Frontend: tsc strict + eslint clean; 19 vitest unit tests (formatters,
  Heikin-Ashi, drawdown, staleness, calibration bucketing, zod contract
  fixtures); 29 Playwright e2e green (desktop + Pixel-5 projects,
  serial — shared prefs store; temp data dir so tests never touch
  operator state).

**Lighthouse** (built SPA on the seeded demo server, lighthouse@12)
- Desktop preset: **Performance 96 · Accessibility 100 · Best Practices
  100**; FCP 1.0s, LCP 1.2s, TTI 1.2s, TBT 0ms — meets every spec
  target.
- Mobile (simulated slow-4G/4× CPU): Accessibility 100, Best Practices
  100, Performance 65 (FCP 5.1s under throttle). Honest note: this is a
  desktop-first terminal; PWA repeat visits are precached (near-instant
  shell). Mobile-perf fast-follow: further route-level splitting of the
  166 KB gz initial bundle.
- A11y fixes landed from the audit: fg-subtle contrast raised to AA on
  both themes, inline links underlined (not color-only), ladder table
  given screen-reader headers.

**Bundle**: initial JS 166.6 KB gz (CI budget 200 KB); charts (58 KB)
and grid (29 KB) split per route; fonts self-hosted.

**Live drills (in-browser)**: token gate; LIVE↔STALE↔recovery via SSE
heartbeat events; halt-banner drill (kill-switch stub → full-width
banner + red badge → recovery); real gold candles via yfinance; honest
503 + degraded panels with Binance egress blocked; replay isolation;
theme toggle; layout edit; service-worker update-on-prompt.

**v3 delta (chart drawing tools)**: trend/hray/fib drawing with
persistence and erase/clear; 9 new unit tests (fib geometry, hit
testing, store caps) and 2 new e2e specs (draw→persist→erase,
fib + Esc cancel) — 1010 python / 28 vitest / 31 Playwright all green.
Found and fixed in the process: LWC's double-click window silently
swallowing rapid placement clicks; an invalid OANDA token bricking gold
charts instead of falling back to yfinance (now probe-gated at registry
build); e2e now hermetic from operator env (token cleared, temp data
dir).

**v4 quality review (full route × theme × viewport audit)**: 32-shot
screenshot matrix + interaction drills + copy/number audits. Findings
fixed: PWA update prompt had no UI (users stranded on stale bundles —
UpdateToast added via useRegisterSW); chart series/indicator/volume
colors were hardcoded dark-theme hexes and did not re-resolve on theme
flip (now derived from tokens, theme in rebuild deps); status strip
consumed 4 wrapped rows on mobile (now one safety-critical row: LIVE,
risk, degraded count — context badges md+); report page P&L/date
columns collided and the agent table rendered headerless-empty (fixed +
honest empty line); print CSS could clip (app shell scrolls <main>
internally — print now flows); position badge read like a price change
(now "pos XAUUSD +76.92"); layout presets were fake (operator/analyst/
risk were identical — now real per-preset widget sets with honest
descriptions); Home default grid had ~40% dead space in hero/snapshot
(heights fitted); decision-rail ladder wrapped awkwardly (compact
format); leaderboard header cramping; favicon added; copy normalized
("risk OK · $100,111", "session —"). Accepted as-is: LWC first
time-axis label clipping (library default), demo-price artifacts
(FakePipelineLLM levels vs real bars — absent with real runs).
Re-verified: 1010 py / 28 vitest / 31 e2e green, Lighthouse desktop
96/100/100 unchanged.

**Live-data test (v5, 2026-07-09)**: Delta Exchange (India) adapter
added — the operator's reachable venue (Binance geo-blocked). Panel
status on live data:

| Surface | Status |
|---|---|
| BTC-USD charts (1m–1w) | LIVE — Delta BTCUSD perp (62,892 at test) |
| XAUUSD charts (1m–1w) | LIVE — Delta PAXGUSD tokenized gold ≈ spot (4,098; first intraday gold) |
| Strip/ribbon ticks | LIVE — backend pollers → SSE, both symbols every 5s |
| Funding/OI/mark | LIVE — Delta (funding 0.01 %/8h, OI $51M) |
| Fear & Greed | LIVE — 22 (extreme fear) |
| DXY / US10Y / XAU-XAG corr | LIVE — yfinance daily (100.9 / 4.57% / 0.97) |
| Correlation matrix | LIVE — all 5 symbols, 24 shared days, BTC×gold 0.556 |
| Session | LIVE — london at test time |
| FRED macro/calendar | degraded (no key) — disclosed |
| Binance feeds | degraded (geo-block) — disclosed |

**The real decision** (`scripts/pro_live_terminal.py`, deepseek-chat,
one full pipeline run on today's GC=F tape): **REJECTED at the critic**
— macro_bear claimed the 10Y yield "has already risen from its lows"
while its cited evidence stated only the current level; the critic
vetoed the fabricated trend. All rails live: kill switch armed,
hash-chained audit written, run/status/tick events on SSE. A refused
trade on live data is the honesty architecture working.

Found by this test and fixed: yfinance now quotes ^TNX in percent
directly — the legacy /10 conversion under-reported US10Y 10× to the
macro agents (convention guard + regression test added).

**Known open items (honest)**
- OANDA_API_TOKEN not yet in .env — gold remains EOD until the operator
  adds it (adapter, poller, registry switch are wired and fake-tested).
- Local Docker Desktop corrupted by a disk-full incident (user purge
  pending); the image build is verified by CI's docker job instead.
- Binance REST/WS geo-blocked from the dev network — superseded: Delta
  Exchange now serves both symbols live on this network; Binance remains
  the probe-gated fallback for networks where it is reachable.
- Paid feeds (Coinglass/Glassnode/ETF flows) remain locked panels
  pending subscription sign-offs.
