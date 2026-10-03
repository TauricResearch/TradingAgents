# Brief: Dashboard Phase 2 — 2026-05-02

## Context
Phase 1 (foundation) is complete: Bun/Hono server, JSX SSR, HTMX tabs, SSE streaming, SQLite, Datatype font, signal timeline, past analyses browser. All 7 issues implemented and merged.

## Proposed Work

### 1. Current Price + P&L in Portfolio Table
**Scope:** Wire yfinance into the portfolio table to show live prices and unrealized P&L.
- `GET /api/prices/:ticker` — currently returns stub; implement yfinance subprocess call
- Portfolio table adds columns: Current Price, P&L ($), P&L (%)
- Color-code P&L (green positive, red negative)
- Datatype sparkline for recent price history per position

**Dependencies:** None (prices.ts stub exists)
**Priority:** P1

### 2. Analysis Markdown Rendering
**Scope:** Render SSE analysis reports as formatted markdown in the analysis tab.
- Analysis tab currently shows raw event list; needs rendered output panel
- Use `server/lib/markdown.ts` (marked + sanitizer) to render agent reports
- Streaming render: append markdown chunks as SSE events arrive
- Position-aware callout: "You hold 500 shares → Recommendation: HOLD"

**Dependencies:** None (markdown.ts exists, SSE pipeline works)
**Priority:** P1

### 3. Watchlist Management
**Scope:** Full CRUD for watchlist with priority levels and last-seen signals.
- `GET /api/watchlist` — list all watchlist items
- `POST /api/watchlist` — add ticker with priority (High/Medium/Low) and thesis
- `DELETE /api/watchlist/:id` — remove from watchlist
- Watchlist panel on Portfolio tab showing ticker, priority, last signal, thesis
- "Add to Watchlist" button from analysis results

**Dependencies:** Watchlist table exists in schema.sql
**Priority:** P2

### 4. Auto-Save Analysis Decisions as Signals
**Scope:** Already partially implemented in analysis.ts (intercepts decision event).
- Verify signal is saved correctly with full reasoning
- Add confidence percentage from analysis output
- Link analysis log path to the signal record for drill-down
- Signal history should show source (manual vs analysis)

**Dependencies:** None (partial implementation exists)
**Priority:** P2

### 5. Analysis Drill-Down from History
**Scope:** Click a past analysis in History tab → full report with all agent outputs.
- `GET /api/analyses/:ticker/:date` — already returns rendered HTML
- Need: navigation from History list → detailed view with back button
- Show all sections: Market, News, Fundamentals, Sentiment, Debate, Final Decision
- Datatype sparkline for confidence trend across multiple analyses of same ticker

**Dependencies:** analyses.ts exists, needs UI polish
**Priority:** P2

### 6. Error Handling + Loading States
**Scope:** Improve UX for failure modes.
- Python subprocess failure → user-friendly error message in SSE panel
- DB connection failure → health indicator in header
- Loading spinners for HTMX swaps
- Timeout handling for long analyses (> 4 min)
- Retry button for failed analysis runs

**Dependencies:** None
**Priority:** P3

## File Structure (additions)
```
server/
├── routes/
│   └── prices.ts          ← yfinance subprocess (currently stub)
├── views/
│   ├── analysis.tsx       ← add markdown render panel
│   └── portfolio.tsx      ← add price/P&L columns
└── static/
    └── style.css          ← P&L color classes, loading states
```

## Success Criteria
- Portfolio table shows live prices with color-coded P&L
- Analysis tab renders formatted markdown reports in real-time
- Watchlist CRUD works from UI
- Every analysis decision auto-saves as a signal
- History → drill-down → full report with back navigation
