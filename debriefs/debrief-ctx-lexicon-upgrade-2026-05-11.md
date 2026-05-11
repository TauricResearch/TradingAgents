# Debrief: CTX Conceptual Lexicon Upgrade

**Date:** 2026-05-11
**Branch:** `feat/ctx-lexicon-jsonl`
**Session:** `ses_ce3a7d`
**Status:** Done — PR ready

---

## What was done

Migrated the CTX conceptual lexicon from a monolithic JSON array to a
maintainable JSONL format with full lifecycle fields. Incorporated 7
silo-relevant terms into `silo-conceptual-lexicon.jsonl`. Deprecate
and blanked 11 context-specific/stub terms.

### Scripts created

| Script | Purpose |
|--------|---------|
| `scripts/ctx-lexicon-convert.ts` | One-shot: JSON array → JSONL, adds date/status/type/heuristic/usage/coined_by fields |
| `scripts/ctx-lexicon-list.ts` | Browse: table view, filter by type/status, full-text search, stats, JSON export |
| `scripts/ctx-lexicon-incorporate.ts` | Merge 7 CTX terms into `silo-conceptual-lexicon.jsonl` with heuristics + usage |

### Just verbs added

```bash
just ctx-lexicon                  # Table: id | title | type | heuristic
just ctx-lexicon-type type=term   # Filter by type
just ctx-lexicon-type type=operational-heuristic
just ctx-lexicon-status stat=active         # Filter by status
just ctx-lexicon-search query=humility       # Full-text search
just ctx-lexicon-stats             # Distribution tables
just ctx-lexicon-convert           # Re-run conversion
just ctx-lexicon-incorporate      # Merge 7 CTX terms into silo lexicon
```

### Data changes

| Metric | Value |
|--------|-------|
| CTX lexicon total | 161 entries |
| Active | 150 |
| Deprecated | 11 (slots preserved for reuse) |
| Slug fix | `g-delian-humility` → `godelian-humility` |
| Silo lexicon added | +7 terms with `meta.heuristic` + `meta.usage` |

---

## What was hard

**The justfile parameter-passing gotcha** consumed ~45 minutes across the
session. just passes `--flag value` as a single token `--flag=value` when
value has no spaces, AND it prepends the param name: `type=term` becomes
`--type=type=term`. The fix: strip the first `word=` prefix from extracted
values. This was documented in `playbooks/just-playbook.md` to prevent
future friction.

---

## What was learned

1. **Script first, just second.** Write the script, test it directly with
   `bun scripts/foo.ts --arg value`, THEN add a just verb. Every attempt
   to design the justfile first added iterations.

2. **`getFlagValue` pattern is universal.** Any script called by just with
   parameters will hit this. The `indexOf("=")` strip heuristic works for
   all flags without flag-specific logic.

3. **JSONL is the right format for this.** Line-level diffs, stream-processable,
   compatible with `reg-check`/`reg-sync`/`reg-list`. The conversion was
   deterministic and reversible.

4. **Deprecate > delete.** Blank the content, keep the slot. The brief
   anticipated this — slots can be reused as the lexicon grows.

---

## What's next

- The second open brief in `UNIFIED-CLI-001`: `brief-ig-api-client-integration.md`
- Consider a `ctx-lexicon-edit.ts` script for adding/editing entries
  (append-only JSONL needs a tool, not hand-editing)
- The deprecated slots in CTX lexicon could be used for new terms as they emerge

---

## Commits

```
93b24d1 chore(briefs): close ctx-lexicon-upgrade as done
6fe7891 fix(ctx-lexicon): fix typo + deprecate 11 context-specific/stub terms
5ae079f feat(ctx-lexicon): incorporate 7 CTX terms into silo lexicon with heuristic+usage
12db366 docs(just-playbook): document parameter-passing gotcha + fix pattern
de2c7aa fix(ctx-lexicon): simplify flag parsing — strip first word= prefix always
821a7d3 feat(ctx-lexicon): robust flag parsing in list script + just verbs
5272506 feat(lexicon): convert CTX JSON array to JSONL + add list/stats scripts
```
