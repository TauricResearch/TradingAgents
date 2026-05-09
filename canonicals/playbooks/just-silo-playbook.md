# Just-Silo Playbook

A **silo** is a self-contained project directory with named compartments,
each carrying a single responsibility. The `justfile` is the facade that
wires them together.

## The Principle

Every project is a silo. A silo contains all the "stuff" — code, docs,
configs, artefacts, indexes — organized so an agent can orient within
seconds of reading `just help`.

## Directory Structure

```
silo/
├── briefs/              # Work proposals (INDEX.jsonl)
├── debriefs/            # Post-work retrospectives (INDEX.jsonl)
│   ├── plans/
│   └── reviews/
├── decisions/           # Architecture Decision Records (INDEX.jsonl)
├── playbooks/           # Reusable conventions (REGISTRY.jsonl)
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
├── archive/             # Retired artefacts (gitignored)
├── justfile             # Task runner facade
├── package.json         # Dependencies (if Node/Bun)
├── pyproject.toml       # Dependencies (if Python)
├── tsconfig.json        # TypeScript config
└── .gitignore           # Standard exclusions
```

## Compartments

### Document Compartments (with Indexes)

Every directory that accumulates documents gets an `INDEX.jsonl`:

| Directory | Purpose | Index |
|-----------|---------|-------|
| `briefs/` | Work proposals, feature requests | `INDEX.jsonl` |
| `debriefs/` | Post-work writeups, reviews | `INDEX.jsonl` |
| `decisions/` | ADRs: why X over Y | `INDEX.jsonl` |
| `playbooks/` | Reusable conventions | `REGISTRY.jsonl` |
| `docs/` | Project documentation | `INDEX.jsonl` |

Schema: `{ file, date, status, summary, meta? }`

Tools: `reg-list.ts`, `reg-check.ts`, `reg-sync.ts`

### Source Compartment

| Directory | Purpose |
|-----------|---------|
| `src/cli/` | Command-line interface |
| `src/lib/` | Shared libraries (used by cli and server) |
| `src/server/` | Web server, API routes, views |

### Script Compartment

| Directory | Purpose |
|-----------|---------|
| `scripts/` | Production automation scripts |
| `scripts/lib/` | Shared modules (LLM client, formatting, DB wrapper) |
| `scripts/lab/` | Experiments, spikes, proofs of concept |

Rule: `scripts/` is TypeScript (Bun). Python scripts live in `scripts/py/`
only if the project has a Python dependency.

### Infrastructure Compartments

| Directory | Purpose |
|-----------|---------|
| `tests/` | Test suites (mirrors `src/` structure) |
| `backups/` | Generated backups (timestamped, pruned by `just backups-prune`) |
| `archive/` | Retired artefacts (old briefs, upstream issues) |

## Justfile Facade

The `justfile` is a **facade**, not a workbench. Complex logic lives in
`scripts/`. Recipes are one-line delegations.

### Navigation

```bash
just help       # Orient: what the project is
just info       # State: branch, env, DB counts
```

### Commit Gate

```bash
just check      # All quality gates must pass
```

Standard gates:
1. Lint/format (biome, ruff, eslint)
2. Type check (tsc, mypy)
3. Custom gates (project-specific)
4. Registry sync (`reg-sync.ts --all`)

### Service Lifecycle

```bash
just start      # Daemon start (PID file, log rotation)
just stop       # Graceful stop
just status     # Status table
just logs       # Tail logs
just restart    # Rotate, stop, start
```

### Registry Commands

```bash
just reg-briefs      # List briefs
just reg-debriefs    # List debriefs
just reg-decisions   # List decisions
just reg-canonical   # List canonical playbooks
just reg-docs        # List docs
just reg-sync        # Check indexes
just reg-sync-fix    # Fix drift
```

### Group Navigation Shortcuts

```bash
just b    # [bun] TypeScript tooling
just d    # [diagrams] Render/clean
just db   # [db] Database operations
just gn   # [gn] GitNexus graphs
just hk   # [hooks] Git hooks
just lab  # [lab] Experiments
just m    # [meta] Orientation
just p    # [python] Python bridge
just pr   # [pr] Pull requests
just r    # [run] Operations
just s    # [srv] Services
just t    # [test] Testing
```

## Conventions

### Max 7±2 per group

Miller's Law. If a `[group]` has more than 9 recipes, split it.

### One logical change per commit

All files that must change together, no more. Run `just check` before
and after.

### Fail-fast protocol

1. Make small change → check → commit or revert
2. If checks fail: revert first, diagnose second
3. If stuck >15 min: stop, revert, ask

### Lab-first development

Prove patterns in `scripts/lab/` before touching production.

### Conceptual Lexicon

The silo maintains a `silo-conceptual-lexicon.jsonl` at root level. Every
coined term, heuristic, or convention that is reused across documents
must be added here. Agents must consult the lexicon before inventing
new terminology — the term may already exist with a stable `id`.

New term process:
1. Check if the concept already exists in the lexicon
2. If yes, use the existing `id` and `[Related: ...]` links
3. If no, add an entry with `status: draft`, a heuristic, and a usage example
4. Upgrade to `status: active` only after the term has been used in two
   or more documents (briefs, playbooks, decisions, debriefs)

### Extract-before-move

Break cross-directory couplings before moving directories.

## Migration Path

For an existing project:

1. Create document compartments (`briefs/`, `debriefs/`, etc.)
2. Move existing documents into appropriate compartments
3. Create indexes (use `reg-sync.ts --fix`)
4. Restructure `justfile` into `[group("...")]` silos
5. Add navigation shortcuts
6. Wire `just check` to run quality gates + registry sync

## Failure Modes

### Index rot

Files added/deleted but index not updated. `reg-sync` detects this.
Run `just reg-sync` periodically.

### Facade bloat

Justfile grows >300 lines. Extract inline logic to `scripts/`.
The justfile should be 90% one-line delegations.

### Nav shortcut collision

Two groups want the same letter. Use two-letter shortcuts (`db`, `gn`, `hk`)
when single letters collide.

## Diagrams

- [silo-structure.svg](../diagrams/silo-structure.svg) — Directory compartment graph
- [just-silo.svg](../diagrams/just-silo.svg) — Justfile group relationship graph
