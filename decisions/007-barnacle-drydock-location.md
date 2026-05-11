# Decision: Drydock as Barnacle Archive

**Date:** 2026-05-11
**Status:** Accepted

## Context

The Barnacle Removal System (BRS) requires a quarantine location for deprecated content — text moved but not deleted. We needed a location that keeps the repo clean while preserving traceability. The silo already has a `decisions/` directory for auditable, persistent records. Using it for drydock avoids a new top-level concern and makes the archive discoverable alongside other system decisions.

## Decision

Barnacles are moved to `decisions/drydock/` (gitignored), with an `INDEX.jsonl` for machine-readable traceability. The deletion log lives at `decisions/drydock/DELETION_LOG.md`.

## Structure

```
decisions/drydock/
├── INDEX.jsonl              # one row per drydocked block
├── DELETION_LOG.md          # human-readable log (append-only)
└── YYYY-MM-DD/
    └── {source-relative-path}/
        └── block-{id}.md    # individual barnacle text
```

`INDEX.jsonl` schema:
```jsonl
{"id":"BRS-001","source":"playbooks/services-playbook.md","line":12,"severity":"warning","type":"orphaned_reference","text":"...","justification":"...","drydocked_at":"2026-05-11T..."}
```

## Escalation Protocol

The scrubber outputs JSONL to `decisions/drydock/pending.jsonl`. A separate Gum-based UI layer (`scripts/barnacle-present.ts` or similar) reads this and presents an interactive Charm table for human yes/no decisions before the scrubber applies changes.

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| `drydock/` at repo root | Top-level noise; gitignored but visible in all directory listings |
| `~/.tradingagents/drydock/` | Machine-local; invisible to agents, not auditable in git history |
| SQLite in `tradingagents.db` | Overloading operational DB with knowledge artefacts (per decision 006) |

## Consequences

**What became easier:**
- Barnacles are traceable: who moved what, when, and why
- The archive is gitignored — no noise in history, no risk of committing removed content
- JSONL index is machine-readable for future tooling (Gum presenter, re-integration scripts)

**What became harder:**
- Two locations to consult: `playbooks/` (current) and `decisions/drydock/` (archived)

**Constraints this imposes:**
- `decisions/drydock/` must be in `.gitignore`
- `DELETION_LOG.md` is append-only (no editing of past entries)
- Scrubber must write `INDEX.jsonl` before returning (checkpoint-before-modify pattern)

## Related

- Brief: `briefs/2026-05-11-brief-barnacle-removal.md`
- Brief: `briefs/2026-05-11-brief-brnacle-scraper-prompt.md`
- Brief: `briefs/2026-05-11-brief-reintegration-protocol.md`
- Brief: `briefs/barnacle-scrubber-plan.md`
