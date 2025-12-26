# Agent Skill Reference Template

Template for adding skill references to agent prompts.

## Standard Format

```markdown
---
name: [agent-name]
role: [Role description]
model: sonnet
tools: [Read, Write, Bash, Grep, Edit, Task]
---

# [Agent Name] Agent

[Agent description and purpose]

## Mission

[Primary goal of this agent]

## Workflow

[Step-by-step workflow]

## Relevant Skills

You have access to these specialized skills when [agent task]:

- **[skill-name]**: [One-line description of guidance provided]
- **[skill-name]**: [One-line description of guidance provided]
- **[skill-name]**: [One-line description of guidance provided]

**Note**: Skills load automatically based on task keywords. Consult skills for detailed guidance on specific patterns.

## Quality Standards

[Agent-specific quality standards]

## Output Format

See **agent-output-formats** skill for standardized output format.

[Additional agent content...]
```

## Example: implementer Agent

```markdown
---
name: implementer
role: Code implementation specialist
model: sonnet
tools: [Read, Write, Bash, Grep, Edit, Task]
---

# Implementer Agent

Production-quality code implementation following architecture plans.

## Mission

Write production-quality code following the architecture plan. Make tests pass if they exist.

## Workflow

1. **Review Plan**: Read architecture plan, identify what to build and where
2. **Find Patterns**: Use Grep/Glob to find similar code, match existing style
3. **Implement**: Write code following the plan, handle errors, use clear names
4. **Validate**: Run tests (if exist), verify code works

## Relevant Skills

You have access to these specialized skills when implementing features:

- **python-standards**: Code style, type hints, docstring conventions
- **api-design**: API implementation patterns and error handling
- **database-design**: Database interaction patterns and query optimization
- **testing-guide**: Writing tests alongside implementation (TDD)
- **security-patterns**: Input validation, secure coding practices
- **observability**: Logging, metrics, tracing
- **error-handling-patterns**: Standardized error handling and recovery

**Note**: Skills load automatically based on task keywords. Consult skills for detailed guidance on specific patterns.

## Quality Standards

- Follow existing patterns (consistency matters)
- Write self-documenting code (clear names, simple logic)
- Handle errors explicitly (don't silently fail)
- Add comments only for complex logic

## Output Format

See **agent-output-formats** skill for standardized output format.

## Efficiency Guidelines

**Read selectively**:
- Read ONLY files mentioned in the plan
- Don't explore the entire codebase
- Trust the plan's guidance

**Implement focused**:
- Implement ONE component at a time
- Test after each component
- Stop when tests pass (don't over-engineer)

## Summary

Trust your judgment to write clean, maintainable code that solves the problem effectively.
```

## Benefits of This Format

### Concise (~150 tokens)

```
## Relevant Skills

You have access to these specialized skills when implementing features:

- **python-standards**: Code style, type hints, docstring conventions
- **api-design**: API implementation patterns and error handling
- **testing-guide**: Writing tests alongside implementation (TDD)

**Note**: Skills load automatically based on task keywords.
```

**Token count**: ~100 tokens

### Vs Verbose Inline Guidance (~500 tokens)

```markdown
## Relevant Skills

### Python Code Style
- Use black for formatting
- Add type hints to all functions
- Write Google-style docstrings
- Follow PEP 8 conventions
- [... 200 more words ...]

### API Design Patterns
- Use REST conventions (GET, POST, PUT, DELETE)
- Return appropriate status codes (200, 201, 400, 404, 500)
- [... 200 more words ...]

### Testing Best Practices
- Use pytest for all tests
- Follow Arrange-Act-Assert pattern
- [... 200 more words ...]
```

**Token count**: ~500 tokens

**Savings**: 400 tokens (80% reduction)

## Template Variations

### Research-Heavy Agent

```markdown
## Relevant Skills

You have access to these specialized skills when researching:

- **research-patterns**: Web research methodology, source evaluation
- **documentation-guide**: Documentation standards for research findings

**Note**: Skills load automatically based on task keywords.
```

### Security-Focused Agent

```markdown
## Relevant Skills

You have access to these specialized skills when auditing security:

- **security-patterns**: OWASP Top 10, common vulnerabilities
- **python-standards**: Secure coding practices in Python
- **testing-guide**: Security testing patterns

**Note**: Skills load automatically based on task keywords.
```

### Documentation Agent

```markdown
## Relevant Skills

You have access to these specialized skills when updating documentation:

- **documentation-guide**: Documentation standards, structure, best practices
- **consistency-enforcement**: Maintaining documentation consistency
- **git-workflow**: Commit messages for documentation changes
- **cross-reference-validation**: Validating internal documentation links

**Note**: Skills load automatically based on task keywords.
```

## Anti-Patterns to Avoid

### ❌ Bad: Listing All Skills

```markdown
## Relevant Skills

- **python-standards**
- **api-design**
- **database-design**
- **testing-guide**
- **security-patterns**
- **git-workflow**
- **github-workflow**
- **documentation-guide**
- **observability**
- **error-handling-patterns**
- **architecture-patterns**
- **code-review**
- **research-patterns**
- **semantic-validation**
[... 7 more skills ...]
```

**Problems:**
- Redundant (all skills already discoverable)
- Bloats context (~300 tokens)
- Doesn't help agent prioritize

### ❌ Bad: Duplicating Skill Content

```markdown
## Relevant Skills

### Python Standards

Use black for formatting:
```bash
black src/
```

Add type hints to all functions:
```python
def process(data: List[str]) -> Dict[str, int]:
    pass
```

Write Google-style docstrings:
```python
def calculate(x: int, y: int) -> int:
    """Calculate sum of two integers.

    Args:
        x: First integer
        y: Second integer

    Returns:
        Sum of x and y
    """
    return x + y
```

[... 400 more words ...]
```

**Problems:**
- Duplicates python-standards skill content
- Wastes ~500 tokens
- Conflicting guidance risk
- Maintenance burden (update skill AND agent)

### ✅ Good: Concise Skill References

```markdown
## Relevant Skills

You have access to these specialized skills when implementing features:

- **python-standards**: Code style, type hints, docstring conventions
- **testing-guide**: Pytest patterns, TDD workflow
- **security-patterns**: Input validation, secure coding

**Note**: Skills load automatically based on task keywords.
```

**Benefits:**
- Concise (~100 tokens)
- No duplication
- Clear what's available
- Progressive disclosure handles details

## Integration Checklist

When adding skill references to an agent:

- [ ] List 3-7 most relevant skills (not all 21)
- [ ] Keep each skill description to one line
- [ ] Add progressive disclosure note
- [ ] Remove inline skill content duplication
- [ ] Use consistent skill names (match SKILL.md)
- [ ] Verify token reduction (~300-500 tokens saved)
- [ ] Test that skills activate correctly

## Summary

Use this template to add efficient skill references to agent prompts:
- **Concise**: 3-7 relevant skills, one line each
- **Complete**: All specialized knowledge accessible
- **Efficient**: ~100 tokens vs ~500 tokens inline
- **Maintainable**: Update skills, not agents
