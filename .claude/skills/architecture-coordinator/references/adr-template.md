# ADR Template

Architecture Decision Records follow this structure. Use this template when creating
new decisions in `docs/agent/decisions/`.

## Filename Convention

```
NNNN-short-descriptive-name.md
```

- `NNNN` — zero-padded sequential number (0001, 0002, ...)
- Use lowercase kebab-case for the name portion

## Template

```markdown
---
title: "Short Decision Title"
status: proposed | accepted | deprecated | superseded
date: YYYY-MM-DD
tags: [relevant, keywords, for, matching]
superseded_by: NNNN-new-decision.md  # only if status is superseded
---

# NNNN — Short Decision Title

## Context

Describe the problem, forces at play, and why a decision is needed.
Include relevant technical constraints, business requirements, and
any alternatives considered.

## Decision

State the decision clearly and concisely. Use active voice.

Example: "Use JWT tokens for API authentication with RS256 signing."

## Consequences & Constraints

List the binding rules that follow from this decision. These are
treated as **absolute laws** by the Architecture-First Reading Protocol.

- **MUST**: [mandatory requirement]
- **MUST NOT**: [explicit prohibition]
- **SHOULD**: [strong recommendation]

Example:
- MUST use RS256 algorithm for all JWT signing
- MUST NOT store tokens in localStorage
- SHOULD rotate signing keys every 90 days

## Actionable Rules

Concrete implementation requirements derived from the decision:

1. [Specific code/config requirement]
2. [Specific code/config requirement]
3. [Specific code/config requirement]

## Alternatives Considered

| Alternative | Reason Rejected |
|---|---|
| Option A | [why not chosen] |
| Option B | [why not chosen] |

## References

- [Link or file reference]
- [Related ADR: NNNN-related.md]
```

## Status Lifecycle

```
proposed → accepted → [deprecated | superseded]
```

- **proposed** — Under discussion, not yet binding
- **accepted** — Active and binding; all code must comply
- **deprecated** — No longer relevant; may be ignored
- **superseded** — Replaced by another ADR (link via `superseded_by`)

## Best Practices

- Keep decisions focused — one decision per file
- Write constraints as testable statements where possible
- Tag decisions with module/domain keywords for easy matching
- Reference related decisions to build a decision graph
- Date all decisions for historical context
