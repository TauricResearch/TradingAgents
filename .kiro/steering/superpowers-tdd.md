---
inclusion: manual
---

# Test-Driven Development

Use when implementing any feature or bugfix.

## The Iron Law

```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

Wrote code before the test? Delete it. Start over. No exceptions.

## Red-Green-Refactor Cycle

### RED — Write Failing Test
- One minimal test showing what should happen
- One behavior per test
- Clear name describing the behavior
- Real code, not mocks (unless unavoidable)

### Verify RED — Watch It Fail (MANDATORY)
- Run the test
- Confirm it fails (not errors — fails)
- Confirm failure message is expected
- Confirm it fails because the feature is missing, not due to typos

### GREEN — Write Minimal Code
- Simplest code to make the test pass
- Don't add features beyond what the test requires
- Don't refactor yet
- Don't "improve" beyond the test

### Verify GREEN — Watch It Pass (MANDATORY)
- Run the test
- Confirm it passes
- Confirm other tests still pass
- If test fails: fix code, not the test

### REFACTOR — Clean Up
- Only after green
- Remove duplication, improve names, extract helpers
- Keep tests green throughout
- Don't add behavior

### Repeat
- Next failing test for next behavior

## Bug Fix Pattern

1. Write failing test that reproduces the bug
2. Watch it fail (confirms test catches the bug)
3. Write minimal fix
4. Watch it pass
5. Verify no regressions

## Red Flags — Stop and Start Over

- Code written before test
- Test passes immediately (you're testing existing behavior)
- Can't explain why test failed
- Rationalizing "just this once"
- "I'll write tests after"
- "Too simple to test" (simple code breaks; test takes 30 seconds)
- "TDD will slow me down" (TDD is faster than debugging)

## When Stuck

| Problem | Solution |
|---------|----------|
| Don't know how to test | Write the API you wish existed. Write assertion first. |
| Test too complicated | Design too complicated. Simplify the interface. |
| Must mock everything | Code too coupled. Use dependency injection. |
| Test setup huge | Extract helpers. Still complex? Simplify design. |

## Verification Checklist

Before marking work complete:
- [ ] Every new function/method has a test
- [ ] Watched each test fail before implementing
- [ ] Each test failed for expected reason
- [ ] Wrote minimal code to pass each test
- [ ] All tests pass
- [ ] No warnings or errors in output
- [ ] Edge cases and errors covered
