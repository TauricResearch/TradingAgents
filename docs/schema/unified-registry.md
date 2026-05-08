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
