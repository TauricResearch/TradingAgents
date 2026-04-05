---
name: explain
description: Explain what a piece of code does, its DDD role, and how it fits in the system
context: fork
allowed-tools: Read, Grep, Glob
---

Explain the code at $ARGUMENTS (file, function, or class name).

**Structure your explanation as:**

1. **What it does** — plain-language summary of purpose and behavior.
2. **DDD role** — which layer it belongs to (entity, value object, repository, use case handler, adapter, interface) and why.
3. **Inputs / Outputs** — key parameters, return values, side effects.
4. **Dependencies** — what it calls and what calls it (read surrounding code if needed).
5. **Notable edge cases** — anything non-obvious about how it behaves.

Keep the explanation concise. Use code snippets only when they directly clarify a point.
If the code is in the wrong DDD layer, flag it.
