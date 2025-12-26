# Progressive Disclosure Architecture Diagram

Visual representation of how progressive disclosure works in Claude Code 2.0+.

## High-Level Architecture

```
┌────────────────────────────────────────────────────────────┐
│                     Claude Code 2.0+                        │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              skills/ Directory                       │  │
│  │                                                      │  │
│  │  ├── testing-guide/SKILL.md                         │  │
│  │  ├── python-standards/SKILL.md                      │  │
│  │  ├── security-patterns/SKILL.md                     │  │
│  │  ├── api-design/SKILL.md                            │  │
│  │  └── ... (17 more skills)                           │  │
│  └──────────────────────────────────────────────────────┘  │
│                            │                                │
│                            │ Startup: Load metadata only    │
│                            ↓                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           Agent Context (Startup)                    │  │
│  │                                                      │  │
│  │  ┌────────────────────────────────────────────────┐ │  │
│  │  │ Agent Prompt: ~500 tokens                      │ │  │
│  │  ├────────────────────────────────────────────────┤ │  │
│  │  │ Skill Metadata: 21 × 50 = ~1,050 tokens       │ │  │
│  │  │ - testing-guide: 50 tokens                     │ │  │
│  │  │ - python-standards: 50 tokens                  │ │  │
│  │  │ - security-patterns: 50 tokens                 │ │  │
│  │  │ - ... (18 more)                                │ │  │
│  │  └────────────────────────────────────────────────┘ │  │
│  │                                                      │  │
│  │  Total: ~1,550 tokens (efficient!)                  │  │
│  └──────────────────────────────────────────────────────┘  │
│                            │                                │
│                            │ Task provided                  │
│                            ↓                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           Task Analysis                              │  │
│  │                                                      │  │
│  │  User Task: "Write tests for authentication"        │  │
│  │             (contains keywords: "tests", "auth")     │  │
│  │                                                      │  │
│  │  Keyword Matching:                                   │  │
│  │  - "tests" matches testing-guide                    │  │
│  │  - "authentication" matches security-patterns       │  │
│  └──────────────────────────────────────────────────────┘  │
│                            │                                │
│                            │ Load matching skills           │
│                            ↓                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │      Agent Context (Task Execution)                  │  │
│  │                                                      │  │
│  │  ┌────────────────────────────────────────────────┐ │  │
│  │  │ Base Context: ~1,550 tokens                    │ │  │
│  │  ├────────────────────────────────────────────────┤ │  │
│  │  │ Task Description: ~200 tokens                  │ │  │
│  │  ├────────────────────────────────────────────────┤ │  │
│  │  │ testing-guide FULL CONTENT: ~5,000 tokens     │ │  │
│  │  ├────────────────────────────────────────────────┤ │  │
│  │  │ security-patterns FULL CONTENT: ~6,000 tokens │ │  │
│  │  └────────────────────────────────────────────────┘ │  │
│  │                                                      │  │
│  │  Total: ~12,750 tokens (only what's needed!)        │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

## Skill Loading Sequence

### Phase 1: Startup (Metadata Loading)

```
┌──────────────┐
│ Claude Code  │
│   Startup    │
└──────┬───────┘
       │
       │ Scan skills/ directory
       ↓
┌────────────────────────────────────────┐
│ For each SKILL.md:                     │
│ 1. Read file                           │
│ 2. Extract YAML frontmatter            │
│ 3. Store metadata in memory            │
│ 4. Discard full content                │
└────────────────────────────────────────┘
       │
       │ Result: Metadata only
       ↓
┌────────────────────────────────────────┐
│ Skill Registry (In Memory)             │
│                                        │
│ testing-guide:                         │
│   keywords: [test, testing, pytest]    │
│   content_path: skills/testing-guide/  │
│                                        │
│ security-patterns:                     │
│   keywords: [security, auth, jwt]      │
│   content_path: skills/security-.../   │
│                                        │
│ ... (19 more skills)                   │
└────────────────────────────────────────┘
       │
       │ Total: ~1,050 tokens
       ↓
┌────────────────────────────────────────┐
│ Ready for tasks!                       │
│ (Minimal context used)                 │
└────────────────────────────────────────┘
```

### Phase 2: Task Execution (Progressive Loading)

```
┌──────────────┐
│ User provides│
│     task     │
└──────┬───────┘
       │
       │ "Write secure API tests with pytest"
       ↓
┌────────────────────────────────────────┐
│ Keyword Extraction                     │
│                                        │
│ Keywords found:                        │
│ - "tests" (→ testing-guide)            │
│ - "pytest" (→ testing-guide)           │
│ - "secure" (→ security-patterns)       │
│ - "api" (→ api-design)                 │
└────────────────────────────────────────┘
       │
       │ Match against skill registry
       ↓
┌────────────────────────────────────────┐
│ Matching Skills:                       │
│ 1. testing-guide (matches: tests, pytest)│
│ 2. security-patterns (matches: secure) │
│ 3. api-design (matches: api)           │
└────────────────────────────────────────┘
       │
       │ Load full content on-demand
       ↓
┌────────────────────────────────────────┐
│ Skill Loading                          │
│                                        │
│ Load testing-guide:                    │
│ - Read full SKILL.md content           │
│ - +5,000 tokens                        │
│                                        │
│ Load security-patterns:                │
│ - Read full SKILL.md content           │
│ - +6,000 tokens                        │
│                                        │
│ Load api-design:                       │
│ - Read full SKILL.md content           │
│ - +4,000 tokens                        │
└────────────────────────────────────────┘
       │
       │ Total: +15,000 tokens
       ↓
