# TradingAgents Pro — Road to 90+/100

Companion to the review series ([V1](PRO_TRADER_REVIEW.md) 58 → [V2](PRO_TRADER_REVIEW_V2.md) 68 → [V3](PRO_TRADER_REVIEW_V3.md) 74; the parallel [score-sprint scorecard](TRADER_REVIEW.md) reached 83). This plan pushes the shippable categories to their honest ceilings and names what only time or money can buy.

## The arithmetic (baseline = most recent scorecard, 83/100)

| Category | Now | Target | Lever (this plan) | Ceiling note |
|---|---|---|---|---|
| Charting | 6 | **9** | Ichimoku cloud, chart-native price alerts, evidence-chip → chart pins, anchored-VWAP-from-click | order flow / DOM / footprint need L2 data we don't buy → hard cap below 10 |
| Trading Experience | 8 | **9** | personal paper order ticket ("you vs the AI"), symbol quick-switch | — |
| AI Explainability | 9 | **10** | AI chat over the evidence record (cited answers only) | — |
| Premium Feel | 8 | **9** | polish sweep: loading skeletons, empty-state copy, motion consistency | subjective; needs a live visual pass |
| Portfolio Management | 8 | **9** | public track-record page surfacing the retro-graded record + calibration curve | real closed-trade n is time-gated → true 10 needs the accrual clock |
| Market Intelligence | 9 | **9.5** | calendar consensus/previous/actual (free source) | liquidations/ETF/whale feeds need paid vendors |
| Value for Money | 8 | **9** | rides the above; more capability at the same price | ceiling tracks the track record |
| Risk Management | 9 | **9.5** | standing risk board polish + correlation-netted exposure surfaced | — |
| Decision Support | 9 | **9.5** | horizon/EV surfaced on the ticket UI (data already exists) | — |
| Speed & Workflow | 9 | **9** | hold — already strong | — |

**Target sum: ~92/100.** Two categories (Charting, Portfolio) carry honest sub-10 ceilings; the plan clears 90 without needing them at 10.

## Batches (deploy after each)

### Batch A — Charting to 9 + Explainability to 10 (biggest single lever)
1. **AI chat over the evidence record** — `POST /api/runs/{id}/ask`: a scoped conversational endpoint answering only from that run's evidence/debate/snapshot, every claim citing an `agent_id`; refuses to answer beyond the record. Panel on the Decisions page. (Explainability 9→10; the reviews' repeated "no way to interrogate the reasoning".)
2. **Chart-native price alerts** — click a price on the chart → create alert (reuses the existing price-alert engine + API); the repeatedly-named "chart-native alert gesture".
3. **Ichimoku cloud** — the P2.5 deferral: implement the 26-bar forward shift in the indicator series pipeline so the cloud projects honestly.

### Batch B — Trading Experience to 9 + Portfolio to 9
4. **Personal paper order ticket** — place your own paper trade through the same `ExecutionRouter`/gates; the journal grades you vs the AI on shared setups. (Every round asked for this.)
5. **Public track-record page** — a dedicated route surfacing the retro-graded decision history + the calibration curve + agent hit-rates, honestly labeled (retro vs live), the thing that converts "trust the process" into "here's the record".

### Batch C — Market Intel + Decision + Premium polish
6. **Calendar consensus figures** — attach consensus/previous/actual from a free source (econdb/FMP free tier) or mark explicitly absent; the last calendar gap.
7. **Ticket UI: surface horizon + EV** — the data (`median_hold_s`, EV) already ships in the payload; render it on the card.
8. **Premium polish sweep** — loading skeletons, empty-state microcopy, motion consistency; a live visual pass (needs the browser).

## Constraints
- Same safety rules as the review rounds: read-only against prod except paper-mode runs; no flatten/arming/settings writes; the personal paper ticket writes only to the PAPER venue, never live.
- Deterministic-math discipline (Constraint 2): the UI renders numbers, the backend computes them; the AI-chat feature answers over evidence, never invents quantities.
- Every batch: full backend + frontend gates green, deploy, verify live, then re-score against the review rubric.

## Verification
Re-run the trader-review rubric after Batch C; a category isn't "moved" until the change is observed live. Honest ceilings (Charting order-flow, Portfolio real-n) stay documented, not gamed.

---

## Execution outcome (17 Jul 2026)

| Item | Result |
|---|---|
| **A1** ask-the-record | ✅ shipped + **verified live with the real model** — cited nfp/macro_bull/judge on a real gold run, refused an out-of-scope BTC question (`answerable:false`). Explainability → 10. |
| **A2** chart-native alerts | ✅ shipped — "alert" tool mode, click a level → price alert, direction inferred from last close. |
| **A3** Ichimoku | ⏸️ deferred (documented): honest cloud needs a forward-timestamped series contract + band-fill primitive; disproportionate for one indicator, Charting ceiling is order-flow breadth regardless. |
| **B1** paper order ticket | ⏸️ skipped per user — adds a user-facing execution-write surface that cuts against the "AI decides" design. |
| **B2** track-record page | ✅ shipped — `/track-record` consolidates live record + retro calibration + agent hit-rates, "proven" bar stated before the numbers. |
| **C1** calendar consensus | ⏸️ vendor-gated (documented) — needs a licensed calendar API key; won't fabricate. |
| **C2** horizon + EV on ticket | ✅ already live (p(win)/EV/median-hold render on the card). |
| **C3** premium polish | ◑ partial — new surfaces use shared Card/Skeleton/EmptyState; a full visual sweep needs the browser preview (unavailable this session). |

**Honest score read after this push:** the shippable engineering moved Explainability→10, Charting→~7.5, Portfolio→~9 (record now visible), with Decision/Value nudging up — landing ~87–89. **Clearing a hard 90 needs the two things engineering can't manufacture:** the accrual clock maturing the live track record (Portfolio/Value ceilings) and a visual polish pass (Premium Feel). Both are teed up, not faked.
