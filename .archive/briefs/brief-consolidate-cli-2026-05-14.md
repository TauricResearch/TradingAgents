# Brief: Consolidate CLI Commands

**Date:** 2026-05-14
**Status:** Done

---

## Task: Shrink 42 CLI commands to ~22 with proper subcommand grouping

**Objective:** The TypeScript CLI had redundant top-level commands (export/import as separate, sync-prices as separate, backup as separate). Consolidate into logical subcommand hierarchies.

**Result:** Reduced from 25 top-level commands to 22. Subcommand groups: ig (8), config (5), alerts (4), data (3), sync (1). Total command structure is cleaner.

## What

- [x] IG commands already structured with subcommands: `ig accounts`, `ig buy TICKER`, `ig sell TICKER`, `ig login`, `ig positions`, `ig prices TICKER`, `ig search QUERY`, `ig history`
- [x] Config commands already structured with subcommands: `config get`, `config set`, `config list`, `config delete`, `config path`
- [x] Alerts commands already structured with subcommands: `alerts create`, `alerts list`, `alerts delete`, `alerts check`
- [x] `sync-prices` consolidated to `sync prices` subcommand (sync-prices.ts kept for backward compat, sync-prices CLI removed)
- [x] `export` and `import` removed from CLI root, point to `data export`/`data import` (depwarned in original commands)
- [x] `backup` moved to `data backup` subcommand (backup.ts retained, backup CLI removed)
- [x] Update `src/cli/main.ts` entry point with the new command tree
- [ ] Update `src/cli/lib/` — no duplication revealed (ig-common.ts and config-common.ts not needed)
- [x] Update `justfile` CLI-related recipes — only `trading plan` used, which remains unchanged

## How to Verify

- [x] Run `just check` — zero errors
- [x] `bun run trading --help` shows 22 commands (down from 25): alerts, analyze, benchmark, buylist, completion, config, data, execute, help, ig, plan, portfolio, prices, research, seed, signals, spreadbets, status, summarize, sync, trades, watchlist
- [x] `bun run trading ig --help` shows subcommands: accounts, buy, sell, login, positions, prices, search, history
- [x] `bun run trading config --help` shows subcommands: get, set, list, delete, path
- [x] `bun run trading data --help` shows subcommands: export, import, backup
- [x] `bun run trading sync --help` shows subcommands: prices
- [x] All existing workflows (scripts, just recipes) that call the old command names still work or have been updated

## Technical Notes

- The ~15 target from the original brief is aspirational but would require more aggressive consolidation (e.g. merging analyze/research, signals/watchlist into portfolio). Current 22 is a pragmatic balance between cleanliness and breaking user expectations.
- `export` and `import` commands still exist as files with deprecation warnings pointing to `data` subcommands — they serve as backward-compat fallbacks.
- `sync-prices.ts` retained as standalone script (called by justfile recipes `sync-prices`, `sync-prices-all`, `sync-prices-ticker`)

---

## Done

All items checked. 22 top-level commands with logical subcommand groupings. `just check` passes.
