---
name: agent-output-formats
version: 1.0.0
type: knowledge
description: Standardized output formats for research, planning, implementation, and review agents. Use when generating agent outputs or parsing agent responses.
keywords: output, format, research, planning, implementation, review, agent response, findings, recommendations, architecture, changes
auto_activate: true
allowed-tools: [Read]
---

# Agent Output Formats Skill

Standardized output formats for all agent types to ensure consistent communication and parsing across the autonomous development workflow.

## When This Skill Activates

- Generating agent outputs
- Parsing agent responses
- Formatting research findings
- Creating planning documents
- Reporting implementation results
- Writing code reviews
- Keywords: "output", "format", "research", "planning", "implementation", "review"

---

## Research Agent Output Format

Research agents (e.g., researcher, issue-creator, brownfield-analyzer) should structure outputs with these sections:

### Template

```markdown
## Patterns Found

[List of discovered patterns with examples]

- **Pattern Name**: Description
  - Example: Code snippet or reference
  - Use case: When to apply this pattern

## Best Practices

[Industry best practices and recommendations]

- **Practice Name**: Description
  - Benefit: Why this matters
  - Implementation: How to apply

## Security Considerations

[Security implications and requirements]

- **Security Concern**: Description
  - Risk: Potential vulnerabilities
  - Mitigation: How to address

## Recommendations

[Actionable recommendations for implementation]

1. **Recommendation**: Detailed guidance
   - Priority: High/Medium/Low
   - Effort: Time estimate
   - Impact: Expected benefit
```

### Example Output

See `examples/research-output-example.md` for a complete example.

---

## Planning Agent Output Format

Planning agents (e.g., planner, migration-planner, setup-wizard) should structure outputs with these sections:

### Template

```markdown
## Feature Summary

[Brief description of what will be built]

**Goal**: What this achieves
**Scope**: What's included/excluded
**Success Criteria**: How to measure success

## Architecture

[High-level design and component relationships]

**Components**: List of major components
**Data Flow**: How data moves through system
**Integration Points**: External dependencies

## Components

[Detailed component specifications]

### Component 1: [Name]
- **Purpose**: What it does
- **Responsibilities**: Core functions
- **Dependencies**: What it needs
- **Files**: Where it lives

## Implementation Plan

[Step-by-step implementation guide]

**Phase 1**: [Description]
1. Step one
2. Step two

**Phase 2**: [Description]
1. Step one
2. Step two

## Risks and Mitigations

[Potential issues and how to address them]

- **Risk**: Description
  - **Impact**: Severity and consequences
  - **Mitigation**: How to prevent or handle
```

### Example Output

See `examples/planning-output-example.md` for a complete example.

---

## Implementation Agent Output Format

Implementation agents (e.g., implementer, retrofit-executor) should structure outputs with these sections:

### Template

```markdown
## Changes Made

[Summary of what was implemented]

**Feature**: What was built
**Approach**: How it was implemented
**Design Decisions**: Key choices made

## Files Modified

[List of changed files with descriptions]

### Created Files
- `path/to/file.py`: Description of new file
- `path/to/test.py`: Test coverage

### Modified Files
- `path/to/existing.py`: Changes made
  - Added: New functionality
  - Modified: Updated behavior
  - Removed: Deprecated code

## Tests Updated

[Test coverage changes]

**New Tests**:
- Test file: What it covers
- Coverage: Percentage or lines

**Updated Tests**:
- Test file: What changed
- Reason: Why it was needed

## Next Steps

[Follow-up actions and recommendations]

1. **Action**: What needs to happen next
   - Owner: Who should do it
   - Priority: Urgency level
   - Blockers: Any dependencies
```

### Example Output

See `examples/implementation-output-example.md` for a complete example.

---

## Review Agent Output Format

Review agents (e.g., reviewer, security-auditor, quality-validator) should structure outputs with these sections:

### Template

```markdown
## Findings

[Overview of review results]

**Reviewed**: What was examined
**Scope**: What was checked
**Summary**: High-level results

## Code Quality

[Code quality assessment]

### Strengths
- **Aspect**: What's done well
  - Evidence: Specific examples

### Areas for Improvement
- **Issue**: What needs work
  - Severity: Critical/Major/Minor
  - Recommendation: How to fix
  - Location: Where the issue is

## Security

[Security analysis]

### Security Strengths
- **Protection**: What's secure
  - Implementation: How it's done

### Security Concerns
- **Vulnerability**: Potential issue
  - CWE Reference: Standard classification
  - Risk Level: High/Medium/Low
  - Remediation: How to fix

## Documentation

[Documentation assessment]

### Documentation Completeness
- **Aspect**: What's documented
  - Quality: How well it's done

### Documentation Gaps
- **Missing**: What needs docs
  - Priority: How important
  - Suggestion: What to add

## Verdict

[Final recommendation]

**Status**: ✅ APPROVED / ⚠️ APPROVED WITH CHANGES / ❌ NEEDS REVISION

**Rationale**: Why this verdict
**Blockers**: Must-fix issues (if any)
**Suggestions**: Nice-to-have improvements
```

### Example Output

See `examples/review-output-example.md` for a complete example.

---

## Commit Message Format

Commit message generator agents should follow conventional commits:

### Template

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Formatting, no code change
- `refactor`: Code restructuring
- `test`: Adding tests
- `chore`: Maintenance tasks

### Example

```
feat(skills): add agent-output-formats skill for standardized outputs

Extracts duplicated output format specifications from 15 agent prompts
into a reusable skill package following progressive disclosure architecture.

Token savings: ~3,000 tokens (200 tokens per agent × 15 agents)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Pull Request Format

PR description generator agents should follow this structure:

### Template

```markdown
## Summary

[Brief description of changes]

- Key change 1
- Key change 2
- Key change 3

## Test Plan

- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing completed
- [ ] Documentation updated

## Related Issues

Closes #XXX

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

---

## Usage Guidelines

### For Agent Authors

When creating or updating agent prompts:

1. **Reference this skill** in the "Relevant Skills" section
2. **Remove duplicate format specifications** from agent prompts
3. **Trust progressive disclosure** - full content loads when needed
4. **Use consistent terminology** from this skill

### For Claude

When executing agents:

1. **Load this skill** when keywords match ("output", "format", etc.)
2. **Follow format templates** for structured outputs
3. **Include all required sections** for agent type
4. **Maintain consistency** across similar agents

### Token Savings

By centralizing output formats in this skill:

- **Before**: ~250 tokens per agent for format specification
- **After**: ~50 tokens for skill reference
- **Savings**: ~200 tokens per agent
- **Total**: ~3,000 tokens across 15 agents (8-12% reduction)

---

## Progressive Disclosure

This skill uses Claude Code 2.0+ progressive disclosure architecture:

- **Metadata** (frontmatter): Always loaded (~150 tokens)
- **Full content**: Loaded only when keywords match
- **Result**: Efficient context usage, scales to 100+ skills

When you use terms like "output format", "research findings", "planning document", or "code review", Claude Code automatically loads the full skill content to provide detailed guidance.

---

## Examples

Complete example outputs are available in the `examples/` directory:

- `research-output-example.md`: Sample research agent output
- `planning-output-example.md`: Sample planning agent output
- `implementation-output-example.md`: Sample implementation agent output
- `review-output-example.md`: Sample review agent output

Refer to these examples when generating agent outputs to ensure consistency and completeness.
