# Introduction Sentence Templates

Variations for introducing the "Relevant Skills" section in agent prompts.

## Standard Templates

### Template 1: Context-Based (Recommended)
```markdown
You have access to these specialized skills when [agent-specific context]:
```

**Examples**:
- "You have access to these specialized skills when planning architecture:"
- "You have access to these specialized skills during implementation:"
- "You have access to these specialized skills when reviewing code:"
- "You have access to these specialized skills during security analysis:"

**When to Use**: Most agent types (implementation, planning, review, security)

### Template 2: Purpose-Based
```markdown
The following skills are available for [purpose]:
```

**Examples**:
- "The following skills are available for architecture planning:"
- "The following skills are available for code implementation:"
- "The following skills are available for quality validation:"

**When to Use**: When emphasizing the purpose over context

### Template 3: Phase-Based
```markdown
Consult these skills during [phase/activity]:
```

**Examples**:
- "Consult these skills during the planning phase:"
- "Consult these skills during code review:"
- "Consult these skills during security scanning:"

**When to Use**: Workflow-oriented agents with distinct phases

### Template 4: Need-Based
```markdown
Reference these skills for [specific need]:
```

**Examples**:
- "Reference these skills for design decisions:"
- "Reference these skills for code quality:"
- "Reference these skills for security compliance:"

**When to Use**: When skills address a specific need

## Minimal Introduction (1-2 Skills)

### Template 5: Direct Reference
```markdown
Reference the **[skill-name]** skill for [purpose].
```

**Examples**:
- "Reference the **testing-guide** skill for TDD patterns and coverage strategies."
- "Consult the **python-standards** skill for code style and type hints."

**When to Use**: Single skill reference or very minimal section

### Template 6: Conditional Reference
```markdown
When [condition], consult the **[skill-name]** skill for [guidance].
```

**Examples**:
- "When planning database changes, consult the **database-design** skill for normalization patterns."
- "When implementing APIs, reference the **api-design** skill for endpoint structure."

**When to Use**: Skills apply only in specific conditions

## Extended Introduction (6+ Skills)

### Template 7: Categorized Introduction
```markdown
You have access to these specialized skills when [context]:

**Core Skills**:
[skill list]

**Optional Skills** (use when applicable):
[skill list]
```

**Example**:
```markdown
You have access to these specialized skills during implementation:

**Core Skills**:
- **python-standards**: Follow for code style
- **testing-guide**: Reference for TDD

**Optional Skills** (use when applicable):
- **observability**: Use when adding logging
- **security-patterns**: Check when handling sensitive data
```

**When to Use**: Many skills (6+) with varying importance

## Selection Guidelines

### Choose Based on Agent Type

**Research Agents**:
```markdown
Consult these skills during research and pattern discovery:
```

**Planning Agents**:
```markdown
You have access to these specialized skills when planning architecture:
```

**Implementation Agents**:
```markdown
You have access to these specialized skills during implementation:
```

**Review Agents**:
```markdown
You have access to these specialized skills when reviewing code:
```

**Documentation Agents**:
```markdown
Reference these skills for documentation standards:
```

**Security Agents**:
```markdown
You have access to these specialized skills during security analysis:
```

### Choose Based on Skill Count

**1-2 Skills**: Use Template 5 or 6 (minimal, direct reference)
**3-5 Skills**: Use Template 1, 2, 3, or 4 (standard introduction)
**6+ Skills**: Use Template 7 (categorized introduction)

## Customization Tips

### Add Agent-Specific Context
Instead of:
```markdown
You have access to these specialized skills:
```

Use:
```markdown
You have access to these specialized skills when implementing features:
```

### Be Specific About When
Instead of:
```markdown
The following skills are available:
```

Use:
```markdown
The following skills are available during the planning phase:
```

### Match Agent Voice
For active agents (implementer, planner):
```markdown
You have access to these specialized skills when [doing action]:
```

For advisory agents (reviewer, advisor):
```markdown
Consult these skills for [validation/guidance]:
```

## Examples by Agent

### implementer.md
```markdown
You have access to these specialized skills during implementation:
```

### planner.md
```markdown
You have access to these specialized skills when planning architecture:
```

### reviewer.md
```markdown
You have access to these specialized skills when reviewing code:
```

### security-auditor.md
```markdown
You have access to these specialized skills during security analysis:
```

### doc-master.md
```markdown
Reference these skills for documentation standards:
```

### researcher.md
```markdown
Consult these skills during research and pattern discovery:
```

## Related Templates

- `skill-section-template.md` - Complete section template
- `closing-sentence-templates.md` - Closing sentence variations
