---
date: 2026-05-02
tags: [feature, ui, infrastructure, api, database, planning]
agent: local-ai
environment: local
---

## Task: TradingAgents Dashboard — Bun/Hono + SSE Implementation

**Objective:** Build a web dashboard for TradingAgents using Bun/Hono that provides portfolio tracking, position-aware analysis, real-time SSE streaming of agent progress, server-side markdown rendering, and signal history — all wrapping the upstream TradingAgents package without forking it.

- [ ] Design SQLite schema for positions, signals, watchlist, and analyses
- [ ] Build Python wrapper script (`scripts/analyze_stream.py`) for clean JSON-line output
- [ ] Build Bun/Hono web server with SSE streaming, API routes, and HTML rendering
- [ ] Build HTMX-based frontend with portfolio, analysis, and signal history views
- [ ] Implement position-aware analysis (inject position context before agent run)
- [ ] Implement JSON log → Markdown renderer for historical analysis display

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser                              │
│  HTMX-driven UI ←──SSE──→ HTML/SSE streams from server      │
│  (no SPA, no build step, no client-side markdown parsing)   │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP + SSE
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Bun / Hono (port 3000)                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │API Routes│ │SSE Proxy │ │SQLite DB │ │Markdown Render│  │
│  │(REST)    │ │/analyze  │ │bun:sqlite│ │marked / itty  │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Static frontend: HTML + HTMX + minimal CSS           │  │
│  │  Server-rendered markdown (no client JS framework)    │  │
│  └───────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │ Bun.spawn()
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              Python Subprocess (analyze_stream.py)           │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │TradingAgents    │  │JSON log parser  │                   │
│  │graph.propagate()│  │→ JSON lines     │                   │
│  └────────┬────────┘  └────────┬────────┘                   │
│           │                    │                             │
│           ▼                    ▼                             │
│  ┌─────────────────────────────────────────┐               │
│  │  Clean JSON-line output on stdout:      │               │
│  │  {"event": "agent_start", "agent": "..."}│              │
│  │  {"event": "tool_call", "tool": "..."}  │               │
│  │  {"event": "report", "section": "..."}  │               │
│  │  {"event": "decision", "rating": "..."} │               │
│  │  {"event": "complete", "state": {...} } │               │
│  └─────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

## Key Actions Checklist:

- [ ] Create `briefs/` directory and this brief
- [ ] Design SQLite schema (positions, signals, watchlist, analyses tables)
- [ ] Create `scripts/analyze_stream.py` — Python wrapper for clean JSON-line output
- [ ] Create `server/` directory with Bun/Hono server
- [ ] Implement SSE `/analyze` route that spawns Python subprocess
- [ ] Implement SQLite CRUD for positions/signals/watchlist via `bun:sqlite`
- [ ] Implement position context injection (read position file → inject into TradingAgents config)
- [ ] Build HTML layout: three tabs (Portfolio, Analysis, Signals)
- [ ] Build HTMX interactions: form submission → SSE stream → DOM updates
- [ ] Implement JSON log → Markdown renderer for historical analysis view
- [ ] Add signal change detection and alert display
- [ ] Test end-to-end: run analysis on TKA.DE, verify SSE streaming, verify position-aware output

## Detailed Requirements

### 1. SQLite Schema & Connection (`portfolio.db`)

**Connection Protocol** — per `playbooks/sqlite-playbook.md`. All database access flows through `DatabaseFactory` (see §1b), never raw `new Database()`.

**Pragmas (enforced by factory, non-negotiable):**
```sql
PRAGMA journal_mode = WAL;          -- concurrent reads during analysis writes
PRAGMA busy_timeout = 5000;         -- wait 5s for locks
PRAGMA mmap_size = 0;               -- stability over speed
PRAGMA foreign_keys = ON;           -- data integrity
PRAGMA synchronous = NORMAL;        -- safe + fast in WAL mode
```

