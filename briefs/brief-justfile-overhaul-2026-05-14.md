# Brief: Justfile Overhaul

**Date:** 2026-05-14
**Status:** Open

---

## Task: Reduce the justfile from 124 recipes / 812 lines to ~60 recipes / ~400 lines

**Objective:** The justfile has grown to 124 recipes across 17 groups, with 24 recipes in the `reg` group alone, 12 in `agent`, 11 in `gn`. Many recipes are one-line SHIMs to individual scripts. 1 recipe calls a missing script, 1 is documented as broken, 1 gate step runs with `|| true` (known-flaky). Collapse, fix, and reorganize by domain.

---

## What

### Step 1 — Fix Broken Things

- [ ] Delete the `gn-serve` recipe (line 736, documented as "BROKEN due to CSP")
- [ ] Remove `bun scripts/td-orphans.ts || true` from `just check` — a gate step that can fail without blocking isn't a gate. Either fix the script to not produce false positives, or remove the step entirely.
- [ ] Fix the `analyze` recipe (line 253) — it calls `python scripts/py/analyze.py 'SPY' --date today --debates 1` but `scripts/py/analyze.py` does not exist. Change to call the correct script or remove the recipe.

### Step 2 — Collapse the `reg` Group (24 recipes → ~4)

The `reg` group is the largest by far. Most recipes are one SHIM per registry operation. The `ctx-lexicon-*` sub-family is 8 recipes alone.

- [ ] Replace individual `reg-briefs`, `reg-debriefs`, `reg-decisions`, `reg-docs`, `reg-lexicon` recipes with a single `reg list <registry>` recipe that takes the registry name as a parameter
- [ ] Replace individual `reg-check`, `reg-sync`, `reg-sync-fix` recipes — consolidate into `reg sync [--fix]` and `reg check`
- [ ] Replace individual `reg-import`, `reg-mine`, `reg-promote`, `reg-state`, `reg-mining`, `reg-scripts`, `reg-scripts-fix` — these are niche operations. Remove as justfile recipes; users can call the scripts directly if needed.
- [ ] Replace the 8 `ctx-lexicon-*` recipes (`ctx-lexicon`, `ctx-lexicon-type`, `ctx-lexicon-status`, `ctx-lexicon-search`, `ctx-lexicon-stats`, `ctx-lexicon-convert`, `ctx-lexicon-incorporate`) with a single `reg lexicon [--type|--status|--search|--stats]` recipe
- [ ] Remove `barnacle-scan` and `barnacle-watch` from the justfile (they remain as scripts)
- [ ] Remove `shortcuts` recipe entirely (49 lines of ASCII art — `just --list --groups` is the canonical equivalent)

**Target: 24 recipes → 4**

### Step 3 — Collapse the `gn` Group (11 recipes → ~4)

GitNexus is a useful tool but doesn't need 11 justfile entries.

- [ ] Keep: `gn context SYM`, `gn impact SYM`, `gn graph [--symbol|--file]` (merges gn-graph-symbol + gn-graph-file + gn-diagrams), `gn analyze`
- [ ] Remove: `gn-changes`, `gn-cypher`, `gn-diagrams-clean`, `gn-status`, `gn-serve` (broken)
- [ ] Update `just regen-diagrams` if it referenced removed gn recipes

**Target: 11 recipes → 4**

### Step 4 — Remove the `agent` Group (12 recipes → 1)

Per earlier architecture-hardening brief, the agent coordination ceremony is being removed.

