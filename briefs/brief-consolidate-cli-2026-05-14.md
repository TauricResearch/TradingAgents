# Brief: Consolidate CLI Commands

**Date:** 2026-05-14
**Status:** Open

---

## Task: Shrink 42 CLI commands to ~15 with proper subcommand grouping

**Objective:** The TypeScript CLI currently has 42 top-level commands, many of which (8 IG commands, 6 config commands) should be subcommands of a parent — reducing the cognitive surface and maintenance burden.

## What

- [ ] Consolidate 8 IG commands (`ig-accounts`, `ig-buy`, `ig-history`, `ig-login`, `ig-positions`, `ig-prices`, `ig-search`, `ig-sell`, `ig`) into a single `ig` command with subcommands: `ig accounts`, `ig buy TICKER`, `ig sell TICKER`, `ig login`, `ig positions`, `ig prices TICKER`, `ig search QUERY`, `ig history`
- [ ] Consolidate 6 config commands (`config-get`, `config-set`, `config-list`, `config-delete`, `config-path`, `config`) into a single `config` command with subcommands: `config get KEY`, `config set KEY VALUE`, `config list`, `config delete KEY`, `config path`
- [ ] Consolidate 3 alerts commands (`alerts-check`, `alerts-create`, `alerts-delete`, `alerts-list`, `alerts`) into a single `alerts` command
- [ ] Review remaining commands for similar consolidation opportunities (e.g. `sync-prices` + `sync` → `sync prices`, `export` + `import` → `data export`/`data import`)
- [ ] Remove or archive any commands that duplicate dashboard functionality without adding value (e.g. `analyze` when the dashboard's analysis tab exists, `portfolio` when the dashboard portfolio tab exists)
- [ ] Update `src/cli/main.ts` entry point with the new command tree
- [ ] Update `src/cli/lib/` — any shared CLI utilities should be extracted if consolidation reveals duplication
- [ ] Update `justfile` CLI-related recipes to match new command names

## How to Verify

- [ ] Run `just check`
- [ ] `bun run trading --help` shows ~15 commands (not 42)
- [ ] `bun run trading ig --help` shows subcommands: accounts, buy, sell, login, positions, prices, search, history
- [ ] `bun run trading config --help` shows subcommands: get, set, list, delete, path
- [ ] All existing workflows (scripts, just recipes) that call the old command names still work or have been updated
- [ ] Edge case: old command names produce a helpful deprecation message pointing to the new name (if not immediately removed)

## Technical Notes

- citty supports nested subcommands natively — see existing `ig` command for pattern
- The IG commands are the biggest consolidation target (8 files → 1 file). Extract shared IG logic into `src/cli/lib/ig-common.ts` rather than duplicating it in subcommand handlers
- Config commands similarly share a common backend — extract into `src/cli/lib/config-common.ts`
- Risk: external scripts or cron jobs calling the old command names. Add deprecation wrappers before removing, or do a `git grep` to find all callers first

---

## Done

When all `[ ]` items are checked and verified.
