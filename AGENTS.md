## MANDATORY: Use td for Task Management (Multi-Agent)

This codebase is collaborative. Multiple agents and the user share the same branch. **Every agent session is a distinct identity.**

### Startup (do this first)

```bash
td usage --new-session     # new identity
td ws current              # any active work session to resume?
td list                    # what's open / in_progress
td reviewable              # what can I review?
```

### Core Rule: Always Use a Work Session

If a task belongs to an epic, or you are doing more than one thing, use a work session (`td ws`). Never juggle individual tasks for epic work.

```bash
# Correct — work session for epic work
td ws start "Epic: Description"
td ws tag <id1> <id2> ...
td ws log "progress"
td ws handoff               # hand off all tagged tasks at once

# Wrong — don't do this for epic work
td start <id1>
td handoff <id1>
```

**Read `playbooks/td-playbook.md` for the full multi-agent protocol.**

**Before starting any work:** read `debriefs/plans/current.md`. It contains the current work plan, priority order, mandatory protocol, and known failure modes. Always start there.

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
| `PORTFOLIO_DB` | `./portfolio.db` | SQLite database path (dev) |
| `TEST_MODE` | `0` | Set to `1` to use `test_portfolio.db` instead of `portfolio.db` |
| `TEST_PORTFOLIO_DB` | `./test_portfolio.db` | Path to test SQLite DB (when `TEST_MODE=1`) |
| `TRADINGAGENTS_MEMORY_LOG_PATH` | `~/.tradingagents/memory/trading_memory.md` | Decision memory log |
| `TRADINGAGENTS_CACHE_DIR` | `~/.tradingagents/cache` | Checkpoint cache base |
| `HLEDGER_FILE` | `~/.hledger.journal` | hLedger journal path (DEV) |
| `TEST_HLEDGER_FILE` | `~/.tradingagents/test_hledger.journal` | hLedger journal path (TEST — active when TEST_MODE=1) |

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
│   │   ├── schema.sql         │   5-table schema (signals, analyses, watchlist; positions deprecated — hledger owns real data)
│   │   ├── hledger.ts         │   hLedger subprocess wrapper
│   │   ├── markdown.ts        │   Server-side markdown renderer
│   │   ├── positions.ts       │   Exit plan helpers (load, compute status)
│   │   ├── governance.ts      │   Risk rules engine
│   │   ├── benchmark.ts       │   Portfolio vs. benchmark (SQLite live prices)
│   │   ├── feedback.ts        │   Signal accuracy + post-mortems
│   │   ├── benchmark.ts       │   Portfolio vs. benchmark comparison
│   │   └── feedback.ts        │   Signal accuracy tracking
│   ├── routes/                │   (12 route modules — see ARCHITECTURE.md)
│   │   └── portfolio-intelligence.ts  │   Unified portfolio view (hledger cash + SQLite positions)
│   ├── views/                 │   (12 .tsx views + partials/)
│   │   └── intelligence.tsx   │   Portfolio Intelligence view
│   └── static/                │   CSS, fonts, favicon, client-side JS
│       └── scripts/           │   External client-side scripts (canonical runtime JS)
│
├── scripts/                   ← TypeScript utilities (Bun native)
│   ├── seed_database.ts       │   Seed SQLite + exit plans + post-mortems
│   ├── summarize_analyses.ts  │   LLM summarisation via OpenRouter
│   ├── get_price.ts           │   Yahoo Finance price + history
│   ├── portfolio-intel.ts     │   Portfolio summary via HTTP
│   ├── render_diagrams.ts     │   DOT/MMD → SVG (graphviz + mmdc)
│   └── extract_mermaid.ts     │   Strip YAML front matter from MMD
│   ├── py/                    │   Python scripts (tradingagents dep)
│   │   ├── analyze_stream.py  │   Bun→Python bridge (TradingAgentsGraph)
│   │   ├── analyze.py         │   CLI wrapper for analyze_stream
│   │   └── smoke_structured_output.py  │   Agent output smoke tests
│   └── README.md              │   Scripts documentation
│
├── briefs/                    ← Work proposals (historical reference)
├── debriefs/                  ← Post-work retrospectives (historical reference)
├── playbooks/                 ← Tool-specific conventions (sqlite, hledger, etc.)
├── tests/                     ← Python test suite
├── Justfile                   ← Unified task runner
└── pyproject.toml             ← Python project definition
```

---

## Working Principles

### Refactor Heuristic

**Commit cadence:** One logical change per commit. "Logical" means: all files that must change together to achieve one goal, no more.

**Fail-fast protocol:**
1. Make small change → check → commit or revert.
2. If checks fail after a change: revert first, diagnose second. Never pile fixes on a broken state.
3. If stuck for >15 min on the same check failure: stop, revert, ask.

**When starting a TD:**
1. Run `just check` — must be clean before starting.
2. Make the change to one file (or a small set of related files).
3. Run `just check` again — must pass.
4. Commit with message: `type(scope): what changed`.
5. Repeat.

**Batch vs. single:** Multiple small tasks that each require the same check run can be done in parallel if they don't touch the same files. If they share files (e.g. updating `biome.json` for multiple changes), do them one at a time — shared config changes are high-friction and high-revert-cost.

### Known Failure Modes

**Static JS copies of TypeScript = maintenance trap.**
The canonical client-side runtime lives in `server/static/scripts/*.js`. These are the single source of truth for browser behaviour — not copies of some TypeScript original. Views reference them via `<script src="/static/scripts/xxx.js" />`. Biome linting for this directory is disabled in `biome.json` (client-side JS has different constraints than server TS). Do not maintain a second inline TypeScript copy in views.

**Biome config changes must be validated immediately.**
`biome.json` is validated by biome itself. If you add a key that doesn't exist (`files.ignore` is not valid at v2.4.14), biome fails with a parse error before running any checks. Always run `just lint` after any `biome.json` change.

**Template literals inside template literals break silently.**
Backtick-quoted strings inside template literals are a syntax error. The JSX compiler won't catch it. Runtime behavior is undefined. Fix: use `String.fromCharCode(34)` for embedded quotes or restructure the string.

**Revert is faster than forward-fix.**
If a change breaks checks and the fix isn't obvious, revert to the last known-good commit. Three failed forward-attempts burned 45 minutes. One revert took 5. Trust the revert.

**No test coverage for views.** `pytest -m smoke` only covers Python. TypeScript views have no automated test. Until we have route-level tests (`td-9dbbac`), the only guard is: check `tsc` + `lint` + manual browser verification.

---

## Quick Reference: How Things Flow


