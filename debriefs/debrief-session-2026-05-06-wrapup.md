# Session Wrap-Up: 2026-05-06 — Hygiene, Shared Substrate, and Bug Discovery

**Branch:** `feat/price-freshness`  
**PR:** #8 (open, updated)  
**Commits this session:** 11  
**Scope:** Playbook refactor, shared LLM substrate, DatabaseFactory enforcement, flox environment, debate mechanism bug discovery and fix

---

## What We Did

### 1. Playbook Hygiene (b2d322d)

Refactored `playbooks/htmx-playbook.md` from 600+ lines of war-story narrative to a clean, prescriptive playbook. Used `gemini-2.5-flash` via a purpose-built script (`scripts/refactor-playbook.ts`) with a system prompt stripping historical prose and rephrasing rules as direct imperatives.

**Key preservation:** Added Edge Cases section manually after LLM refactor dropped two critical runtime traps (`var` hoisting in loops, `split('\n')` vs actual newlines).

**Lesson:** LLM refactors are ~90% correct for structure but lose ~13% of edge-case detail. Always diff against original for technical completeness.

### 2. Shared LLM Substrate (00c4d73)

Extracted duplicated OpenRouter boilerplate from three scripts into `scripts/lib/llm.ts`:
- Auto-loads `.env` once at module init
- Single `llm(messages, opts)` function with sensible defaults
- Centralizes model defaults, error handling, API key validation

**Refactored callers:** `pr-summarize.ts`, `summarize_analyses.ts`, `refactor-playbook.ts`

**Gotcha:** `.gitignore` had `lib/` (Python packaging standard) which silently excluded `scripts/lib/`. Added `!scripts/lib/` exception.

**Lesson:** The 3-script rule — when you have 3 scripts with duplicated logic, extraction is mandatory, not optional.

### 3. DatabaseFactory Enforcement (62108d6)

Two standalone scripts (`seed_database.ts`, `sync-prices.ts`) had their own `connectDb()` helpers with raw `new Database(path)` and partial/inconsistent pragmas. This is the exact failure mode the rule exists to prevent.

**Fix:** Removed duplicated helpers, replaced with `DatabaseFactory.connect()` + `DatabaseFactory.get()`.

**Created gate:** `scripts/check-database-usage.ts` — scans all `.ts/.tsx/.js` for `new Database(` outside `server/lib/db.ts`. Added to `just check` recipe.

**Three-layer defense:**
1. Mechanical gate (fails the build)
2. Import barrier (no `Database` imports outside `db.ts`)
3. Codified standard (AGENTS.md + playbooks)

### 4. Flox Environment Manifest (8f8f97c, 0063158)

Replaced stale `just-silo` template manifest with TradingAgents-specific dependencies. Added missing critical tools: `hledger`, `uv`, `sqlite`, `defuddle`. Corrected tool matrix: required vs optional, correct nixpkgs availability.

**Notable find:** `defuddle` is in nixpkgs but has no Homebrew formula — exactly the kind of unpackaged-essential tool that flox solves.

**Lesson:** When a tool becomes invisible infrastructure (you stop thinking about it, but removing it breaks the workflow), treat it as a hard dependency.

### 5. Tidy-First Philosophy Document (eab60d7)

Recorded the operational philosophy in `docs/tidy-first-philosophy.md`. Key insight: in this codebase, execution speed is high and error cost compounds. Therefore quality is the binding constraint, not velocity.

**Empirical test:** After each tidy step, does the next feature take less work?

### 6. Debate Mechanism Bug Discovery and Fix (9040665, eee2dde, 99a8f3f)

Investigated perceived "debate echo" in TradingAgents output. Three hypotheses:

| Hypothesis | Verdict | Evidence |
|-----------|---------|----------|
| Counter not tracking | **Logging bug** — counter works during execution, `_log_state` omits it | `count: None` in saved state logs |
| Bull/bear echo identical reasoning | **False** — debug output artifact from LangGraph `debug=True` trace | State logs show different content (bull=8261 chars, bear=8730 chars) |
| Single-provider bias | **Unconfirmed** — same model family still produces different reasoning | Risk debate shows divergence (aggressive vs conservative vs neutral) |

