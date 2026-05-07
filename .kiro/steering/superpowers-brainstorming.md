---
inclusion: manual
---

# Brainstorming: Ideas Into Designs

Use this when starting any creative work — new features, components, or significant behavior changes.

## Hard Gate

Do NOT write any code or take implementation actions until a design is presented and the user approves it. This applies regardless of perceived simplicity.

## Process

1. **Explore project context** — check relevant files, docs, recent commits
2. **Ask clarifying questions** — one at a time, prefer multiple choice when possible
3. **Propose 2-3 approaches** — with trade-offs and a recommendation
4. **Present design in sections** — get approval after each section
5. **Write design doc** — save to `.kiro/specs/<feature-name>/design.md`
6. **Self-review** — check for placeholders, contradictions, ambiguity
7. **User reviews spec** — wait for approval before proceeding
8. **Transition** — create implementation plan (tasks.md)

## Design Principles

- Break systems into units with one clear purpose and well-defined interfaces
- Each unit should be understandable and testable independently
- Prefer smaller, focused files over large ones doing too much
- In existing codebases, follow established patterns
- Scale each section to its complexity — a few sentences if simple, more if nuanced

## Scope Check

If the request covers multiple independent subsystems, flag it immediately. Help decompose into sub-projects before diving into details. Each sub-project gets its own design → plan → implementation cycle.

## Anti-Patterns

- "This is too simple for a design" — simple projects are where unexamined assumptions waste the most work
- Asking multiple questions at once — one per message
- Jumping to implementation before approval
- Proposing only one approach without alternatives

## Key Questions to Explore

- What is the purpose? What problem does this solve?
- What are the constraints (performance, compatibility, dependencies)?
- What does success look like? How will we know it works?
- What's the simplest thing that could work?
