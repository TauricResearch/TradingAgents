---
name: Memory Reader
description: >
  Reads and applies the project's structured memory system (docs/agent/) at the start
  of any technical task. Use this skill at the beginning of every new session, when
  starting a new feature or bug fix, when switching to a different part of the codebase,
  or when the user says "read memory", "load context", "check decisions", "what's the
  current state", "read the ADRs", "what are the conventions", or "catch me up".
  This skill acts as a gatekeeper — it ensures all code changes respect established
  architecture decisions and current project state. Trigger proactively at session start
  before writing any code.
version: 1.0.0
---

# Memory Reader

Load the project's structured memory before doing any technical work. This skill
ensures you understand the current state, architectural constraints, and coding
conventions before writing or proposing any code changes.

## When to Read Memory

Read memory **before** any of these actions:
- Implementing a feature
- Fixing a bug
- Refactoring code
- Adding a new module or agent
- Modifying configuration
- Changing architecture
- Writing or modifying tests

If `docs/agent/` doesn't exist, skip gracefully and suggest running the memory-builder
skill to set it up.

## Reading Sequence

Follow this sequence in order. Each step builds on the previous.

### Step 1: Current State

Read `docs/agent/CURRENT_STATE.md` and extract:
- **Active milestone** — what's the current focus?
- **Recent progress** — what just shipped? What PRs merged?
- **Blockers** — what's stuck or fragile?

This tells you what the team is working on right now and what to be careful around.

### Step 2: Relevant Architecture Decisions

List all files in `docs/agent/decisions/` and find ADRs relevant to your current task.

**How to match relevance:**

1. Extract keywords from the task (e.g., "add a new vendor" → vendor, fallback, routing)
2. Match against ADR filenames (e.g., `002-data-vendor-fallback.md`, `011-opt-in-vendor-fallback.md`)
3. When uncertain, read the ADR — a false positive costs less than missing a constraint

**For each relevant ADR, extract:**
- `Consequences & Constraints` — treat as **hard rules** (MUST/MUST NOT)
- `Actionable Rules` — treat as **implementation requirements**
- `Status` — only `accepted` or `active` ADRs are binding

| Status | Binding? |
|--------|----------|
| `accepted` / `active` | Yes — all code must comply |
| `proposed` | Informational only |
| `deprecated` | Ignore |
| `superseded` | Follow the superseding ADR instead |
| Missing status field | Default to `accepted` (binding) |

### Step 3: Context Files

Read the context files relevant to your task. You don't always need all 5 — pick
based on what you're doing:

| If your task involves... | Read these |
|--------------------------|------------|
| System design, workflows, adding agents | `ARCHITECTURE.md` |
| Writing code, patterns, gotchas | `CONVENTIONS.md` |
| Finding files, classes, extending the system | `COMPONENTS.md` |
| Dependencies, APIs, providers | `TECH_STACK.md` |
| Understanding project terminology | `GLOSSARY.md` |
| Any significant change | All of them |

Context files live in `docs/agent/context/`. If the directory doesn't exist, note
the absence and proceed without — but flag it to the user.

### Step 4: Active Plans

Check `docs/agent/plans/` for any plan related to the current task.

- If a plan exists, identify the current step and follow it
- Do not skip steps without explicit user approval
- If no plan exists, proceed but note the absence

### Step 5: Acknowledge

Start your first response to any technical task with a brief acknowledgment:

```
I've reviewed the project memory:
- **State**: [one-line summary of current milestone]
- **ADRs**: [relevant decisions noted, or "none applicable"]
- **Context**: [key conventions or constraints for this task]
- **Plan**: [current step, or "no active plan"]

Proceeding with [task description]...
```

If no docs exist:

```
No memory files found in docs/agent/. Proceeding without constraints.
Consider running the memory-builder skill to set up the project memory.
```

## Conflict Resolution

When a user request contradicts an ADR:

1. **Stop** — do not write conflicting code
2. **Quote** the specific rule, including the file path
3. **Present options**:

```
Conflict with `docs/agent/decisions/NNN-name.md`:

> "[exact quoted rule]"

Your request to [description] would violate this constraint.

Options:
  A) Modify the approach to comply with the ADR
  B) Update the ADR to allow this exception (I can draft the amendment)
  C) Proceed with an explicit exception (will be logged)
```

4. **Wait** for the user's decision before proceeding

## Staleness Detection

While reading, check for signs that the memory is outdated:

- Freshness markers (`<!-- Last verified: YYYY-MM-DD -->`) older than 14 days
- CURRENT_STATE.md mentions milestones that appear completed in git history
- Context files reference files or classes that no longer exist
- Dependency versions in TECH_STACK.md don't match pyproject.toml

If staleness is detected, warn the user:

```
Memory may be stale — [specific issue found]. Consider running the
memory-builder skill in update mode to refresh.
```

## Updating State After Work

After completing a significant task, update `docs/agent/CURRENT_STATE.md`:

- Add completed work to "Recent Progress"
- Remove resolved items from "Active Blockers"
- Update the milestone summary if it changed

This keeps the memory fresh for the next session. Only update CURRENT_STATE.md —
the other context files are updated via the memory-builder skill.

## Graceful Degradation

| Missing Resource | Action |
|------------------|--------|
| `docs/agent/` entirely | Proceed without constraints; suggest scaffolding |
| `CURRENT_STATE.md` only | Warn, continue to decisions |
| `decisions/` empty | Note absence, proceed freely |
| `context/` empty | Proceed; suggest running memory-builder |
| `plans/` empty | Proceed without plan context |
| Individual context file | Note which is missing, use what's available |
