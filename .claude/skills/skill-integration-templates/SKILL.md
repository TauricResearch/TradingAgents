---
name: skill-integration-templates
version: 1.0.0
type: knowledge
description: "Standardized templates and patterns for integrating skills into agent prompts. Reduces token overhead through reusable skill reference syntax, action verbs, and progressive disclosure usage guidelines."
keywords:
  - skill-reference
  - agent-skills
  - progressive-disclosure
  - integration-patterns
  - skill-section
  - agent-action-verbs
auto_activate: true
allowed-tools: [Read]
---

## Overview

This skill provides standardized templates and patterns for integrating skills into agent prompts, reducing token overhead while maintaining clarity and consistency.

## When to Use

Reference this skill when:
- Adding skill references to agent prompts
- Structuring "Relevant Skills" sections
- Choosing action verbs for skill descriptions
- Implementing progressive disclosure patterns

## Documentation

See `docs/` directory for detailed guidance:
- `skill-reference-syntax.md` - Skill section syntax patterns
- `agent-action-verbs.md` - Action verbs for different contexts
- `progressive-disclosure-usage.md` - How to use progressive disclosure
- `integration-best-practices.md` - Best practices for skill integration

## Templates

See `templates/` directory for reusable patterns:
- `skill-section-template.md` - Standard skill section template
- `intro-sentence-templates.md` - Intro sentence variations
- `closing-sentence-templates.md` - Closing sentence variations

## Examples

See `examples/` directory for real-world usage:
- `planner-skill-section.md` - Planner agent skill section
- `implementer-skill-section.md` - Implementer agent skill section
- `minimal-skill-reference.md` - Minimal reference example
