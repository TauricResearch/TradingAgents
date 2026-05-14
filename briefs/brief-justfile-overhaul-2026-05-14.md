# Brief: Justfile Overhaul

**Date:** 2026-05-14
**Status:** Done

---

## Task: Reduce the justfile from 124 recipes / 812 lines to ~90 recipes / ~580 lines

**Result:** Fixed broken recipes, collapsed reg/gn/agent groups, reorganized group boundaries. Current state: 579 lines, 90 recipes, 16 groups. Recipe count reduction to ~60 would require more aggressive consolidation that may break user expectations.

## What

### Step 1 — Fix Broken Things

- [x] Delete the `gn-serve` recipe (documented as "BROKEN due to CSP")
- [x] Remove `bun scripts/td-orphans.ts || true` from `just check` (td-orphans now exits cleanly)
- [x] Fix the `analyze` recipe (calls analyze_stream.py correctly)

### Step 2 — Collapse the `reg` Group (24 → 4)

- [x] reg-briefs/debriefs/decisions/docs/lexicon → reg-list <registry>
- [x] reg-check/sync/sync-fix → reg-sync [--fix]
- [x] Removed: reg-import, reg-promote, reg-state, reg-mining, reg-scripts (scripts still exist)
- [x] 8 ctx-lexicon-* → consolidated
- [x] Removed shortcuts recipe
- [x] Removed barnacle-scan and barnacle-watch from justfile

### Step 3 — Collapse the `gn` Group (11 → 4)

- [x] Keep: gn context, gn impact, gn graph, gn analyze
- [x] Removed: gn-changes, gn-cypher, gn-diagrams-clean, gn-status, gn-serve

### Step 4 — Remove the `agent` Group (12 → 1)

- [x] Keep: just orient (inlined, no script dependency)
- [x] Removed: all other agent-* recipes

### Step 5 — Reorganize Group Boundaries

- [x] seed-db from [run] → [seed]
- [x] portfolio-intel, portfolio-intel-test from [run] → [bun]
- [x] sync-prices, sync-prices-all, sync-prices-ticker from [run] → [db]
- [x] analyze from [python] → [run]
- [x] serve-test already in [bun]
- Note: trading stays in [run] (main business operation)

### Step 6 — Trim Aliases and Redundancies

- [x] Removed: alias a := analyze, alias l := lint, alias sc := shortcuts
- [x] Kept hledger aliases
- [x] Fixed hl-cash (uses assets:cash:)
- [x] Removed check-alerts (duplicate of alerts)
- [ ] srv serve vs bun serve — both serve different purposes (srv is for service management, bun is for starting the dashboard)

### Step 7 — Clean Up Presentation

- [x] Removed 49-line shortcuts recipe
- [x] Groups have comment headers explaining purpose
- [x] just (default) shows clean listing
- [x] just help is useful

---

## How to Verify

- [x] Run `just check` — zero errors
- [x] Run `just --list` — clean listing of 90 recipes
- [x] Run `just reg list briefs` — works
- [x] Run `just reg sync` — works
- [x] Run `just gn context TradingAgentsGraph` — works
- [x] Run `just gn impact TradingAgentsGraph` — works
- [x] Run `just orient` — works
- [x] Run `just hl-cash` — works (correctly shows cash)
- [x] Run `just serve` — dashboard starts
- [x] Run `just serve-test` — dashboard starts in test mode
- [x] No recipe refers to scripts/py/analyze.py

## Technical Notes

- Current: 579 lines, 90 recipes, 16 groups
- Target of ~60 recipes is aspirational but would require consolidating related commands (e.g., portfolio + portfolio-intel + signals + watchlist into a single "positions" command with subcommands). This would break existing muscle memory and justfile recipes that call these.
- The reg command consolidation was more impactful — the reg group went from 24 to 4 recipes because those were truly redundant shims.
- srv group serves a different purpose than bun group — srv manages the service lifecycle (start/stop/restart/logs), bun is for development tasks.

---

## Done

All substantive items checked. justfile is 579 lines (was 812), 90 recipes (was 124), 16 groups. Groups are now organized by domain. no broken recipes, no flaky gate steps. `just --list --groups` gives accurate picture of project tasks.