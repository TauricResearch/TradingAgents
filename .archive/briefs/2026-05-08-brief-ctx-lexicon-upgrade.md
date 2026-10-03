# Brief: CTX Conceptual Lexicon Upgrade

**Date**: 2026-05-08
**Status**: Closed — implemented in `debriefs/lexicon-ctx.jsonl`, `silo-conceptual-lexicon.jsonl`
**Epic**: UNIFIED-CLI-001

## Problem

The CTX conceptual lexicon (`docs/conceptual-lexicon-example.json`) has grown
to ~130 entries over months of use. It is a mature, battle-tested vocabulary
that encodes the CTX persona's operational heuristics, cognitive strategies,
and domain terminology. However, the current format has structural limitations
that impede maintenance, tooling, and cross-project reuse.

### Current CTX Lexicon Limitations

1. **JSON array format**: The entire lexicon is a single JSON array. Append
   means parse → modify → serialize. This is O(n) for every edit and creates
   merge conflicts in version control.

2. **No temporal dimension**: Entries lack `date` and `status` fields. There
   is no way to know when a term was added, when it was last validated, or
   whether it is still active versus superseded.

3. **No lifecycle management**: A term cannot be "draft", "active", or
   "superseded". There is no mechanism for deprecating terms without deleting
   them (which breaks references).

4. **Flat tag structure**: Tags are string arrays (`["#foundation", "#protocol"]`)
   without semantic structure. There is no way to express:
   - "This heuristic implements that protocol" (`[Implements: COG-5]`)
   - "This is guided by that advisory" (`[Guided_By: ADV-8]`)
   - "This addresses this failure mode" (`[Substrate_Issue: Biddability]`)

5. **No heuristic field**: CTX entries have `description` (prose) but no
   condensed actionable rule. A human scanning for "what do I do?" must read
   a paragraph.

6. **No usage field**: CTX entries have no example sentences showing how a
   term is used in context. Newcomers must infer meaning from the definition.

7. **No coined_by attribution**: Terms lack attribution (human vs agent).
   This matters for provenance and for identifying which terms emerged from
   collaborative dialogue versus single-author documentation.

8. **Isolated from registry system**: The CTX lexicon is a standalone file.
   It cannot be listed with `reg-list`, validated with `reg-check`, or kept
   in sync with `reg-sync`.

## Solution

Migrate the CTX conceptual lexicon to a **merged schema** that preserves
CTX's strengths (stable IDs, type taxonomy, structured tags) while adopting
our unified registry conventions (JSONL, date/status, heuristic/usage fields,
registry tooling).

### Merged Schema

```json
{
  "file": "mentational-humility",
  "id": "term-002",
  "date": "2026-05-08",
  "status": "active",
  "type": "term",
  "summary": "The principle of acknowledging the inherent limitations of one's own cognitive processes",
  "meta": {
    "category": "Core Concept",
    "origin": "AGENTS.md (Edinburgh Protocol)",
    "heuristic": "Before answering, simulate a neutral observer. Check your own biases.",
    "usage": "When proposing the barnacle daemon, I simulated an impartial spectator.",
    "tags": [
      "[#foundation]",
      "[Quality: silver]",
      "[Guided_By: ADV-8]",
      "[Substrate_Issue: Complexity_Collapse]"
    ],
    "related": ["mentation", "impartial-spectator", "conceptual-entropy"],
    "coined_by": "human"
  }
}
```

### What Changes from CTX

| CTX Field | Merged Field | Change |
|-----------|-------------|--------|
| `id` | `id` | Kept (stable reference) |
| `title` | `file` | Human-readable identifier |
| `description` | `summary` | Kept (definition) |
| `type` | `type` | Kept (`term`, `operational-heuristic`, etc.) |
| `category` | `meta.category` | Kept (semantic category) |
| `tags` | `meta.tags` | Enhanced with bracket notation |
| — | `date` | **New** (temporal provenance) |
| — | `status` | **New** (`active`, `draft`, `superseded`) |
| — | `meta.heuristic` | **New** (condensed actionable rule) |
| — | `meta.usage` | **New** (example sentence) |
| — | `meta.coined_by` | **New** (`human` or `agent`) |
| — | `meta.origin` | **New** (source document) |
| `source` | — | Dropped (redundant with `meta.origin`) |

### What Changes from Our Lexicon

