---
inclusion: manual
---

# Systematic Debugging

Use when encountering any bug, test failure, or unexpected behavior.

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If you haven't completed Phase 1, you cannot propose fixes.

## Phase 1: Root Cause Investigation

1. **Read error messages carefully** — don't skip past them. Read stack traces completely. Note line numbers, file paths, error codes.

2. **Reproduce consistently** — can you trigger it reliably? What are the exact steps? If not reproducible, gather more data — don't guess.

3. **Check recent changes** — git diff, recent commits, new dependencies, config changes, environmental differences.

4. **Gather evidence at component boundaries** — for multi-component systems, add diagnostic logging at each layer boundary to identify WHERE it breaks before guessing WHY.

5. **Trace data flow** — where does the bad value originate? Trace backward through the call stack to the source. Fix at source, not at symptom.

## Phase 2: Pattern Analysis

1. Find working examples of similar code in the codebase
2. Compare working vs broken — list every difference
3. Understand dependencies and assumptions
4. Don't assume "that can't matter"

## Phase 3: Hypothesis and Testing

1. Form a single, specific hypothesis: "X is the root cause because Y"
2. Make the SMALLEST possible change to test it
3. One variable at a time
4. Didn't work? Form NEW hypothesis — don't pile fixes on top

## Phase 4: Implementation

1. Write a failing test reproducing the bug (TDD)
2. Implement a single fix addressing root cause
3. Verify: test passes, no regressions
4. **If 3+ fixes have failed**: STOP. Question the architecture. Discuss with user before attempting more.

## Red Flags — STOP and Return to Phase 1

- "Quick fix for now, investigate later"
- "Just try changing X and see if it works"
- "It's probably X, let me fix that"
- "I don't fully understand but this might work"
- Proposing solutions before tracing data flow
- Each fix reveals a new problem in a different place
- "One more fix attempt" after 2+ failures

## Quick Reference

| Phase | Key Activity | Success Criteria |
|-------|-------------|------------------|
| 1. Root Cause | Read errors, reproduce, trace | Understand WHAT and WHY |
| 2. Pattern | Find working examples, compare | Identify differences |
| 3. Hypothesis | Form theory, test minimally | Confirmed or new hypothesis |
| 4. Implementation | Failing test, fix, verify | Bug resolved, tests pass |
