# Epic: Dashboard v1 — From Pipeline to Intelligence

**Date:** 2026-05-03
**Epic ID:** DASH-001
**Status:** In Progress
**Stories:** DASH-001-S01 through DASH-001-S07

---

## Vision

The dashboard is a daily workflow tool — open it in the morning, see the state of the portfolio, understand what needs attention, drill into any analysis. It should feel like a pilot's instrument panel: dense but readable, immediate, honest. No friction between opening the page and understanding the position.

The framework (TradingAgents CLI / LangGraph) does the analysis. The dashboard does the tracking, the context, and the decisions. This epic closes the gap between what the agents produce and what the operator can act on.

---

## Stories

### DASH-001-S01 — Portfolio P&L with Live Prices

**What:** The portfolio view shows cost basis but not current value. Wire `/api/prices/:ticker` into the positions table so each row shows live price, current value, and P&L in GBP.

**Acceptance:**
- Each position row shows: entry price, current price, current value, P&L (% and £)
- Prices fetched from `/api/prices/:ticker` (already exists)
- Daily price cache applies (one fetch per ticker per calendar day)
- Rows sorted by P&L descending (worst first, urgency visible)
- Currency: GBP throughout

**Estimate:** 0.5d

---

### DASH-001-S02 — DataType Sparklines: Signals View

**What:** Add 20-day price history sparklines to each signal row in the signals view. Sparkline trends left-to-right with most recent on the right. Color matches signal type (buy=green, sell=red, hold=neutral).

**Acceptance:**
- Each signal row has a sparkline column
- Data source: `GET /api/prices/:ticker` → `history[]`, reversed before rendering
- `datatype.tsx` component used (no ad-hoc `{l:...}` strings)
- `font-feature-settings: 'calt' 1, 'liga' 1` applied to chart spans
- Empty history shows "—" not a broken chart

**Estimate:** 0.5d

---

### DASH-001-S03 — DataType Sparklines: Portfolio View

**What:** Add 20-day price history sparklines to each position row in the portfolio view. Same pattern as S02 — fetch, reverse, render.

**Acceptance:**
- Each position row has a sparkline column (last 20 closes)
- Same rendering approach as S02
- Sparkline fits in existing table column layout

**Estimate:** 0.5d

---

### DASH-001-S04 — Analysis History Drill-Down

**What:** The History tab shows a list of completed analyses. Clicking one opens the full report — all agent reports, debate rounds, risk assessment, and final decision — with a back button to return.

**Acceptance:**
- History view lists all analyses with ticker, date, decision, confidence
- Click analysis → full report view rendered from `analyses.raw_state` JSON
- Agent reports (market, news, fundamentals) displayed as readable sections
- Debate rounds shown in order
- Risk assessment and final decision prominent
- Back navigation returns to history list
- Markdown rendering for agent report content

**Estimate:** 1d

---

### DASH-001-S05 — Portfolio vs. Benchmark Comparison

**What:** The benchmark route needs portfolio total value to compute alpha. Wire portfolio total value from the holdings route into the benchmark route so the comparison works.

**Acceptance:**
- Benchmark view shows portfolio vs. benchmark (e.g. MSCI World) performance
- Portfolio total value = sum of current holdings + cash
- Benchmark index prices fetched from `/api/prices/:ticker` with ^SPX, ^FTSE etc. tickers
- Sparkline showing alpha (portfolio return vs benchmark return) over time
- Returns displayed in GBP with % comparison

**Estimate:** 0.5d

---

### DASH-001-S06 — Signal Accuracy Tracking

**What:** Correlate signals with position outcomes. When a signal fires and a position exists, track whether the signal was right (position gained) or wrong (position lost). Show accuracy score per ticker, per analyst, and overall.

**Acceptance:**
- Feedback view shows: signal → position → outcome → accuracy
- Accuracy calculated when position is closed or after 30 days
- Per-ticker accuracy: what % of signals for AAPL were correct?
- Per-analyst accuracy: how often did the market analyst beat the news analyst?
- AI accuracy score on About page updated from real data
- Post-mortems linked to signals where available

**Estimate:** 1d

---

### DASH-001-S07 — Prospects Platform Filter

**What:** Add a platform dropdown filter to the prospects view header so the user can filter the watchlist by platform (degiero, ibkr, pension:nn, etc.).

**Acceptance:**
- Dropdown in prospects header lists all platforms present in the watchlist
- "All platforms" default
- Filtering updates the watchlist without page reload
- Platform tag shown on each card

**Estimate:** 0.25d

---

## Done

| Story | Status |
|---|---|
| Governance rules as YAML config | ✅ DASH-000 |
| Workflow Kanban (3-column: Approved / Holdings / Pending Exit) | ✅ Done |
| Agent reports persisted to `analyses.raw_state` | ✅ Done |
| Exits: live prices, two-level cache, exit strategy display | ✅ Done |
| Seed data (14 positions, 37 signals, exit plans, post-mortems) | ✅ Done |
| Secret sanitization on all text fields | ✅ Done |
| Tab state preserved on refresh | ✅ Done |
| Daily price cache (midnight UTC expiry, shared cache.ts) | ✅ Done |

---

## Exit Criteria

All 7 stories complete and passing. The dashboard can be used daily as the primary interface for monitoring and managing the portfolio with no further gaps in the core workflow.

**Stretch:** If time allows, add governance violation bars (DataType `{b:...}`) to the governance view — position weight bars showing how far each violation is over the limit.

---

## Notes

- Governance config: `~/.tradingagents/governance.yaml` — per-platform overrides supported
- Price cache: `~/.tradingagents/positions/` YAML files as source of truth for exit plans
- Base currency: GBP throughout
- DataType font: `server/static/fonts/Datatype.woff2` — GSUB ligatures required
- No auth for now — internal dev tool