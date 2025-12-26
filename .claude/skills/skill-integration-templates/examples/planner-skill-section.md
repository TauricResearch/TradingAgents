# Planner Agent Skill Section Example

Real-world example from `planner.md` agent showing effective skill integration.

## Original (Before Streamlining)

```markdown
## Relevant Skills

You have access to these specialized skills when planning architecture:

- **agent-output-formats**: Standardized output formats for agent responses
- **architecture-patterns**: System design, ADRs, design patterns, scalability patterns
- **project-management**: Project scope, goal alignment, constraint checking
- **database-design**: Schema design, normalization, query patterns
- **api-design**: API design patterns, endpoint structure, versioning
- **file-organization**: Project structure standards and organization
- **testing-guide**: Testing strategy patterns and coverage approaches
- **python-standards**: Language conventions affecting architecture decisions
- **security-patterns**: Security architecture and threat modeling

When planning a feature, consult the relevant skills to ensure your architecture follows best practices and patterns.
```

**Token Count**: ~190 tokens

## Streamlined (After Streamlining)

```markdown
## Relevant Skills

You have access to these specialized skills when planning architecture:

- **architecture-patterns**: Apply for system design and scalability decisions
- **api-design**: Follow for endpoint structure and versioning
- **database-design**: Use for schema planning and normalization
- **testing-guide**: Reference for test strategy planning
- **security-patterns**: Consult for security architecture

Consult the skill-integration-templates skill for formatting guidance.
```

**Token Count**: ~90 tokens

**Token Savings**: 100 tokens (52% reduction)

## Key Improvements

1. **Reduced skill count** from 9 to 5 (kept only most relevant)
2. **Concise descriptions** - One line per skill instead of multi-word descriptions
3. **Action verbs** - "Apply", "Follow", "Use", "Reference", "Consult" match planning context
4. **Meta-skill reference** - Points to skill-integration-templates for formatting guidance
5. **Removed redundant closing** - "When planning..." was verbose

## Why This Works

### Progressive Disclosure
- Full skill content loads on-demand when skills are referenced
- Lightweight metadata (skill names) stays in context
- Planner can still access all 9 original skills if needed

### Token Efficiency
- 190 tokens → 90 tokens (100 token savings)
- Essential skills still listed
- No loss of functionality

### Maintained Quality
- Planner still knows which skills are available
- Action verbs guide when to use each skill
- Closing sentence provides formatting guidance

## Usage in planner.md

**Location**: `plugins/autonomous-dev/agents/planner.md`

**Full Context**:
```markdown
---
name: planner
description: Architecture planning and design for complex features
model: opus
tools: [Read, Grep, Glob]
---

You are the **planner** agent.

## Your Mission

Design detailed, actionable architecture plans for requested features...

[agent-specific mission and workflow]

## Relevant Skills

You have access to these specialized skills when planning architecture:

- **architecture-patterns**: Apply for system design and scalability decisions
- **api-design**: Follow for endpoint structure and versioning
- **database-design**: Use for schema planning and normalization
- **testing-guide**: Reference for test strategy planning
- **security-patterns**: Consult for security architecture

Consult the skill-integration-templates skill for formatting guidance.

[rest of agent prompt]
```

## Related Examples

- `implementer-skill-section.md` - Implementer agent example
- `minimal-skill-reference.md` - Minimal reference pattern
