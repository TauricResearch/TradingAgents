---
name: skill-integration
version: 1.0.0
type: knowledge
description: Standardized patterns for how agents discover, reference, and compose skills using progressive disclosure architecture
keywords: skill, skills, progressive disclosure, skill discovery, skill composition, agent integration, skill reference
auto_activate: true
allowed-tools: [Read]
---

# Skill Integration Skill

Standardized patterns for how agents discover, reference, and use skills effectively in Claude Code 2.0+.

## When This Activates
- Working with agent prompts or skill references
- Implementing new agents or skills
- Understanding skill architecture
- Optimizing context usage
- Keywords: "skill", "progressive disclosure", "skill discovery", "agent integration"

## Overview

The skill-integration skill provides standardized patterns for:
- **Skill discovery**: How agents find relevant skills based on task keywords
- **Progressive disclosure**: Loading skill content on-demand to prevent context bloat
- **Skill composition**: Combining multiple skills for complex tasks
- **Skill reference format**: Consistent way agents reference skills in prompts

## Progressive Disclosure Architecture

### What It Is
Progressive disclosure is a design pattern where:
1. **Metadata stays in context** - Skill names, descriptions, keywords (~50 tokens)
2. **Full content loads on-demand** - Detailed guidance only when needed (~5,000-15,000 tokens)
3. **Context stays efficient** - Support 50-100+ skills without bloat

### Why It Matters
**Without progressive disclosure:**
- 20 skills × 500 tokens each = 10,000 tokens in context
- Context bloated before agent even starts work
- Can't scale beyond 20-30 skills

**With progressive disclosure:**
- 100 skills × 50 tokens each = 5,000 tokens in context
- Full skill content only loads when relevant
- Scales to 100+ skills without performance issues

### How It Works

```
┌─────────────────────────────────────────────────────────┐
│                   Agent Context                          │
│                                                          │
│  Agent Prompt: ~500 tokens                              │
│  Skill Metadata: 20 skills × 50 tokens = 1,000 tokens  │
│  Task Description: ~200 tokens                          │
│                                                          │
│  Total: ~1,700 tokens (efficient!)                      │
└─────────────────────────────────────────────────────────┘
                          │
                          │ Agent encounters keyword
                          │ matching skill
                          ↓
┌─────────────────────────────────────────────────────────┐
│              Skill Content Loads On-Demand               │
│                                                          │
│  Skill Full Content: ~5,000 tokens                      │
│  Loaded only when needed                                │
│                                                          │
│  Total context: 1,700 + 5,000 = 6,700 tokens           │
│  Still efficient!                                        │
└─────────────────────────────────────────────────────────┘
```

## Skill Discovery Mechanism

### Keyword-Based Activation

Skills auto-activate when task keywords match skill keywords:

**Example: testing-guide skill**
```yaml
---
name: testing-guide
keywords: test, testing, pytest, tdd, coverage, fixture
auto_activate: true
---
```

**Task triggers skill:**
- "Write tests for user authentication" → matches "test", "testing"
- "Add pytest fixtures for database" → matches "pytest", "fixture"
- "Improve test coverage to 90%" → matches "testing", "coverage"

### Manual Skill Reference

Agents can explicitly reference skills in their prompts:

```markdown
## Relevant Skills

You have access to these specialized skills:

- **testing-guide**: Pytest patterns, TDD workflow, coverage strategies
- **python-standards**: Code style, type hints, docstring conventions
- **security-patterns**: Input validation, authentication, OWASP compliance
```

**Benefits:**
- Agent knows which skills are available for its domain
- Progressive disclosure still applies (metadata in context, content on-demand)
- Helps agent make better decisions about when to consult specialized knowledge

## Skill Composition

### Combining Multiple Skills

Complex tasks often require multiple skills:

**Example: Implementing authenticated API endpoint**

```markdown
Task: "Implement JWT authentication for user API endpoint"

Skills activated:
1. **api-design** - REST API patterns, endpoint structure
2. **security-patterns** - JWT validation, authentication best practices
3. **python-standards** - Code style, type hints
4. **testing-guide** - Security testing patterns
5. **documentation-guide** - API documentation standards

Progressive disclosure:
- All 5 skill metadata in context (~250 tokens)
- Full content loads only as needed (~20,000 tokens total)
- Agent accesses relevant sections progressively
```

### Skill Layering

Skills can reference other skills:

```markdown
## Relevant Skills

- **testing-guide**: Testing patterns (references python-standards for test code style)
- **security-patterns**: Security best practices (references api-design for secure endpoints)
- **documentation-guide**: Documentation standards (references python-standards for docstrings)
```

**Benefits:**
- Natural skill hierarchy
- Agent discovers related skills automatically
- No need to list every transitive dependency

## Standardized Agent Skill References

### Template Format

Every agent should include a "Relevant Skills" section:

```markdown
## Relevant Skills

You have access to these specialized skills when [agent task]:

- **[skill-name]**: [Brief description of what guidance this provides]
- **[skill-name]**: [Brief description of what guidance this provides]
- **[skill-name]**: [Brief description of what guidance this provides]

**Note**: Skills load automatically based on task keywords. Consult skills for detailed guidance on specific patterns.
```

### Best Practices

✅ **Do's:**
- List 3-7 most relevant skills for agent's domain
- Use consistent skill names (match SKILL.md `name:` field)
- Keep descriptions concise (one line)
- Add note about progressive disclosure
- Trust skill discovery mechanism

