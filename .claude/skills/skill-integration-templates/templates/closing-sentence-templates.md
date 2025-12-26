# Closing Sentence Templates

Variations for closing the "Relevant Skills" section, pointing to skill-integration-templates for formatting guidance.

## Standard Templates

### Template 1: Direct Reference (Recommended)
```markdown
Consult the skill-integration-templates skill for formatting guidance.
```

**When to Use**: Default closing for most agents

### Template 2: Detailed Reference
```markdown
See skill-integration-templates skill for skill reference syntax and integration best practices.
```

**When to Use**: When emphasizing both syntax and practices

### Template 3: Action-Oriented
```markdown
Reference skill-integration-templates skill when structuring skill sections.
```

**When to Use**: When emphasizing the action of structuring

### Template 4: Conditional
```markdown
Use skill-integration-templates skill to format skill references correctly.
```

**When to Use**: When emphasizing correct formatting

## Minimal Closings (1-2 Skills)

### Template 5: Implicit Reference
```markdown
See skill-integration-templates skill for formatting.
```

**When to Use**: Minimal skill sections where brevity is key

### Template 6: Guidance Focus
```markdown
Consult skill-integration-templates skill for formatting guidelines.
```

**When to Use**: Single skill reference needing formatting guidance

## Extended Closings (6+ Skills)

### Template 7: Comprehensive Reference
```markdown
For skill reference syntax, action verbs, and integration patterns, consult the skill-integration-templates skill.
```

**When to Use**: Extended skill sections with many references

### Template 8: Multi-Resource
```markdown
See skill-integration-templates skill for:
- Skill reference syntax patterns
- Action verb selection guidelines
- Progressive disclosure best practices
```

**When to Use**: Complex skill sections needing detailed formatting guidance (rare)

## No-Closing Pattern (Alternative)

Some agents may omit the closing sentence if:
- Only 1-2 skills referenced
- Minimal skill section
- Agent prompt is highly constrained for token budget

**Example** (minimal, no closing):
```markdown
## Relevant Skills

Reference the **testing-guide** skill for TDD patterns.
```

**Use Sparingly**: Closing sentence is recommended for consistency

## Selection Guidelines

### Choose Based on Agent Complexity

**Simple Agents** (3-5 skills):
```markdown
Consult the skill-integration-templates skill for formatting guidance.
```

**Complex Agents** (6+ skills):
```markdown
See skill-integration-templates skill for skill reference syntax and integration best practices.
```

**Minimal Agents** (1-2 skills):
```markdown
See skill-integration-templates skill for formatting.
```

### Choose Based on Emphasis

**Formatting Emphasis**:
```markdown
Use skill-integration-templates skill to format skill references correctly.
```

**Syntax Emphasis**:
```markdown
Reference skill-integration-templates skill when structuring skill sections.
```

**Best Practices Emphasis**:
```markdown
See skill-integration-templates skill for skill reference syntax and integration best practices.
```

## Examples by Agent

### implementer.md
```markdown
Consult the skill-integration-templates skill for formatting guidance.
```

### planner.md
```markdown
Consult the skill-integration-templates skill for formatting guidance.
```

### reviewer.md
```markdown
See skill-integration-templates skill for skill reference syntax and integration best practices.
```

### security-auditor.md
```markdown
Consult the skill-integration-templates skill for formatting guidance.
```

### doc-master.md
```markdown
Reference skill-integration-templates skill when structuring skill sections.
```

### researcher.md
```markdown
Consult the skill-integration-templates skill for formatting guidance.
```

## Customization Tips

### Keep It Concise
Prefer shorter closings unless complexity demands detail:
```markdown
✓ Consult the skill-integration-templates skill for formatting guidance.
✗ For comprehensive guidance on skill reference syntax, action verb selection,
  progressive disclosure patterns, and integration best practices, please
  consult the skill-integration-templates skill documentation.
```

### Use Consistent Verb
Match the verb to your introduction:
- If intro uses "Consult", closing can use "Consult"
- If intro uses "Reference", closing can use "Reference"
- If intro uses "Use", closing can use "Use"

**Example**:
```markdown
## Relevant Skills

Consult these skills during implementation:
- **python-standards**: Follow for code style

Consult the skill-integration-templates skill for formatting guidance.
```

### Be Direct
Point directly to the skill without preamble:
```markdown
✓ Consult the skill-integration-templates skill for formatting guidance.
✗ If you need additional help with formatting, you can consult the
  skill-integration-templates skill for detailed guidance.
```

## Common Mistakes

### Mistake 1: Too Verbose
```markdown
For additional information about how to properly format skill references,
including syntax patterns, action verb selection, and progressive disclosure
usage, please refer to the comprehensive documentation in the
skill-integration-templates skill.
```

**Fix**: Be concise
```markdown
Consult the skill-integration-templates skill for formatting guidance.
```

### Mistake 2: Missing Skill Name
```markdown
See the templates skill for formatting guidance.
```

**Fix**: Use exact skill name
```markdown
Consult the skill-integration-templates skill for formatting guidance.
```

### Mistake 3: Ambiguous Reference
```markdown
See related documentation for formatting.
```

**Fix**: Explicitly name the skill
```markdown
Consult the skill-integration-templates skill for formatting guidance.
```

### Mistake 4: No Closing (when needed)
```markdown
## Relevant Skills

- **python-standards**: Follow for code style
- **testing-guide**: Reference for TDD
```

**Fix**: Add closing sentence
```markdown
## Relevant Skills

- **python-standards**: Follow for code style
- **testing-guide**: Reference for TDD

Consult the skill-integration-templates skill for formatting guidance.
```

## Quick Reference

| Agent Type | Recommended Closing |
|-----------|---------------------|
| Simple (3-5 skills) | "Consult the skill-integration-templates skill for formatting guidance." |
| Complex (6+ skills) | "See skill-integration-templates skill for skill reference syntax and integration best practices." |
| Minimal (1-2 skills) | "See skill-integration-templates skill for formatting." or omit |

## Related Templates

- `skill-section-template.md` - Complete section template
- `intro-sentence-templates.md` - Introduction sentence variations
