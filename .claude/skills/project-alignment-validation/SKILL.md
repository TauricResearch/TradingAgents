---
name: project-alignment-validation
version: 1.0.0
type: knowledge
description: Semantic validation patterns for PROJECT.md alignment (GOALS, SCOPE, CONSTRAINTS, ARCHITECTURE)
keywords: alignment, PROJECT.md, validation, GOALS, SCOPE, CONSTRAINTS, ARCHITECTURE, semantic, gap, conflict, resolution
auto_activate: true
allowed-tools: [Read, Grep, Glob]
---

# Project Alignment Validation Skill

Comprehensive patterns for validating alignment between features, code, and PROJECT.md. Focuses on semantic validation (intent and goals) rather than literal pattern matching.

## When This Skill Activates

- Validating feature alignment with PROJECT.md
- Assessing gaps between current state and goals
- Resolving conflicts between documentation and implementation
- Checking GOALS, SCOPE, CONSTRAINTS, ARCHITECTURE compliance
- Keywords: "alignment", "PROJECT.md", "validation", "GOALS", "SCOPE", "semantic", "gap"

---

## Core Validation Approach

### Semantic Validation Philosophy

**Semantic validation** focuses on understanding the *intent* and *purpose* behind requirements, not just literal text matching.

**Key Principles**:
1. **Intent over Syntax**: Validate that features serve project goals, not just match keywords
2. **Context-Aware**: Consider project phase, constraints, and strategic direction
3. **Progressive Assessment**: Start with high-level goals, drill down to details
4. **Graceful Gaps**: Identify gaps without blocking progress; prioritize by impact

**Contrast with Literal Validation**:
- ❌ **Literal**: "Feature must contain keyword 'authentication'"
- ✅ **Semantic**: "Feature must support project's user management goals"

---

## PROJECT.md Structure

### Four Core Sections

Every PROJECT.md should define:

1. **GOALS**: Strategic objectives and desired outcomes
2. **SCOPE**: What's in scope (and explicitly out of scope)
3. **CONSTRAINTS**: Technical, resource, and policy limitations
4. **ARCHITECTURE**: High-level design principles and patterns

### Validation Checklist

For each feature, validate against all four sections:

```markdown
## Alignment Checklist

### GOALS Alignment
- [ ] Feature serves at least one project goal
- [ ] Feature doesn't conflict with any goals
- [ ] Feature priority matches goal priority
- [ ] Success metrics align with goal metrics

### SCOPE Alignment
- [ ] Feature is explicitly in scope
- [ ] Feature doesn't overlap with out-of-scope items
- [ ] Feature respects scope boundaries
- [ ] Feature dependencies are in scope

### CONSTRAINTS Alignment
- [ ] Feature respects technical constraints
- [ ] Feature works within resource constraints
- [ ] Feature complies with policy constraints
- [ ] Feature considers timeline constraints

### ARCHITECTURE Alignment
- [ ] Feature follows architectural patterns
- [ ] Feature integrates with existing components
- [ ] Feature respects design principles
- [ ] Feature maintains architectural consistency
```

See: `docs/alignment-checklist.md` for detailed checklist with examples

---

## Gap Assessment Methodology

### Identify Gaps

Gaps occur when current state doesn't match desired state defined in PROJECT.md.

**Types of Gaps**:
1. **Feature Gaps**: Missing functionality needed to achieve goals
2. **Documentation Gaps**: PROJECT.md doesn't reflect actual implementation
3. **Constraint Gaps**: Implementation violates stated constraints
4. **Architectural Gaps**: Code doesn't follow design principles

### Prioritize Gaps

Not all gaps are equal. Prioritize by:

**Impact Assessment**:
- **Critical**: Blocks primary goals, violates hard constraints
- **High**: Significantly delays goals, creates technical debt
- **Medium**: Slows progress, reduces quality
- **Low**: Minor inconvenience, cosmetic issues

**Effort Estimation**:
- **Quick Win**: High impact, low effort (prioritize)
- **Strategic**: High impact, high effort (plan carefully)
- **Tactical**: Medium impact, medium effort (schedule)
- **Defer**: Low impact, high effort (defer or drop)

### Document Gaps

Use standardized gap assessment template:

```markdown
## Gap Assessment

### Gap Summary
- **Type**: [Feature/Documentation/Constraint/Architectural]
- **Impact**: [Critical/High/Medium/Low]
- **Effort**: [Quick Win/Strategic/Tactical/Defer]

### Current State
[Describe what exists today]

### Desired State
[Describe what PROJECT.md defines]

### Gap Details
[Explain the specific differences]

### Recommended Action
[Propose concrete steps to close gap]

### Dependencies
[List any prerequisites or blockers]
```

