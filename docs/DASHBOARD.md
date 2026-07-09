# TradingAgents Pro — Dashboard Design & Architecture

The premium terminal: a Vite + React + TypeScript SPA served by the same
FastAPI app on :8600, replacing the single-file legacy page (kept at
`/legacy` during transition). Design principle zero: **honesty is the
product** — rejections, degraded feeds, and small sample sizes render with
the same fidelity as wins. The dashboard never fakes liveness and never
computes a trading number (Constraint 2: all quantities come from the
deterministic pipeline; the UI formats them).

## Information architecture

| Route | Module | Answers |
|---|---|---|
| `/` | Home — the 5-second briefing | safe? AI stance? P&L? what changed? what's next? |
| `/trade/:symbol` | Trading Workspace — chart-first | market now, levels in context |
| `/decisions[/:runId]` | AI Decision Center | why this trade, how risky |
| `/portfolio` | Portfolio | performance, integrity |
| `/intel` | Market Intelligence | conditions, calendar, feed coverage |
| `/settings` | Settings | theme, presets, connections, kill-switch runbook |
| `/report` | Print-ready operations report (browser print = PDF export) |
| `/legacy` | The previous single-page dashboard |

Global chrome on every route (immovable by design): status strip
(connection LIVE/STALE/DISCONNECTED, regime, session, risk badge,
positions, degraded-feed count, prices, search/notifications/theme) and
the full-width TRADING HALTED banner. All state is URL-addressable.

## Design system

Tokens in `frontend/src/styles/globals.css` (Tailwind v4 `@theme`), dark
default with a GitHub-light equivalent theme (`[data-theme="light"]`,
WCAG AA contrast):

- Surfaces `#0d1117 / #161b22 / #1c2128`, borders `#21262d / #30363d`
- Semantics: bull `#3fb950`, bear `#f85149`, neutral `#d29922`, accent
  `#79c0ff` (+ muted variants)
- **Stale ≠ neutral**: staleness renders desaturated amber + dashed
  border so "old data" can never be confused with "neutral direction"
- Type: Inter Variable (UI) + JetBrains Mono (numerics, always
  `tabular-nums`); 4px spacing grid; radii 6/8/12
- Direction is always glyph + word + color via `<DirectionBadge>`
  (▲ bull / ▼ bear / – neutral) — A11Y-01 enforced by construction

Component inventory: shadcn-style vendored primitives
(`components/ui/`) + trading components (`DecisionCard`, `GateWaterfall`,
`DebateTimeline`, `ConsensusBar`, `CalibrationChart`, `AgentLeaderboard`,
`EvidencePanel`, `AlertFeedList`, `PriceChart`, `EquityCurve`,
`Sparkline`, `StatCard`, `EmptyState`, `Freshness`, `WidgetGrid`,
`CommandPalette`, `NotificationCenter`). Storybook
(`npm run storybook`, a11y addon, dark/light toolbar) documents them.

## State & live data

- **TanStack Query** per endpoint with zod validation at the boundary
  (`lib/api/types.ts` mirrors `service.py` — drift fails loudly).
- **SSE** `/api/stream` is the primary transport (run/alert/position/
  status/tick + 15s heartbeat events); while healthy, polling relaxes
  5s → 60s (`refetchInterval` is a function so mounted queries pick the
  change up). EventSource authenticates via the session cookie
  (`POST /api/session` exchanges `X-API-Key`; header auth still works).
- **Live prices**: vendor preference is probe-gated at startup — when
  Delta Exchange is reachable (the operator's venue; Binance is
  geo-blocked on their network), both BTC-USD (BTCUSD perp) and XAUUSD
  (XAUTUSD Tether Gold, ≈ spot with a small disclosed basis) serve
  live intraday candles and backend-polled ticks over SSE; otherwise
  browser→Binance WS for BTC and OANDA/yfinance for gold. The decision
  pipeline still computes on GC=F daily — the XAUT-vs-futures basis is
  a disclosed presentation difference, not hidden. Vendor unreachable ⇒
  honest degraded states, never blank panels.
- **Staleness**: any success bumps a global monotonic marker; >12s ⇒
  STALE, never-connected ⇒ DISCONNECTED (ports the legacy ALERT-01).

## On-demand pipeline runs & persistent history (v7)

- **Trigger**: `POST /api/pipeline/run` `{symbol, timeframe}` — symbol
  ∈ {XAUUSD, BTC-USD}, timeframe ∈ {1h, 4h, 1d}. Returns 202 and runs
  in a background thread through the SAME service as the hourly loop
  (full debate→critic→judge→gates→PM chain, paper execution, recorder,
  memory). 422 invalid choice, 409 while a run is in flight
  (single-flight by design), 503 in monitor mode (no service wired).
  UI: "Run" button on the Decisions run rail, palette action
  "Run pipeline…", and a "Run pipeline now" CTA on the empty state.
  The dialog states the honest cost (≈ $0.10–0.20/run in model calls).
