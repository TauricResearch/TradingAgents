# EXHAUSTIVE JUSTFILE ANALYSIS
## /Users/petersmith/Dev/GitHub/TradingAgents/justfile

---

## EXECUTIVE SUMMARY

| Metric | Count |
|--------|-------|
| **Total Recipes** | 124 |
| **Total Groups** | 15 |
| **Aliases** | 9 |
| **Modules** | 1 |
| **Recipes with [confirm()]** | 2 |
| **SHIM recipes** | 31 |
| **WRAPPER recipes** | 73 |
| **COMPOSITE recipes** | 15 |
| **NATIVE recipes** | 5 |
| **Missing scripts** | 1 |
| **Undefined recipe calls** | 4 |

---

## RECIPES BY GROUP (COMPLETE LIST)

### [agent] — 10 recipes
Multi-agent coordination protocol (playbooks/td-playbook.md)

| Recipe | Line | Type | Purpose |
|--------|------|------|---------|
| `agent-claim` | 370 | SHIM | Claim task before touching files |
| `agent-claim-force` | 375 | WRAPPER | Force-claim (bypass collision check) |
| `agent-collisions` | 414 | WRAPPER | Show file collisions only |
| `agent-handoff` | 390 | WRAPPER | Structured handoff with note |
| `agent-handoff-full` | 395 | WRAPPER | Full handoff with done/remaining |
| `agent-next` | 365 | WRAPPER | What should I work on next? |
| `agent-orient` | 355 | SHIM | Full session startup |
| `agent-orient-c` | 360 | WRAPPER | Compact orientation (one line per section) |
| `agent-sync` | 409 | SHIM | Sync state: git vs main + file collisions |
| `wt-delete` | 346 | WRAPPER | Delete a worktree (removes dir + branch) |

**Arguments passed:**
- `agent-claim {{ ID }}` — passes task ID
- `agent-claim-force {{ ID }} --force` — passes ID + flag
- `agent-handoff {{ ID }} --note "handoff"` — passes ID + note
- `agent-handoff-full {{ ID }} --done @"$done_file" --remaining @"$remaining_file"` — passes ID + file refs
- `agent-log {{ ID }} {{ MSG }}` — passes ID + message
- `agent-log {{ ID }} {{ MSG }} --blocked` — passes ID + message + flag
- `agent-orient --compact` — passes flag
- `agent-orient --next` — passes flag
- `agent-sync --collisions` — passes flag
- `wt-create {{ NAME }} --base {{ BASE }}` — passes name + base branch
- `wt-create-task {{ NAME }} --base {{ BASE }} --task {{ TASK }}` — passes name + base + task ID
- `wt-delete {{ NAME }} --delete` — passes name + flag

---

### [bun] — 10 recipes
TypeScript server tooling

| Recipe | Line | Type | Purpose |
|--------|------|------|---------|
| `barnacle-watch` | 169 | WRAPPER | Watch for barnacles (runs scan every 60 min) |
| `check` | 196 | WRAPPER | Type-check + lint + custom gates |
| `convert-hex-oklch` | 206 | SHIM | Convert :root hex palette to oklch() |
| `format` | 211 | WRAPPER | Format all files with Biome |
| `lint` | 216 | WRAPPER | Lint code with Biome |
| `lint-fix` | 221 | WRAPPER | Lint and auto-fix errors |
| `serve` | 226 | COMPOSITE | Start dashboard server (LIVE mode, port 3000) |
| `test-smoke` | 268 | WRAPPER | Run pytest test suite |
| `test-trade-calc` | 273 | WRAPPER | Run trade calculator unit tests |
| `test-trade-calc-integration` | 278 | WRAPPER | Run trade calculator integration tests |

**Arguments passed:**
- `bun scripts/check-database-usage.ts` — no args
- `bun scripts/reg-sync.ts --all` — passes --all flag
- `bun scripts/td-orphans.ts || true` — no args, warning only

