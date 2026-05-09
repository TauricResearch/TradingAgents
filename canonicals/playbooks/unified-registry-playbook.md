# Unified Registry Playbook

Every document directory in the repository carries an `INDEX.jsonl` that
describes its contents. One schema, one set of tools, universal coverage.

## The Principle

**If it accumulates files, it gets an index.**

No directory should be a black box where only the author knows what's there
and what it means. The index is the single source of truth for:
- What files exist in the directory
- When they were created or last modified
- What state they are in
- What they are about

## Unified Schema

All indexes use the same JSONL structure:

```json
{
  "file": "filename.md",
  "date": "YYYY-MM-DD",
  "status": "done|open|accepted|canonical|active|...",
  "summary": "Human-readable description",
  "meta": { "registry-specific": "fields" }
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `file` | yes | Filename (no path), relative to the directory |
| `date` | yes | ISO date `YYYY-MM-DD` |
| `status` | yes | Registry-specific state |
| `summary` | yes | One-line description of the document |
| `meta` | no | Registry-specific data (epic, adr, session, type, topic, etc.) |

## Registry-Specific Mappings

| Registry | `status` values | `meta` fields | Index file |
|----------|----------------|---------------|------------|
| briefs | `done`, `open`, `in_progress` | `epic` | `briefs/INDEX.jsonl` |
| debriefs | `done` | `epic`, `adr`, `session` | `debriefs/INDEX.jsonl` |
| decisions | `Accepted`, `Proposed`, `Superseded` | `supersedes`, `superseded_by` | `decisions/INDEX.jsonl` |
| playbooks | `canonical`, `project` | `source`, `mining_candidate`, `mining_note`, `last_mined` | `playbooks/REGISTRY.jsonl` |
| canonicals | `canonical`, `draft`, `deprecated` | `source`, `mining_candidate`, `mining_note`, `last_mined` | `canonicals/INDEX.jsonl` |
| scripts | `portable`, `adaptable`, `project` | `lang` | `scripts/INDEX.jsonl` |
| docs | `active`, `archived`, `draft` | `type`, `topic` | `docs/INDEX.jsonl` |

## Tools

### Display: `reg-list.ts`

Human-readable listing with terminal-width wrapping:

```bash
bun scripts/reg-list.ts briefs
bun scripts/reg-list.ts debriefs
bun scripts/reg-list.ts decisions
bun scripts/reg-list.ts playbooks
bun scripts/reg-list.ts canonicals
bun scripts/reg-list.ts docs
```

Justfile shortcuts:

```bash
just reg-briefs
just reg-debriefs
just reg-decisions
just reg-canonicals
just reg-scripts
just reg-docs
```

### Mining: `reg-mine.ts`

Extract a proven project playbook to canonicals/ by stripping project-specific tokens:

```bash
bun scripts/reg-mine.ts lab-first-playbook.md        # dry run → stdout
bun scripts/reg-mine.ts lab-first-playbook.md --apply # write to canonicals/playbooks/
```

**What gets stripped:** `TradingAgents` → `<PROJECT>`, `src/server/` → `<SRC-SERVER>/`,
ticker symbols, session IDs, project env vars. Mining is stripping, not rewriting.

### Promotion Review: `reg-promote.ts`

Show what would be stripped before mining. Does not write unless `--apply`:

```bash
bun scripts/reg-promote.ts conventions-playbook.md       # summary of changes
bun scripts/reg-promote.ts conventions-playbook.md --diff # line-by-line diff
bun scripts/reg-promote.ts conventions-playbook.md --apply # delegate to reg-mine
```

### Import: `reg-import.ts`

Pull a canonical playbook into a new project:

```bash
bun scripts/reg-import.ts gum-playbook.md        # dry-run preview
bun scripts/reg-import.ts gum-playbook.md --apply # copy + register
```

Fails gracefully if playbook already exists.

### Script Registry: `reg-sync-scripts.ts`

Detect and index all scripts with portability classification:

```bash
bun scripts/reg-sync-scripts.ts        # check scripts/INDEX.jsonl
bun scripts/reg-sync-scripts.ts --fix  # regenerate
```

Portability levels:
- `portable` — No project dependencies (registry tools, `lib/`)
- `adaptable` — Minor project deps, easy to generalise
- `project` — TradingAgents-specific (lab, trading, IG, etc.)

### Validation: `reg-check.ts`

Schema validation — ensures all entries have required fields:

```bash
bun scripts/reg-check.ts          # all registries
bun scripts/reg-check.ts briefs   # single registry
```

Run as part of `just check` (commit gate).

### Sync Check: `reg-sync.ts`

Detects drift between filesystem and index:

```bash
bun scripts/reg-sync.ts --all          # check all indexes
bun scripts/reg-sync.ts briefs         # check single index
bun scripts/reg-sync.ts --all --fix    # regenerate stale indexes
```

Reports:
- **MISSING** — files on disk not in the index (need to be added)
- **STALE** — entries in index for files that no longer exist

Run as part of `just check` (commit gate).

### Migration: `reg-migrate.ts`

One-time migration tool for converting legacy schemas to unified:

```bash
bun scripts/reg-migrate.ts --dry-run   # preview
bun scripts/reg-migrate.ts --apply     # execute (creates .backup files)
```

## Adding a New Registry

1. Create `NEWTYPE/INDEX.jsonl` with unified schema entries
2. Add to `scripts/reg-check.ts` `REGISTRIES` map
3. Add to `scripts/reg-list.ts` `FILE_MAP`
4. Add to `scripts/reg-sync.ts` `REGISTRIES` map
5. Add just recipes:
   ```just
   reg-newtype:
       bun scripts/reg-list.ts newtype
   ```
6. Document in this playbook

## Commit Gate Integration

`just check` includes:

1. `bunx biome check .` — lint/format
2. `tsc --project tsconfig.server.json --noEmit` — type check
3. `bun scripts/check-database-usage.ts` — no raw Database() instances
4. `bun scripts/reg-sync.ts --all` — document indexes up to date
5. `bun scripts/reg-sync-scripts.ts` — script index up to date

All must pass before commit.

## Conventions

### Index File Naming

- Default: `INDEX.jsonl`
- Exception: `playbooks/REGISTRY.jsonl` (historical, accepted)

### Date Semantics

- For new files: creation date
- For modified files: last meaningful update (not auto-format)
- Use `date` from `git log -1 --format=%ad --date=short <file>` when in doubt

### Status Values

Use lowercase for most statuses (`done`, `open`, `active`).
Exception: decisions use title case (`Accepted`, `Proposed`, `Superseded`)
to match ADR convention.

### Summary Style

- Imperative mood: "Replace ASCII diagrams with DOT" not "Replaced..."
- One sentence, no period
- Specific enough to distinguish from other entries

### Meta Field Usage

Put registry-specific data in `meta`, not at top level. This keeps the
schema uniform and tools generic.

## War Story: Why Four Schemas Became One

Originally each document type invented its own index format:

- briefs: `{ file, status, date, summary, epic }`
- debriefs: `{ file, date, decision, epic, adr, session }`
- decisions: `{ file, date, status, summary, supersedes }`
- playbooks: `{ file, canonical, covers, mining_candidate }`

This required `reg-list.ts` to carry a switch statement with four branches
and `reg-check.ts` to validate four different schemas. Adding a fifth
document type meant inventing a fifth schema and adding a fifth branch
to every tool.

The unified schema eliminated all special cases. One format function,
one validation schema, one sync check. New registries slot in without
modifying tool code.

## Failure Mode: Index Rot

Without `reg-sync`, indexes silently drift from the filesystem. Files get
added, deleted, renamed. The index becomes a lie that misleads agents and
humans alike.

The fix is mechanical: run `just reg-sync` periodically. It reports
drift in seconds. Fix with `--fix` or manually. No guesswork.
