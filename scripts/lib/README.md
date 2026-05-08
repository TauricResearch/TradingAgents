# scripts/lib — Shared Production Helpers

TypeScript modules imported by multiple scripts. Not for experiments.

## Purpose

Extract reusable logic that appears in more than one script. Eliminates
duplication and provides a single point of maintenance.

## Rules

- **Pass `just check`.** Files here are production code. Strict types, no
  unused locals, no `any` without justification.
- **No side effects at import time.** Modules must be safe to import.
  Initialization logic belongs in the calling script.
- **No CLI output.** Helpers return values. Callers decide how to display them.
- **Document the interface.** Each exported function needs a JSDoc comment
  explaining parameters, return type, and example usage.

## Boundary with scripts/lab/

| | `scripts/lib/` | `scripts/lab/` |
|---|---|---|
| Purpose | Shared helpers | Disposable experiments |
| Type checking | Strict (`just check` must pass) | Loose (`strict: false`) |
| Importable by | Production scripts | Nothing (self-contained) |
| Lifetime | Permanent | Temporary; delete when experiment ends |
| Commit to repo | Yes | Only if serving as reference |

## Current Modules

| File | Used By | What It Does |
|------|---------|--------------|
| `llm.ts` | `pr-summarize.ts`, `summarize_analyses.ts`, `refactor-playbook.ts` | OpenRouter LLM substrate. Auto-loads `.env`, handles retries, returns parsed JSON. |
| `gum.ts` | `server-lifecycle.ts`, `lab/gum.ts` | Charm Gum CLI styling via `Bun.spawn`. Thin wrapper around `gum style` with stdin piping. |

## Adding a New Module

1. Create the file in this directory.
2. Add it to the table above.
3. Update the `Current Modules` section in this README.
4. Run `just check` — it must pass.