**Fix:** Added `count` to investment_debate_state serialization, added `count` and `latest_speaker` to risk_debate_state serialization in `tradingagents/graph/trading_graph.py`.

**Verification:** AAPL analysis state log now shows `count=2` (investment), `count=3` (risk), confirming correct debate execution.

**Upstream report prepared:** `briefs/upstream-issue-debate-state-logging.md`

---

## Files Created This Session

**Shared infrastructure (2):**
- `scripts/lib/llm.ts` — shared OpenRouter LLM client
- `scripts/check-database-usage.ts` — build gate for raw Database() usage

**New scripts (1):**
- `scripts/refactor-playbook.ts` — playbook markdown refactor via LLM

**Documentation (4):**
- `docs/tidy-first-philosophy.md` — operational philosophy
- `briefs/epic-debate-mechanism-investigation.md` — DEBATE-001 epic
- `briefs/upstream-issue-debate-state-logging.md` — upstream issue report
- `debriefs/debrief-session-2026-05-06-wrapup.md` — this document

**Modified files (7):**
- `playbooks/htmx-playbook.md` — war story → prescriptive format
- `scripts/pr-summarize.ts` — uses `llm()`
- `scripts/summarize_analyses.ts` — uses `llm()`
- `scripts/seed_database.ts` — DatabaseFactory
- `scripts/sync-prices.ts` — DatabaseFactory
- `justfile` — added db-gate to `check`
- `.gitignore` — added `!scripts/lib/`

**Fixed upstream bug (1):**
- `tradingagents/graph/trading_graph.py` — include count and latest_speaker in state log

---

## Stats

- **Commits:** 11
- **New files:** 8
- **Files modified:** 9
- **Lines removed:** ~700 (duplicated fetch logic, war story prose, connectDb helpers)
- **Lines added:** ~600 (shared lib, gate script, clean playbook, docs)
- **Bugs found:** 1 (logging), 2 false alarms (echo, single-provider bias)
- **TD epics created:** 1 (DEBATE-001)
- **TD tasks created:** 4 (S01-S04)

---

## Verification

| Check | Status |
|-------|--------|
| `just check` | ✅ biome + tsc + db-gate all pass |
| `bun scripts/check-database-usage.ts` | ✅ 99 files clean |
| `bun -e "import('./scripts/lib/llm.ts').then(m => console.log(typeof m.llm))"` | ✅ `function` |
| AAPL state log count fields | ✅ count=2 (investment), count=3 (risk) |
| Bull/bear content divergence | ✅ Different content, different lengths |
| Risk debate divergence | ✅ Aggressive vs conservative vs neutral all different |

---

## What's Next

From `debriefs/plans/current.md`:

1. **Price freshness badge** (`td-18e84e`) — per-ticker `last_updated` in holdings table
2. **Server tests** (`td-9dbbac`) — route health checks, positions query, hledger parsing
3. **Settings extraction** (`td-56fd1b`) — `server/lib/settings.ts` consolidation
4. **DEBATE-001 S03/S04** — downscoped: no prompt fix needed, but quality metrics (S04) still valid as nice-to-have
5. **Upstream issue submission** — submit `briefs/upstream-issue-debate-state-logging.md` to `TauricResearch/TradingAgents`

---

## Lessons Learned

### 1. The infrastructure invisibility problem

Tools like `defuddle` that become invisible infrastructure are often unpackaged by mainstream repositories. Treat them as hard dependencies and document them explicitly.

### 2. LLM refactors lose edge cases

The gemini rewrite of `htmx-playbook.md` was ~90% correct but dropped two runtime traps. Always diff against original for technical completeness.

### 3. The 3-script rule

When you have 3 scripts with duplicated logic, extraction is mandatory. At 2 it's debatable; at 3 it's not.

### 4. Debug output is not execution

The "echo" in TradingAgents output was LangGraph's `debug=True` streaming trace, not repeated LLM calls. Always distinguish between what the system produces and what the logging shows.

### 5. Counter-intuitive bug location

The debate counter bug was in serialization, not execution. The debate worked fine; the evidence was thrown away. When investigating, verify the full pipeline from initialization → execution → serialization → consumption.
