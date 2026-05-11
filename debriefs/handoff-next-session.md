# Handoff: Next Agent Session

**Date:** 2026-05-06
**Current branch:** `feat/price-freshness` (created from `main`, pushed to origin)
**Last commit on main:** `be46eec` — docs update after PR #7 merge

---

## What Just Happened

This session completed three major workstreams:

1. **PR #5 forward-port** — Aborted a messy 3-way merge, cherry-picked/rewrote all features (accounts, allocation bar, spread bets, cash breakdown, manual balance) into the JSX architecture. PR #5 closed as redundant. PR #7 created and merged to main.

2. **Final HTML builder eliminations** — Converted the last two string-concatenation routes to JSX:
   - `portfolio.ts` → `portfolio-data.ts` + `portfolio-summary.tsx`
   - `analyses-db.ts` → `analysis-data.ts` + `analysis-report.tsx`

3. **TD hygiene** — Closed 33 stale TDs that were completed but never marked done. Board now reflects reality.

**Result:** Zero HTML string builders remain. Zero inline JS scripts in views. All 10 routes follow data→JSX→thin-route pattern. `just check` green.

---

## What's Left (5 open TDs)

| ID | Priority | What | Status |
|----|----------|------|--------|
| `td-18e84e` | P2 | Price freshness badge (`last_updated` per ticker) | **READY — branch exists for this** |
| `td-984925` | P1 | Types consolidation (inline interfaces → `server/lib/types.ts`) | `in_review` |
| `td-02ccec` | P2 | Split `PortfolioIntel` (16 fields → smaller types) | `open` |
| `td-9dbbac` | P2 | Server tests (route health, positions query, hledger) | `in_review` |
| `td-56fd1b` | P1 | Hygiene epic (parent of above) | `open` |

---

## Recommended Next Actions

### Option A: Price freshness badge (`td-18e84e`) — small, well-defined
- Add `last_updated` timestamp to price cache or DB
- Show badge in portfolio/holdings views next to each ticker
- Good warmup task for a new session

### Option B: Types consolidation (`td-984925`) — mechanical, high value
- Audit all `server/lib/*-data.ts` and `server/routes/*.tsx` for inline interfaces
- Move duplicates to `server/lib/types.ts`
- Re-export from data layers to avoid breaking consumers

### Option C: Server tests (`td-9dbbac`) — fills a real gap
- Route health checks (GET /, /health, /api/positions, etc.)
- Positions query validation
- hledger output parsing smoke tests

---

## Critical Context for Next Agent

### Branch
You are on `feat/price-freshness`. If doing `td-18e84e`, stay here. For other tasks, consider cutting a new branch from `main`.

### Startup ritual
```bash
td usage --new-session
td ws start "Epic: Description"  # if doing epic work
td ws tag <id>
just check                        # MUST be green before touching anything
```

### Architecture invariants
- **TypeScript/Bun only** for server work. Python reserved for `tradingagents/` core + bridge.
- **Data first, JSX second** — extract `lib/{route}-data.ts` before writing components.
- **`.ts` → `.tsx`** rename required for any file containing JSX. Update `server/index.tsx` imports.
- **Hono JSX `style` is a string**, not a React object.
- **External JS only** — `server/static/scripts/*.js`, referenced via `<script src>`.

### Known failure modes (recently learned)
- Forward-port vs merge: >15 conflicts = abort merge, rewrite
- Script path changes: update ALL references in one commit
- `PortfolioIntel` has 16 fields — unwieldy, needs splitting

---

## Files to Read First

1. `debriefs/plans/current.md` — current priorities and known failure modes
2. `AGENTS.md` — project identity, rules, file map
3. `playbooks/htmx-playbook.md` — HTMX + JSX patterns
4. `playbooks/typescript-hono-playbook.md` — TS/Hono invariants

---

## Verification Commands

```bash
just check                        # biome + tsc — must pass
bun run server/index.tsx          # smoke test server startup
curl -s http://localhost:3000/api/portfolio/intelligence | python3 -m json.tool
curl -s http://localhost:3000/api/portfolio/intelligence/html | head -c 200
```

---

*End handoff. Good luck.*

---

## Session: ses_ce3a7d — 2026-05-11

**Branch:** `feat/ctx-lexicon-jsonl` — 10 commits, ready for PR to `main`

### What was done

**Brief:** `brief-ctx-lexicon-upgrade.md` — **CLOSED ✓**

1. Converted `docs/conceptual-lexicon-example.json` (161-entry JSON array) → `debriefs/lexicon-ctx.jsonl` (JSONL)
2. Added 3 scripts: `ctx-lexicon-convert.ts`, `ctx-lexicon-list.ts`, `ctx-lexicon-incorporate.ts`
3. Incorporated 7 CTX terms into `silo-conceptual-lexicon.jsonl` with heuristic + usage fields
4. Fixed slug typo: `g-delian-humility` → `godelian-humility`
5. Deprecated + blanked 11 context-specific/stub terms (slots preserved for reuse)
6. Added 8 just verbs: `ctx-lexicon`, `ctx-lexicon-type`, `ctx-lexicon-status`, `ctx-lexicon-search`, `ctx-lexicon-stats`, `ctx-lexicon-convert`, `ctx-lexicon-incorporate`
7. Documented just parameter-passing gotcha + fix pattern in `playbooks/just-playbook.md`
8. Added `just --unstable --fmt --check` as first step of `check` recipe

**CTX lexicon final state:** 161 entries — 150 active, 11 deprecated

### Key technical lessons

1. **Script first, just second** — always test script directly before wiring to just
2. **`getFlagValue` pattern** — strip first `word=` prefix via `indexOf("=")` to handle just's `param=value` passing
3. **`just --unstable --fmt --check` first in `check`** — catches structural justfile breakage immediately
4. **Deprecate > delete** — blank content, keep slot

### Not done

- `brief-ig-api-client-integration.md` — still open (second brief in UNIFIED-CLI-001 epic)
- SideCar terminal setup for `td` task display (context window issue prevented completion)

### Just verbs to know

```bash
just ctx-lexicon                      # List CTX lexicon
just ctx-lexicon-type type=term       # Filter by type
just ctx-lexicon-status stat=active   # Filter by status
just ctx-lexicon-search query=humility # Full-text search
just ctx-lexicon-stats                # Distribution stats
just ctx-lexicon-convert             # Re-run JSON→JSONL conversion
just ctx-lexicon-incorporate         # Merge CTX terms into silo lexicon
```

### Branch status

```bash
git checkout feat/ctx-lexicon-jsonl
git log --oneline main..HEAD  # 10 commits to merge
```

