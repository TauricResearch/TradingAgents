# TradingAgents Pro — Roadmap to 10/10

Companion to [PRO_TRADER_REVIEW.md](PRO_TRADER_REVIEW.md) (16 Jul 2026, verdict 🟡). This plan converts every scoring gap into concrete workstreams with file-level pointers, acceptance criteria, and sequencing.

**The honest premise up front:** three of the ten scores cannot be *shipped* to 10 — they must be *accrued*. Decision Support, Portfolio Management, and Value for Money are gated on a live track record that only calendar time produces. The plan therefore splits into (A) defects fixable this week, (B) features buildable this quarter, and (C) evidence that accrues on a schedule we can start **today** — and the single most important action in this document is starting the accrual clock now (see Workstream T).

**Scoreboard target:**

| Category | Now | After P0–P1 | After P2–P4 | Gate to 10 |
|---|---|---|---|---|
| Trading Experience | 6 | 7.5 | 9 | 10 needs symbol breadth + my-own-trades |
| Decision Support | 7.5 | 8.5 | 9.5 | 10 needs calibrated P(win)/EV (n≥100) |
| Charting | 4 | 6 | 9–10 | position tool, profile, multi-chart, depth |
| Market Intelligence | 4 | 6.5 | 9–10 | real calendar + news + derivatives depth |
| AI Explainability | 9 | 9.5 | 10 | interrogation (AI chat over evidence) |
| Risk Management | 6.5 | 8.5 | 10 | coherent stops + standing limits board |
| Portfolio Management | 3 | 5 | 9–10 | backtest UI + live record accrual |
| Speed & Workflow | 7 | 8.5 | 10 | alerts that fire + zero dead-ends |
| Premium Feel | 7 | 9 | 10 | polish sweep + state consistency |
| Value for Money | 4 | 6 | 9–10 | follows the track record, not features |

---

## Phase 0 — Trust-wound triage (days, not weeks)

Cheap fixes that each repair a named trust failure from the review. Ship as one polish release.