┌────────────────────────────────────────┐
│ Agent Context                          │
│                                        │
│ Base: ~1,550 tokens                    │
│ Task: ~200 tokens                      │
│ Skills: ~15,000 tokens                 │
│ ─────────────────────────────          │
│ Total: ~16,750 tokens                  │
│                                        │
│ (Only 8% of 200K context budget)       │
└────────────────────────────────────────┘
       │
       │ Agent processes task
       ↓
┌────────────────────────────────────────┐
│ Task Completed!                        │
└────────────────────────────────────────┘
```

## Token Comparison

### Traditional Approach (Load All Skills)

```
Startup:
┌──────────────────────────────────────┐
│ Agent Prompt: 500 tokens             │
├──────────────────────────────────────┤
│ testing-guide: 5,000 tokens          │
├──────────────────────────────────────┤
│ python-standards: 3,000 tokens       │
├──────────────────────────────────────┤
│ security-patterns: 6,000 tokens      │
├──────────────────────────────────────┤
│ api-design: 4,000 tokens             │
├──────────────────────────────────────┤
│ ... (17 more skills)                 │
└──────────────────────────────────────┘
Total: ~100,000 tokens (50% of budget!)

Problems:
❌ Half of context budget used before task starts
❌ Most skills irrelevant to task
❌ Slow loading time
❌ Can't scale beyond 20-30 skills
```

### Progressive Disclosure (Load on Demand)

```
Startup:
┌──────────────────────────────────────┐
│ Agent Prompt: 500 tokens             │
├──────────────────────────────────────┤
│ Skill Metadata: 1,050 tokens         │
│ (21 skills × 50 tokens)              │
└──────────────────────────────────────┘
Total: ~1,550 tokens (< 1% of budget!)

Task Execution:
┌──────────────────────────────────────┐
│ Base: 1,550 tokens                   │
├──────────────────────────────────────┤
│ Task: 200 tokens                     │
├──────────────────────────────────────┤
│ testing-guide: 5,000 tokens          │ ← Loaded on-demand
├──────────────────────────────────────┤
│ security-patterns: 6,000 tokens      │ ← Loaded on-demand
├──────────────────────────────────────┤
│ api-design: 4,000 tokens             │ ← Loaded on-demand
└──────────────────────────────────────┘
Total: ~16,750 tokens (8% of budget)

Benefits:
✅ Only 8% of context budget used
✅ Only relevant skills loaded
✅ Fast startup
✅ Scales to 100+ skills
```

## Multi-Stage Loading Example

Progressive disclosure can load skills at any point during task execution:

```
Task: "Implement user registration API with secure password storage and tests"

Time: 0 minutes
┌──────────────────────────────┐
│ Context: 1,750 tokens        │
│ - Agent + metadata + task    │
└──────────────────────────────┘

Time: 2 minutes (API design phase)
┌──────────────────────────────┐
│ Context: 5,750 tokens        │
│ + api-design: 4,000 tokens   │ ← Loaded when agent starts API design
└──────────────────────────────┘

Time: 5 minutes (Security implementation)
┌──────────────────────────────┐
│ Context: 11,750 tokens       │
│ + security-patterns: 6K      │ ← Loaded when agent encounters security requirements
└──────────────────────────────┘

Time: 8 minutes (Database schema)
┌──────────────────────────────┐
│ Context: 15,250 tokens       │
│ + database-design: 3.5K      │ ← Loaded when agent designs schema
└──────────────────────────────┘

Time: 12 minutes (Testing)
┌──────────────────────────────┐
│ Context: 20,250 tokens       │
│ + testing-guide: 5K          │ ← Loaded when agent writes tests
└──────────────────────────────┘

Time: 15 minutes (Documentation)
┌──────────────────────────────┐
│ Context: 24,250 tokens       │
│ + documentation-guide: 4K    │ ← Loaded when agent documents API
└──────────────────────────────┘

Task Completed!
Final context: 24,250 tokens (12% of budget)
```

## Scalability

### With Progressive Disclosure

```
Number of Skills vs Context Usage (Startup):

10 skills:  500 tokens (metadata)
20 skills:  1,000 tokens (metadata)
50 skills:  2,500 tokens (metadata)
100 skills: 5,000 tokens (metadata)

Scales linearly! ✅
```

### Without Progressive Disclosure

```
Number of Skills vs Context Usage (Startup):

10 skills:  50,000 tokens (full content)
20 skills:  100,000 tokens (full content)
50 skills:  250,000 tokens (exceeds budget!) ❌
100 skills: 500,000 tokens (impossible!) ❌

Doesn't scale! ❌
```

## Summary

Progressive disclosure architecture:

**Key principles:**
1. **Metadata always in context** (~50 tokens per skill)
2. **Content loads on-demand** (only when needed)
3. **Keyword-based activation** (automatic skill discovery)
4. **Linear scaling** (supports 100+ skills)

**Benefits:**
- 85% reduction in context usage
- Fast startup times
- Scales to 100+ skills
- Only relevant skills load

**Result:** Efficient, scalable skill system that maintains full access to specialized knowledge without context bloat.
