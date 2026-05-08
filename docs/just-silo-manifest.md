# Just-Silo Manifest

**Pattern**: Semantic recipe grouping for `just` command runners.
**Status**: Canonical (reusable across projects).
**Source**: TradingAgents.
**Covers**: justfile organization, group-based navigation, commit gates,
service lifecycle, registry management.

## The Pattern

Instead of a flat `justfile` with 100+ recipes in alphabetical order,
recipes are organized into **silos** — semantic groups that map to project
concerns. Each silo is a `[group("name")]` attribute. A navigation layer
provides single-letter shortcuts to list recipes within a group.

## Silo Taxonomy

| Silo | Concern | Recipes | Shortcut |
|------|---------|---------|----------|
| **nav** | Navigation | 15 letter shortcuts | (none — this IS the nav) |
| **meta** | Orientation | `help`, `info` | `m` |
| **bun** | TypeScript/Bun | `check`, `lint`, `serve`, `test-*` | `b` |
| **test** | Testing | `test-*`, `copy-test-to-dev` | `t` |
| **run** | Trading Operations | `analyze`, `portfolio`, `buylist`, `alerts`, `research`, `sync-prices`, `seed-db`, `trading` | `r` |
| **python** | Python Bridge | `install`, `run`, `test-smoke` | `p` |
| **srv** | Services | `start`, `stop`, `status`, `logs` | `srv` |
| **db** | Database | `backup`, `stats`, `reset` | `db` |
| **seed** | Seeding | `seed-*` | `s` |
| **reg** | Registry | `reg-*` (list, check, sync) | (via `r`) |
| **diagrams** | Diagrams | `diagrams`, `regen-diagrams` | `d` |
| **gn** | GitNexus | `gn-*` (graph, impact, context) | `gn` |
| **pr** | Pull Requests | `pr-fetch`, `pr-summarize` | `pr` |
| **td** | Task Management | `td-status`, `td-next`, `td-context` | (via `r`) |
| **hooks** | Git Hooks | `install-hooks`, `push` | `hk` |
| **lab** | Experiments | `lab-gum` | `lab` |

## Principles

1. **Max 7±2 per group** — Miller's Law. Groups with >9 recipes are
   candidates for splitting.
2. **One-letter shortcuts** — `just b` lists `[bun]` recipes. No typing
   `just --list --unsorted --color always`.
3. **Facade, not workbench** — Complex logic lives in scripts. Recipes
   are one-line delegations.
4. **Commit gate at `check`** — `just check` runs all quality gates
   (lint, typecheck, custom rules, registry sync).
5. **Registry for every document directory** — If it accumulates files,
   it gets an `INDEX.jsonl`.

## Commit Gate

`just check` enforces:

```
bunx biome check .               # lint + format
tsc --project tsconfig.server.json --noEmit  # type check
bun scripts/check-database-usage.ts          # custom gate
bun scripts/reg-sync.ts --all                # indexes up to date
```

All four must pass before commit.

## Navigation Shortcuts

```bash
just b      # [bun] recipes
just d      # [diagrams] recipes
just db     # [db] recipes
just gn     # [gn] recipes
just hk     # [hooks] recipes
just lab    # [lab] recipes
just m      # [meta] recipes
just p      # [python] recipes
just pr     # [pr] recipes
just r      # [run] recipes
just s      # [seed] recipes
just srv    # [srv] recipes
just t      # [test] recipes
```

## Registry Integration

Every silo that produces documents (briefs, debriefs, decisions, playbooks,
docs) has an `INDEX.jsonl` managed by `reg-sync.ts`:

```bash
just reg-sync      # check all indexes
just reg-sync-fix  # regenerate stale indexes
```

## Service Lifecycle

The `[srv]` silo manages long-running processes:

```bash
just start     # daemon start (PID file, log rotation)
just stop      # graceful stop (SIGTERM → wait → SIGKILL)
just status    # Gum-formatted status table
just logs      # tail recent logs
just restart   # rotate, stop, start
```

## Diagram

See [just-silo.svg](diagrams/just-silo.svg) for the full silo relationship
graph.