**0.1 Stop/invalidation coherence (the #1 finding).**
The ticket's stop is `entry ± 2×ATR` template math while the reflection names a concrete invalidation level; the stop must be derived from the invalidation, not parallel to it.
- Where: the PM/risk sizing node in [nodes.py](tradingagents/pro/pipeline/nodes.py) produces levels; `ReflectionNote.invalidation` ([schemas.py](tradingagents/pro/pipeline/schemas.py)) is free text merged into the ticket view.
- Change: (a) make `ReflectionNote` carry a **structured** `invalidation_price: float | None` alongside the prose; (b) in the sizing node, set `stop_loss = invalidation_price ± buffer(0.25×ATR)` when present, and recompute `position_size` from the risk budget so risk-per-trade stays constant as the stop tightens; (c) add a validator in [recommendation.py](tradingagents/contracts/recommendation.py) that **rejects** any recommendation whose stop is beyond its stated invalidation by more than the buffer — same fail-closed pattern already used for `risk_reward`.
- Done when: no ticket can exist whose thesis dies before its stop; tests cover BUY/SELL mirror cases.

**0.2 One volatility opinion.** Status strip and decision card must read the same regime source (`/api/regime` is already deterministic). Kill whichever secondary computation feeds `StatusStrip.tsx` ([frontend/src/app/StatusStrip.tsx](frontend/src/app/StatusStrip.tsx)); if strip and card legitimately measure different horizons, label them ("1h regime" vs "session vol").

**0.3 Rendering/formatting sweep.**
- Render markdown (or strip `**`) in invalidation/rationale text — flagship card, decision page, alerts.
- Human numbers: funding `8.57e-5` → "0.0086% / 8h (7.8% ann.)"; OI with units; consistent thousands separators. One `formatMetric()` in the frontend, driven by a per-metric format hint in the `/api/intel` payload.
- Label the vote glyphs: `▲12 buy · –7 hold · ▼30 sell` (tooltip at minimum).
- Never leak raw exception strings to the UI: feed errors map to "coinmetrics: forbidden (subscription?)" with the raw detail behind a disclosure. Where: feed degradation strings originate in [builder.py](tradingagents/pro/ingestion/builder.py) `missing_feeds` and flow to `/api/intel`.

**0.4 State that doesn't flicker.** "LIVE · $99,913" vs "monitor only" across page loads is Cloud Run scale-out serving instances without the paper service attached ([main.py](tradingagents/pro/main.py) builds service state per-process).
- Immediate: `--min-instances=1 --max-instances=1` for the stateful service in [deploy_cloud_run.sh](scripts/deploy_cloud_run.sh) (the paper loop is a singleton anyway; two instances would double-trade).
- Durable: move run history/positions/metrics behind a shared store (Firestore fits the existing Firebase stack) so any instance renders the same book; keep the loop leader-elected.
- Done when: 50 hard reloads never change the safety chrome.

**0.5 Progress counters agree.** One source of truth for run progress ("stage N/M"); the 3D board and verdict chip both subscribe to it via the existing SSE stream.

**0.6 Suppress statistics that aren't.** Leaderboard hit/gap and calibration points render only at n≥20 per agent/bucket; below that show "accruing (n=1)" — the honesty pattern the product already uses elsewhere. Same for the 12%-similar analog: threshold analogs at similarity ≥0.5, dedupe the description/outcome text (the duplication bug is in how `HistoricalAnalog.outcome` embeds the full description — fix at write time in the memory layer, [memory.py](tradingagents/pro/memory/memory.py)).

**Exit criteria for P0:** frustrations #1–#5, #7, #9–#12, #16 from the review are unreproducible. Premium Feel 7→9, Risk 6.5→8.

---## Phase 1 — Event risk & the information loop (2–4 weeks)

The FOMC-day-short-with-zero-FOMC-mentions failure, end to end.

**1.1 A real economic calendar.** FRED release dates ([fred_macro.py](tradingagents/pro/ingestion/fred_macro.py)) fundamentally lack times and consensus — swap the *calendar* source (keep FRED for series data): econdb / Trading Economics / FMP calendar API (licensing pass needed; ForexFactory scraping is fragile+ToS-risky). New `ingestion/econ_calendar.py` feed producing `{event, ts_utc, importance, consensus, previous, actual}`; dedupe recurring entries (the 7×FOMC bug). Surface: countdown chip on Home and on the Trade page event strip ("FOMC in 3h 12m"), consensus/prior/actual columns on Intel.

**1.2 The pipeline must *read* the calendar.** New pre-entry **event gate** in [graph.py](tradingagents/pro/pipeline/graph.py) beside the risk gate: within X hours of a high-importance event for the traded asset (FOMC/CPI/NFP for gold), the gate either (a) blocks NEW entries (default), or (b) requires the debate to have explicitly addressed the event — enforceable the same way the critic already enforces unrebutted evidence. Config in `ProConfig` ([config.py](tradingagents/contracts/config.py)). Done when: a run started 2h before FOMC either declines to trade or its judge rationale names the event.

**1.3 News earns its lane.** [news.py](tradingagents/pro/ingestion/news.py) already ingests quarantined headlines; the news/sentiment team produced 0 evidence in the reviewed run. Fix the feed→agent wiring so headlines reach the team prompt with timestamps+sources; add a headline panel to Intel and the Trade page (source-attributed, click-through). Done when: NEWS_SENTIMENT evidence count > 0 on a normal day and headlines are visible in the UI.

**1.4 Notifications that fire.** The SSE stream already broadcasts run/alert events; the bell ([NotificationCenter](frontend/src/components)) just never receives them. Unify the Home alert feed and the bell (one event bus, two views); add browser push (service worker exists — the PWA precaches already) for: verdict change, run complete, gate rejection, price-alert hit, feed degradation, kill-switch/halt. Surface price-alert creation on the chart (right-click / button → `/api/price-alerts`, API already exists). Done when: a run completing while the tab is backgrounded produces an OS notification.

**1.5 "Since you left" tracks what matters:** verdict changes, new runs, position changes, limit proximity — not just "nothing changed."

**Exit criteria:** Market Intelligence 4→6.5, Speed/Workflow 7→8.5; the review's deal-breaker #2 is closed.

---

## Phase 2 — Charting to parity-where-it-counts (4–8 weeks)

Not chasing TradingView's 400 indicators — closing the gaps a professional actually hits daily. All in [PriceChart.tsx](frontend/src/components/charts/PriceChart.tsx) + [drawings/](frontend/src/components/charts/drawings/).

**2.1 Long/short position tool** (the #1 chart gap): drag entry→stop→target, live R:R + size readout wired to the same risk math as tickets; "adopt AI levels" one-click prefill. This doubles as the **what-if calculator** (review improvement #10).
**2.2 Drawing palette:** rectangles/zones, parallel channel, text notes; object list with per-drawing visibility/delete; drawings persist per symbol+timeframe (localStorage → prefs API).
**2.3 Pane resize handles** and per-pane height persistence.
**2.4 Volume profile** (fixed-range + session) computed server-side in [indicators.py](tradingagents/pro/ingestion/indicators.py) — deterministic, same trust story ("LLMs never calculate financial quantities").
**2.5 Indicator depth, curated:** Ichimoku, Stochastic, OBV, anchored VWAP, pivots, Supertrend — ~15 total, each period-editable. Depth beyond that comes from **2.7**.
**2.6 Multi-chart layouts:** 2×1 and 2×2 grids (symbol × timeframe), crosshair-synced — `ChartSync.tsx` already syncs compare mode; generalize it.
**2.7 (Stretch) user indicator plugins:** sandboxed JS/expression DSL evaluated client-side, clearly labeled "your code, not platform math."

**Exit criteria:** Charting 4→8 (10 needs 2.6+2.7 plus alerts-from-chart from 1.4). A trader can plan, mark up, and measure their own variant of the AI's trade without leaving the page.

---

## Phase 3 — Risk visible, not just enforced (2–3 weeks)

The rails exist ([safety.py](tradingagents/pro/execution/safety.py), [config.py](tradingagents/contracts/config.py) RiskLimits/LiveRiskLimits); the trader can't *see* them.

**3.1 Standing risk board** (new Home/Portfolio widget + `/api/risk` endpoint): daily loss vs `max_daily_loss_pct`, drawdown vs HWM vs `max_drawdown_pct`, open risk (Σ distance-to-stop × size), margin/leverage usage, circuit-breaker counter ("2 of 3 consecutive losses"), orders/hour vs cap — each as "used / limit / distance," green-amber-red.
**3.2 Correlation-netted exposure:** the 30-day matrix already computed server-side (`/api/intel/correlations`) — apply it to open positions: "gold + BTC long = 1.73 effective positions (ρ 0.73)."
**3.3 Volatility-aware sizing:** size from risk budget ÷ stop distance (falls out of 0.1) with regime-scaled risk budget; show the formula on the ticket.
**3.4 Per-position live telemetry:** current R multiple, distance-to-stop in ATRs, time-in-trade, "invalidation proximity" warning (uses 0.1's structured level).
**3.5 Kill-switch/flatten drill documentation** in Settings: keep the operator-side philosophy, add a "test the dead-man switch" runbook and last-heartbeat display (deadman state already exists in [deadman.py](tradingagents/pro/deadman.py)).

**Exit criteria:** Risk Management 8→10. The reviewer's question "would it protect my capital?" becomes answerable from one screen.

---

## Phase 4 — The proof engine: backtest UI + track record (3–5 weeks build + calendar time)

**4.1 Backtest in the product, not a CLI.** The engine exists ([backtest/](tradingagents/pro/backtest/) — BacktestEngine, walk-forward, Monte Carlo, LLM cache; [pro_real_replay.py](scripts/pro_real_replay.py) drives it). Build: a Backtest tab — pick symbol/period/config → job runs server-side (billing-guarded, cost estimate up front like the run dialog) → equity curve, walk-forward windows, Monte Carlo cone, trade list with per-trade reasoning links (the recorder already stores runs). Empty panel never again tells the user to run a Python script.
**4.2 Track-record page** (public, tamper-evident): every closed paper/live trade with entry/exit/R, cumulative curve, calibration chart front and center, hash-chain verification link (the audit log in [arming.py](tradingagents/pro/arming.py) already chains; expose a verifier). Marketing page = this page. Nothing sells a subscription except this.
**4.3 P(win)/EV on tickets — gated:** once calibration buckets hit n≥30, display `P(win)` from the realized bucket hit-rate and `EV = P·reward − (1−P)·risk` in R units. Until then the ticket keeps showing only the derived breakeven rate (already honest). Schema: add optional fields to [recommendation.py](tradingagents/contracts/recommendation.py); UI renders only when non-null.
**4.4 Analog quality:** similarity threshold ≥0.5, dedup fix (P0.6), and aggregate stats — "7 similar setups: 4W/3L, avg +0.8R" — instead of one prose blob.

**Exit criteria:** Portfolio Management 3→7 on build; →9–10 as the record accrues (see T).

---

## Phase 5 — Breadth & the analyst you can question (6–10 weeks)

**5.1 Symbol universe:** FX majors (EURUSD, USDJPY, GBPUSD), silver, oil, SPX/NDX proxies — the ingestion architecture already routes per-asset feed stacks ([builder.py](tradingagents/pro/ingestion/builder.py)); each new symbol needs a feed stack + agent-roster review + eval-set extension in [evals/golden.py](tradingagents/pro/evals/golden.py). 10+ symbols changes the product class and unblocks:
**5.2 Scanner:** "run the cheap deterministic layer (regime + indicators + quant agents, no LLM debate) across the universe every N minutes; rank by setup quality; full debate on demand." This is the natural scanner design for this architecture — the deterministic evidence layer is already separable.
**5.3 Watchlists that matter** (arbitrary served symbols, per-view), portfolio heatmap once >2 assets.
**5.4 My-own paper order ticket:** place manual paper trades through the same [ExecutionRouter](tradingagents/pro/execution) with the same gates; journal grades "you vs the AI" on shared setups. Read-only-over-*live* stays; paper is where traders build trust by competing with the machine.
**5.5 AI chat over the evidence record:** conversational endpoint scoped to a run's evidence + debate + market snapshot ("what breaks this trade if DXY reclaims 101?"), answers must cite evidence ids — same provenance discipline as the pipeline. Takes Explainability 9→10.
**5.6 Derivatives depth:** license one of the feeds the Intel page already lists as NOT SUBSCRIBED (Coinglass liquidations first — highest signal per dollar for BTC), plus funding across venues; GVZ term structure for gold.

**Exit criteria:** Trading Experience →9–10, Market Intelligence →9, Explainability →10.

---

## Workstream T — the accrual clock (start today, runs in parallel with everything)

The only path to 10/10 on Decision Support, Portfolio, and Value. Nothing above substitutes for it.

- **T.1 Run the paper loop continuously** on an always-on host (the code already warns against laptop hosts). Both symbols, hourly cadence. At a realistic 1–3 traded decisions/day/symbol (most verdicts HOLD or get gated), **n=100 closed trades ≈ 6–10 weeks**. Every week of delay moves the 10/10 date a week.
- **T.2 Freeze the eval-gated config** during accrual (evals harness already exists in [evals/](tradingagents/pro/evals/)) — a track record built on a shifting config proves nothing; version the record per config hash (the audit chain supports this).
- **T.3 Weekly honesty report:** automated post of calibration curve + per-agent hit rates as n grows (the Report page already computes these; schedule it).
- **T.4 Definition of "proven":** n≥100 closed trades, calibration buckets within ±10pts of diagonal at n≥30/bucket, profit factor >1 net of realistic costs on the walk-forward. Publish the definition *before* the results — that's the honesty brand.

---

## Sequencing & effort (1–2 engineers)

| Phase | Duration | Depends on | Score impact |
|---|---|---|---|
| P0 triage | 1–2 wk | — | Premium 9, Risk 8, trust wounds closed |
| T accrual | starts day 1, 8–12 wk elapsed | config freeze | gates all 10s |
| P1 events/news/alerts | 2–4 wk | — | Intel 6.5, Workflow 8.5 |
| P2 charting | 4–8 wk | — | Charting 8 |
| P3 risk board | 2–3 wk | P0.1 | Risk 10 |
| P4 proof engine | 3–5 wk | T underway | Portfolio 7→9 |
| P5 breadth/chat | 6–10 wk | P1, P4 | Experience 9–10, Explainability 10 |

Critical path to "🟢 Excellent — I would happily pay": **P0 + P1 + T through week 8**. Critical path to "⭐ World-Class": everything above plus a published, verified record — realistically **two quarters**.

## Regression gate

Re-run the professional-trader review (same rubric, same persona, live deployment) at the end of each phase; a phase isn't done while any of its named review findings still reproduces. Wire the cheap ones into CI/e2e where possible (markdown artifacts, sci-notation, calendar dedup, stop-vs-invalidation validator are all unit-testable).
