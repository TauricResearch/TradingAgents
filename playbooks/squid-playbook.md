# SQUID — Registry and Concept Lexicon CRUD

SQUID provides unified Create/Read/Update/Delete operations for all registries and the conceptual lexicon.

## Operations

| Op | What it does |
|----|--------------|
| `save` | Upsert — create if not exists, update if exists |
| `query` | Search/filter entries (read-only) |
| `insert` | Strict create — fails if entry already exists |
| `delete` | Remove entry — fails if not found |

## Registries

All registries share one schema:

```
file    string   — filename (unique per registry)
date    string   — ISO date (YYYY-MM-DD)
status  enum     — open | done | active | closed | wontfix
summary string   — human-readable description
meta    object   — optional arbitrary metadata
```

**Registry** = one of: `briefs`, `debriefs`, `decisions`, `playbooks`, `docs`

## Conceptual Lexicon

The conceptual lexicon has a separate schema:

```
slug         string   — unique identifier (kebab-case)
term         string   — display name
type         enum     — concept | operational-heuristic | anti-pattern | principle | pattern
heuristic    string   — decision guidance (one-liner)
usage        string   — when to use this term
coined_by?   string   — optional attribution
status       enum     — active | deprecated | draft
```

## Usage

### Registry operations

```bash
# Query — list all entries, optionally filtered
just squid briefs query
just squid debriefs query --status active
just squid debriefs query --status done

# Query — single entry
just squid debriefs query debrief-silo-sandbox-2026-05-11.md

# Save — upsert (create or update)
just squid debriefs save debrief-foo.md --status done --summary "Something done"

# Insert — strict create (fails if duplicate)
just squid briefs insert --file 2026-05-12-brief-new-work.md \
  --date 2026-05-12 \
  --status open \
  --summary "Brief description"

# Delete — remove entry (fails if not found)
just squid debriefs delete old-debrief.md
```

### Conceptual lexicon operations

```bash
# Query — list all terms
just squid ctx query

# Query — filtered
just squid ctx query --type operational-heuristic
just squid ctx query --status active

# Query — single term
just squid ctx query godelian-humility

# Save — upsert
just squid ctx save godelian-humility --status deprecated

# Insert — strict create
just squid ctx insert --slug new-term --term "New Term" \
  --type concept \
  --heuristic "Think carefully" \
  --usage "Use when..."

# Delete — remove term
just squid ctx delete old-term
```

## Safety

All write operations (`save`, `insert`, `delete`) require `--dry-run` to preview before executing.

```bash
# Preview what would happen
just squid debriefs save debrief-foo.md --status done --dry-run

# Execute
just squid debriefs save debrief-foo.md --status done
```

After every write, the file is re-parsed to confirm valid JSONL before the operation completes.

## Index files

Registry index files:
- `briefs/INDEX.jsonl`
- `debriefs/INDEX.jsonl`
- `decisions/INDEX.jsonl`
- `playbooks/REGISTRY.jsonl`
- `docs/INDEX.jsonl`

Conceptual lexicon:
- `silo-conceptual-lexicon.jsonl`

## Implementation

- `scripts/lib/registry-types.ts` — shared Zod schemas
- `scripts/reg-crud.ts` — registry operations
- `scripts/ctx-crud.ts` — conceptual lexicon operations
- `Justfile.squid` — experimental justfile with SQUID verbs