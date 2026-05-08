# Debrief: Silo Infrastructure Session (2026-05-08)

**Date**: 2026-05-08
**Session**: ses_f5f225
**Scope**: Unified registry system, conceptual lexicon, barnacle detection,
justfile facade, silo template, CTX lexicon integration

---

## What We Built

### 1. Unified Registry System

Every document directory in the silo carries an `INDEX.jsonl` that describes
its contents. One schema, one set of tools, universal coverage.

**Schema**: `{ file, date, status, summary, meta? }`

**Directories indexed**:
- `briefs/` — work proposals
- `debriefs/` — post-work retrospectives
- `decisions/` — architecture decision records
- `playbooks/` — reusable conventions
- `docs/` — project documentation

**Tools**:
- `reg-list.ts` — human-readable display (wraps to terminal width)
- `reg-check.ts` — schema validation (required fields)
- `reg-sync.ts` — detect drift between filesystem and index (MISSING, STALE)
- `reg-migrate.ts` — one-time legacy-to-unified migration
- `reg-state.ts` — consolidated project state across all compartments

**Commit gate**: `just check` now includes `reg-sync.ts --all` as the 4th
check (after biome, tsc, db-usage).

### 2. Conceptual Lexicon (v2 Merged Schema)

`silo-conceptual-lexicon.jsonl` at root level — unmissable, same tier as
`justfile` and `AGENTS.md`.

**19 entries** covering the silo's operational vocabulary:

| ID | Term | Type | Status |
|----|------|------|--------|
| oh-001 | barnacle | operational-heuristic | active |
| term-002 | silo | pattern | active |
| term-003 | facade | pattern | active |
| oh-004 | lab-first | operational-heuristic | active |
| oh-005 | scrape | operational-heuristic | active |
| oh-006 | extract-before-move | operational-heuristic | active |
| oh-007 | fail-fast | operational-heuristic | active |
| oh-008 | index-rot | operational-heuristic | active |
| term-009 | unified-schema | pattern | active |
| term-010 | conceptual-entropy | term | draft |
| term-011 | mentation | term | draft |
| term-012 | impartial-spectator | term | draft |
| oh-013 | factored-design | operational-heuristic | active |
| oh-014 | optimal-simplicity | operational-heuristic | active |
| oh-015 | fast-slow-thinking | operational-heuristic | active |
| oh-016 | console-first-validation | operational-heuristic | active |
| oh-017 | tase-mandate | operational-heuristic | active |
| oh-018 | data-first-diagnostics | operational-heuristic | active |
| oh-019 | exploratory-programming | operational-heuristic | active |

**v2 merged schema** combines our unified structure with CTX's tag taxonomy:
- Stable IDs (`term-001`, `oh-058`)
- Type discrimination (`term`, `operational-heuristic`, `pattern`, `failure-mode`, `philosophy`)
- Structured tags (`[Implements: COG-5]`, `[Guided_By: ADV-8]`, `[Substrate_Issue: Biddability]`, `[Quality: silver]`)
- Heuristic field (condensed actionable rule)
- Usage field (example sentence)
- Coined_by attribution (`human` or `agent`)

### 3. CTX Lexicon Integration

Converted CTX conceptual lexicon (161 entries) from JSON array to JSONL
with merged schema. 7 silo-relevant terms incorporated into the silo
lexicon with silo-specific heuristics and usage.

- `debriefs/lexicon-ctx.jsonl` — 161 converted CTX entries
- `scripts/ctx-lexicon-convert.ts` — conversion tool

### 4. Barnacle Detection

`scripts/barnacle-scan.ts` — two-phase scan for stale conventions:

**Mechanical checks**:
- Capitalized `Justfile` alongside `justfile`
- Stale path references (`server/` vs `src/server/`)
- Unused justfile recipes
- Stale playbooks (>30 days)
- Missing doc indexes

**LLM semantic analysis** (Gemini 2.5 Flash via OpenRouter):
- Reads conventions-playbook.md + AGENTS.md + justfile + selected playbooks
- Identifies contradictions, tool-fighting conventions, obsolete justifications
- Returns structured JSON: `{ severity, location, description, fix }`

**Justfile recipe**: `just barnacle-scan`
**Watcher**: `just barnacle-watch MINUTES=60`

### 5. Justfile Facade Refactoring

- Extracted 12-line inline bash `push` recipe → `scripts/push-with-diagrams.ts`
- Extracted 4-line inline jq `reg-check` recipe → `scripts/reg-check.ts`
- Added `[doc("...")]` attributes to 5 key recipes
- Replaced overflowing `column -t` tables with human-readable `reg-list.ts`
- Added `reg-sync`, `reg-sync-fix`, `reg-docs`, `reg-state`, `reg-lexicon`,
  `reg-lexicon-ctx`, `barnacle-scan`, `barnacle-watch` recipes
- Added group navigation shortcuts: `just b`, `just d`, `just db`, `just gn`, etc.

### 6. Silo Template

