---
name: Architecture-First Reading Protocol
description: >
  This skill should be used at the start of every new technical task, new session,
  or when switching to a different part of the codebase. It enforces mandatory reading
  of architectural decisions, current project state, and active plans before any code
  is written, modified, or proposed. Relevant when the user says "implement a feature",
  "fix a bug", "refactor code", "add a new module", "modify configuration", "change architecture",
  "start a task", "begin work on", "let's build", or "work on". This skill acts as a gatekeeper
  ensuring all code changes respect established Architecture Decision Records (ADRs).
version: 0.1.0
---

# Architecture-First Reading Protocol

## Purpose

Enforce a mandatory reading sequence before writing any code, modifying configurations,
or proposing solutions. All established architectural rules in `docs/agent/decisions/`
are treated as absolute laws. Violating an ADR without explicit user approval is forbidden.

## Mandatory Reading Sequence

Execute the following steps **in order** before producing any code or solution.

### Step 1: Read Current State

Read `docs/agent/CURRENT_STATE.md` to understand:

- The active milestone and sprint focus
- Any blockers or constraints currently in effect
- Recent changes that affect the working context

If the file does not exist, note this and proceed — but flag it to the user as a gap.

### Step 2: Query Architectural Decisions

List all files in `docs/agent/decisions/` and identify which ADRs are relevant to the
current task. If this directory does not exist, skip to Step 3.

**Relevance matching rules:**

- Match by filename keywords (e.g., task involves "auth" → read `0002-jwt-auth.md`)
- Match by YAML `tags` in ADR frontmatter if present
- When uncertain, read the ADR — false positives cost less than missed constraints

**For each relevant ADR, extract and internalize:**

- `Consequences & Constraints` section → treat as hard rules
- `Actionable Rules` section → treat as implementation requirements
- `Status` field → only `accepted` or `active` ADRs are binding

See `references/adr-template.md` for the expected ADR structure.

### Step 3: Check Active Plans

List files in `docs/agent/plans/` and identify any plan related to the current task.
If this directory does not exist, skip to Step 4.

- Read the active plan to determine which step is currently being executed
- Do not skip steps unless the user explicitly instructs it
- If no plan exists for the task, proceed but note the absence

### Step 4: Acknowledge Reading

Begin the first response to any technical task with a brief acknowledgment:

```
I have reviewed:
- `CURRENT_STATE.md`: [one-line summary]
- `decisions/XXXX-name.md`: [relevant constraint noted]
- `plans/active-plan.md`: [current step]

Proceeding with [task description]...
```

If no docs exist yet, state:

```
No architecture docs found in docs/agent/. Proceeding without ADR constraints.
Consider scaffolding the agent memory structure if this project needs architectural governance.
```

## Conflict Resolution Protocol

When a user request contradicts an ADR rule:

1. **STOP** — do not write or propose conflicting code
2. **Quote** the specific rule from the decision file, including the file path
3. **Inform** the user of the conflict clearly:

```
⚠️ Conflict detected with `docs/agent/decisions/XXXX-name.md`:

Rule: "[exact quoted rule]"

Your request to [description] would violate this constraint.

Options:
  A) Modify the approach to comply with the ADR
  B) Update the ADR to allow this exception (I can draft the amendment)
  C) Proceed with an explicit architectural exception (will be logged)
```

4. **Wait** for the user's decision before proceeding

## Directory Structure Expected

```
docs/agent/
├── CURRENT_STATE.md          # Active milestone, blockers, context
├── decisions/                # Architecture Decision Records
│   ├── 0001-example.md
│   ├── 0002-example.md
│   └── ...
├── plans/                    # Active implementation plans
│   ├── active-plan.md
│   └── ...
└── logs/                     # Session logs (optional)
```

## Graceful Degradation

Handle missing documentation gracefully:

| Condition | Action |
|---|---|
| `docs/agent/` missing entirely | Proceed without constraints; suggest scaffolding |
| `CURRENT_STATE.md` missing | Warn user, continue to decisions check |
| `decisions/` empty | Note absence, proceed without ADR constraints |
| `plans/` empty | Proceed without plan context |
| ADR has no `Status` field | Treat as `accepted` (binding) by default |

## Integration with Existing Workflows

This protocol runs **before** the existing TradingAgents flows:

- Before the Agent Flow (analysts → debate → trader → risk)
- Before the Scanner Flow (scanners → deep dive → synthesis)
- Before any CLI changes, config modifications, or test additions

## Additional Resources

### Reference Files

- **`references/adr-template.md`** — Standard ADR template for creating new decisions
- **`references/reading-checklist.md`** — Quick-reference checklist for the reading sequence
