# TradingAgents Agent Orientation

**The only file you should reference for project rules. All other docs are supplementary.**

---

## HARD RULES

- **NEVER delete untracked files** without explicit user permission
- **NEVER run git clean, rm -rf, or destructive shell commands** without explicit user permission
- **NEVER modify AGENTS.md** without explicit user authorization
- **ALWAYS ask** before modifying or removing user data
- **NEVER push directly to remote \`main\`** — all updates to upstream remote \`main\` must strictly be merged through approved GitHub Pull Requests (PRs). Local merges to \`main\` are only permitted for local checking/validation.

## CRITICAL FILES

These files are core infrastructure. Modification requires user authorization.

| File | Why protected |
|------|---------------|
| `justfile` | Quality guard — `just check` enforces biome + tsc + DB gate before any commit |
| `biome.json` | All linting fails if this is malformed |
| `tsconfig.server.json` | Type safety gate — errors go undetected if paths are wrong |
| `playbooks/conventions-playbook.md` | Conventions document — breaking it allows barnacles to return |
| `playbooks/td-playbook.md` | Solo workflow protocol — keep current
| `src/server/lib/db.ts` | All SQL access — corruption breaks every database operation |
| `src/server/lib/schema.sql` | Schema drift causes data corruption |
| `pyproject.toml` | Python dependency tree — corruption breaks the trading pipeline |

---

## Session Startup

```bash
just orient   # branch, git status, last commit, in-flight tasks
git fetch origin
td usage --new-session   # new session identity
```

Reference: `playbooks/td-playbook.md` for the full workflow.

---

## Language: TypeScript First

- **Dashboard/server work** → TypeScript with Bun only.
- **Python reserved for:** `tradingagents/` core package, `src/cli/main.py`, `scripts/py/analyze_stream.py`.
- **No Python for auxiliary tasks** — use `bun -e "..."` or a `.ts` script instead.

---

## Project Identity

Two systems, one codebase:

| System | Language | Rule |
|--------|----------|------|
| `tradingagents/` package | Python 3.13 | **Never fork or modify core logic.** The bridge is `scripts/py/analyze_stream.py`. |
| Dashboard server | TypeScript (Bun/Hono) | **Wraps the Python package via subprocess only.** |

---

## Coding Rules

1. **Database — `DatabaseFactory` only.** Never `new Database()`. Always `parseFloat()` on REAL columns.
2. **Frontend — HTMX + SSR only.** Server renders HTML via Hono JSX. No SPA frameworks, no client-side markdown.
3. **HTMX + JSON don't mix.** Use `hx-swap="none"` + `fetch()` for JSON endpoints. Never `hx-swap="innerHTML"` on JSON.
4. **Python bridge — JSON lines only.** `scripts/py/analyze_stream.py` is the only Bun↔Python bridge. No Rich, no ANSI.
5. **SSE events** — types: `start`, `agent_report`, `debate_round`, `decision`, `complete`, `error`. `idleTimeout: 240`.
6. **Datatype font** — use `src/server/static/fonts/Datatype.woff2`. CSS: `font-feature-settings: 'calt' 1, 'liga' 1`. Signal class on parent div.
7. **Error responses** — `{ error: "...", detail: "...", hint: "..." }`. Never "Failed to load."

---

## Working Principles

- **Branch before editing.** Never commit directly to `main`. One epic = one feature branch.
- **Commit cadence.** One logical change per commit. If checks fail: revert first, diagnose second.
- **30-file PR cap.** If diff exceeds 30 files, split. Stack branches, don't bundle.
- **Pre-PR gates:** `just check` green → semantic review → docs check.
- **Induced requirements — document immediately.** When a design choice creates a second-order dependency (e.g., a JSON column that a later phase must parse), capture it as a decision record with `type: induced-requirement` *the moment it emerges*. Do not defer. Induced requirements accrue interest — the longer they sit undocumented, the more data must be retroactively reformatted, and the more likely they become a blocking bug instead of a known constraint. See `decisions/013-strategy-rule-schema.md` for the template.
- **GitHub PR Integration:** Push features to remote branch, create PR, wait for server-side reviews and CI checks, and merge via GitHub PR only. Never merge locally and push to remote \`main\`. See [git-workflow-playbook.md](file:///Users/petersmith/dev/github/tradingagents/playbooks/git-workflow-playbook.md).

Detailed conventions: `playbooks/conventions-playbook.md`
Detailed TD protocol: `playbooks/td-playbook.md`
Architecture reference: `ARCHITECTURE.md`

---

## Scope

**This file overrides `~/.pi/agent/AGENTS.md` for all agent sessions inside this repository.**

The global `~/.pi/agent/AGENTS.md` provides Edinburgh Protocol rules and pi agent configuration. This project-level file takes precedence and overrides those rules for the duration of any session inside the TradingAgents repository. See `SILO_MANIFEST.md` for the complete asset map.

> **pi-intercom** — Coordinate with other local pi sessions on related codebases.
>
> Use `/skill: pi-intercom` for patterns. **When:** same codebase (parallel work), reference
> codebase (consulting patterns), related repos (shared libraries). **Not when:** unrelated
> codebases, trivial questions, or when you can proceed independently. **Principle:** prefer
> `send` for notifications; `ask` only when blocked waiting for input.