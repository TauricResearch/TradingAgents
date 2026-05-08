# Debrief: Directory Restructure — From Flat to Tiered

## Context

The TradingAgents project had a flat TypeScript layout:
- `server/` — Hono dashboard
- `cli/trading/` — TypeScript CLI
- `scripts/` — Support scripts
- `src/` — **empty**, but claiming to be the source root

The `src/` directory was an architectural lie. It existed in the repo but
contained nothing, while production code lived at root alongside Python
components (`cli/`, `tradingagents/`).

## Objective

Restructure to a tiered hierarchy:
- `src/` — Production code (strict types, tested)
- `scripts/` — Support code (loose types, tooling)
- `scripts/lab/` — Experiments (no type constraints)

## The Three Phases

### Phase 0: Extract Shared Substrate (BREAK CROSS-DIRECTORY IMPORTS)

**Problem:** `server/lib/db.ts` and `server/lib/trade-calculator.ts` were
imported by `scripts/`, `cli/trading/`, and `tests/`.

**Approach:** Move shared modules to `src/lib/` first, update all imports,
verify no `../server/lib/` references remain.

**Files changed:** 31 (2 renamed, 29 import updates)

**Gate:** `grep -rn "server/lib" scripts/ cli/trading/ tests/ = 0` ✅

**Lesson:** Never move a directory that has external dependents. Extract
shared modules first. The coupling must be broken before the structure
changes.

### Phase 1: Move Production Directories

**Approach:** `server/` → `src/server/`, `cli/trading/` → `src/cli/`

**Files changed:** 91 (89 renamed, 2 tsconfig updates)

**Gate:** `tsc --noEmit` passes ✅

**Lesson:** After moving directories, import depth changes:
- `../../src/lib/` → `../../lib/` (inside `src/server/routes/`)
- `../src/lib/` → `../lib/` (inside `src/server/index.tsx`)

The tsconfig include paths must also update:
- `"server/**/*.ts"` → `"src/server/**/*.ts"`
- `"server/**/*.tsx"` → `"src/**/*.ts", "src/**/*.tsx"`

### Phase 2: Update Wiring

**Problem:** Hardcoded paths in `justfile`, `package.json`, shell scripts,
and comment strings.

**Files changed:** 11 (justfile, package.json, server-lifecycle.ts,
check-view-scripts.ts, comments in seed/sync scripts)

**Gate:** Server starts and health check passes ✅

**Lesson:** Every hardcoded path is a barnacle. Search for `"server/"` and
`"cli/trading"` across the entire repo, not just `.ts` files.
Comments and doc strings also mislead future agents.

## What Went Wrong (and Was Fixed)

### 1. `check-view-scripts.ts` broke

The gate script hardcoded:
- `VIEWS_DIR = join(import.meta.dir, "..", "server", "views")` — wrong after move
- `serveStatic` check looked for `root: "./server/static"` — the actual code
  uses `resolve(import.meta.dir, "static")` (computed path)

**Fix:** Updated both paths, added `hasComputedRoot` check alongside
`hasLiteralRoot`.

### 2. `server-lifecycle.ts` spawned old path

`spawn("bun", ["run", "server/index.tsx"])` — started the OLD server from the
PREVIOUS commit, not the newly moved one.

**Fix:** Updated to `src/server/index.tsx`. Verified: `just start` now
launches the correct file.

### 3. Biome formatter complained about long strings

The `console.error` message in `check-view-scripts.ts` exceeded line length
when updated with the new path.

**Fix:** Broke into multi-line string with proper indentation.

## What We Learned

### The Empty `src/` Was a Barnacle

An empty directory that claims to be the source root is worse than no
directory at all. It creates a false expectation. Every new agent assumes
`src/` is where the code lives, then finds nothing and gets confused.

The fix was not to delete `src/` but to **make it real**.

### Manual grep Beat GitNexus for Real-Time Refactoring

GitNexus `analyze` takes ~3 seconds, but:
- `context` queries sometimes return "not found" for valid symbols
- FTS indices were read-only during the session (tool limitation)
- It could not tell us WHICH files still reference old paths

`grep -rn "server/lib" scripts/ cli/trading/ tests/` was instant,
precise, and gave us the exact file:line locations to fix.

**Rule:** Use the right tool for the job. GitNexus is for understanding
architecture. grep is for find-and-replace refactoring.

### The `extract-before-move` Pattern Is General

This is not specific to directory moves. Any structural change:
1. Identify couplings (what depends on what)
2. Break couplings (extract shared substrate)
3. Move structure (directories, functions, modules)
4. Verify (gates, then spot-checks)

Skipping step 2 creates a mess. We saw this in the Gum formatting work too:
experiment in a lab script first, then port the working pattern.

## New Directory Hierarchy

```
src/                    # Production TypeScript (strict, tested)
  server/               # Hono dashboard (from server/)
    index.tsx
    routes/
    views/
    static/
    lib/                # Server-only modules (NOT imported outside src/)
  cli/                  # TypeScript CLI (from cli/trading/)
    main.ts
    commands/
    lib/
  lib/                  # Shared production modules
    db.ts
    trade-calculator.ts

scripts/                # Support TypeScript (loose, tooling)
  lab/                  # Experiments (loosest)
    README.md           # Tier 0: wild west
  lib/                  # Shared helpers
    README.md           # Tier 1: strict types, reusable
  *.ts                  # Standalone scripts

cli/                    # Python CLI (frozen component)
  main.py
  utils.py
  static/

tradingagents/          # Python core (frozen component)
  agents/
  graph/
  llm_clients/
```

## Updated Conventions

| Convention | Justification |
|------------|---------------|
| `src/` is the production root | Contains all strict TypeScript; `tsc --noEmit` enforced |
| `src/lib/` for shared modules | Imported by `src/server/` and `src/cli/`; NOT by `scripts/` |
| `src/server/lib/` for server-only modules | NOT imported outside `src/server/` |
| Extract-before-move | Break couplings before moving directories |
| grep for old paths after rename | Faster and more precise than knowledge graph for refactoring |

## Files Touched

- **Phase 0:** 31 files (2 renamed: `server/lib/` → `src/lib/`)
- **Phase 1:** 91 files (89 renamed: `server/` → `src/server/`, `cli/trading/` → `src/cli/`)
- **Phase 2:** 11 files (justfile, package.json, scripts, comments)

**Total:** 133 files changed across 3 commits.

## TD Epic

- `td-91df32` — Directory Restructure: labs → scripts → src (closed)
- `td-c0ed4e` — Phase 0: Extract shared substrate (closed)
- `td-59e3fc` — Phase 1: Move production directories (closed)
- `td-b7acb4` — Phase 2: Update wiring (closed)