---

### [db] — 8 recipes
SQLite backup, restore, and maintenance

| Recipe | Line | Type | Purpose |
|--------|------|------|---------|
| `backup` | 498 | SHIM | Backup portfolio.db (timestamped copy) |
| `backup-test` | 503 | WRAPPER | Backup test_portfolio.db |
| `backups-list` | 508 | WRAPPER | List existing backups |
| `backups-prune` | 513 | WRAPPER | Prune backups older than N days (default: 30) |
| `db-active` | 518 | COMPOSITE | Show which database is currently active |
| `db-stats` | 530 | COMPOSITE | Show row counts for LIVE database |
| `db-stats-test` | 536 | COMPOSITE | Show row counts for TEST database |
| `trading` | 490 | WRAPPER | Unified trading CLI — generate trade plan |

**Arguments passed:**
- `bun scripts/db-backup.ts --test` — passes --test flag
- `bun scripts/db-backup.ts --list` — passes --list flag
- `bun scripts/db-backup.ts --prune 30` — passes --prune with value

---

### [diagrams] — 3 recipes
Render .dot / .mmd to .svg

| Recipe | Line | Type | Purpose |
|--------|------|------|---------|
| `copy-test-to-dev-apply` | 620 | WRAPPER | Copy TEST artefacts to LIVE (apply changes) |
| `diagrams` | 625 | SHIM | Render .dot and .mmd source files to .svg |
| `diagrams-clean` | 630 | COMPOSITE | Remove all generated .svg files |

---

### [gn] — 11 recipes
GitNexus code knowledge graph

| Recipe | Line | Type | Purpose |
|--------|------|------|---------|
| `gn-analyze` | 705 | WRAPPER | Re-index the repo (run after significant code changes) |
| `gn-changes` | 695 | WRAPPER | Map uncommitted changes to affected symbols |
| `gn-context` | 685 | WRAPPER | 360-degree view of a symbol |
| `gn-cypher` | 700 | WRAPPER | Raw Cypher query against the knowledge graph |
| `gn-diagrams` | 720 | WRAPPER | Generate key GitNexus graphs for the project |
| `gn-diagrams-clean` | 729 | COMPOSITE | Remove generated GitNexus diagrams |
| `gn-graph-file` | 715 | WRAPPER | Export file module graph to DOT/SVG |
| `gn-graph-symbol` | 710 | WRAPPER | Export symbol impact graph to DOT/SVG |
| `gn-impact` | 690 | WRAPPER | Blast radius: what breaks if you change a symbol |
| `gn-serve` | 736 | COMPOSITE | ⚠️ BROKEN: gitnexus serve fails due to CSP |
| `pr-summarize` | 678 | WRAPPER | Summarize PR changes |

**Arguments passed:**
- `gitnexus context "{{ SYM }}" --repo TradingAgents` — passes symbol + repo
- `gitnexus impact "{{ SYM }}" --direction upstream --repo TradingAgents` — passes symbol + direction + repo
- `gitnexus detect-changes --scope unstaged --repo TradingAgents` — passes scope + repo
- `gitnexus cypher "{{ QUERY }}" --repo TradingAgents` — passes query + repo
- `gitnexus analyze --force .` — passes --force flag
- `bun scripts/gitnexus-to-dot.ts --symbol {{ SYM }} --depth 1 --render` — passes symbol + depth + render
- `bun scripts/gitnexus-to-dot.ts --file {{ FILE }} --render` — passes file + render
- `bun scripts/gitnexus-batch.ts --render` — passes --render flag

---

### [hooks] — 2 recipes
Git workflow automation

| Recipe | Line | Type | Purpose |
|--------|------|------|---------|
| `install-hooks` | 802 | SHIM | Install pre-push hook that auto-regenerates diagrams |
| `lab-gum` | 794 | WRAPPER | Gum CLI output experiment |

---

### [lab] — 1 recipe
Terminal experiments

