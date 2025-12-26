# Skill Section Template

Standard template for adding "Relevant Skills" sections to agent prompts.

## Basic Template

```markdown
## Relevant Skills

You have access to these specialized skills when [agent-specific context]:

- **[skill-name]**: [Action verb] [purpose] for [use case]
- **[skill-name]**: [Action verb] [purpose] for [use case]
- **[skill-name]**: [Action verb] [purpose] for [use case]

Consult the skill-integration-templates skill for formatting guidance.
```

## Template Variables

### [agent-specific context]
Describes when/where skills apply for this agent:
- "during implementation"
- "when planning architecture"
- "reviewing code"
- "analyzing security"
- "writing documentation"

### [skill-name]
Exact skill directory name (must match):
- `python-standards`
- `testing-guide`
- `architecture-patterns`
- `security-patterns`
- etc.

### [Action verb]
Context-appropriate verb (see `agent-action-verbs.md`):
- Research agents: "Consult", "Reference", "Use"
- Planning agents: "Apply", "Leverage", "Follow"
- Implementation agents: "Follow", "Adhere to", "Use"
- Review agents: "Validate against", "Check using"

### [purpose]
Concise statement of what skill provides:
- "for code style and conventions"
- "for API endpoint design"
- "for test strategy planning"
- "for security vulnerability scanning"

### [use case]
Specific application context:
- "for function naming and structure"
- "for endpoint versioning"
- "for test coverage strategies"
- "for OWASP Top 10 checks"

## Filled Examples

### Example 1: Implementation Agent
```markdown
## Relevant Skills

You have access to these specialized skills during implementation:

- **python-standards**: Follow for code style, type hints, and docstrings
- **testing-guide**: Reference for TDD implementation patterns
- **observability**: Use for logging and monitoring patterns

Consult the skill-integration-templates skill for formatting guidance.
```

### Example 2: Planning Agent
```markdown
## Relevant Skills

You have access to these specialized skills when planning architecture:

- **architecture-patterns**: Apply for system design and scalability decisions
- **api-design**: Follow for endpoint structure and versioning
- **database-design**: Use for schema planning and normalization

Consult the skill-integration-templates skill for formatting guidance.
```

### Example 3: Review Agent
```markdown
## Relevant Skills

You have access to these specialized skills when reviewing code:

- **code-review**: Validate against quality and maintainability standards
- **python-standards**: Check style, type hints, and documentation
- **security-patterns**: Scan for OWASP vulnerabilities

Consult the skill-integration-templates skill for formatting guidance.
```

## Minimal Template (1-2 Skills)

```markdown
## Relevant Skills

Reference the **[skill-name]** skill for [purpose] and [use case].
```

**Example**:
```markdown
## Relevant Skills

Reference the **testing-guide** skill for TDD patterns and coverage strategies.
```

## Extended Template (6+ Skills)

```markdown
## Relevant Skills

You have access to these specialized skills when [context]:

**Core Skills**:
- **[skill-name]**: [Action verb] [purpose]
- **[skill-name]**: [Action verb] [purpose]

**Optional Skills** (use when applicable):
- **[skill-name]**: [Action verb] for [specific condition]
- **[skill-name]**: [Action verb] for [specific condition]

Consult the skill-integration-templates skill for formatting guidance.
```

## Usage Guidelines

1. **Choose appropriate template** based on skill count (minimal/basic/extended)
2. **Fill variables** with agent-specific values
3. **Select action verbs** matching agent type (see `agent-action-verbs.md`)
4. **Keep section concise** (<30 lines total)
5. **Reference meta-skill** for formatting guidance

## Related Templates

- `intro-sentence-templates.md` - Introduction sentence variations
- `closing-sentence-templates.md` - Closing sentence variations