- **Stage progress**: `record_run(on_node=...)` publishes SSE `stage`
  events per pipeline node; the frontend shows a live
  "running {symbol} · {stage}" chip until the terminal `run` event.
- **Snapshot routing**: gold 1d = the loop's canonical GC=F daily
  pipeline; gold 1h/4h = Delta XAUTUSD bars + gold macro feeds; BTC =
  Delta BTCUSD bars + FRED + on-chain (CoinMetrics/Fear&Greed) + Delta
  funding/OI. Per-asset `ProConfig` selects the matching agent roster.
- **Persistence**: `PipelineRecorder(store_dir=data/runs)` writes each
  completed run as one JSON file (atomic tmp+fsync+rename; contracts
  round-trip via `model_dump`/`model_validate`) and reloads them on
  boot — run history survives container restarts. Corrupt files are
  skipped with a warning; files beyond `max_runs` are pruned oldest
  first. Run rail rows carry a timeframe badge from the stored bars.

## Charts

TradingView **Lightweight Charts** (Apache-2.0): candles, Heikin-Ashi
(client-side redraw of the same bars — presentation, not information),
line, area; recommendation levels as price lines (entry solid accent,
stop dashed bear, TPs dotted bull with close-fractions); journal trade
markers; live last-price via `series.update`. Timeframes come from
`/api/symbols` capability disclosure so a dead button never renders.
Indicator series come from `/api/bars/indicators` — computed by the same
deterministic engine the pipeline uses.

**Drawing tools (v3)**: trendlines, horizontal rays, and Fibonacci
retracements via a custom Lightweight Charts primitive
(`components/charts/drawings/`). Anchored in data space (time + price)
so they survive pan/zoom/timeframe; per-symbol persistence rides the
prefs pipeline (cross-device); toolbar is desktop-only (honest: touch
drawing is out of scope). Implementation note: LWC suppresses the
second click of a <500ms pair as double-click detection — placement
subscribes both `subscribeClick` and `subscribeDblClick` with a
same-tap dedupe, and the placement preview updates the primitive
imperatively (never through React state).

**Descoped honestly** (need the licensed TradingView library): volume
profile, Renko, freeform drawing beyond trend/ray/fib. No fake
market-depth ladder (only an imbalance scalar exists). No manual order
ticket (the loop is autonomous; operator controls are pause/kill).

## Personalization

`react-grid-layout` per module behind an explicit Edit mode; presets
Operator/Analyst/Risk; hidden-widget restore; localStorage for instant
boot, debounced mirror to `PUT /api/prefs`. Safety chrome and freshness
dots are excluded from customization. Mobile (<768px) renders a fixed
priority stack with bottom-tab navigation.

## Keyboard & command palette

`⌘K` palette (navigate / trade context / actions / run search) and vim
chords (`g h|t|d|p|i|s`, `x` symbol toggle, `1–7` timeframes, `⇧D`
theme, `?` cheatsheet) share one registry. **The kill switch has no
shortcut and no dashboard button**: Settings shows the operator runbook
command behind a typed HALT confirmation — the dashboard is read-only
over execution by design.

## PWA & performance

- vite-plugin-pwa, `registerType: "prompt"` (a trading UI is never
  silently swapped); precache = shell only; **`/api/**` NetworkOnly**
  (cached kill-switch state would be a safety bug) except historical
  bars (NetworkFirst, 5 min). No query cache persists to IndexedDB.
- Route-level code splitting; charts/grid in separate chunks; initial
  JS ≈ 166 KB gzip (CI budget 200 KB); fonts self-hosted.

## Empty/degraded/error states

Every widget renders one of: skeleton (max ~5s) → data / empty (honest
copy, timestamps) / degraded (stale styling + disclosure) / error
(per-widget `ErrorBoundary`; one broken panel never blanks the
terminal) / **locked** (unsubscribed paid feeds — Coinglass liquidations,
Glassnode whale flows, ETF flows, gold microstructure — shown with
provider names in Intel's feed-coverage panel; a trust signal, not a
bug).

## Testing

- Vitest: formatters, Heikin-Ashi math, staleness thresholds,
  calibration bucketing, zod contract fixtures.
- Playwright (`frontend/e2e/`, desktop + iPhone projects) against the
  seeded demo server with auth on: token gate, 5-second-test assertions,
  decision center, run pinning, chart canvas, CSV download, palette,
  chords, feed coverage, SSE reachability.
- Python: 56 backend tests cover every new endpoint offline (fakes).

## Dev workflow

```bash
# terminal 1: backend with seeded state
python scripts/pro_dashboard_demo.py 8600
# terminal 2: hot-reloading frontend (proxies /api to :8600)
cd frontend && npm run dev
# production build (lands in tradingagents/pro/dashboard/static/)
npm run build
```

`PRO_DASHBOARD_DEV=1` enables CORS for the Vite origin if you bypass the
proxy. The FastAPI app serves the built SPA when present and falls back
to the legacy template when not (dev checkouts without node keep
working).