See: `docs/gap-assessment-methodology.md` for complete methodology

---

## Conflict Resolution Patterns

### Detect Conflicts

Conflicts arise when:
- Feature serves one goal but violates another
- Feature is in scope but violates constraints
- Implementation follows architecture but misses goals
- Documentation and code tell different stories

### Resolution Strategies

**Strategy 1: Update PROJECT.md** (Documentation is wrong)
- Current state is correct, PROJECT.md is outdated
- Update PROJECT.md to reflect actual strategic direction
- Validate changes with stakeholders

**Strategy 2: Modify Feature** (Implementation is wrong)
- PROJECT.md is correct, feature needs adjustment
- Refactor feature to align with goals/scope/constraints
- May require re-planning or re-architecting

**Strategy 3: Negotiate Compromise** (Both partially correct)
- Find middle ground that serves goals within constraints
- May require adjusting both PROJECT.md and implementation
- Document trade-offs and rationale

**Strategy 4: Escalate Decision** (Requires stakeholder input)
- Conflict involves strategic direction or priorities
- Present options with trade-offs to decision makers
- Document decision and update PROJECT.md

See: `docs/conflict-resolution-patterns.md` for detailed resolution workflows

---

## Progressive Disclosure

This skill provides layered documentation:

### Always Available (Frontmatter)
- Skill name and description
- Keywords for auto-activation
- Quick reference to core concepts

### Available in Full Content
- Detailed alignment checklist
- Semantic validation approach
- Gap assessment methodology
- Conflict resolution patterns
- Templates for reports and assessments
- Real-world examples and scenarios

### Load Full Content When Needed
- Creating alignment reports
- Assessing project health
- Resolving complex conflicts
- Onboarding new projects
- Validating strategic changes

---

## Documentation Resources

### Comprehensive Guides
- `docs/alignment-checklist.md` - Standard validation steps for GOALS/SCOPE/CONSTRAINTS/ARCHITECTURE
- `docs/semantic-validation-approach.md` - Semantic vs literal validation philosophy
- `docs/gap-assessment-methodology.md` - Identify, prioritize, and document gaps
- `docs/conflict-resolution-patterns.md` - Strategies for resolving alignment conflicts

### Templates
- `templates/alignment-report-template.md` - Standard structure for alignment reports
- `templates/gap-assessment-template.md` - Gap documentation template
- `templates/conflict-resolution-template.md` - Conflict resolution workflow

### Examples
- `examples/alignment-scenarios.md` - Common scenarios and recommended fixes
- `examples/misalignment-examples.md` - Real-world misalignment cases
- `examples/project-md-structure-example.md` - Well-structured PROJECT.md

---

## Integration Points

### Agents
- **alignment-validator**: Use checklist for quick validation
- **alignment-analyzer**: Use gap assessment for detailed analysis
- **project-progress-tracker**: Use GOALS validation for progress tracking

### Hooks
- **validate_project_alignment.py**: Use checklist for pre-commit validation
- **auto_update_project_progress.py**: Use GOALS tracking patterns
- **enforce_pipeline_complete.py**: Use alignment patterns for feature validation

### Libraries
- **alignment_assessor.py**: Use gap assessment methodology
- **project_md_updater.py**: Use conflict resolution patterns
- **brownfield_retrofit.py**: Use alignment checklist for retrofit analysis

---

## Best Practices

1. **Validate Early**: Check alignment before implementation, not after
2. **Document Decisions**: Record why features align or don't align
3. **Update Iteratively**: PROJECT.md should evolve with project understanding
4. **Prioritize Gaps**: Not all gaps are critical; focus on high-impact items
5. **Semantic First**: Understand intent before applying validation rules
6. **Graceful Degradation**: Alignment issues are warnings, not blockers (unless critical)

---

## Success Criteria

Feature validation is successful when:
- ✓ Feature clearly serves at least one project goal
- ✓ Feature is explicitly in scope (or scope updated to include it)
- ✓ Feature respects all constraints (or constraints documented as trade-offs)
- ✓ Feature follows architectural patterns (or deviations justified)
- ✓ Gaps are identified, prioritized, and tracked
- ✓ Conflicts are resolved with documented rationale

---

**Last Updated**: 2025-11-16
**Version**: 1.0.0
**Related Skills**: semantic-validation, file-organization, research-patterns, project-management
