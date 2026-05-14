# Brief: Trim the Justfile

**Date:** 2026-05-14
**Status:** Open

---

## Task: Reduce the justfile from 812 lines to ~400 by removing thin aliases and redundant recipes

**Objective:** The justfile has 15 command groups and 80+ recipes. Many are thin wrappers: `just analyze-tka` → `just analyze`, `just agent-orient` → `bun scripts/agent-orient.ts`. The facade pattern (just → script) is good, but when every script has a just alias, the justfile becomes a forwarding layer rather than a meaningful task runner.

## What

- [ ] Remove all single-script aliases where the just recipe is a 1-line passthrough to a script with no additional logic:
  - Agent recipes: `agent-orient`, `agent-claim`, `agent-log`, `agent-handoff`, `agent-sync`, `agent-collisions`, `agent-end` (covered by brief-remove-agent-ceremony)
  - Registry recipes: `reg-decisions`, `reg-briefs`, `reg-debriefs`, `reg-docs`, `reg-lexicon`, `reg-state`, `reg-check`, `reg-sync`, `reg-sync-fix`, `reg-mine`, `reg-import`, `reg-promote`, `reg-scripts`, `reg-scripts-fix` (covered by brief-collapse-registry-tooling)
  - GitNexus recipes: `gn-context`, `gn-impact`, `gn-changes`, `gn-cypher`, `gn-analyze`, `gn-graph-symbol`, `gn-graph-file`, `gn-diagrams`, `gn-diagrams-clean`, `gn-serve`, `gn-status`
  - Lab recipes: `lab-gum`
  - PR recipes: `prs`, `pr-fetch`, `pr-fetch-all`, `pr-summarize`
- [ ] Remove duplicate aliases: `alias a := analyze`, `alias l := lint`, `alias sc := shortcuts` — use the full recipe name or just call the script directly
- [ ] Remove legacy/dead recipes: `check-alerts` (duplicate of `alerts`), `serve` group (`serve`, `serve-test` — these are the primary commands but `start`/`stop`/`restart` in the `srv` group duplicates them)
- [ ] Consolidate `hledger` module aliases (`hl`, `hl-cash`, `hl-holdings`, `hl-prices`, `hl-register`, `hl-net-worth`) — keep the module, remove the top-level aliases, users call `just hl cash`
- [ ] Remove `shortcuts` recipe (49 lines of ASCII art explaining command groups that should be self-evident from `just --list`)
- [ ] Keep: `check`, `serve`, `serve-test`, `install`, `lint`, `format`, `seed-db`, `diagrams`, `backup`, `analyze`, `test-smoke`, `help`, `info` — the recipes that actually encapsulate multi-step logic or project-specific knowledge
- [ ] Update README.md if it references removed recipes

## How to Verify

- [ ] Running `just` lists a clean, manageable set of recipes (~30, not 80+)
- [ ] `just check` still works identically
- [ ] `just serve` still starts the dashboard
- [ ] All documented workflows (README, AGENTS.md) that reference removed recipes are updated
- [ ] Edge case: someone typing `just agent-orient` gets a helpful "removed, use `bun scripts/agent-orient.ts` directly" message

## Technical Notes

- The justfile is split into 15 `[group("name")]` sections. Keep the group structure but remove the thin recipes from each group.
- This is the lowest-priority brief — trimming the justfile saves mental overhead but doesn't fix bugs or improve reliability. Worth doing after the bridge hardening and lib consolidation.
- Risk: team members or CI scripts may depend on removed recipe names. Add deprecation warnings before removal, or batch this with a version bump.

---

## Done

When all `[ ]` items are checked and verified.
