---
name: commit
description: Stage changes and generate a conventional commit message, then commit
disable-model-invocation: true
---

Create a git commit for the current staged (or all) changes.

1. Run `git diff --staged` (and `git diff` if nothing is staged) to understand the changes.
2. Infer the commit type from the diff:
   - `feat` — new capability
   - `fix` — bug fix
   - `refactor` — restructure without behavior change
   - `test` — add or update tests
   - `chore` — tooling, deps, config
   - `docs` — documentation only
   - `perf` — performance improvement
   - `ci` — CI/CD pipeline changes
3. Infer the scope from the package affected:
   - `cli` — CLI entry point, user interaction, Notion publishing
   - `agents` — agent nodes, @tool functions, state definitions
   - `dataflows` — data fetching, vendor routing, API clients
   - `graph` — LangGraph orchestration, node wiring
   - `llm` — LLM provider clients, model catalog
   - `tests` — test files
   - `docs` — design documents
4. Write a subject line: `<type>(<scope>): <imperative summary>` — max 72 characters.
5. Add a body if the change is non-obvious: explain *what* and *why*, not *how*.
6. Stage any unstaged files relevant to the change if the user confirms.
7. Commit using the message. Never use `--no-verify`.

If $ARGUMENTS is provided, use it as additional context or the commit message directly.
