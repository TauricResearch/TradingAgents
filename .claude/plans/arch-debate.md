# Architecture Debate Plan

Use this when you have two or more ways to solve a problem and need to think through the trade-offs before committing.

---

## Prompt

```
I need to decide between these approaches for [problem statement]:

**Option A:** [brief description]
**Option B:** [brief description]
(Optional) **Option C:** [brief description]

Debate these options across the following dimensions:

1. **Complexity** — How hard is each to implement, understand, and maintain?
2. **DDD fit** — Does it respect domain boundaries? Does it leak concerns across layers?
3. **Testability** — How easy is each to unit test and integration test?
4. **Performance** — Any obvious bottlenecks or scaling concerns?
5. **Reversibility** — How hard is it to change later if requirements shift?
6. **Risk** — What is most likely to go wrong with each approach?

For each dimension, argue FOR and AGAINST each option.
End with a recommendation and the key condition under which you'd choose the other option instead.

Do not write any code yet. Debate only.
```

---

## When to use
- Before designing a new domain or service
- When two engineers disagree on approach
- When you're unsure which layer owns a piece of logic
- Before choosing between sync vs async, event-driven vs direct call, etc.
