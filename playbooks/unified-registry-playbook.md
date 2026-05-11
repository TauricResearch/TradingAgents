---
date: 2026-05-08
updated: 2026-05-11
tags:
  - playbook
  - registry
  - meta
  - documentation
agent: antigravity
environment: local
---

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
| docs | `active`, `archived`, `draft` | `type`, `topic` | `docs/INDEX.jsonl` |

> **2026-05-11:** The `canonicals/` directory was removed. Playbooks live in `playbooks/` only.
> The registry tracks `meta.source` to indicate origin. External registries own canonical versions.

## Tools

### Display: `reg-list.ts`

Human-readable listing with terminal-width wrapping:

```bash
bun scripts/reg-list.ts briefs
bun scripts/reg-list.ts debriefs
bun scripts/reg-list.ts decisions
bun scripts/reg-list.ts playbooks
bun scripts/reg-list.ts docs
```

Justfile shortcuts:

```bash
just reg-briefs
just reg-debriefs
just reg-decisions
just reg-scripts
just reg-docs
```

### Mining: `reg-mine.ts`

Extract project-specific tokens to produce a cleaner, more portable version.
Writes to `playbooks/` and updates `last_mined` in the registry.

```bash
bun scripts/reg-mine.ts lab-first-playbook.md        # dry run → stdout
bun scripts/reg-mine.ts lab-first-playbook.md --apply # write to playbooks/
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

Pull a playbook from another source into `playbooks/`:

```bash
bun scripts/reg-import.ts gum-playbook.md        # dry-run preview
bun scripts/reg-import.ts gum-playbook.md --apply # copy + register
```

Fails gracefully if playbook already exists.

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

## Commit Gate Integration

`just check` includes:

1. `bunx biome check .` — lint/format
2. `tsc --project tsconfig.server.json --noEmit` — type check
3. `bun scripts/check-database-usage.ts` — no raw Database() instances
4. `bun scripts/reg-sync.ts --all` — document indexes up to date

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