| Recipe | Line | Type | Purpose |
|--------|------|------|---------|
| `service-help` | 787 | SHIM | Show all available service commands |

---

### [meta] — 3 recipes
Project info, help, state

| Recipe | Line | Type | Purpose |
|--------|------|------|---------|
| `default` | 6 | WRAPPER | List all available recipes |
| `help` | 11 | WRAPPER | Orient: what the project is and how to navigate it |
| `info` | 16 | WRAPPER | State: current branch, env, DB counts, active tasks |

**Arguments passed:**
- `python scripts/gen-info-md.py` — no args

---

### [pr] — 4 recipes
GitHub pull request helpers

| Recipe | Line | Type | Purpose |
|--------|------|------|---------|
| `pr-fetch` | 659 | COMPOSITE | Save a PR review as markdown |
| `pr-fetch-all` | 674 | SHIM | Snapshot all open PRs |
| `prs` | 653 | COMPOSITE | List open PRs |
| `regen-diagrams` | 636 | WRAPPER | Regenerate all diagrams: static + gitnexus graphs |

**Arguments passed:**
- `bash scripts/pr-fetch-all.sh` — no args

---

### [python] — 8 recipes
tradingagents package, analysis

| Recipe | Line | Type | Purpose |
|--------|------|------|---------|
| `analyze` | 253 | WRAPPER | Run analysis on a ticker |
| `install` | 238 | WRAPPER | Install Python dependencies |
| `run` | 243 | WRAPPER | Launch interactive CLI (tradingagents analyze) |
| `run-cli` | 248 | WRAPPER | Launch CLI via python module |
| `serve-test` | 232 | COMPOSITE | Start dashboard server (TEST mode) |
| `summarize` | 258 | WRAPPER | Generate LLM summary for a ticker |
| `summarize-all` | 263 | WRAPPER | Regenerate all LLM summaries |
| `test-cli` | 283 | WRAPPER | Run CLI command smoke tests |

**Arguments passed:**
- `python scripts/py/analyze.py 'SPY' --date today --debates 1` — ⚠️ **SCRIPT MISSING**
- `bun run scripts/summarize_analyses.ts` — no args
- `bun run scripts/summarize_analyses.ts --all` — passes --all flag
- `uv run pytest tests/ -v` — passes -v flag

---

### [reg] — 21 recipes
Registry: briefs, debriefs, playbook indexes (JSONL + jq)

| Recipe | Line | Type | Purpose |
|--------|------|------|---------|
| `barnacle-scan` | 164 | SHIM | Scan for barnacles (stale conventions) |
| `ctx-lexicon` | 90 | WRAPPER | List conceptual lexicon |
| `ctx-lexicon-convert` | 110 | SHIM | Convert lexicon format |
| `ctx-lexicon-incorporate` | 114 | SHIM | Incorporate lexicon entries |
| `ctx-lexicon-stats` | 106 | WRAPPER | Show lexicon statistics |
| `reg-briefs` | 66 | SHIM | List all briefs (human-readable) |
| `reg-check` | 124 | SHIM | Validate all registries |
| `reg-debriefs` | 71 | SHIM | List all debriefs (human-readable) |
| `reg-decisions` | 61 | SHIM | List all decisions (human-readable) |
| `reg-docs` | 81 | SHIM | List all docs (human-readable) |
| `reg-import` | 144 | SHIM | Import a canonical playbook into the project |
| `reg-lexicon` | 86 | SHIM | List conceptual lexicon (terms, heuristics, definitions) |
| `reg-mine` | 139 | SHIM | Mine a playbook from project to canonicals |
| `reg-mining` | 76 | WRAPPER | List project playbooks that are mining candidates |
| `reg-promote` | 149 | SHIM | Promote a playbook |
| `reg-scripts` | 154 | SHIM | Sync script index: list all scripts with portability |
| `reg-scripts-fix` | 159 | WRAPPER | Sync script index — regenerate from disk |
| `reg-state` | 119 | SHIM | Show consolidated project state |
| `reg-sync` | 129 | WRAPPER | Check all indexes are up-to-date |
| `reg-sync-fix` | 134 | WRAPPER | Fix stale/missing index entries |
| `shortcuts` | 26 | COMPOSITE | Shortcut reference: just <letter> → group menu |