Canonical directory structure with named compartments:

```
silo/
├── briefs/              # Work proposals (INDEX.jsonl)
├── debriefs/            # Retrospectives (INDEX.jsonl)
├── decisions/           # ADRs (INDEX.jsonl)
├── playbooks/           # Conventions (REGISTRY.jsonl)
├── docs/                # Documentation (INDEX.jsonl)
├── scripts/             # Automation
│   ├── lib/             # Shared modules
│   └── lab/             # Experiments
├── src/                 # Source code
│   ├── cli/
│   ├── lib/
│   └── server/
├── tests/
├── backups/
├── archive/
├── silo-conceptual-lexicon.jsonl  # ← vocabulary
├── justfile             # Facade
└── ...
```

**Documents**:
- `briefs/2026-05-08-brief-just-silo-template.md`
- `playbooks/just-silo-playbook.md`
- `docs/just-silo-manifest.md`
- `docs/diagrams/silo-structure.svg`
- `docs/diagrams/just-silo.svg`

### 7. Playbooks Written/Updated

- `unified-registry-playbook.md` — schema, tools, sync, commit gate
- `just-silo-playbook.md` — directory structure, facade conventions, lexicon
- `conventions-playbook.md` — barnacle definition and removal record
- `ci-cd-playbook.md` — pre-push hooks, diagram regeneration
- `lab-first-playbook.md` — experiments before production
- `services-playbook.md` — PID file protocol, log rotation
- `gum-playbook.md` — terminal formatting
- `gitnexus-playbook.md` — graph visualization
- `gitnexus-usage-guide.md` — practical commands

---

## How It Helps in a New Repo

### Greenfield Project

**Day 1**:
```bash
# Copy the silo template
mkdir new-project && cd new-project
# Copy: briefs/, debriefs/, decisions/, playbooks/, docs/, scripts/, src/, tests/
# Copy: justfile, package.json, tsconfig.json, AGENTS.md
# Create: silo-conceptual-lexicon.jsonl with starter terms
```

**Day 2**:
```bash
just help      # orient
just check     # verify gates pass
just reg-sync  # verify indexes match filesystem
```

**Day 3+**:
- Briefs for features go in `briefs/`, auto-indexed
- Debriefs for completed work go in `debriefs/`, auto-indexed
- Decisions for architectural choices go in `decisions/`, auto-indexed
- Conventions that generalize go in `playbooks/`, marked `canonical: true`
- Terms that recur go in `silo-conceptual-lexicon.jsonl`

**Benefits**:
- No undifferentiated blob. Every file has a home.
- `just reg-state` shows project health at a glance.
- `just barnacle-scan` catches convention drift before it costs hours.
- `just check` enforces quality before every commit.

### Brownfield Project

**Phase 0: Extract**
```bash
# Identify the "stuff" — scattered documents, accumulated conventions
# Create document compartments
mkdir briefs debriefs decisions playbooks docs
# Move existing documents into appropriate compartments
# Create indexes with reg-sync --fix
```

**Phase 1: Structure**
```bash
# Restructure justfile into [group("...")] silos
# Add navigation shortcuts
# Extract inline bash to scripts/
# Wire just check to run quality gates + registry sync
```

**Phase 2: Lexicon**
```bash
# Read existing docs, extract recurring terms
# Add to silo-conceptual-lexicon.jsonl
# Link terms with [Related: ...] tags
# Now agents can reference stable IDs instead of guessing
```

**Phase 3: Barnacle Hunt**
```bash
just barnacle-scan
# Fix critical findings
# Document removals in debriefs/
# Update conventions-playbook.md with removal record
```

**Benefits**:
- No "where does this go?" ambiguity.
- No "what did we call that thing?" ambiguity.
- Existing code stays untouched during restructure.
- New conventions slot into the silo without reorganization.

### Integration Project (Existing + New System)

**The Problem**: Two codebases with different conventions. Agents get confused.

**The Solution**: Each codebase is its own silo. The silo template provides
a common interface:

```bash
# Silo A (existing system)
cd system-a
just reg-state     # 14 briefs, 3 in-progress tasks, 2 barnacles
just barnacle-scan # find stale conventions

# Silo B (new integration)
cd system-b
just reg-state     # 2 briefs, 1 open task, clean
just check         # all gates pass
```

**Cross-silo vocabulary**: Both silos share the same conceptual lexicon
schema. Terms coined in Silo A can be `[Related: ...]` in Silo B.

**Benefits**:
- Common interface across disparate codebases.
- Agents orient in seconds (`just help`, `just info`).
- Barnacles caught before they propagate across system boundaries.

---

## Benefits for Agents

### 1. Orientation Speed

**Before**: Agent reads 683-line justfile, 12 playbooks, scattered docs.
Takes 10+ minutes to understand where things live.

**After**: Agent runs `just help`, `just info`, `just reg-state`. Knows
the project state in 30 seconds. Knows where to look for anything.

### 2. Stable References

