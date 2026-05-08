# Diagrams

This directory contains both hand-crafted architectural diagrams and auto-generated code dependency graphs.

## Hand-crafted (static)

| Diagram | Source | Description |
|---------|--------|-------------|
| `system-overview` | `system-overview.dot` | High-level TradingAgents architecture |
| `langgraph-workflow` | `langgraph-workflow.dot` | LangGraph agent orchestration flow |
| `persistence` | `persistence.dot` | Database and persistence layer |

These are edited by hand and committed with the repo.

## Auto-generated (from GitNexus)

| Diagram | Command | Description |
|---------|---------|-------------|
| `gn-impact-calculateTradePlan` | `just gn-graph-symbol calculateTradePlan` | Callers and callees of `calculateTradePlan` |
| `gn-impact-DatabaseFactory` | `just gn-graph-symbol DatabaseFactory --depth 2` | 2-level impact of `DatabaseFactory` |
| `gn-impact-calculateATR` | `just gn-graph-symbol calculateATR` | ATR function dependencies |

These are generated from the live codebase graph. Regenerate after significant refactors:

```bash
just gn-diagrams          # generate key project graphs
just regen-diagrams       # full pipeline: clean + generate + render
```

## Linking diagrams in Markdown

Use relative paths from the repo root:

```markdown
![calculateTradePlan impact graph](docs/diagrams/gn-impact-calculateTradePlan.png)
```

Or with a caption:

```markdown
| Impact of `calculateTradePlan` |
|:--:|
| ![Impact graph](docs/diagrams/gn-impact-calculateTradePlan.png) |
| *12 nodes, 11 edges. Shows all callers (tests, routes, CLI) and callees (ATR, swing detection, rounding).* |
```

## Keeping diagrams in sync with code

Diagrams are only useful if they reflect the current codebase. Two workflows ensure this:

### Option 1: Pre-push hook (recommended)

Install once. Every push automatically regenerates and commits diagrams if source files changed:

```bash
just install-hooks
```

This installs `.git/hooks/pre-push` which:
1. Detects if source files (not docs/diagrams) changed
2. Runs `just regen-diagrams`
3. Auto-commits updated diagrams with a standard message
4. Lets the push proceed

### Option 2: Explicit `just push`

Run instead of `git push`:

```bash
just push
```

This runs `just regen-diagrams`, commits any diagram changes, then pushes.

### Manual regeneration

For ad-hoc updates (e.g., after a big refactor, before writing documentation):

```bash
just regen-diagrams
```

This runs:
1. `rm docs/diagrams/*.svg`
2. `just gn-diagrams` — generate gitnexus graphs
3. `bun scripts/render_diagrams.ts` — render all `.dot` to `.svg`
