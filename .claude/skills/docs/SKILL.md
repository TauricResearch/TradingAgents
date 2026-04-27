---
name: docs
description: Generate Google-style docstrings and module documentation
context: fork
allowed-tools: Read, Grep, Glob
---

Generate or improve documentation for $ARGUMENTS (file, function, or class).

**Steps:**
1. Read the target code to understand its purpose, inputs, outputs, and side effects.
2. Identify which package it belongs to:
   - `cli/` — CLI entry point, user interaction, Notion publishing
   - `agents/` — LLM node functions, @tool definitions, state management
   - `dataflows/` — data fetching, vendor routing, API clients
   - `graph/` — LangGraph orchestration, node wiring, conditional logic
   - `llm_clients/` — LLM provider abstraction, model catalog
3. Write or update Google-style docstrings with Args, Returns, Raises sections.
4. Add module-level docstring if missing, stating the module's responsibility.

**Rules:**
- Every public function and class gets a docstring.
- Use type hints in signatures, not in docstrings.
- Keep docstrings concise — explain *what* and *why*, not implementation details.
- For @tool functions, ensure the docstring works as the LLM tool description.