**Arguments passed:**
- `bun scripts/reg-list.ts decisions` — passes "decisions"
- `bun scripts/reg-list.ts briefs` — passes "briefs"
- `bun scripts/reg-list.ts debriefs` — passes "debriefs"
- `bun scripts/reg-list.ts docs` — passes "docs"
- `bun scripts/reg-list.ts lexicon` — passes "lexicon"
- `bun scripts/ctx-lexicon-list.ts --type={{ type }}` — passes --type with value
- `bun scripts/ctx-lexicon-list.ts --status={{ stat }}` — passes --status with value
- `bun scripts/ctx-lexicon-list.ts --search={{ query }}` — passes --search with value
- `bun scripts/ctx-lexicon-list.ts --stats` — passes --stats flag
- `bun scripts/reg-sync.ts --all` — passes --all flag
- `bun scripts/reg-sync.ts --all --fix` — passes --all --fix flags
- `jq -r 'select(.meta.mining_candidate == true) | "\(.file) — \(.meta.mining_note)"' playbooks/REGISTRY.jsonl` — pure jq, no script

---

### [run] — 12 recipes
Business operations (analyze, sync)

| Recipe | Line | Type | Purpose |
|--------|------|------|---------|
| `agent-end` | 419 | COMPOSITE | End session cleanly: handoff all in-progress tasks |
| `analyze-tka` | 431 | WRAPPER | Run analysis on TKA.DE (default test ticker) |
| `buylist` | 449 | WRAPPER | Show contingency buylist |
| `check-alerts` | 444 | SHIM | Check exit plan alerts for all positions |
| `portfolio` | 436 | WRAPPER | Show portfolio holdings via CLI |
| `portfolio-intel` | 459 | SHIM | Show portfolio holdings (LIVE) |
| `portfolio-intel-test` | 464 | NATIVE | Show portfolio holdings (TEST mode) |
| `research` | 454 | WRAPPER | Show portfolio holdings (LIVE, uses hledger + SQLite) |
| `seed-db` | 485 | SHIM | Seed LIVE SQLite database |
| `sync-prices` | 469 | WRAPPER | Sync prices for all open positions |
| `sync-prices-all` | 474 | WRAPPER | Full sync: gap fill + catch-up for all open positions |
| `sync-prices-ticker` | 479 | WRAPPER | Sync prices for a single ticker |

**Arguments passed:**
- `bun run src/cli/main.ts portfolio` — passes "portfolio"
- `bun run src/cli/main.ts alerts` — passes "alerts"
- `bun run src/cli/main.ts buylist` — passes "buylist"
- `bun run src/cli/main.ts research SPY` — passes "research SPY"
- `bun scripts/portfolio-intel.ts` — no args
- `bun scripts/portfolio-intel.ts test` — passes "test"
- `bun run scripts/sync-prices.ts` — no args
- `bun run scripts/sync-prices.ts --all` — passes --all flag
- `bun scripts/sync-prices.ts --ticker "${TICKER}"` — passes --ticker with env var

---

### [seed] — 5 recipes
Database seeding

| Recipe | Line | Type | Purpose |
|--------|------|------|---------|
| `db-reset-test` | 543 | WRAPPER | Reset TEST database (destroy and recreate) |
| `seed-db-exit-plans` | 563 | WRAPPER | Seed exit plans from YAML (LIVE) |
| `seed-db-positions` | 553 | WRAPPER | Seed positions only (LIVE) |
| `seed-db-prices` | 568 | WRAPPER | Seed prices from Yahoo Finance (backfill) |
| `seed-db-signals` | 558 | WRAPPER | Seed signals only (LIVE) |