**Golden Rules (from sqlite-playbook):**
1. **WAL mode mandatory** — dashboard reads overlap with analysis writes (signal logging)
2. **ReadWrite mandatory** — even "read-only" queries need `readonly: false` because WAL readers write to `-shm`
3. **Singleton connection** — one long-lived DB instance via `DatabaseFactory`, injected into route handlers
4. **Transactions for bulk ops** — wrap multi-row inserts in `db.transaction()` (50 → 10,000 ops/sec)
5. **Graceful close** — `db.close()` on server shutdown to checkpoint WAL
6. **Optimize on close** — `PRAGMA optimize;` before disconnect

```sql
-- What you currently own
CREATE TABLE positions (
    id         INTEGER PRIMARY KEY,
    ticker     TEXT NOT NULL,
    exchange   TEXT DEFAULT 'US',
    quantity   INTEGER NOT NULL,
    avg_cost   REAL NOT NULL,       -- average entry price
    entry_date TEXT NOT NULL,       -- ISO date
    thesis     TEXT,                -- why you bought it
    status     TEXT DEFAULT 'open', -- open | closed
    notes      TEXT
);

-- Closed positions for P&L history
CREATE TABLE trades (
    id          INTEGER PRIMARY KEY,
    position_id INTEGER REFERENCES positions(id),
    ticker      TEXT NOT NULL,
    action      TEXT NOT NULL,      -- buy | sell
    quantity    INTEGER NOT NULL,
    price       REAL NOT NULL,
    date        TEXT NOT NULL,      -- ISO date
    reason      TEXT,               -- why (e.g., "AI sell signal", "manual exit")
    fees        REAL DEFAULT 0
);

-- Signal history: what the AI said, when
CREATE TABLE signals (
    id         INTEGER PRIMARY KEY,
    ticker     TEXT NOT NULL,
    date       TEXT NOT NULL,       -- analysis date
    signal     TEXT NOT NULL,       -- Buy | Overweight | Hold | Underweight | Sell
    reasoning  TEXT,                -- executive summary
    confidence TEXT,                -- high | medium | low (derived)
    created_at TEXT NOT NULL        -- ISO timestamp of analysis run
);

-- Watchlist: prospects you're tracking but don't own
CREATE TABLE watchlist (
    id         INTEGER PRIMARY KEY,
    ticker     TEXT NOT NULL,
    exchange   TEXT DEFAULT 'US',
    thesis     TEXT,                -- why you're watching it
    priority   TEXT DEFAULT 'medium', -- high | medium | low
    added_date TEXT NOT NULL,
    last_signal TEXT               -- most recent signal for this ticker
);

-- Full analysis output (stored as JSON, rendered on demand)
CREATE TABLE analyses (
    id         INTEGER PRIMARY KEY,
    ticker     TEXT NOT NULL,
    date       TEXT NOT NULL,       -- analysis date
    config     TEXT,                -- JSON: which analysts, LLM, debate rounds
    raw_state  TEXT,                -- full JSON state log from TradingAgents
    decision   TEXT,                -- final decision text
    created_at TEXT NOT NULL
);
```

### 1b. Database Factory (`server/lib/db.ts`)

```typescript
import { Database } from "bun:sqlite";

let _instance: Database | null = null;

export const DatabaseFactory = {
  connect(path: string): Database {
    if (!_instance) {
      _instance = new Database(path, { readwrite: true, create: true });
      _instance.run("PRAGMA journal_mode = WAL");
      _instance.run("PRAGMA busy_timeout = 5000");
      _instance.run("PRAGMA mmap_size = 0");
      _instance.run("PRAGMA foreign_keys = ON");
      _instance.run("PRAGMA synchronous = NORMAL");
    }
    return _instance;
  },
  async close(): Promise<void> {
    if (_instance) {
      _instance.run("PRAGMA optimize");
      _instance.close();
      _instance = null;
    }
  },
  get(): Database {
    if (!_instance) throw new Error("Database not initialized");
    return _instance;
  },
};
```

