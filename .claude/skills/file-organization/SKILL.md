---
name: file-organization
version: 1.0.0
type: knowledge
description: Enforces project file organization standards from CLAUDE.md/PROJECT.md - auto-fix mode
category: enforcement
auto_activate: true
allowed-tools: [Read, Write, Edit, Grep, Glob]
keywords:
  - file
  - organization
  - structure
  - directory
  - standards
  - enforcement
triggers:
  - before_file_create
  - before_file_move
  - before_directory_create

---

# File Organization Skill

**Purpose**: Enforce project-specific file organization rules from CLAUDE.md and PROJECT.md.

## When This Skill Activates

- Keywords: 

---

## Core Concepts

### Overview

This skill provides comprehensive guidance on file organization. For detailed patterns and implementation examples, see the documentation files in `docs/`.

**Key Topics**:
- Detailed methodologies and best practices
- Implementation patterns and examples
- Common pitfalls and anti-patterns
- Cross-references to related skills

**See**: Documentation files in `docs/` directory for complete details


---

## Quick Reference

| Topic | Details |
|-------|---------|
| Detailed Guide 1 | `docs/detailed-guide-1.md` |
| Detailed Guide 2 | `docs/detailed-guide-2.md` |
| Detailed Guide 3 | `docs/detailed-guide-3.md` |

---

## Progressive Disclosure

This skill uses progressive disclosure to prevent context bloat:

- **Index** (this file): High-level concepts and quick reference (<500 lines)
- **Detailed docs**: `docs/*.md` files with implementation details (loaded on-demand)

**Available Documentation**:
- `docs/detailed-guide-1.md` - Detailed implementation guide
- `docs/detailed-guide-2.md` - Detailed implementation guide
- `docs/detailed-guide-3.md` - Detailed implementation guide

---

## Cross-References

**Related Skills**:
- See PROJECT.md for complete skill dependencies

**Related Tools**:
- See documentation files for tool-specific guidance


---

## Key Takeaways

1. Research existing patterns before implementing
2. Follow established best practices
3. Refer to detailed documentation for implementation specifics
4. Cross-reference related skills for comprehensive understanding