**Arguments passed:**
- `bun scripts/seed_database.ts --positions` — passes --positions flag
- `bun scripts/seed_database.ts --signals` — passes --signals flag
- `bun scripts/seed_database.ts --exit-plans` — passes --exit-plans flag
- `bun scripts/seed_database.ts --prices` — passes --prices flag
- `bash scripts/init-test-db.sh --reset` — passes --reset flag

---

### [srv] — 7 recipes
Dashboard lifecycle

| Recipe | Line | Type | Purpose |
|--------|------|------|---------|
| `gn-status` | 744 | WRAPPER | Show index status |
| `logs` | 782 | SHIM | Show recent server logs |
| `ports` | 777 | SHIM | Show listening ports |
| `restart` | 771 | WRAPPER | Restart dashboard server |
| `start` | 758 | WRAPPER | Start dashboard server (background daemon) |
| `status` | 752 | WRAPPER | Show all service status |
| `stop` | 765 | WRAPPER | Stop dashboard server |

**Arguments passed:**
- `bun scripts/server-lifecycle.ts status` — passes "status"
- `bun scripts/server-lifecycle.ts start` — passes "start"
- `bun scripts/server-lifecycle.ts stop` — passes "stop"
- `bun scripts/server-lifecycle.ts restart` — passes "restart"
- `bun scripts/server-lifecycle.ts ports` — passes "ports"
- `bun scripts/server-lifecycle.ts logs` — passes "logs"
- `bun scripts/server-lifecycle.ts service-help` — passes "service-help"

---

### [td] — 5 recipes
Task management

| Recipe | Line | Type | Purpose |
|--------|------|------|---------|
| `td-context` | 309 | NATIVE | Get full context for a td issue |
| `td-new` | 293 | NATIVE | Start new td session |
| `td-next` | 304 | NATIVE | Show next priority issue |
| `td-status` | 298 | COMPOSITE | Show current td session and workspace |
| `test-quick` | 288 | SHIM | Quick smoke test for structured output |

**Arguments passed:**
- `td context {{ ID }}` — passes ID
- `.venv/bin/python scripts/py/smoke_structured_output.py openai` — passes "openai"

---

### [test] — 7 recipes
Development and test DB tools

| Recipe | Line | Type | Purpose |
|--------|------|------|---------|
| `copy-test-to-dev` | 615 | WRAPPER | Copy TEST artefacts to LIVE (dry-run) |
| `seed-test-journal` | 576 | SHIM | Seed hledger test journal |
| `test-db-signal` | 601 | WRAPPER | Seed signals to TEST DB |
| `test-db-stats` | 606 | COMPOSITE | Show row counts for LIVE and TEST DB |
| `test-init` | 584 | SHIM | Create fresh test_portfolio.db with schema |
| `test-reset` | 589 | WRAPPER | Wipe and recreate test DB |
| `test-seed` | 594 | WRAPPER | Seed test DB with E2E data |

**Arguments passed:**
- `bash scripts/init-test-db.sh` — no args
- `bash scripts/init-test-db.sh --reset` — passes --reset flag
- `bash scripts/seed_test_journal.sh` — no args
- `bun scripts/seed_database.ts --db ./test_portfolio.db --signals` — passes --db + --signals

---

### [ungrouped] — 3 recipes
(No group specified)

| Recipe | Line | Type | Purpose |
|--------|------|------|---------|
| `alerts` | 441 | WRAPPER | Check exit plan alerts for all positions |
| `push` | 807 | WRAPPER | Explicit push with diagram regen |
| `test-seed-db` | 573 | NATIVE | Seed TEST SQLite database |

---

### [worktree] — 4 recipes
Git worktree management