### 2. Python Wrapper (`scripts/analyze_stream.py`)

Purpose: Run TradingAgents and emit clean JSON lines to stdout. No Rich, no terminal escape codes.

```
Input:  ticker, date, analyst_selection, llm_config, position_context
Output: JSON lines on stdout, one per event

Events:
  {"event": "start", "ticker": "TKA.DE", "date": "2026-05-02"}
  {"event": "agent_start", "agent": "Market Analyst"}
  {"event": "tool_call", "tool": "get_stock_data", "args": {"symbol": "TKA.DE"}}
  {"event": "tool_result", "tool": "get_stock_data", "status": "ok"}
  {"event": "report", "section": "market_report", "content": "..."}
  {"event": "agent_complete", "agent": "Market Analyst"}
  {"event": "debate_start", "type": "investment", "round": 1}
  {"event": "debate_complete", "type": "investment", "decision": "..."}
  {"event": "decision", "signal": "Overweight", "reasoning": "..."}
  {"event": "complete", "log_path": "/path/to/full_states_log.json"}
  {"event": "error", "message": "..."}
```

The wrapper:
- Loads TradingAgents graph
- Injects position context if the ticker is in `portfolio.db`
- Uses callbacks/hooks to capture state transitions
- Emits JSON lines as events occur
- Writes the full state log to `~/.tradingagents/logs/` as normal

### 3. Bun/Hono Server (`server/index.ts`)

Routes:

```
GET  /                          → Portfolio dashboard (HTML)
GET  /analyze                   → Analysis form (HTML)
GET  /signals                   → Signal history (HTML)
GET  /analysis/:id              → Full analysis detail (HTML, rendered markdown)

GET  /api/positions             → List all positions (JSON)
POST /api/positions             → Add position (JSON)
DELETE /api/positions/:id       → Close/remove position (JSON)

GET  /api/watchlist             → List watchlist items (JSON)
POST /api/watchlist             → Add watchlist item (JSON)
DELETE /api/watchlist/:id       → Remove watchlist item (JSON)

POST /api/analyze               → Trigger analysis, returns job SSE stream
GET  /api/analyze/stream        → SSE stream for in-progress analysis
GET  /api/signals               → Signal history (JSON, filterable by ticker)
GET  /api/signals/:ticker       → Signal timeline for specific ticker (JSON)
GET  /api/analyses              → List past analyses (JSON)
GET  /api/analyses/:id          → Full analysis with rendered markdown (JSON)

GET  /api/health                → Server health check
GET  /api/prices/:ticker        → Current price (via yfinance subprocess)
```

### 4. Frontend Layout (HTMX-driven)

