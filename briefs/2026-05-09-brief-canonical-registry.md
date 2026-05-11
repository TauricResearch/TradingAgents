# Brief: Canonical Registry Framework

**Date:** 2026-05-09
**Author:** ses_0dd889
**Status:** Superseded
**Priority:** P2
**Type:** Epic (multi-story)

---

## Problem

The playbook registry is a classification system, not a distribution system.
It can label a playbook "canonical" but cannot extract, share, or import it.
There is no mechanism to:
- Strip project-specific content from a proven playbook
- Pull a canonical playbook into a new project
- Submit a project playbook back when it proves its worth
- Index reusable scripts

**Current state (quantified):**
- 29 total playbooks
- 15 marked "canonical" but never extracted from project context
- 8 flagged `mining_candidate=true` but `last_mined: null`
- 0 scripts indexed for reuse
- 0 extraction or import mechanisms exist

## Vision

A two-way membrane between project-specific knowledge and portable patterns:

```
Project                          Canonical Registry
───────                          ──────────────────
playbooks/ (project-specific)    canonicals/
  ┌──────────┐                     ┌────────────┐
  │ lab-first  │  ──reg-mine──►    │ lab-first   │
  │ (proven)   │   (strip detail)  │ (generic)   │
  └──────────┘                     └────────────┘
  ┌──────────┐                     ┌────────────┐
  │ htmx     │  ◄──reg-import──    │ htmx        │
  │ (new)    │   (pull generic)    │ (updated)   │
  └──────────┘                     └────────────┘
```

## Design Principles

1. **Backward compatibility.** Existing `reg-check.ts`, `reg-sync.ts`, `reg-list.ts`
   continue working against `playbooks/REGISTRY.jsonl`. No breaking changes.

2. **Same schema, separate index.** `canonicals/` uses the unified JSONL schema
   with its own `INDEX.jsonl`. Status values: `canonical`, `draft`, `deprecated`.

3. **Move, don't duplicate.** The 15 existing canonical playbooks that are already
   clean move to `canonicals/playbooks/`. They are removed from `playbooks/`.
   `playbooks/` becomes project-only.

4. **Mining is stripping, not rewriting.** The `reg-mine.ts` tool removes
   project-specific examples and paths. It does not rewrite the playbook.

5. **Scripts are first-class.** `canonicals/scripts/` holds reusable scripts with
   project-agnostic interfaces.

6. **Destination: just-silo.** The canonical registry framework (tools, schema,
   conventions) is designed for lift-and-shift to the `just-silo` canonical
   template project. TradingAgents is the proving ground.

## Proposed Directory Structure

```
canonicals/
  playbooks/          # Generic playbooks (15 moved from playbooks/)
  scripts/            # Reusable scripts (indexed)
  templates/          # Project scaffolding templates
  INDEX.jsonl         # Canonical registry index
  README.md           # How to adopt, how to contribute
```

## Stories

### S01: Create canonicals/ directory and seed with existing canonical playbooks

Move the 15 playbooks already marked `status: canonical` from `playbooks/` to
`canonicals/playbooks/`. Update `playbooks/REGISTRY.jsonl` to remove them.
Create `canonicals/INDEX.jsonl` with unified schema entries.

**Acceptance:**
- `canonicals/playbooks/` contains 15 clean playbooks
- `playbooks/REGISTRY.jsonl` has 14 entries (project-only)
- `canonicals/INDEX.jsonl` exists and passes `reg-check.ts`
- `just check` is green

### S02: Build reg-mine.ts — extraction mechanism

Given a `playbooks/<file>` with `mining_candidate: true`, produce a clean
`canonicals/playbooks/<file>` by stripping project-specific content.

**What gets stripped:**
- TradingAgents-specific paths (`src/server/`, `tradingagents/`)
- Ticker references (AAPL, TKA.DE)
- Project-specific environment variables
- Ephemeral dates and session IDs
- Internal just recipe names

**What stays:**
- The pattern/convention/heuristic itself
- Generic examples (replace AAPL with `<TICKER>`)
- Tool-agnostic explanations

**Acceptance:**
- `bun scripts/reg-mine.ts lab-first-playbook.md` produces clean output
- Output is valid markdown with no TradingAgents-specific paths
- Can be run in dry-run mode (shows diff without writing)

### S03: Build reg-import.ts — import mechanism

Pull a canonical playbook into the current project's `playbooks/` directory,
marking it as `status: canonical` in `playbooks/REGISTRY.jsonl`.

**Acceptance:**
- `bun scripts/reg-import.ts gum-playbook.md` copies from `canonicals/` to `playbooks/`
- Adds entry to `playbooks/REGISTRY.jsonl` with `source: canonical`
- Fails gracefully if playbook already exists in project

### S04: Build reg-promote.ts — feedback mechanism