| Recipe | Line | Type | Purpose |
|--------|------|------|---------|
| `td-reset` | 314 | COMPOSITE | Reset td database |
| `wt-create` | 325 | WRAPPER | Create a worktree (sibling dir, new branch) |
| `wt-create-task` | 330 | WRAPPER | Create a worktree linked to a TD task |
| `wt-list` | 341 | WRAPPER | List all worktrees |

---

## CLASSIFICATION BREAKDOWN

### SHIM (31 recipes)
1-line passthrough to a bun/python/shell script with no added logic

```
agent-claim
agent-orient
agent-sync
backup
barnacle-scan
check-alerts
convert-hex-oklch
ctx-lexicon-convert
ctx-lexicon-incorporate
diagrams
install-hooks
lab-gum
logs
portfolio-intel
pr-fetch-all
reg-briefs
reg-check
reg-debriefs
reg-decisions
reg-docs
reg-import
reg-lexicon
reg-mine
reg-promote
reg-scripts
reg-state
seed-db
seed-test-journal
service-help
test-init
test-quick
```

### WRAPPER (73 recipes)
Calls a script with project-specific defaults or environment setup

```
agent-claim-force
agent-collisions
agent-handoff
agent-handoff-full
agent-next
agent-orient-c
analyze
analyze-tka
backup-test
backups-list
backups-prune
barnacle-watch
buylist
check
ctx-lexicon
ctx-lexicon-stats
copy-test-to-dev
copy-test-to-dev-apply
db-reset-test
format
gn-analyze
gn-changes
gn-context
gn-cypher
gn-diagrams
gn-graph-file
gn-graph-symbol
gn-impact
help
install
lint
lint-fix
portfolio
pr-summarize
regen-diagrams
reg-mining
reg-scripts-fix
reg-sync
reg-sync-fix
research
restart
run
run-cli
seed-db-exit-plans
seed-db-positions
seed-db-prices
seed-db-signals
serve-test
start
status
stop
summarize
summarize-all
sync-prices
sync-prices-all
sync-prices-ticker
test-cli
test-db-signal
test-reset
test-seed
test-smoke
test-trade-calc
test-trade-calc-integration
trading
wt-create
wt-create-task
wt-delete
```

### COMPOSITE (15 recipes)
Combines multiple operations

```
agent-end
agent-handoff-full
db-active
db-stats
db-stats-test
default
diagrams-clean
gn-diagrams-clean
gn-serve
pr-fetch
prs
serve
shortcuts
td-status
test-db-stats
```

### NATIVE (5 recipes)
Pure shell logic, no script called

```
portfolio-intel-test
td-context
td-new
td-next
test-seed-db
```

---

## ALIASES (9 total)

| Alias | Target | Purpose |
|-------|--------|---------|
| `a` | `analyze` | Run analysis on a ticker |
| `l` | `lint` | Lint code with Biome |
| `sc` | `shortcuts` | Shortcut reference |
| `hl` | `hledger::hl` | hLedger accounting |
| `hl-cash` | `hledger::hl-cash` | hLedger cash report |
| `hl-holdings` | `hledger::hl-holdings` | hLedger holdings report |
| `hl-prices` | `hledger::hl-prices` | hLedger prices report |
| `hl-register` | `hledger::hl-register` | hLedger register report |
| `hl-net-worth` | `hledger::hl-net-worth` | hLedger net worth report |

---

## MODULES (1 total)

| Module | Path | Purpose |
|--------|------|---------|
| `hledger` | (imported) | Plain-text accounting integration |

---

## RECIPES WITH [confirm()] ATTRIBUTE (2 total)

| Recipe | Line | Confirmation Message |
|--------|------|---------------------|
| `db-reset-test` | 541 | "Destroy and recreate test_portfolio.db?" |
| `stop` | 763 | "Stop the dashboard server?" |

---

## SCRIPT ANALYSIS

### Scripts Called from Justfile (70 total)