```
┌─ TradingAgents Dashboard ───────────────────────────────────┐
│ [Portfolio] [Analysis] [Signals] [Settings]                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  PORTFOLIO TAB                                              │
│  ┌─ Positions ────────────────────────────────────────┐    │
│  │ Ticker │ Shares │ Cost │ Current │ P&L │ Signal   │    │
│  │ TKA.DE │  500   │ €8.45│ €10.09  │+19% │Overweight│    │
│  │ AAPL   │   50   │$185  │ $192    │+3.8%│Hold      │    │
│  └────────────────────────────────────────────────────┘    │
│  [+ Add Position]                                          │
│                                                             │
│  ┌─ Signal Alerts ───────────────────────────────────┐    │
│  │ ⚠ TKA.DE: Hold → Overweight (2026-05-02)         │    │
│  │ 📊 AAPL analysis complete: Hold (no change)       │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─ Watchlist ───────────────────────────────────────┐    │
│  │ Ticker │ Priority │ Last Signal │ Thesis          │    │
│  │ MSFT   │ High     │ Buy         │ Cloud dominance │    │
│  │ 7203.T │ Medium   │ Hold        │ Auto recovery   │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ANALYSIS TAB                                               │
│  ┌─ Run New Analysis ────────────────────────────────┐    │
│  │ Ticker: [TKA.DE]  Date: [2026-05-02]              │    │
│  │ Analysts: ☑ Market  ☐ Social  ☑ News  ☑ Fund      │    │
│  │ LLM: [OpenRouter ▼]  Deep: [gpt-5.4 ▼]            │    │
│  │ Quick: [gpt-5.4-mini ▼]  Debates: [2 ▼]           │    │
│  │                                                   │    │
│  │ ⚠ Position context: 500 shares @ €8.45 (+19.4%)  │    │
│  │   Agents will be aware of your position           │    │
│  │                                    [▶ Run Analysis]│    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─ Live Progress (SSE) ─────────────────────────────┐    │
│  │ [▓▓▓▓▓▓░░░░░░] 5/10 agents complete              │    │
│  │ ✓ Market Analyst — complete                       │    │
│  │ ✓ News Analyst — complete                         │    │
│  │ ● Fundamentals Analyst — in progress              │    │
│  │ ○ Research Team — pending                         │    │
│  │ ○ Trader — pending                                │    │
│  │ ○ Risk Management — pending                       │    │
│  │ ○ Portfolio Manager — pending                     │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─ Analysis Output (streamed markdown) ─────────────┐    │
│  │ ## Market Analysis                                │    │
│  │ TKA.DE is showing a short-term recovery inside... │    │
│  │                                                   │    │
│  │ ## Final Decision: Overweight                     │    │
│  │ Build 1.25x to 1.75x benchmark weight in tranches │    │
│  │                                                   │    │
│  │ ⚠ You hold 500 shares → Recommendation: HOLD     │    │
│  │   (don't add after a 19% run, wait for pullback)  │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  SIGNALS TAB                                                │
│  ┌─ TKA.DE Signal Timeline ──────────────────────────┐    │
│  │                                                   │    │
│  │ Overweight  ████████████ 2026-05-02 (current)     │    │
│  │ Hold        ██████████████████ 2026-04-28         │    │
│  │ Hold        ██████████████████████ 2026-04-15     │    │
│  │                                                   │    │
│  │ Entry: €8.45 ──────────────→ Current: €10.09     │    │
│  │ Signal return: +19.4%                            │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  [Select ticker ▼]  [Show chart]                           │
│                                                             │
│  ┌─ All Signals ─────────────────────────────────────┐    │
│  │ Date     │ Ticker │ Signal     │ Price │ Notes    │    │
│  │ 2026-05-02│TKA.DE │ Overweight │ €10.09│ Kone deal│    │
│  │ 2026-05-02│ AAPL   │ Hold       │ $192  │ Stable   │    │
│  │ 2026-04-28│ TKA.DE │ Hold       │ €9.12 │ Recovery │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5. Position-Aware Analysis Flow

```
User clicks "Run Analysis" on TKA.DE
         │
         ▼
Bun checks portfolio.db: "Do we own TKA.DE?"
         │
    YES  │  NO
         │
         ▼              ▼
Read position     No position context
context:          needed
"500 shares
@ €8.45, +19.4%"  │
         │         │
         └────┬────┘
              ▼
Bun spawns: python3 scripts/analyze_stream.py \
  --ticker TKA.DE \
  --date 2026-05-02 \
  --position-context "500 shares @ €8.45 (+19.4%)"
              │
              ▼
Python wrapper injects context into TradingAgents config
(Portfolio Manager prompt includes position status)
              │
              ▼
Analysis runs, emits JSON-line events to stdout
              │
              ▼
Bun reads stdout, transforms to SSE, streams to browser
              │
              ▼
