---
description: Critical thinking analysis - validates alignment, challenges assumptions, identifies risks
argument-hint: Proposal or decision to analyze (e.g., "Add Redis for caching")
---

# Critical Thinking Analysis

Invoke the **advisor agent** to analyze proposals, validate alignment, and identify risks before implementation.

## Implementation

Invoke the advisor agent with the user's proposal.

ARGUMENTS: {{ARGUMENTS}}

Use the Task tool to invoke the advisor agent with subagent_type="advisor" and provide the proposal from ARGUMENTS.

## What This Does

You describe a proposal or decision point. The advisor agent will:

1. Validate alignment with PROJECT.md goals, scope, and constraints
2. Analyze complexity cost vs benefit
3. Identify technical and project risks
4. Suggest simpler alternatives
5. Provide clear recommendation (PROCEED/CAUTION/RECONSIDER/REJECT)

**Time**: 2-3 minutes

## Usage

```bash
/advise Add Redis for caching

/advise Refactor to microservices architecture

/advise Switch from REST to GraphQL

/advise Add real-time collaboration features
```

## Output

The advisor provides:

- **Alignment Score** (0-10): How well proposal serves PROJECT.md goals
- **Decision**: PROCEED / CAUTION / RECONSIDER / REJECT
- **Complexity Assessment**: Estimated LOC, files, time
- **Pros/Cons**: Trade-off analysis
- **Alternatives**: Simpler, more robust, or hybrid approaches
- **Risk Assessment**: What could go wrong

## When to Use

Use `/advise` when making significant decisions:

- Adding new dependencies (Redis, Elasticsearch, etc.)
- Architecture changes (microservices, event-driven, etc.)
- Scope expansions (mobile support, multi-tenancy, etc.)
- Technology replacements (GraphQL vs REST, etc.)
- Scale changes (handling 100K users, etc.)

## Integration

The **advisor-triggers** skill automatically suggests `/advise` when it detects significant decision patterns in your requests.

## Next Steps

After receiving advice:

1. **PROCEED**: Continue with `/plan` or `/auto-implement`
2. **CAUTION**: Address concerns, then proceed
3. **RECONSIDER**: Evaluate alternatives before proceeding
4. **REJECT**: Don't implement, or update PROJECT.md first

## Comparison

| Command | Time | What It Does |
|---------|------|--------------|
| `/advise` | 2-3 min | Critical analysis (this command) |
| `/research` | 2-5 min | Pattern and best practice research |
| `/plan` | 3-5 min | Architecture planning |
| `/auto-implement` | 20-30 min | Full pipeline |

## Technical Details

This command invokes the `advisor` agent with:
- **Model**: Opus (deep reasoning for critical analysis)
- **Tools**: Read, Grep, Glob, Bash, WebSearch, WebFetch
- **Permissions**: Read-only analysis (cannot modify code)

---

**Part of**: Core workflow commands
**Related**: `/plan`, `/auto-implement`, advisor-triggers skill
**GitHub Issue**: #158