#### TypeScript Scripts (bun scripts/*.ts)
- agent-claim.ts ✓
- agent-handoff.ts ✓
- agent-log.ts ✓
- agent-orient.ts ✓
- agent-sync.ts ✓
- barnacle-scan.ts ✓
- check-alerts.ts ✓
- check-database-usage.ts ✓
- color-tools/convert-hex-to-oklch.ts ✓
- ctx-lexicon-convert.ts ✓
- ctx-lexicon-incorporate.ts ✓
- ctx-lexicon-list.ts ✓
- db-backup.ts ✓
- gitnexus-batch.ts ✓
- gitnexus-to-dot.ts ✓
- lab/gum.ts ✓
- portfolio-intel.ts ✓
- pr-summarize.ts ✓
- push-with-diagrams.ts ✓
- reg-check.ts ✓
- reg-import.ts ✓
- reg-list.ts ✓
- reg-mine.ts ✓
- reg-promote.ts ✓
- reg-state.ts ✓
- reg-sync-scripts.ts ✓
- reg-sync.ts ✓
- seed_database.ts ✓
- server-lifecycle.ts ✓
- summarize_analyses.ts ✓
- sync-prices.ts ✓
- td-orphans.ts ✓
- worktree-init.ts ✓

#### Python Scripts (python scripts/py/*.py)
- analyze.py ✗ **MISSING**
- gen-info-md.py ✓
- smoke_structured_output.py ✓

#### Bash Scripts (bash scripts/*.sh)
- copy-test-to-dev.sh ✓
- init-test-db.sh ✓
- install-pre-push-hook.sh ✓
- pr-fetch-all.sh ✓
- seed_test_journal.sh ✓

### Missing Scripts

| Script | Called From | Line | Issue |
|--------|-------------|------|-------|
| `scripts/py/analyze.py` | `analyze` recipe | 254 | **MISSING** — Recipe calls `python scripts/py/analyze.py 'SPY' --date today --debates 1` but file does not exist |

---

## UNDEFINED RECIPE CALLS

These are called within the justfile but not defined:

| Call | Context | Issue |
|------|---------|-------|
| `--list` | Line 7: `@just --list` | Built-in just flag, not a recipe |
| `--unstable` | Line 197: `just --unstable --fmt --check` | Built-in just flag |
| `recipes` | (not found) | Possible typo or removed recipe |
| `seed-db-test` | (not found) | Possible typo; should be `test-seed-db` |

---

## DUPLICATE/OVERLAPPING RECIPES

### Potential Duplicates

| Recipe 1 | Recipe 2 | Overlap | Recommendation |
|----------|----------|---------|-----------------|
| `analyze` | `analyze-tka` | Both run analysis; `-tka` is hardcoded to TKA.DE | Keep both; `-tka` is convenience shortcut |
| `backup` | `backup-test` | Both backup; one for LIVE, one for TEST | Keep both; different databases |
| `db-stats` | `db-stats-test` | Both show row counts; one for LIVE, one for TEST | Keep both; different databases |
| `test-init` | `test-reset` | Both initialize test DB; `-reset` also wipes | Keep both; `-init` creates fresh, `-reset` wipes existing |
| `test-seed` | `test-seed-db` | Both seed test DB | **POTENTIAL DUPLICATE** — `test-seed` (line 594) calls `init-test-db.sh --reset` + SQL; `test-seed-db` (line 573) calls `bun scripts/seed_database.ts --db ./test_portfolio.db` |
| `seed-db` | `seed-db-positions` | Both seed; one is full, one is positions only | Keep both; `-positions` is focused variant |
| `seed-db` | `seed-db-signals` | Both seed; one is full, one is signals only | Keep both; `-signals` is focused variant |
| `seed-db` | `seed-db-prices` | Both seed; one is full, one is prices only | Keep both; `-prices` is focused variant |
| `seed-db` | `seed-db-exit-plans` | Both seed; one is full, one is exit-plans only | Keep both; `-exit-plans` is focused variant |
| `sync-prices` | `sync-prices-all` | Both sync prices; one is catch-up, one is full | Keep both; `-all` is comprehensive variant |
| `sync-prices` | `sync-prices-ticker` | Both sync prices; one is all, one is single ticker | Keep both; `-ticker` is focused variant |
| `portfolio` | `portfolio-intel` | Both show portfolio; one via CLI, one via HTTP | Keep both; different interfaces |
| `portfolio-intel` | `portfolio-intel-test` | Both show portfolio; one LIVE, one TEST | Keep both; different databases |
| `copy-test-to-dev` | `copy-test-to-dev-apply` | Both copy TEST to LIVE; one dry-run, one apply | Keep both; `-apply` is confirmation variant |
| `gn-diagrams` | `gn-diagrams-clean` | Both manage diagrams; one generates, one cleans | Keep both; opposite operations |
| `diagrams` | `diagrams-clean` | Both manage diagrams; one generates, one cleans | Keep both; opposite operations |
| `regen-diagrams` | `diagrams` | Both render diagrams | **POTENTIAL DUPLICATE** — `regen-diagrams` (line 636) is more comprehensive (cleans + generates GitNexus + renders DOT); `diagrams` (line 625) only renders DOT/MMD |

