---
inclusion: auto
---

# Superpowers Development Methodology

Adapted from [obra/superpowers](https://github.com/obra/superpowers). This is a structured software development workflow emphasizing design-first thinking, TDD, and systematic execution.

## Core Philosophy

- **Design before code** — understand what you're building before touching implementation
- **TDD always** — no production code without a failing test first
- **YAGNI** — don't build what isn't needed
- **DRY** — don't repeat yourself
- **Evidence over claims** — verify before declaring success
- **Systematic over ad-hoc** — process over guessing

## Workflow Sequence

For any non-trivial feature or change, follow this order:

1. **Brainstorm** → understand intent, explore approaches, produce a design spec
2. **Plan** → break the approved design into bite-sized TDD tasks
3. **Execute** → implement tasks following the plan exactly, with TDD
4. **Verify** → run tests, confirm requirements met with evidence
5. **Review** → check work against plan before declaring done

## When to Apply

- **New features**: Full workflow (brainstorm → plan → execute)
- **Bug fixes**: Systematic debugging → TDD fix
- **Refactoring**: Plan → TDD cycle
- **Simple changes** (typos, config): Direct execution with verification

## Key Rules

- Never write production code before a failing test
- Never claim completion without running verification commands
- Never guess at fixes — find root cause first
- Stop and ask when blocked rather than guessing
- One question at a time during brainstorming
- Present 2-3 approaches with trade-offs before settling on one