**Before**: "Use the thing where we check for problems before they happen"
— ambiguous, refers to nothing stable.

**After**: "Run `just barnacle-scan` per `oh-001`" — unambiguous, links
to definition, heuristic, and usage.

### 3. Error Prevention

**Before**: Agent adds a file but forgets the index. Index rots silently.
Next agent thinks the file doesn't exist.

**After**: `just check` fails with `reg-sync --all` reporting MISSING.
Agent fixes before commit.

### 4. Convention Evolution

**Before**: New convention invented in chat, dies in chat. Next agent
reinvents it.

**After**: New term added to `silo-conceptual-lexicon.jsonl` with
`status: draft`. After use in 2+ documents, upgraded to `active`. Now
it's durable, referenceable, searchable.

### 5. Cross-Project Transfer

**Before**: Agent works on Project A, learns conventions, moves to Project B.
Conventions differ subtly. Agent makes wrong assumptions.

**After**: Both projects are silos. Both have `silo-conceptual-lexicon.jsonl`.
Agent reads the lexicon first. Knows which terms are shared (`barnacle`,
`facade`) and which are project-specific.

---

## Benefits for Humans

### 1. Project State at a Glance

```bash
just reg-state
# BRIEFS: 17 (16 done | 1 open)
# DEBRIEFS: 28 (25 done | 3 active)
# TASKS: 2 open | 3 in_progress | 1 reviewable
# HEALTH: ✓ all indexes match filesystem
```

No clicking through Jira, no reading Slack scrollback. One command.

### 2. Convention Justification

**Before**: "Why do we do it this way?" → "I don't know, it's always been
like that."

**After**: `just reg-lexicon` → `oh-001 barnacle` → heuristic: "If a
convention fights the tool default, suspect it." Origin: conventions-playbook.
Now there's a living justification.

### 3. Onboarding Speed

**Before**: New team member reads README, gets confused, asks 20 questions.

**After**: New team member runs `just help`, `just reg-lexicon`, reads
`silo-conceptual-lexicon.jsonl`. Knows the vocabulary in 5 minutes.

### 4. Post-Mortem Material

Every completed brief has a debrief. Every debrief is indexed. Retrospectives
are searchable by date, epic, or decision. No knowledge lost in chat history.

### 5. Barnacle Removal as Ritual

Stale conventions are surfaced mechanically. Removing them is documented
(`scrape` verb, removal record in conventions-playbook). The silo gets
*lighter* over time, not heavier.

---

## The Core Insight

**A silo is not a directory structure. It is a cognitive prosthetic.**

The directory structure is the hardware. The registry system, the conceptual
lexicon, the barnacle scanner, the commit gate — these are the software that
runs on top. Together they create a **self-documenting, self-validating,
self-healing project context**.

An agent entering a silo does not need to be told "where things live" or
"what words mean". The silo tells them. The agent's job shifts from
*orientation* to *execution*.

A human managing a silo does not need to remember what is in flight, what
conventions are active, or what needs cleaning up. The silo reports it.
The human's job shifts from *tracking* to *deciding*.

The silo template is the **minimum viable infrastructure** for this. Every
project should be a silo. Every silo should have a lexicon. Every lexicon
should be at root level, unmissable, canonical.

---

## Files Created/Modified (Session)

| File | What |
|------|------|
| `silo-conceptual-lexicon.jsonl` | 19-term conceptual vocabulary (canonical path) |
| `debriefs/lexicon-ctx.jsonl` | 161-term CTX lexicon (converted) |
| `scripts/reg-list.ts` | Human-readable registry display |
| `scripts/reg-check.ts` | Schema validation |
| `scripts/reg-sync.ts` | Staleness detection (MISSING/STALE) |
| `scripts/reg-migrate.ts` | Legacy-to-unified migration |
| `scripts/reg-state.ts` | Consolidated project state |
| `scripts/barnacle-scan.ts` | Stale convention detection |
| `scripts/ctx-lexicon-convert.ts` | CTX lexicon conversion |
| `scripts/lexicon-migrate.ts` | Lexicon v1→v2 migration |
| `scripts/push-with-diagrams.ts` | Pre-push diagram regen |
| `justfile` | Facade with extracted scripts, [doc()], nav shortcuts |
| `AGENTS.md` | Updated with lexicon as primary resource |
| `playbooks/just-silo-playbook.md` | Silo template with lexicon convention |
| `playbooks/unified-registry-playbook.md` | Registry system documentation |
| `docs/schema/unified-registry.md` | Schema spec + tag taxonomy |
| `briefs/2026-05-08-brief-ctx-lexicon-upgrade.md` | CTX upgrade brief |
| `briefs/2026-05-08-brief-just-silo-template.md` | Silo template brief |
| `docs/just-silo-manifest.md` | Concise silo manifest |
| `docs/diagrams/silo-structure.svg` | Directory compartment graph |
| `docs/diagrams/just-silo.svg` | Justfile group graph |