---

## DEAD RECIPES

These recipes are defined but never called within the justfile (excluding entry points):

**Count: 124 recipes** (all recipes are "dead" in the sense that they're not called by other recipes — they're entry points meant to be called by users)

This is **normal and expected** for a task runner. Recipes are meant to be invoked directly by users, not called by other recipes.

---

## CONFIGURATION DECLARATIONS

### Set Directives (Line 179-181)

```justfile
set shell := ["bash", "-o", "pipefail", "-c"]
set positional-arguments
set dotenv-load
```

**Purpose:**
- `shell` — Use bash with pipefail for robust error handling
- `positional-arguments` — Allow recipes to accept positional arguments
- `dotenv-load` — Auto-load .env file

---

## SUMMARY OF ISSUES

### Critical Issues
1. **Missing script: `scripts/py/analyze.py`** (Line 254)
   - Recipe `analyze` calls `python scripts/py/analyze.py 'SPY' --date today --debates 1`
   - File does not exist
   - **Action:** Either create the script or update the recipe to call a different script

### Minor Issues
1. **Undefined recipe calls:**
   - `--list`, `--unstable` — Built-in just flags (not issues)
   - `recipes` — Possible typo or removed recipe
   - `seed-db-test` — Possible typo; should be `test-seed-db`

2. **Potential duplicate recipes:**
   - `test-seed` vs `test-seed-db` — Both seed test DB but use different approaches
   - `regen-diagrams` vs `diagrams` — `regen-diagrams` is more comprehensive

3. **Broken recipe:**
   - `gn-serve` (Line 736) — Marked as broken due to CSP on gitnexus.vercel.app

### Recommendations
1. **Fix missing script:** Create `scripts/py/analyze.py` or update recipe to call existing script
2. **Clarify test seeding:** Document difference between `test-seed` and `test-seed-db`
3. **Consolidate diagram recipes:** Consider merging `diagrams` and `regen-diagrams` or clarify their purposes
4. **Remove broken recipe:** Either fix `gn-serve` or remove it entirely

---

## STATISTICS

| Metric | Count |
|--------|-------|
| Total recipes | 124 |
| Total groups | 15 |
| Recipes per group (avg) | 8.3 |
| Largest group | [reg] with 21 recipes |
| Smallest group | [lab] with 1 recipe |
| SHIM recipes | 31 (25%) |
| WRAPPER recipes | 73 (59%) |
| COMPOSITE recipes | 15 (12%) |
| NATIVE recipes | 5 (4%) |
| Recipes with arguments | 89 (72%) |
| Recipes with [confirm()] | 2 (1.6%) |
| Aliases | 9 |
| Modules | 1 |
| Scripts called | 70 |
| Missing scripts | 1 |
| Undefined calls | 4 |

