---
name: explain
description: Explain what a piece of code does, its role in the project, and how it fits in the system
context: fork
allowed-tools: Read, Grep, Glob
---

Explain the code at $ARGUMENTS (file, function, or class name).

**Structure your explanation as:**

1. **What it does** — plain-language summary of purpose and behavior.
2. **Project role** — which package it belongs to and its responsibility:
   - `cli/` — user interaction, display, Notion publishing
   - `agents/` — LLM node functions, @tool definitions, state management
   - `dataflows/` — data fetching, vendor routing, API clients
   - `graph/` — LangGraph orchestration, node wiring, conditional logic
   - `llm_clients/` — LLM provider abstraction, model catalog
3. **Inputs / Outputs** — key parameters, return values, side effects.
4. **Dependencies** — what it calls and what calls it (read surrounding code if needed).
5. **Notable edge cases** — anything non-obvious about how it behaves.

Keep the explanation concise. Use code snippets only when they directly clarify a point.
If the code is in a package that doesn't match its responsibility, flag it.
