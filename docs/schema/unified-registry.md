# Unified Registry Schema

All document indexes use a single JSONL schema. No registry-specific fields
at the top level — only a common structure with an optional `meta` bag for
registry-specific data.

## Schema

```json
{
  "file": "filename.md",
  "date": "YYYY-MM-DD",
  "status": "done|open|accepted|canonical|project|...",
  "summary": "Human-readable description",
  "tags": ["tag1", "tag2"],
  "meta": {
    "registry-specific": "fields go here"
  }
}
```

## Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `file` | string | Filename (no path) |
| `date` | string | ISO date `YYYY-MM-DD` |
| `status` | string | Registry-specific state |
| `summary` | string | One-line description |

## Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `tags` | string[] | Cross-cutting categories |
| `meta` | object | Registry-specific data (epic, adr, session, etc.) |

## Registry Mappings

| Registry | `status` values | `meta` fields |
|----------|----------------|---------------|
| briefs | `done`, `open`, `in_progress` | `epic` |
| debriefs | `done` | `epic`, `adr`, `session` |
| decisions | `Accepted`, `Proposed`, `Superseded` | `supersedes`, `superseded_by` |
| playbooks | `canonical`, `project` | `source`, `mining_candidate`, `mining_note`, `last_mined` |
| docs | `active`, `archived`, `draft` | `type`, `topic` |
| lexicon | `active`, `draft` | `category`, `heuristic`, `usage`, `tags`, `related`, `coined_by` |

## Validation

```bash
# All registries
bun scripts/reg-check.ts

# Single registry
bun scripts/reg-check.ts briefs
```

## Sync Check

Detect missing or stale entries:

```bash
# Check all indexes against filesystem
bun scripts/reg-sync.ts --all

# Fix stale/missing entries (regenerate from disk)
bun scripts/reg-sync.ts --all --fix
```

## Display

```bash
# Human-readable list
bun scripts/reg-list.ts briefs
bun scripts/reg-list.ts debriefs
bun scripts/reg-list.ts decisions
bun scripts/reg-list.ts playbooks
```

## Lexicon Schema (v2 — Merged with CTX)

The lexicon uses an extended schema that merges our unified structure with
CTX's tag taxonomy:

```json
{
  "file": "barnacle",
  "id": "oh-001",
  "date": "2026-05-08",
  "status": "active",
  "type": "operational-heuristic",
  "summary": "A convention without living justification...",
  "meta": {
    "category": "process",
    "origin": "playbooks/conventions-playbook.md",
    "heuristic": "If a convention fights the tool default, suspect it.",
    "usage": "The capitalized Justfile rule is a barnacle.",
    "tags": [
      "[#process]",
      "[Quality: silver]",
      "[Related: convention]",
      "[Origin: playbooks/conventions-playbook.md]"
    ],
    "related": ["convention", "friction", "scrape"],
    "coined_by": "agent"
  }
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `file` | yes | Human-readable term identifier |
| `id` | yes | Stable machine ID (`term-001`, `oh-058`) |
| `date` | yes | ISO date |
| `status` | yes | `active`, `draft` |
| `type` | yes | `term`, `operational-heuristic`, `pattern`, `failure-mode`, `philosophy` |
| `summary` | yes | Definition |
| `meta.category` | yes | Semantic category |
| `meta.heuristic` | yes | Condensed actionable rule |
| `meta.usage` | yes | Example sentence |
| `meta.tags` | yes | Structured bracket notation (see below) |
| `meta.related` | yes | Related term identifiers |
| `meta.coined_by` | yes | `human` or `agent` |

### Tag Taxonomy (Bracket Notation)

| Prefix | Example | Meaning |
|--------|---------|---------|
| `[#category]` | `[#process]` | Semantic category |
| `[Quality: level]` | `[Quality: silver]` | Maturity: bronze / silver / gold |
| `[Related: term]` | `[Related: silo]` | Bidirectional link to related term |
| `[Origin: source]` | `[Origin: playbook.md]` | Source document |
| `[Guided_By: term]` | `[Guided_By: fail-fast]` | This term is guided by that principle |
| `[Implements: term]` | `[Implements: PHI-2]` | This implements that protocol |
| `[Substrate_Issue: mode]` | `[Substrate_Issue: Biddability]` | Addresses this failure mode |

## Adding a New Registry

1. Create `NEWTYPE/INDEX.jsonl`
2. Use unified schema: `{ file, date, status, summary, meta? }`
3. Add to `scripts/reg-check.ts` `REGISTRIES` map
4. Add to `scripts/reg-list.ts` `FILE_MAP`
5. Add to `scripts/reg-sync.ts` `REGISTRIES` map
6. Add just recipes:
   ```just
   reg-newtype: bun scripts/reg-list.ts newtype
   ```

No special-case formatting. No custom validation rules.
