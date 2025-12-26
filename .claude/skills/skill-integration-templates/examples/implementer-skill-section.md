# Implementer Agent Skill Section Example

Real-world example from `implementer.md` agent showing effective skill integration.

## Original (Before Streamlining)

```markdown
## Relevant Skills

You have access to these specialized skills during implementation:

- **agent-output-formats**: Standardized output formats for agent responses
- **python-standards**: Python code style, type hints, docstring conventions
  - Use for writing clean, idiomatic Python code
  - Reference for naming conventions and code organization
- **observability**: Logging patterns, monitoring, and debugging strategies
  - Apply when adding logging or monitoring to code
- **error-handling-patterns**: Standardized error handling and validation
  - Use for consistent error messages and exception handling

When implementing features, consult these skills to ensure your code follows project standards and best practices.
```

**Token Count**: ~150 tokens

## Streamlined (After Streamlining)

```markdown
## Relevant Skills

You have access to these specialized skills during implementation:

- **python-standards**: Follow for code style, type hints, and docstrings
- **observability**: Use for logging and monitoring patterns
- **error-handling-patterns**: Apply for consistent error handling

Consult the skill-integration-templates skill for formatting guidance.
```

**Token Count**: ~70 tokens

**Token Savings**: 80 tokens (53% reduction)

## Key Improvements

1. **Removed verbose sub-bullets** - Eliminated "Use for...", "Reference for..." details
2. **One line per skill** - Concise purpose statements
3. **Action verbs** - "Follow", "Use", "Apply" match implementation context
4. **Meta-skill reference** - Points to skill-integration-templates
5. **Removed agent-output-formats** - Not needed in Relevant Skills section (referenced elsewhere)

## Why This Works

### Progressive Disclosure
- Full python-standards skill (~2,000 tokens) loads on-demand
- Full observability skill (~1,500 tokens) loads on-demand
- Full error-handling-patterns skill (~1,200 tokens) loads on-demand
- Context overhead: 70 tokens vs. 150 tokens

### Token Efficiency
- 150 tokens → 70 tokens (80 token savings)
- No functionality lost
- Same skills available

### Maintained Quality
- Implementer knows which skills to reference
- Action verbs guide usage
- Progressive disclosure handles details

## Usage in implementer.md

**Location**: `plugins/autonomous-dev/agents/implementer.md`

**Full Context**:
```markdown
---
name: implementer
description: Code implementation following architecture plans
model: opus
tools: [Read, Write, Edit, Grep, Glob, Bash]
---

You are the **implementer** agent.

## Your Mission

Write production-quality code following the architecture plan. Make tests pass if they exist.

[agent-specific mission and workflow]

## Relevant Skills

You have access to these specialized skills during implementation:

- **python-standards**: Follow for code style, type hints, and docstrings
- **observability**: Use for logging and monitoring patterns
- **error-handling-patterns**: Apply for consistent error handling

Consult the skill-integration-templates skill for formatting guidance.

[rest of agent prompt]
```

## Comparison: Verbose vs. Concise

### Verbose (Bad)
```markdown
- **python-standards**: Python code style, type hints, docstring conventions
  - Use for writing clean, idiomatic Python code
  - Reference for naming conventions and code organization
  - Apply for documentation standards
```

**Why Bad**:
- 4 lines for one skill (80+ tokens)
- Duplicates content from python-standards skill
- Defeats progressive disclosure purpose

### Concise (Good)
```markdown
- **python-standards**: Follow for code style, type hints, and docstrings
```

**Why Good**:
- 1 line for one skill (~15 tokens)
- Progressive disclosure loads details on-demand
- Token efficient

## Related Examples

- `planner-skill-section.md` - Planner agent example
- `minimal-skill-reference.md` - Minimal reference pattern
