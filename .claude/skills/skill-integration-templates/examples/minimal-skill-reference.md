# Minimal Skill Reference Example

Minimal pattern for agents with 1-2 skill references.

## Single Skill Reference

### Example 1: Direct Reference
```markdown
## Relevant Skills

Reference the **testing-guide** skill for TDD patterns and coverage strategies.
```

**Token Count**: ~20 tokens

**When to Use**: Agent primarily needs one skill

### Example 2: Conditional Reference
```markdown
## Relevant Skills

When planning database changes, consult the **database-design** skill for normalization and indexing patterns.
```

**Token Count**: ~25 tokens

**When to Use**: Skill applies only in specific conditions

## Two Skill References

### Example 3: Minimal List
```markdown
## Relevant Skills

- **python-standards**: Follow for code style and type hints
- **testing-guide**: Reference for TDD implementation
```

**Token Count**: ~30 tokens

**When to Use**: Agent needs exactly two skills, minimal approach preferred

### Example 4: Descriptive
```markdown
## Relevant Skills

Consult these skills during implementation:
- **python-standards**: Code style and conventions
- **observability**: Logging patterns
```

**Token Count**: ~35 tokens

**When to Use**: Two skills with brief context

## No Closing Sentence Pattern

For minimal sections (1-2 skills), the closing sentence referencing skill-integration-templates can be omitted:

### Example 5: Ultra-Minimal
```markdown
## Relevant Skills

Reference the **testing-guide** skill for TDD patterns.
```

**Token Count**: ~15 tokens

**When to Use**: Extreme token budget constraints

## When to Use Minimal Pattern

Use minimal skill references when:
1. **Agent has 1-2 primary skills** - Not all agents need many skills
2. **Token budget is tight** - Every token counts for concise agents
3. **Skills are obvious** - Agent's role clearly maps to specific skills
4. **Simplicity is preferred** - Avoid unnecessary structure

## When to Use Standard Pattern

Use standard pattern (see `skill-section-template.md`) when:
1. **Agent has 3+ skills** - Structure improves readability
2. **Token budget allows** - ~90-100 tokens is acceptable
3. **Context is needed** - Intro/closing sentences add clarity
4. **Consistency matters** - Most agents use standard pattern

## Real-World Example

### quality-validator.md (Minimal Pattern)
```markdown
## Relevant Skills

You have access to these specialized skills when validating features:

- **testing-guide**: Validate test coverage and quality
- **code-review**: Assess code quality metrics

See skill-integration-templates skill for formatting.
```

**Token Count**: ~50 tokens

**Why Minimal**:
- Only 2 core skills needed
- Agent has focused mission
- Token efficiency matters

## Comparison: Minimal vs. Standard

### Minimal (1-2 Skills)
```markdown
## Relevant Skills

Reference the **testing-guide** skill for TDD patterns.
```
**Tokens**: ~15-30

**Pros**: Extremely concise, no unnecessary structure
**Cons**: No meta-skill reference, less guidance

### Standard (3-5 Skills)
```markdown
## Relevant Skills

You have access to these specialized skills during implementation:

- **python-standards**: Follow for code style
- **testing-guide**: Reference for TDD
- **observability**: Use for logging

Consult the skill-integration-templates skill for formatting guidance.
```
**Tokens**: ~70-90

**Pros**: Clear structure, meta-skill reference, consistent format
**Cons**: Higher token count

## Guidelines

### Omit Closing Sentence If:
- Only 1-2 skills referenced
- Agent has severe token constraints
- Simplicity is paramount

### Include Closing Sentence If:
- 3+ skills referenced
- Following standard pattern
- Consistency with other agents matters

## Examples by Agent Type

### Research Agent (Single Skill)
```markdown
## Relevant Skills

Consult the **research-patterns** skill for search strategies and information gathering techniques.
```

### Utility Agent (Two Skills)
```markdown
## Relevant Skills

- **file-organization**: Follow for project structure standards
- **semantic-validation**: Use for alignment checking
```

### Minimal Workflow Agent (Conditional)
```markdown
## Relevant Skills

When validating PROJECT.md alignment, reference the **semantic-validation** skill.
```

## Related Examples

- `planner-skill-section.md` - Standard multi-skill example
- `implementer-skill-section.md` - Standard implementation example