❌ **Don'ts:**
- List all 21 skills (redundant, bloats context)
- Duplicate skill content in agent prompt
- Provide detailed skill guidance inline
- Override skill content with conflicting guidance
- Assume skills are "just documentation"

### Example: implementer Agent

```markdown
## Relevant Skills

You have access to these specialized skills when implementing features:

- **python-standards**: Code style, type hints, docstring conventions
- **api-design**: REST API patterns, error handling
- **database-design**: Query optimization, schema patterns
- **testing-guide**: Writing tests alongside implementation
- **security-patterns**: Input validation, secure coding practices
- **observability**: Logging, metrics, tracing
- **error-handling-patterns**: Standardized error handling and recovery

**Note**: Skills load automatically based on task keywords. Consult skills for detailed guidance on specific patterns.
```

**Token impact:**
- Before: 500+ tokens of inline guidance
- After: 150 tokens referencing skills
- Savings: 350 tokens (70% reduction)

## Token Reduction Benefits

### Per-Agent Savings

Typical agent with verbose "Relevant Skills" section:

**Before (verbose inline guidance):**
```markdown
## Relevant Skills

### Testing Patterns
- Use pytest for all tests
- Follow Arrange-Act-Assert pattern
- Use fixtures for setup
- Aim for 80%+ coverage
- [... 300 more words ...]

### Code Style
- Use black for formatting
- Add type hints to all functions
- Write Google-style docstrings
- [... 200 more words ...]

### Security
- Validate all inputs
- Use parameterized queries
- [... 150 more words ...]
```

**Token count**: ~500 tokens

**After (skill references):**
```markdown
## Relevant Skills

You have access to these specialized skills when implementing features:

- **testing-guide**: Pytest patterns, TDD workflow, coverage strategies
- **python-standards**: Code style, type hints, docstring conventions
- **security-patterns**: Input validation, secure coding practices

**Note**: Skills load automatically based on task keywords. Consult skills for detailed guidance.
```

**Token count**: ~150 tokens

**Savings**: 350 tokens per agent (70% reduction)

### Across All Agents

- 20 agents × 350 tokens saved = 7,000 tokens
- Plus: Skills themselves deduplicate shared guidance
- Result: 20-30% overall token reduction in agent prompts

### Scalability

**With inline guidance (doesn't scale):**
- 20 agents × 500 tokens = 10,000 tokens
- Can't add more specialized guidance without bloating prompts
- Context budget limits agent capability

**With skill references (scales infinitely):**
- 20 agents × 150 tokens = 3,000 tokens
- Can add 100+ skills without impacting agent prompt size
- Progressive disclosure ensures context efficiency

## Real-World Examples

### Example 1: researcher Agent

**Before:**
```markdown
## Relevant Skills

### Research Patterns
When researching, follow these best practices:
- Start with official documentation
- Check multiple sources for accuracy
- Document sources with URLs
- Identify common patterns across sources
- Note breaking changes and deprecations
- Verify information is current (check dates)
- Look for code examples and real-world usage
- [... 400 more words ...]
```

**Token count**: ~600 tokens

**After:**
```markdown
## Relevant Skills

You have access to these specialized skills when researching:

- **research-patterns**: Web research methodology, source evaluation
- **documentation-guide**: Documentation standards for research findings

**Note**: Skills load automatically based on task keywords.
```

**Token count**: ~100 tokens

**Savings**: 500 tokens (83% reduction)

### Example 2: planner Agent

**Before:**
```markdown
## Relevant Skills

### Architecture Patterns
Follow these architectural patterns:
- [... 300 words ...]

### API Design
When designing APIs:
- [... 250 words ...]

### Database Design
For database schemas:
- [... 200 words ...]

### Testing Strategy
Plan testing approach:
- [... 200 words ...]
```

**Token count**: ~700 tokens

**After:**
```markdown
## Relevant Skills

You have access to these specialized skills when planning:

- **architecture-patterns**: Design patterns, SOLID principles
- **api-design**: REST API patterns, versioning strategies
- **database-design**: Schema design, query optimization
- **testing-guide**: Test strategy, coverage planning

**Note**: Skills load automatically based on task keywords.
```

**Token count**: ~130 tokens

**Savings**: 570 tokens (81% reduction)

## Detailed Documentation

For comprehensive skill integration guidance:
- **Skill Discovery**: See [docs/skill-discovery.md](docs/skill-discovery.md) for keyword matching and activation
- **Skill Composition**: See [docs/skill-composition.md](docs/skill-composition.md) for combining skills
- **Progressive Disclosure**: See [docs/progressive-disclosure.md](docs/progressive-disclosure.md) for architecture details

## Examples

- **Agent Template**: See [examples/agent-skill-reference-template.md](examples/agent-skill-reference-template.md)
- **Composition Example**: See [examples/skill-composition-example.md](examples/skill-composition-example.md)
- **Architecture Diagram**: See [examples/progressive-disclosure-diagram.md](examples/progressive-disclosure-diagram.md)

## Integration with autonomous-dev

All 20 agents in the autonomous-dev plugin follow this skill integration pattern:
- Each agent lists 3-7 relevant skills
- No inline skill content duplication
- Progressive disclosure prevents context bloat
- Scales to 100+ skills without performance issues

**Result**: 20-30% token reduction in agent prompts while maintaining full access to specialized knowledge.

---

**Version**: 1.0.0
**Type**: Knowledge skill (no scripts)
**See Also**: agent-output-formats, documentation-guide, python-standards
