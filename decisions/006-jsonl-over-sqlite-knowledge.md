# Decision: JSONL over SQLite for Knowledge Management

**Date:** 2026-05-08
**Status:** Accepted

## Context

The project accumulated 26 playbooks, 16 briefs, and 27 debriefs in flat markdown directories with inconsistent naming conventions. We needed queryable indexes that were git-diffable, zero-dependency, and queryable without a running server. The alternatives were SQLite (already in the stack), YAML frontmatter, or JSONL files.

## Decision

JSONL indexes (`INDEX.jsonl` / `REGISTRY.jsonl`) as the source of truth for briefs, debriefs, and playbooks. One JSON object per line. Queryable with `jq`. Validated at commit time via `just reg-check`. Schema types in `src/server/lib/registry-types.ts`. SQLite is reserved for operational data (positions, trades, signals, prices).

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| SQLite indexes | Can't query without a running server; migration versioning adds complexity; not git-diffable |
| YAML frontmatter in each file | Requires parsing every file to answer "show me all open briefs"; no atomic updates |
| Markdown index tables | Unqueryable at scale; manual sorting/filtering; breaks at 20+ entries |
| Dedicated search tool (Meilisearch, Typesense) | Overkill for 70 documents; adds infrastructure dependency |

## Consequences

**What became easier:**
- Instant queries with `jq` ("show me all canonical playbooks", "show briefs by date")
- Git-diffable — a changed status is a one-line diff
- Append-only — `echo '{"file":"x","status":"open"}' >> INDEX.jsonl` is a valid update
- Validated at commit time — `just reg-check` catches missing fields
- Zero runtime dependency — the filesystem is the database

**What became harder:**
- JSONL has no schema enforcement at write time (only at read/validation time)
- Manual entries can have typos or missing fields (caught by `just reg-check` but not prevented)
- No relational queries — can't join briefs to debriefs without jq pipelines
- Requires contributor discipline — an agent that adds a playbook without updating REGISTRY.jsonl creates drift

**Constraints this imposes:**
- All index files must pass `jq -e '.'` (valid JSON) and `just reg-check` (required fields)
- Schema types in `registry-types.ts` are the contract
- `just reg-*` recipes are the query interface
- SQLite is explicitly NOT for knowledge management — operational data only

## Related

- Debrief: `debriefs/debrief-session-2026-05-07-wrapup.md`
- Playbook: `playbooks/playbooks-playbook.md`
- Type definitions: `src/server/lib/registry-types.ts`
- Recipe: `Justfile` (reg-* group)