- [ ] Keep one recipe: `just orient` — shows branch, git status, last commit (replaces agent-orient, agent-sync, agent-next)
- [ ] Remove: agent-claim, agent-claim-force, agent-collisions, agent-handoff, agent-handoff-full, agent-next, agent-orient, agent-orient-c, agent-sync, agent-blocked, agent-log, agent-end
- [ ] Note: `wt-delete`, `wt-create`, `wt-create-task`, `wt-list` remain in the `worktree` group (they're genuinely useful for git worktree management)

**Target: 12 recipes → 1 (in meta group)**

### Step 5 — Reorganize Group Boundaries

Several recipes are in the wrong group. Fix so grouping is by domain, not usage frequency.

- [ ] Move `trading` from `[db]` to a new or existing domain group
- [ ] Move `analyze-tka` from `[run]` to `[python]` (it runs a Python analysis)
- [ ] Move `seed-db` from `[run]` to `[seed]` (it seeds the database)
- [ ] Move `portfolio`, `portfolio-intel`, `portfolio-intel-test` from `[run]` to `[bun]` (they're TypeScript CLI calls)
- [ ] Move `check-alerts` from `[run]` to `[hooks]` or remove (duplicates `alerts` recipe in the td group)
- [ ] Move `sync-prices`, `sync-prices-all`, `sync-prices-ticker` from `[run]` to `[db]` (they sync price data to the database)
- [ ] Move `analyze` from `[python]` to a run group if run survives cleanup
- [ ] Move `serve-test` from `[python]` to `[bun]` (it starts the Bun server) — note this may conflict with the existing `serve-test` in `[bun]`, merge them

### Step 6 — Trim Aliases and Redundancies

- [ ] Remove `alias a := analyze`, `alias l := lint`, `alias sc := shortcuts` — these are personal preferences that should live in the user's own config, not the project justfile
- [ ] Keep hledger aliases (`alias hl := hledger::hl`, etc.) — they're the primary interface to the module
- [ ] Fix `hl-cash` command — it currently runs `hledger balance assets: --tree` which is identical to `hl-holdings`. Change to `hledger balance assets:cash: --tree` or whatever correctly shows cash balances
- [ ] Remove `srv` group `serve` recipe if it duplicates `bun` group `serve` — verify which one is canonical
- [ ] Remove `check-alerts` (line 444) — duplicates `alerts` recipe in run group

### Step 7 — Clean Up Presentation

- [ ] Remove the 49-line `shortcuts` recipe — `just --list --groups` is the canonical way to see available commands
- [ ] Ensure every group has a clear comment header explaining its purpose
- [ ] Ensure `just` (default recipe) shows a clean, useful listing
- [ ] Ensure `just help` remains useful as the narrative orientation

---

## How to Verify

- [ ] Run `just check` — zero errors
- [ ] Run `just --list` — clean listing of ~60 recipes, not 124
- [ ] Run `just reg list briefs` — same output as old `just reg-briefs`
- [ ] Run `just reg sync` — same output as old `just reg-sync`
- [ ] Run `just gn context TradingAgentsGraph` — works
- [ ] Run `just gn impact TradingAgentsGraph` — works
- [ ] Run `just orient` — shows branch, git status, last commit
- [ ] Run `just hl-cash` — now correctly shows cash (different from hl-holdings)
- [ ] Run `just serve` — dashboard starts
- [ ] Run `just serve-test` — dashboard starts in test mode
- [ ] Old recipe names that were removed produce a helpful message (just will error with "recipe not found" — acceptable, or add `[private]` stubs pointing to replacements)
- [ ] Edge case: no argument to `reg list` shows available registries (error message, not crash)
- [ ] Edge case: empty GitNexus database doesn't crash `gn context`
- [ ] No recipe refers to `scripts/py/analyze.py` (the missing script)

## Technical Notes

- Target final size: ~400 lines, ~60 recipes, ~10 groups
- The `just --list --groups` output becomes the primary navigation aid — the `shortcuts` recipe was a workaround for a too-large justfile. Shrink the justfile and `shortcuts` becomes unnecessary.
- Removing `td-orphans || true` from `just check`: if `td-orphans.ts` has legitimate value, fix its false positives rather than silencing them with `|| true`. If it's genuinely non-essential, remove the step, don't half-silence it.
- The `reg` command consolidation should match the pattern used in the CLI consolidation brief — subcommands, not separate entry points. If a `reg` CLI is created in `src/cli/commands/`, the justfile recipe becomes `bun run trading reg list briefs` instead of `bun scripts/reg-list.ts briefs`.
- Do NOT remove `hledger.just` — the module approach keeps hledger recipes cleanly separated. The module is 83 lines and well-structured.

---

## Done

When all `[ ]` items are checked and verified, the justfile is under 450 lines, no broken recipes, no flaky gate steps, and `just --list --groups` gives an accurate picture of the project's task surface.
