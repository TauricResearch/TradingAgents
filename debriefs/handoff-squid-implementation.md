# Handoff: SQUID Implementation Session

**Session:** ses_b9d84b (this session)
**Branch:** `main` (just pushed: `799c48a`)
**Status:** Pushed, clean state — ready for new session

---

## What Just Happened

**SQUID** — a unified CRUD system for registries and the conceptual lexicon.

**Name origin:** Save, Query, Insert, Delete. `insert` not `indesrt` (typo corrected).

### Committed this session (on `main`)

```
799c48a feat(squid): schema library + squid playbook + justfile backup
```

**Files:**
- `scripts/lib/registry-types.ts` — shared Zod schemas (RegistryEntry + ConceptEntry)
- `playbooks/squid-playbook.md` — full documentation of SQUID operations
- `Justfile.bak` — backup of the original justfile before experimentation

---

## What's Left to Do

### 1. Implement the two CRUD scripts

| Script | Purpose | Schema |
|--------|---------|--------|
| `scripts/reg-crud.ts` | Registry save/query/insert/delete | `RegistryEntry` |
| `scripts/ctx-crud.ts` | Conceptual lexicon save/query/insert/delete | `ConceptEntry` |

Both use `scripts/lib/registry-types.ts` for Zod schemas and helpers.

**Safety on both:**
- `--dry-run` flag on all write operations (save, insert, delete)
- Validate with Zod before write
- Re-parse after write to confirm valid JSONL
- Auto-backup before any mutation

### 2. Experimental justfile

`Justfile.squid` — separate from `Justfile` (which is backed up as `Justfile.bak`).

SQUID verbs to implement:
```
just squid <registry> query [--status <status>] [file]
just squid <registry> save <file> --status <status> --summary <summary> [--dry-run]
just squid <registry> insert --date <date> --status <status> --summary <summary> [--dry-run]
just squid <registry> delete <file> [--dry-run]
just squid ctx query [--type <type>] [--status <status>] [slug]
just squid ctx save <slug> --<field> <value> [--dry-run]
just squid ctx insert --slug <slug> --term <term> --type <type> --heuristic <heuristic> --usage <usage> [--dry-run]
just squid ctx delete <slug> [--dry-run]
```

### 3. Test cycle

1. Build `reg-crud.ts` — test with `just squid debriefs query`
2. Build `ctx-crud.ts` — test with `just squid ctx query`
3. Build SQUID verbs in `Justfile.squid`
4. Test all operations end-to-end
5. **Restore original justfile:** `cp Justfile.bak Justfile`
6. **Lift-and-shift:** port tested verbs from `Justfile.squid` into `Justfile`

---

## Schema Reference

**RegistryEntry:**
```
file:    string  (YYYY-MM-DD)
date:    string  (YYYY-MM-DD)
status:  open | done | active | closed | wontfix
summary: string
meta:    object  (optional)
```

**ConceptEntry:**
```
slug:       string
term:       string
type:       concept | operational-heuristic | anti-pattern | principle | pattern
heuristic:  string
usage:      string
coined_by:  string  (optional)
status:     active | deprecated | draft
```

---

## Key Context

- **Justfile backup:** `Justfile.bak` (original, safe to restore)
- **Justfile.squid:** experimental justfile (still needs to be created)
- **`scripts/lib/registry-types.ts`:** already committed — shared schema library
- **`playbooks/squid-playbook.md`:** already committed — full docs
- **Registries:** briefs, debriefs, decisions, playbooks, docs — all share RegistryEntry schema
- **Conceptual lexicon:** `silo-conceptual-lexicon.jsonl` — separate schema

---

## Startup for next session

```bash
git fetch origin main
git checkout main
git pull origin main
td usage --new-session
bun scripts/agent-orient.ts
```

Then resume SQUID implementation — build `reg-crud.ts` first, then `ctx-crud.ts`, then `Justfile.squid`.

---

*End of handoff. Good luck with SQUID.*