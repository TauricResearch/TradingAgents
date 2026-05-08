# Decisions Playbook

## Purpose

An **Architecture Decision Record (ADR)** captures a significant technical choice — the *why* behind the *what*. Unlike briefs (aspirational, written before) and debriefs (retrospective, written after), ADRs are written *during* implementation, at the moment of decision.

**The ADR answers the question nobody asked at the time but everyone will ask six months later: "Why did we do it this way?"**

## When to Write an ADR

Write an ADR when you:
- Choose between two or more viable alternatives (Bun vs Node, HTMX vs React)
- Adopt a new tool, pattern, or constraint that shapes the architecture
- Discover a trade-off that future contributors need to understand
- Deprecate or supersede a previous decision

Don't write an ADR for:
- Obvious choices with no real alternative ("we used SQLite because we needed a database")
- Temporary workarounds that don't shape the architecture
- Personal preference (tabs vs spaces) — those go in the conventions playbook

## ADR Format

Every ADR is a single `.md` file in `decisions/`. Use numbered prefixes (`001-`, `002-`) for chronological ordering. Use the template at `decisions/TEMPLATE.md`.

```markdown
# Decision: [Title]

**Date:** YYYY-MM-DD
**Status:** [Proposed | Accepted | Superseded]

## Context
What situation led to this decision? One paragraph.

## Decision
What did we choose? One sentence.

## Alternatives Considered
| Alternative | Why Rejected |
|-------------|-------------|
| Option A | Reason |
| Option B | Reason |

## Consequences
**What became easier:**
- 

**What became harder:**
- 

**Constraints this imposes:**
- 

## Related
- Debrief: `debriefs/debrief-*.md`
- Playbook: `playbooks/*.md`
- ADR: `decisions/NNN-*.md` (supersedes / superseded by)
```

## Status Lifecycle

```
Proposed → Accepted → Superseded
                ↓
           (never deleted — ADRs are historical records)
```

- **Proposed:** Under discussion. Not yet committed to.
- **Accepted:** The decision is in effect. The architecture follows this.
- **Superseded:** A later ADR replaced this decision. Add `Superseded by: decisions/NNN-*.md` to the top.

Never delete an ADR. Even superseded decisions are valuable — they explain why something was tried and why it was abandoned.

## Linking ADRs to the Knowledge System

ADRs don't exist in isolation. They connect to:

| Link | How |
|------|-----|
| **Debrief** | Add the ADR filename to the `adr` field in `debriefs/INDEX.jsonl`. The debrief captures *when* the decision was made; the ADR captures *why*. |
| **Playbook** | Reference the ADR in the "Related" section of relevant playbooks. The ADR is the decision; the playbook is the pattern that emerged from it. |
| **Brief** | If a brief's implementation produces architectural decisions, list the ADRs in the brief's Technical Notes. |
| **Superseding ADR** | When a decision is replaced, the new ADR links to the old one via `Superseded by:`. The old ADR's status changes to Superseded. |

## Indexing

The `decisions/INDEX.jsonl` file tracks all ADRs:

```jsonl
{"file":"001-bun-hono-stack.md","date":"2026-05-02","status":"Accepted","supersedes":null,"superseded_by":null,"summary":"Bun runtime with Hono web framework, server-side JSX, HTMX for client interactivity"}
```

Add an entry whenever you write an ADR. Update the entry when an ADR is superseded.

## Location

All ADRs reside in `decisions/`.
- `decisions/TEMPLATE.md` — the template for new ADRs
- `decisions/NNN-slug.md` — individual ADRs (numbered sequentially)
- `decisions/INDEX.jsonl` — machine-readable index

## Differences from Briefs and Debriefs

| | Brief | ADR | Debrief |
|---|-------|-----|---------|
| **When** | Before | During | After |
| **Answers** | "What will we build?" | "Why did we choose X?" | "What happened?" |
| **Audience** | Implementer | Future maintainer | Future agent |
| **Lifespan** | Becomes irrelevant after implementation | Retains value indefinitely | Historical reference |
| **Updates** | Status only (Open → Done) | Status only (Proposed → Accepted → Superseded) | Never (frozen on completion) |

## Review Checklist

Before committing an ADR:
- [ ] Uses the `decisions/TEMPLATE.md` format
- [ ] Alternatives table has at least two entries with specific rejection reasons
- [ ] Consequences include both "easier" and "harder"
- [ ] Constraints are specific and actionable ("Must use Hono JSX" not "Must be careful")
- [ ] Related links are correct and files exist
- [ ] `decisions/INDEX.jsonl` entry added
- [ ] Debrief `adr` field updated if applicable
