# TradingAgents — Visitor Orientation

> **Boot time:** ~60 seconds. Read this file, run the commands at the bottom.

---

## What This Does

**Multi-agent LLM trading framework** with a web dashboard. Python core (`tradingagents/` package) wrapped by a Bun/Hono server. The dashboard never forks or modifies the core — communication is via subprocess bridge only.

```
Core (Python)              Bridge (JSON lines)           Dashboard (Bun/Hono)
─────────────              ───────────────────           ───────────────────
TradingAgentsGraph  ──►  scripts/py/analyze_stream.py  ──►  SSE → browser
                         (stdout: JSON lines only)
```

---

## Critical Files (Don't Break)

| File | Why protected |
|------|---------------|
| `justfile` | Quality gate — `just check` enforces biome + tsc + DB validation |
| `biome.json` | Malformation kills all linting |
| `tsconfig.server.json` | Wrong paths break type checking silently |
| `src/server/lib/db.ts` | `DatabaseFactory` — enforces WAL mode + pragmas for all SQL |
| `src/server/lib/schema.sql` | Schema drift corrupts data |
| `pyproject.toml` | Dependency tree corruption breaks the pipeline |

**Rules:**
- Database → use `DatabaseFactory.get()`, never `new Database()`
- Frontend → HTMX + SSR only. No SPA frameworks.
- Python bridge → JSON lines only. No Rich, no ANSI.

---

## Language Boundary

| System | Language | Boundary |
|--------|----------|----------|
| `tradingagents/` core | Python 3.13 | **Never modify** |
| `src/cli/main.py` | Python | Allowed |
| `scripts/py/analyze_stream.py` | Python | Bridge only — JSON lines, no Rich |
| Everything else | TypeScript (Bun) | Dashboard, tooling, scripts |

---

## Architecture in One Paragraph

**Python core:** LangGraph workflow with specialized LLM agents (Analyst Team → Research Team [Bull/Bear debate] → Trader → Risk Management → Portfolio Manager).

**Bun server:** 11-tab dashboard, HTMX + JSX SSR, SQLite via `DatabaseFactory`, hLedger as authoritative source for positions.

**Bridge:** `scripts/py/analyze_stream.py` writes JSON lines to stdout. Bun reads and streams as SSE events (`start`, `agent_report`, `debate_round`, `decision`, `complete`, `error`).

**Persistence layers:** SQLite (signals, analyses, watchlist) → hLedger (positions, cash) → memory log (decision history) → YAML exit plans.

---

## Active Conventions (Highlight)

| Convention | Reason |
|------------|--------|
| `justfile` lowercase | Formatter compatibility |
| `.tsx` for JSX files | Biome parser requirement |
| `Bun.spawn` over `execSync` | Streaming support, no quoting bugs |
| No `new Database()` | Factory enforces WAL + consistency |
| 30-file PR cap | Reviewable, bisectable |
| One commit per logical change | Revert is fast; forward-fix is slow |

Full list: `playbooks/conventions-playbook.md`

---

## Workflow (td-based)

```bash
just orient           # git status, branch, last commit
td usage --new-session # register session
td next               # pick up highest priority issue
```

For multi-issue work:
```bash
td ws start "name"    # open work session
td ws tag <ids>       # claim issues
```

On session end:
```bash
td handoff <id>       # capture state (REQUIRED)
```

Full protocol: `playbooks/td-playbook.md`

---

## Current Context

```bash
# Run these to see live state:
echo "=== BRANCH ===" && git branch --show-current
echo "=== LAST COMMIT ===" && git log -1 --oneline
echo "=== OPEN ISSUES ===" && td list --json 2>/dev/null | jq '.issues[] | select(.status == "open") | .title' 2>/dev/null || echo "(td not available)"
echo "=== IN REVIEW ===" && td reviewable 2>/dev/null || echo "(td not available)"
```

**Quick reference:**

| What's open | What needs review |
|-------------|-------------------|
| Run `td next` | Run `td reviewable` |

---

## If You Get Stuck

1. **Check for barnacles** — `playbooks/conventions-playbook.md` → Barnacle Inspection Prompt
2. **Architecture questions** → `ARCHITECTURE.md` is the single source of truth
3. **DB issues** → Use `DatabaseFactory` only; check `schema.sql`
4. **Python bridge** → `scripts/py/analyze_stream.py` is the only Bun↔Python path

---

## First Session Commands

```bash
# Orientation
just orient
git fetch origin

# Register session
td usage --new-session

# Check for barnacles
cat playbooks/conventions-playbook.md | grep -A 30 "Barnacle Inspection Prompt"

# Start working
td next
```