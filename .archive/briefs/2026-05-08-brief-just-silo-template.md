# Brief: Just-Silo Template

**Date**: 2026-05-08
**Status**: open
**Epic**: UNIFIED-CLI-001

## Problem

Every new project starts as an undifferentiated blob of files. Conventions
emerge organically — or not at all. Agents and humans waste cycles
discovering where things live, what the commit gate is, how to start services,
whether the database is live or test.

## Solution

A canonical **silo template**: a directory structure with named compartments,
each with a single responsibility, wired together by a `justfile` facade.

A silo is a self-contained project directory. It contains all the "stuff" —
code, docs, configs, artefacts, indexes — organized so an agent can orient
within seconds.

## Silo Structure

```
silo/
├── briefs/              # Work proposals (INDEX.jsonl)
├── debriefs/            # Post-work retrospectives (INDEX.jsonl)
│   ├── plans/
│   └── reviews/
├── decisions/           # Architecture Decision Records (INDEX.jsonl)
├── playbooks/           # Reusable conventions (INDEX.jsonl)
│   └── REGISTRY.jsonl   # Canonical vs project-specific
├── docs/                # Project documentation (INDEX.jsonl)
│   ├── diagrams/        # Generated diagrams
│   └── schema/          # Schema documentation
├── scripts/             # Automation scripts
│   ├── lib/             # Shared script modules
│   └── lab/             # Experiments and spikes
├── src/                 # Source code
│   ├── cli/             # Command-line interface
│   ├── lib/             # Shared libraries
│   └── server/          # Web server / API
├── tests/               # Test suites
├── backups/             # Generated backups (gitignored)
├── archive/             # Retired artefacts (gitignored content)
├── justfile             # Task runner facade
├── package.json         # Dependencies (if Node/Bun)
├── pyproject.toml     # Dependencies (if Python)
├── tsconfig.json        # TypeScript config
└── .gitignore           # Standard exclusions
```

## Compartment Responsibilities

| Directory | What lives here | Index |
|-----------|----------------|-------|
| `briefs/` | Work proposals, feature requests, research questions | `INDEX.jsonl` |
| `debriefs/` | Post-work writeups, gap analyses, reviews | `INDEX.jsonl` |
| `decisions/` | ADRs: why we chose X over Y | `INDEX.jsonl` |
| `playbooks/` | Reusable conventions, process documentation | `REGISTRY.jsonl` |
| `docs/` | Project documentation, guides, manifests | `INDEX.jsonl` |
| `scripts/` | Automation: backups, sync, analysis, diagram generation | (none) |
| `scripts/lib/` | Shared script modules (llm.ts, gum.ts, db.ts) | (none) |
| `scripts/lab/` | Experiments, spikes, proofs of concept | (none) |
| `src/` | Production source code | (none) |
| `tests/` | Test suites | (none) |
| `backups/` | Generated backups (timestamped, pruned) | (none) |
| `archive/` | Retired artefacts (old briefs, upstream issues) | (none) |

## Justfile Facade

The `justfile` is the **facade**, not the workbench. Every recipe is a
one-line delegation to a script or tool.

### Silo Navigation

```bash
just help       # Orient: what the project is
just info       # State: branch, env, DB counts, active tasks
```

### Commit Gate

```bash
just check      # All quality gates must pass
```

Quality gates:
1. Lint/format (biome, ruff, eslint — project-dependent)
2. Type check (tsc, mypy)
3. Custom gates (no raw Database(), no unicode escapes, etc.)
4. Registry sync (all INDEX.jsonl files match filesystem)

### Service Lifecycle

```bash
just start      # Start services (PID files, log rotation)
just stop       # Graceful stop
just status     # Gum-formatted status table
just logs       # Tail recent logs
```

### Registry Commands

```bash
just reg-briefs      # List briefs (human-readable)
just reg-debriefs    # List debriefs
just reg-decisions   # List decisions
just reg-canonical   # List canonical playbooks
just reg-docs        # List docs
just reg-sync        # Check indexes against filesystem
just reg-sync-fix    # Regenerate stale indexes
```

### Group Navigation

```bash
just b    # [bun] recipes
just d    # [diagrams] recipes
just db   # [db] recipes
just s    # [srv] recipes
just t    # [test] recipes
```

## Registry Convention

Every directory that accumulates documents gets an `INDEX.jsonl`:

```json
{"file":"filename.md","date":"2026-05-08","status":"done","summary":"What this document is about","meta":{"epic":"EPIC-001"}}
```

Tools:
- `reg-list.ts` — human-readable display
- `reg-check.ts` — schema validation
- `reg-sync.ts` — detect drift (files vs index)

## Migration Path

For an existing project:

1. Create `briefs/`, `debriefs/`, `decisions/`, `playbooks/`, `docs/`
2. Move existing documents into appropriate compartments
3. Create `INDEX.jsonl` for each (use `reg-sync.ts --fix`)
4. Restructure `justfile` into `[group("...")]` silos
5. Add navigation shortcuts (`just b`, `just d`, etc.)
6. Wire `just check` to run quality gates + registry sync

## Acceptance Criteria

- [ ] `just help` orients a new agent in <30 seconds
- [ ] `just check` passes (lint + typecheck + gates + registry sync)
- [ ] Every document directory has an `INDEX.jsonl`
- [ ] `just reg-sync` reports all indexes up to date
- [ ] Navigation shortcuts exist for all major groups
- [ ] `justfile` is <300 lines (facade, not workbench)
- [ ] Complex logic lives in `scripts/`, not inline bash