On complete: save signal to portfolio.db, render final report
```

### 6. File Structure

```
TradingAgents/
├── briefs/
│   └── brief-dashboard-2026-05-02.md    ← this file
├── server/
│   ├── index.ts                          ← Bun/Hono entry point
│   ├── routes/
│   │   ├── portfolio.ts                  ← position CRUD, watchlist
│   │   ├── analysis.ts                   ← SSE analysis trigger
│   │   ├── signals.ts                    ← signal history API
│   │   └── prices.ts                     ─ current price fetcher
│   ├── views/
│   │   ├── layout.html                   ← base HTML template
│   │   ├── portfolio.html                ← portfolio tab
│   │   ├── analysis.html                 ← analysis tab
│   │   ├── signals.html                  ← signals tab
│   │   └── partials/
│   │       ├── position-row.html         ← HTMX partial
│   │       ├── signal-alert.html         ← HTMX partial
│   │       └── analysis-progress.html    ← HTMX partial (SSE target)
│   ├── lib/
│   │   ├── db.ts                         ← DatabaseFactory (singleton + WAL)
│   │   ├── markdown.ts                   ← server-side MD renderer
│   │   └── sse.ts                        ← SSE helper / event builder
│   └── static/
│       ├── style.css                     ← minimal styles
│       └── htmx.min.js                   ← HTMX CDN or vendored
├── scripts/
│   └── analyze_stream.py                 ← Python wrapper for TA
├── portfolio.db                          ← SQLite database (gitignored, WAL mode)
├── portfolio.db-wal                      ← WAL file (auto-created, gitignored)
├── portfolio.db-shm                      ← shared memory (auto-created, gitignored)
└── .env                                  ← API keys (already exists)
```

**Note:** `portfolio.db-wal` and `portfolio.db-shm` are created automatically by WAL mode. Ensure `.gitignore` includes `*.db-wal` and `*.db-shm`.

### 7. Dependencies

**Bun (`server/package.json`):**
```json
{
  "dependencies": {
    "hono": "^4.x",
    "@hono/node-server": "^1.x"  (or just use Bun native)
  },
  "devDependencies": {
    "@types/bun": "latest"
  }
}
```

**Python (already in project venv):**
- No new dependencies — uses existing TradingAgents install
- `scripts/analyze_stream.py` imports from `tradingagents` package directly

### 8. Constraints & Design Decisions

- **SQLite only** — no PostgreSQL, no migration framework. Schema is simple enough to evolve manually
- **WAL mode mandatory** — concurrent reads during analysis writes (signal logging, trade entry)
- **Single DB connection** — `DatabaseFactory` singleton, injected into all routes. No raw connections
- **HTMX only** — no React, no Vue, no build step. Server renders HTML, HTMX swaps fragments
- **SSE for streaming** — no WebSockets, no polling. SSE is unidirectional (server→browser), perfect for analysis progress
- **Markdown rendered server-side** — Bun uses a lightweight markdown parser, client receives clean HTML
- **Portfolio is read-only from TA's perspective** — TradingAgents never writes to the DB; it only reads position context. All DB writes go through Bun API routes
- **Signal recording is automatic** — every completed analysis writes its signal to `signals` table. No manual step
- **Graceful shutdown** — server must call `DatabaseFactory.close()` to checkpoint WAL before exit
- **Transactions for bulk ops** — multi-row inserts (seed, batch analysis) wrapped in `db.transaction()`
- **No fork of TradingAgents** — the wrapper communicates via config injection only

## Verification

- [ ] `bun run server/index.ts` starts without errors
- [ ] `GET /` returns portfolio dashboard HTML
- [ ] `POST /api/positions` creates a position, appears in UI
- [ ] `POST /api/analyze` triggers SSE stream, browser shows live progress
- [ ] Analysis completes, signal saved to DB, report rendered as HTML
- [ ] Position context appears in agent output when analyzing a held ticker
- [ ] Signal timeline shows correct history for TKA.DE
- [ ] JSON log from past analysis renders as readable Markdown
- [ ] WAL mode confirmed: `PRAGMA journal_mode` returns `wal`
- [ ] Concurrent read during analysis write does not produce `SQLITE_BUSY`
- [ ] Graceful shutdown checkpoints WAL (no orphaned `-wal`/`-shm` files)
