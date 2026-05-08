# Lab-First Playbook

## Rule

**Before modifying production code, create a standalone lab script.**

Lab scripts are disposable experiments. They prove an approach works before it
touches anything that `just check` validates or that users depend on.

## When to Use a Lab

| Situation | Lab? |
|-----------|------|
| New CLI output formatting (Gum, tables, colours) | **Yes** |
| New external API integration | **Yes** |
| Unfamiliar library or API pattern | **Yes** |
| Database schema change with migration logic | **Yes** |
| Refactoring with uncertain scope | Maybe — if complex |
| Simple bug fix with clear cause | No |
| Adding a route that follows existing patterns | No |

## Lab Script Conventions

### Location

```
scripts/lab-<topic>.ts
```

Examples:
- `scripts/lab-gum.ts` — CLI output formatting
- `scripts/lab-ig-auth.ts` — IG API authentication flow
- `scripts/lab-db-migration.ts` — SQLite schema migration experiment

### Structure

```typescript
#!/usr/bin/env bun
/**
 * Lab: <What you are experimenting with>
 *
 * Safe playground. No production code touched.
 * Run: bun scripts/lab-<topic>.ts
 */

// ── Experiment 1: <hypothesis> ─────────────────────────────────
// Code here

// ── Experiment 2: <alternative approach> ───────────────────────
// Code here

// ── Experiment N: <what worked> ────────────────────────────────
// Code here
```

### Rules

1. **No imports from `server/` or `cli/` or `tradingagents/`.** Lab scripts are
   self-contained. If you need a shared function, inline it or copy it.
2. **No test files.** Labs are for manual exploration, not CI.
3. **Named experiments.** Each block is a hypothesis: "Experiment 1: Bun.spawn
   vs execSync for Gum output."
4. **Delete when done.** Once the pattern is ported to production, the lab script
   can be removed. Or keep it as a reference — but mark it `// DEPRECATED`.
5. **Not committed to PRs unless it's a reference.** Lab scripts are local
   working files. Only commit if they serve as documentation.

## Workflow

```
1. Identify the problem (e.g. "status output looks broken")
2. Create lab script:              touch scripts/lab-<topic>.ts
3. Experiment freely:               bun scripts/lab-<topic>.ts
4. Find working pattern:            (no check cycle, no commit pressure)
5. Port to production:              edit production file with proven pattern
6. Verify:                          just check
7. Commit:                          git commit
8. (Optional) Delete lab:          rm scripts/lab-<topic>.ts
```

## Anti-Patterns

**Don't:** Edit production code, see it break, fix, commit, see it break again.
This is thrashing. It wastes `just check` cycles, pollutes git history, and
stresses everyone.

**Don't:** Spend more than 15 minutes on a single approach in the lab. If it
isn't working, try a different library, a different API, or a different
architecture. The lab is for rapid pivoting.

**Don't:** Leave lab scripts in the repo without a clear purpose. They become
orphaned code that confuses future readers.

## War Story 2: The Directory Restructure

We needed to move `server/` and `cli/trading/` into `src/`. Instead of moving
everything at once, we used the lab principle at the architecture level:

1. **Phase 0 (extract):** Move shared modules (`db.ts`, `trade-calculator.ts`)
   to `src/lib/` first, update all imports, verify with `grep`.
2. **Phase 1 (move):** Only then move `server/` → `src/server/` and
   `cli/trading/` → `src/cli/`. No cross-directory couplings remained.
3. **Phase 2 (wire):** Update `justfile`, `package.json`, hardcoded paths.

If we had moved directories first, 11 import statements and 1 hardcoded path
would have broken simultaneously. The "extract-before-move" pattern is the
lab principle applied to directory structure: prove the coupling is broken
before changing the structure.

## War Story 1: Gum Formatting

The server lifecycle CLI (`scripts/server-lifecycle.ts`) had a working ASCII
status display. We tried to replace it with Gum formatting directly in the
production file. Three iterations, all broken. User said: "STOP."

We created `scripts/lab-gum.ts`. First attempt with `execSync` + `input`:
broken. Second attempt with `Bun.spawn` + `stdin.write()`: perfect. Ported the
working pattern back. Total time saved: 10+ minutes. Risk: zero.
