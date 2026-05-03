## MANDATORY: Use td for Task Management

Run td usage --new-session at conversation start (or after /clear). This tells you what to work on next.

Sessions are automatic (based on terminal/agent context). Optional:
- td session "name" to label the current session
- td session --new to force a new session in the same context

Use td usage -q after first read.

---

## MANDATORY: Project Identity

This repo contains **two distinct systems** sharing one codebase:

| System | What | Language | Entry Point |
|--------|------|----------|-------------|
| **tradingagents package** | Multi-agent LLM trading framework | Python 3.13 | `tradingagents analyze` (CLI) / `TradingAgentsGraph` (API) |
| **Dashboard server** | Web UI wrapping the Python package | TypeScript (Bun/Hono) | `bun run server/index.tsx` |

**Golden rule:** The dashboard wraps the `tradingagents` package via subprocess. **Never fork or modify `tradingagents/` core agent logic** unless fixing a bug. The bridge is `scripts/analyze_stream.py`.

---

## MANDATORY: Server Configuration

### Port

The dashboard server listens on port **3000** by default.

```bash
# Environment variable override:
export TA_DASHBOARD_PORT=8080
bun run server/index.tsx
```

If port 3000 is occupied, kill stale processes before restarting:
```bash
pkill -9 -f bun   # zombie bun processes are common
```

### Startup Commands

| Task | Command |
|------|---------|
| Start dashboard | `bun run server/index.tsx` |
| Run CLI analysis | `tradingagents analyze` or `just run` |
| Analyze specific ticker | `just analyze TKA.DE` |
| Run tests | `uv run pytest -v -m smoke` |
| Type check server | `tsc --project tsconfig.server.json --noEmit` |
| Lint | `just lint` |

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `TA_DASHBOARD_PORT` | `3000` | Dashboard HTTP port |
| `PORTFOLIO_DB` | `./portfolio.db` | SQLite database path |
| `TRADINGAGENTS_MEMORY_LOG_PATH` | `~/.tradingagents/memory/trading_memory.md` | Decision memory log |
| `TRADINGAGENTS_CACHE_DIR` | `~/.tradingagents/cache` | Checkpoint cache base |
| `HLEDGER_FILE` | `~/.hledger.journal` | hLedger journal path |

---

## MANDATORY: Coding Rules

### 1. Database — `DatabaseFactory` only

All SQLite access goes through `server/lib/db.ts` → `DatabaseFactory`.
- **Never** use `new Database()` directly.
- **Always** use the factory singleton (WAL mode, pragmas enforced).
- **Always** `parseFloat()` on SQLite REAL columns — they return strings.

### 2. Frontend — HTMX + SSR only

- Server renders HTML via Hono JSX (`.tsx` with `/** @jsxImportSource hono/jsx */`).
- **No SPA frameworks** (no React, Vue, Svelte on client).
- **No client-side markdown** — rendered server-side via `server/lib/markdown.ts`.
- Use `pageOrPartial(c, <View />)` for routes that serve both full pages and HTMX partials.

### 3. HTMX + JSON APIs don't mix

- HTMX expects HTML. If an endpoint returns JSON, use `hx-swap="none"` + direct `fetch()` in JS.
- Never `hx-swap="innerHTML"` on a JSON endpoint — it dumps raw JSON into the DOM.

### 4. Python bridge — JSON lines only

- `scripts/analyze_stream.py` is the **only** bridge between Bun and TradingAgents.
- Emits JSON lines to stdout. No Rich, no ANSI escape codes.
- Must run with `PYTHONUNBUFFERED=1` (handled by Bun spawn) for real-time streaming.
- Position context is injected via the memory log (wrap, don't fork).

### 5. SSE events

- Stream from `scripts/analyze_stream.py` stdout → SSE → browser.
- Event types: `start`, `agent_report`, `debate_round`, `decision`, `complete`, `error`.
- `idleTimeout: 240` on the Hono server (4 min) — analyses can take several minutes.

### 6. Datatype font

- Uses the **variable font** from `server/static/fonts/Datatype.woff2` (has GSUB table).
- Static fonts (e.g. from CDN) lack GSUB — chart ligatures will not render.
- Three chart types: `{l:values}` sparkline, `{b:values}` bar chart, `{p:value}` pie chart.
- `font-feature-settings: 'calt' 1, 'liga' 1` is mandatory in CSS.
- Signal class on **parent** div, children use `color: inherit`.

### 7. Error handling

- Never hide errors from the UI. "Failed to load" is useless.
- Propagate actual error message + hint (e.g., "OPENROUTER_API_KEY not configured").
- API responses use `{ error: "...", detail: "...", hint: "..." }` structure.

---

## File Map

```
TradingAgents/
├── AGENTS.md                  ← THIS FILE (agent orientation)
├── ARCHITECTURE.md            ← System architecture reference
├── PLAYBOOK.md                ← User guide for running analyses
├── README.md                  ← Project README
├── CHANGELOG.md               ← Release history
│
├── tradingagents/             ← Python package (core framework — don't fork)
│   ├── graph/                 │   LangGraph workflow (TradingAgentsGraph)
│   ├── agents/                │   LLM-powered agent definitions
│   └── default_config.py      │   All config keys + defaults
│
├── cli/                       ← Python CLI (typer-based)
│   └── main.py                │   `tradingagents analyze` entry point
│
├── server/                    ← Bun/Hono dashboard server
│   ├── index.tsx              │   Entry: routes, lifecycle, graceful shutdown
│   ├── lib/                   │
│   │   ├── db.ts              │   DatabaseFactory (WAL, singleton)
│   │   ├── schema.sql         │   5-table schema + migrations
│   │   ├── hledger.ts         │   hLedger subprocess wrapper
│   │   ├── markdown.ts        │   Server-side markdown renderer
│   │   ├── positions.ts       │   Position helpers
│   │   ├── governance.ts      │   Risk rules engine
│   │   ├── benchmark.ts       │   Portfolio vs. benchmark comparison
│   │   └── feedback.ts        │   Signal accuracy + post-mortems
│   ├── routes/                │   (11 route modules — see ARCHITECTURE.md)
│   ├── views/                 │   (11 .tsx views + partials/)
│   └── static/                │   CSS, fonts, favicon
│
├── scripts/                   ← Utility scripts
│   ├── analyze_stream.py      │   Python→SSE bridge (JSON lines)
│   ├── analyze.py             │   CLI analysis helper
│   └── summarize_analyses.py  │   Batch LLM summarisation
│
├── briefs/                    ← Work proposals (historical reference)
├── debriefs/                  ← Post-work retrospectives (historical reference)
├── playbooks/                 ← Tool-specific conventions (sqlite, hledger, etc.)
├── tests/                     ← Python test suite
├── Justfile                   ← Unified task runner
└── pyproject.toml             ← Python project definition
```

---

## Quick Reference: How Things Flow

```
User clicks "Run Analysis" in browser
         │
         ▼
Bun/Hono POST /api/analyze
         │
         ▼
Bun spawns: PYTHONUNBUFFERED=1 python3 scripts/analyze_stream.py
         │
         ▼
analyze_stream.py creates TradingAgentsGraph, calls .propagate()
         │
         ▼
TradingAgentsGraph runs: Analysts → Research → Trader → Risk → Portfolio Manager
         │
         ▼
analyze_stream.py emits JSON lines: start → agent_report → debate_round → decision → complete
         │
         ▼
Bun reads stdout line-by-line, forwards as SSE events to browser
         │
         ▼
Browser HTMX appends events to progress panel; final decision saved to signals table
```
