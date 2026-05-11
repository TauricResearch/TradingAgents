## MANDATORY: Use td for Task Management (Multi-Agent)

This codebase is collaborative. Multiple agents and the user share the same branch. **Every agent session is a distinct identity.**

### Startup (do this first)

```bash
td usage --new-session     # new identity
bun scripts/agent-orient.ts   # orientation: branch + td + in-flight
bun scripts/agent-sync.ts     # sync: git state + file collisions
# → Full protocol: playbooks/td-playbook.md
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

### Agent Coordination Protocol

**Rule 0 — Claim before touch.** Never edit a file until you have:
1. Run `bun scripts/agent-claim.ts <id>` on the owning task
2. Verified no other session has claimed it
3. Checked `bun scripts/agent-sync.ts --collisions` for file conflicts

**Rule 1 — One epic per session.** Tag relevant tasks to your workspace:
```bash
td ws start "Epic: Description"
td ws tag <id1> <id2> ...
```

**Rule 2 — Log progress.** `bun scripts/agent-log.ts <id> "did X"` after every substantive change.

**Rule 3 — Handoff on close.** Always run `bun scripts/agent-handoff.ts <id> --done X --remaining Y` before `td close`.

**Rule 4 — Broadcast on collision risk.** If you need a file another agent is working on:
```bash
td comment <id> "@<session>: requesting handover"
```

**Rule 5 — Sync before start.** When resuming: `bun scripts/agent-sync.ts` to verify you haven't drifted from main.

**Full protocol:** `playbooks/td-playbook.md`

---

### Language Selection — TypeScript First

This codebase is **primarily a Bun/TypeScript house.**

- **Dashboard/server work** (routes, views, scripts, tooling): **TypeScript with Bun only.**
- **Python is reserved for:** the `tradingagents/` core package, the CLI entry point (`src/cli/main.py`), and the bridge script (`scripts/py/analyze_stream.py`).
- **No Python for auxiliary tasks.** Do not reach for Python for one-off conversions, data transforms, or code-generation scripts. Use `bun -e "..."`, a `.ts` script in `scripts/`, or a throwaway `.ts` file instead.
- **Never add a Python dependency** to solve a problem that a 20-line TypeScript snippet or an npm package can handle.

---

## MANDATORY: Project Identity

This repo contains **two distinct systems** sharing one codebase:

| System | What | Language | Entry Point |
|--------|------|----------|-------------|
| **tradingagents package** | Multi-agent LLM trading framework | Python 3.13 | `tradingagents analyze` (CLI) / `TradingAgentsGraph` (API) |
| **Dashboard server** | Web UI wrapping the Python package | TypeScript (Bun/Hono) | `bun run src/server/index.tsx` |

**Golden rule:** The dashboard wraps the `tradingagents` package via subprocess. **Never fork or modify `tradingagents/` core agent logic** unless fixing a bug. The bridge is `scripts/analyze_stream.py`.

---

## MANDATORY: Server Configuration

### Port

The dashboard server listens on port **3000** by default.

```bash
# Environment variable override:
export TA_DASHBOARD_PORT=8080
bun run src/server/index.tsx
```

If port 3000 is occupied, kill stale processes before restarting:
```bash
pkill -9 -f bun   # zombie bun processes are common
```

### Startup Commands

| Task | Command |
|------|---------|
| Start dashboard | `bun run src/server/index.tsx` |
| Run CLI analysis | `trading analyze <TICKER>` or `tradingagents analyze` |
| Trade plan | `trading plan <TICKER> [--mode spreadbet]` |
| IG trading | `trading ig <login|accounts|search|prices|positions|buy|sell>` |
| Portfolio summary | `trading portfolio` |
| Watchlist | `trading watchlist` |
| Signals | `trading signals [TICKER]` |
| Config defaults | `trading config <get|set|list|path>` |
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

All SQLite access goes through `src/server/lib/db.ts` → `DatabaseFactory`.
- **Never** use `new Database()` directly.
- **Always** use the factory singleton (WAL mode, pragmas enforced).
- **Always** `parseFloat()` on SQLite REAL columns — they return strings.

### 2. Frontend — HTMX + SSR only

- Server renders HTML via Hono JSX (`.tsx` with `/** @jsxImportSource hono/jsx */`).
- **No SPA frameworks** (no React, Vue, Svelte on client).
- **No client-side markdown** — rendered server-side via `src/server/lib/markdown.ts`.
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

- Uses the **variable font** from `src/server/static/fonts/Datatype.woff2` (has GSUB table).
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
├── src/cli/                   ← TypeScript CLI (`trading`)
│   ├── main.ts                │   Entry: citty subcommand dispatch
│   ├── commands/              │   plan, execute, ig, portfolio, watchlist, signals, analyze, config, seed, sync, backup, summarize
│   └── lib/                   │   platforms.ts, args.ts, ig-instruments.ts
│
├── cli/                       ← Python CLI (`tradingagents`)
│   └── main.py                │   `tradingagents analyze` entry point
│
├── src/server/                ← Bun/Hono dashboard server
│   ├── index.tsx              │   Entry: routes, lifecycle, graceful shutdown
│   ├── lib/                   │
│   │   ├── db.ts              │   DatabaseFactory (WAL, singleton)
│   │   ├── schema.sql         │   Schema: positions, trades, signals, watchlist, analyses, prices, accounts, spreadbet_positions, account_balances
│   │   ├── hledger.ts         │   hLedger subprocess wrapper
│   │   ├── markdown.ts        │   Server-side markdown renderer
│   │   ├── positions.ts       │   Exit plan helpers (load, compute status)
│   │   ├── governance.ts      │   Risk rules engine
│   │   ├── benchmark.ts       │   Portfolio vs. benchmark (SQLite live prices)
│   │   ├── feedback.ts        │   Signal accuracy + post-mortems
│   │   ├── portfolio-data.ts  │   Portfolio summary computation + price fetching
│   │   ├── portfolio-intel-data.ts │   Intelligence: accounts, allocation, spread bets
│   │   ├── analysis-data.ts   │   Analysis types + fmtDate helper
│   │   └── types.ts           │   Shared type definitions
│   ├── routes/                │   (12 route modules — see ARCHITECTURE.md)
│   │   ├── portfolio-intelligence.tsx  │   Unified portfolio view (hledger cash + SQLite positions)
│   │   └── portfolio-balance.ts      │   POST manual account balance update
│   ├── views/                 │   (12 .tsx views + partials/)
│   │   ├── intelligence.tsx   │   Portfolio Intelligence view
│   │   ├── portfolio-summary.tsx │   Portfolio P&L summary + positions table
│   │   └── analysis-report.tsx  │   Analysis report + event sections + list/card views
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

### Git Branching — Always Branch Before Editing

**Never commit directly to `main`.** Before starting any epic or multi-commit work:

```bash
# Check current state first
git branch -v

