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

1. **No imports from `src/server/` or `cli/` or `tradingagents/`.** Lab scripts are
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

## War Story 2: Status Display Templates

Context window was exhausted. Previous session had partially fixed
`scripts/server-lifecycle.ts` but reverted to hand-rolled ANSI boxes. The
user asked: "Let's think through what we require."

Instead of editing `server-lifecycle.ts` directly, we created
`scripts/lab/status-templates.ts` with four competing layouts (A–D), all
using live service detection. Each template was a complete hypothesis:
- Template A: Fixed-width bordered table
- Template B: Compact inline verbs
- Template C: Two-column cards
- Template D: Minimal, no border

All were evaluated against real data. A and B failed on content wrapping.
C was visually heavy. D lacked presence. From the evaluation, we extracted
Template E — the simplest correct version: one border, dynamic width,
title/hint outside, inline ANSI dots.

Only then did we edit `server-lifecycle.ts`. One shot, correct first time.
Seven biome lint issues were also fixed in the same commit because we were
not thrashing on a broken production file.

## War Story 3: Portfolio and IG History (Session ses_02a5c6)

One session built four Gum-styled CLI commands (portfolio, IG history, alerts,
plus the status display from War Story 2). All used lab-first:

| Feature | Lab Script | What Was Tested | Production Result |
|---------|-----------|----------------|-------------------|
| Status display | `scripts/lab/status-templates.ts` | 4 layouts with live data | Template E selected, zero reverts |
| Portfolio table | `scripts/lab/portfolio-gum.ts` | Multi-column financial table | Dynamic width validated, no wrapping |
| IG history | `scripts/lab/ig-history.ts` | Activity vs transaction layout | Mock data proved format before API call |
| Exit plan alerts | `scripts/lab/alerts.ts` | Alert severity logic | Edge cases (multi-target, time stop) caught early |

**Result:** 4 features, 6 commits, zero forward-fixes, zero reverts, all `just check` green.
Compare to previous session's direct-editing approach: 35+ bundled commits,
2 broken tests, scope violation, context window exhaustion.

## New Rules (Validated by Evidence)

### The Context Window Rule

**If you're on attempt 3 of the same file without a green `just check`, stop.
Create a lab.**

The previous session's debrief: "Context window: EXHAUSTED." The implementer
had edited `server-lifecycle.ts` directly, broken it, fixed it, broken it
again. By attempt 3, the file was a palimpsest of half-solutions. A lab would
have absorbed that entropy.

### The Live Data Principle

**Use real data for layout experiments. Use mock data for API shape experiments.**

- `status-templates.ts` used live service detection (Dashboard PID, hledger
  status, etc.) because a table that looks good with 2 rows may wrap with 7.
- `ig-history.ts` used mock data because the question was "Does this format
  handle the IG response shape?" not "Does the IG API respond?"

This distinction prevents false positives. A layout that works with dummy
strings fails when real PIDs, paths, and timestamps are inserted.

### The One-Shot Port Rule

**A lab-proven pattern should port to production in a single edit, passing
`just check` first time.**

If the port requires forward-fixes, the lab wasn't finished. The lab's job is
to eliminate all unknowns so the production edit is mechanical. Template E
was proven before it touched `server-lifecycle.ts`. The port was one edit,
one commit, one green check.