Given a project playbook, show what would be stripped to make it canonical.
Does not write to `canonicals/` — produces a diff for human review.

**Acceptance:**
- `bun scripts/reg-promote.ts lab-first-playbook.md` shows project-specific content
- Outputs a diff with `--diff` flag
- With `--apply`, writes to `canonicals/playbooks/` and updates `last_mined`

### S05: Script registry — index reusable scripts

Create `scripts/INDEX.jsonl` (or `canonicals/scripts/INDEX.jsonl`) that indexes
scripts by portability level.

**Portability levels:**
- `portable` — No project dependencies (e.g. `lib/gum.ts`, `reg-check.ts`)
- `adaptable` — Minor project deps, easy to generalise (e.g. `barnacle-scan.ts`)
- `project` — Project-specific (e.g. `seed_database.ts`, `get_price.ts`)

**Acceptance:**
- Script registry exists with unified schema
- `reg-sync-scripts.ts` detects new scripts and prompts for portability level
- Reusable scripts can be imported into `canonicals/scripts/`

### S06: Documentation and just recipes

- Add `just reg-mine`, `just reg-import`, `just reg-promote`, `just reg-canonicals`
- Update `playbooks-playbook.md` with new registry concept
- Update `unified-registry-playbook.md` with canonical directory rules

## Failure Modes to Avoid

| Failure | Prevention |
|---------|-----------|
| Breaking existing reg-check/reg-sync | Keep `playbooks/REGISTRY.jsonl` as primary index; canonicals/ is separate |
| Duplicating playbooks | Move canonicals out of playbooks/, don't copy |
| Mining produces broken playbooks | Dry-run mode mandatory; diff review before apply |
| Script registry becomes unmaintained | Make it part of `just check` (warn on un-indexed scripts) |
| Canonicals/ becomes a dumping ground | Require `reg-promote` review; no direct commits to canonicals/ |

## The Lift-and-Shift Test

The ultimate validation of this registry is a lift-and-shift to `just-silo`,
the canonical silo template project. If the registry mechanism cannot export
itself, it is not a real registry — it is a local convention pretending to be
portable.

**What moves to just-silo:**
- Unified JSONL schema and registry concept (unified-registry-playbook.md)
- Core registry tools: reg-check.ts, reg-sync.ts, reg-list.ts (project-agnostic logic)
- The canonical/portable distinction and mining/promotion workflow
- The script registry concept (portability levels)

**What stays in TradingAgents:**
- TradingAgents-specific playbook content (examples, paths, tickers)
- Project-specific scripts (seed_database.ts, get_price.ts)
- The actual canonical playbooks themselves (briefs-playbook, debriefs-playbook, etc.)

**Why this matters for design:**
- Registry tools must not hardcode "playbooks" or "TradingAgents" — they take a directory path
- The unified schema must be truly generic — no registry-specific required fields
- `reg-import.ts` must work against any project with a unified-schema INDEX.jsonl
- The lift-and-shift is not a later task — it is the validation mechanism

## Non-Goals

- External registry (separate repo) — out of scope for this epic; lift-and-shift is a follow-up
- Automated mining (no human review) — the diff must be reviewed
- Versioning within canonicals/ — use git history
- Cross-project sync — manual import/export for now

## Success Criteria

1. `canonicals/` exists with 15+ clean playbooks
2. `reg-mine.ts`, `reg-import.ts`, `reg-promote.ts` all functional
3. Script registry indexes all scripts with portability levels
4. `just check` includes canonical index validation
5. No regression in existing registry tools
6. **Tools are project-agnostic** — no hardcoded "TradingAgents" or "playbooks" paths; accept directory arguments

## Follow-Up Epic

**LIFT-AND-SHIFT-001:** Move canonical registry framework from TradingAgents to just-silo
- Extract registry tools and schema to just-silo repo
- Validate reg-import.ts works in a fresh just-silo project
- Update just-silo documentation with registry adoption guide

## Related

- `playbooks/unified-registry-playbook.md` — existing registry system
- `playbooks/playbooks-playbook.md` — meta-playbook about playbooks
- `playbooks/just-silo-playbook.md` — the silo template that is the destination
- `silo-conceptual-lexicon.jsonl` — terms: `barnacle`, `index-rot`, `silo`, `facade`

---

**Superseded:** 2026-05-11 — see `decisions/008-defuddle-web-content.md` for analogous pattern.

The canonicals/ directory approach was abandoned in favor of a simpler model:
- All playbooks live in `playbooks/`
- The registry tracks source (project vs. external) via `meta.source` field
- When submitting to an external registry, the registry owns the canonical version
- The project does not maintain a parallel canonical store

`canonicals/` was removed. Playbooks were merged back into `playbooks/`.
Registry scripts (reg-mine.ts, reg-import.ts, reg-promote.ts) updated to reference `playbooks/` instead of `canonicals/`.