# If on main with clean state and about to start new work:
git checkout -b feat/<epic-name>

# If on main with uncommitted changes:
# → commit or stash first, then branch
```

**Rules:**
- If on `main` and about to write code → create a branch first
- If on a feature branch → you're good, keep working
- If on main with no uncommitted changes but also no branch → you're about to break protocol
- One epic = one feature branch. Stack if you have dependent epics.
- Merge via PR (even if you're the only reviewer — it forces the pre-PR checklist)

**Session start checklist:**
```bash
git status && git branch -v   # confirm branch
just check                    # must be green
td usage --new-session        # new identity
td ws current                 # any active work to resume?
```

If `git branch -v` shows `* main` and you have a brief to implement → create a branch before touching any files.

---

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

### PR Size Discipline

**One concern per PR.** A PR that bundles a directory restructure, a new CLI, API integration, a trade calculator, and documentation into one changeset is unreviewable and un-bisectable. PR #9 (191 files, 16k lines) is the cautionary example — the review cycle stretched over days because no single reviewer could assess five independent concerns at once.

**Rules:**
- **Hard cap: 30 files per PR.** If `git diff --stat main...HEAD | wc -l` exceeds 30, split it. Mechanical renames (e.g. `server/` → `src/server/`) are an exception — they're low-risk and reviewable by pattern, not by line.
- **One PR per td epic story.** Epics with multiple stories should produce multiple PRs, not one. Use `td` story IDs to track which PR maps to which story.
- **Stack branches, don't bundle.** If Story B depends on Story A, cut branch B from branch A, not from `main`. Merge bottom-up: A → `main`, then rebase B onto `main`, then merge B.
- **Justify exceptions in the PR body.** If a PR genuinely can't be split (e.g. a cross-cutting type change that touches 40 files), explain why in the description. "It's all related" is not a justification.

**Why it matters:**
- Review surface area: a 30-file PR gets a thorough review in minutes. A 191-file PR gets a skim.
- `git bisect`: a small, focused commit isolates breakage to one change. A monolithic commit says "something in these 191 files broke."
- Merge velocity: small PRs merge in hours. Large PRs accumulate conflicts and drift over days.

### Pre-PR Checklist

Before opening a PR or marking a task for review, run through these gates. Automated reviewers (CodeRabbit, etc.) are a safety net, not a replacement — they catch ~1 real bug per 3 flagged items. Self-review catches the rest before the bot sees them.

**Gate 1: Mechanical**
- [ ] `just check` — biome + tsc + DB usage gate, all green
- [ ] `git diff --stat main...HEAD | wc -l` — under 30 files (or justified in PR body)
- [ ] All new `.tsx` files have `/** @jsxImportSource hono/jsx */` if they contain JSX
- [ ] No new `.ts` files contain JSX (must be `.tsx`)
- [ ] No `console.log` left in production paths (debug logging is fine, remove before merge)
- [ ] No `new Database()` outside `src/server/lib/db.ts`

**Gate 2: Semantic**
- [ ] New routes return correct status codes (404 for missing, not 200)
- [ ] SQLite REAL columns are parsed with `parseFloat()` before arithmetic
- [ ] hLedger output parsing handles edge cases (empty output, missing fields)
- [ ] SSE events follow the defined schema (see ARCHITECTURE.md)
- [ ] Error responses use `{ error, detail, hint }` structure

**Gate 3: Documentation**
- [ ] Paths in docs match actual file locations (not `server/` when it's `src/server/`)
- [ ] New scripts have a line in `scripts/README.md` if they're long-lived
- [ ] `debriefs/plans/current.md` reflects actual td state after the PR merges

Skip Gate 3 for documentation-only or lint-only PRs.

### Known Failure Modes

**Static JS copies of TypeScript = maintenance trap.**
The canonical client-side runtime lives in `src/server/static/scripts/*.js`. These are the single source of truth for browser behaviour — not copies of some TypeScript original. Views reference them via `<script src="/static/scripts/xxx.js" />`. Biome linting for this directory is disabled in `biome.json` (client-side JS has different constraints than server TS). Do not maintain a second inline TypeScript copy in views.

**Biome config changes must be validated immediately.**
`biome.json` is validated by biome itself. If you add a key that doesn't exist (`files.ignore` is not valid at v2.4.14), biome fails with a parse error before running any checks. Always run `just lint` after any `biome.json` change.

**Template literals inside template literals break silently.**
Backtick-quoted strings inside template literals are a syntax error. The JSX compiler won't catch it. Runtime behavior is undefined. Fix: use `String.fromCharCode(34)` for embedded quotes or restructure the string.

**Revert is faster than forward-fix.**
If a change breaks checks and the fix isn't obvious, revert to the last known-good commit. Three failed forward-attempts burned 45 minutes. One revert took 5. Trust the revert.

**No test coverage for views.** `pytest -m smoke` only covers Python. TypeScript views have no automated test. Until we have route-level tests (`td-9dbbac`), the only guard is: check `tsc` + `lint` + manual browser verification.

**Route file with JSX retaining `.ts` extension.**
Biome will produce cryptic parse errors: "expected `>` but instead found `data"`. The parser treats JSX as TypeScript class syntax. Fix: rename to `.tsx` and update all imports in `src/server/index.tsx`.

**Forward-porting vs merging.**
When a PR was written against old architecture that you've since refactored, evaluate conflict count × semantic distance. String-concat vs JSX is a chasm, not a gap. If >15 conflict regions: abort merge, cherry-pick ideas, rewrite into new architecture.

**Script path unification.**
When a script moves (e.g. `scripts/` → `scripts/py/`), update ALL references in a single commit. Piecemeal updates create runtime "file not found" errors that only surface in production.

---

## Quick Reference: How Things Flow

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **TradingAgents** (5074 symbols, 6891 relationships, 140 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any function, class, or method signature.** Before renaming, extracting, removing, or changing the signature of a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user. Not needed for docs, lint, config, or one-line fixes that don't change the call graph.
- **MUST run `gitnexus_detect_changes()` before committing structural changes** to verify your changes only affect expected symbols and execution flows. Skip for documentation-only or lint-only commits.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `silo-conceptual-lexicon.jsonl` | **Consult first.** Vocabulary, heuristics, and conventions used in this silo |
| `gitnexus://repo/TradingAgents/context` | Codebase overview, check index freshness |
| `gitnexus://repo/TradingAgents/clusters` | All functional areas |
| `gitnexus://repo/TradingAgents/processes` | All execution flows |
| `gitnexus://repo/TradingAgents/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