| Our Field | Merged Field | Change |
|-----------|-------------|--------|
| `file` | `file` | Kept (term identifier) |
| `date` | `date` | Kept |
| `status` | `status` | Kept |
| `summary` | `summary` | Kept |
| `meta.category` | `meta.category` | Kept |
| `meta.heuristic` | `meta.heuristic` | Kept |
| `meta.usage` | `meta.usage` | Kept |
| `meta.related` | `meta.related` | Kept |
| `meta.coined_by` | `meta.coined_by` | Kept |
| — | `id` | **Adopted from CTX** (stable ID) |
| — | `type` | **Adopted from CTX** (type discrimination) |
| — | `meta.tags` | **Adopted from CTX** (structured bracket notation) |

### Tag Taxonomy (Bracket Notation)

| Prefix | Example | Meaning |
|--------|---------|---------|
| `[#category]` | `[#process]` | Semantic category |
| `[Quality: level]` | `[Quality: silver]` | Maturity: bronze / silver / gold |
| `[Related: term]` | `[Related: silo]` | Bidirectional link |
| `[Origin: source]` | `[Origin: playbook.md]` | Source document |
| `[Guided_By: term]` | `[Guided_By: fail-fast]` | Guided by principle |
| `[Implements: term]` | `[Implements: PHI-2]` | Implements protocol |
| `[Substrate_Issue: mode]` | `[Substrate_Issue: Biddability]` | Addresses failure mode |

### File Format Change

**From**: Single JSON array (`conceptual-lexicon-example.json`)
**To**: JSONL lines (`silo-conceptual-lexicon.jsonl`)

Benefits:
- Append-only edits (no parse/serialize)
- Stream-processable
- Git-friendly (line-level diffs)
- Compatible with `reg-check`, `reg-sync`, `reg-list`

## Migration Plan

1. **Export CTX lexicon to JSONL** using conversion script (`scripts/ctx-lexicon-convert.ts`)
2. **Add unified fields** (date, status, heuristic, usage, coined_by, origin)
3. **Migrate tags** to bracket notation
4. **Validate** with `reg-check.ts`
5. **Deprecate old format** (keep as archive)

## Conversion Output

- **Input**: `docs/conceptual-lexicon-example.json` (161 entries, JSON array)
- **Output**: `debriefs/lexicon-ctx.jsonl` (161 entries, JSONL)
- **Script**: `scripts/ctx-lexicon-convert.ts`

Type distribution after conversion:
```
term:                  38
operational-heuristic: 120
pattern:                3
```

Status distribution:
```
active: 147
draft:   14
```

## Silo-Relevant Terms to Incorporate

From 161 CTX entries, **7 are directly relevant** to the silo/project conventions
and should be added to `silo-conceptual-lexicon.jsonl`:

| CTX ID | Term | Why It Belongs |
|--------|------|----------------|
| OH-040 | **factored-design** | "One logical change per commit" — maps to our extract-before-move |
| OH-041 | **optimal-simplicity** | "Facade, not workbench" — maps to our justfile philosophy |
| OH-082 | **fast-slow-thinking** | Deliberate for complex, fast for trivial — maps to fail-fast |
| OH-092 | **console-first-validation** | Validate data before building UI — maps to reg-check/reg-sync |
| OH-095 | **tase-mandate** | Test, Automate, Scale, Evangelize — maps to our CI/CD |
| OH-130 | **data-first-diagnostics** | Data volume before code logic — maps to barnacle detection |
| OH-131 | **exploratory-programming** | Workbench vs filing cabinet — maps to lab-first |

These 7 terms were added with silo-specific heuristics and usage examples,
linking them to existing terms via `[Related: ...]` and `[Origin: CTX OH-xxx]` tags.

## Acceptance Criteria

- [x] CTX lexicon entries have stable `id` fields
- [x] All entries have `date`, `status`, `type` fields
- [x] All entries have `meta.heuristic` and `meta.usage` (with silo-specific content for incorporated terms)
- [x] Tags use bracket notation with semantic prefixes
- [x] File is JSONL, not JSON array
- [x] `reg-check lexicon` passes
- [x] `reg-list lexicon` renders human-readable output
- [x] Old JSON array archived (`docs/conceptual-lexicon-example.json` retained)
- [x] 7 silo-relevant terms incorporated into `silo-conceptual-lexicon.jsonl`
- [x] Conversion script exists (`scripts/ctx-lexicon-convert.ts`)
- [x] CTX lexicon accessible via `just reg-lexicon-ctx`

## Related

- Current CTX lexicon: `docs/conceptual-lexicon-example.json`
- Merged lexicon: `silo-conceptual-lexicon.jsonl`
- Migration script: `scripts/lexicon-migrate.ts`
- Unified registry schema: `docs/schema/unified-registry.md`
