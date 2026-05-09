# Just Playbook

## Core Principle

**The justfile is a facade, not a workbench.**

It enumerates what's available and delegates to scripts. It has zero logic of its own. Every non-trivial implementation lives in a script — testable, debuggable, versioned independently.

---

## Critical Settings

```just
set shell := ["bash", "-o", "pipefail", "-c"]
set dotenv-load := true
set positional-arguments := true

default:
    @just --list
```

| Setting | Why |
|---------|-----|
| `pipefail` | Pipeline fails on first error, not last |
| `dotenv-load` | Load `.env` for local overrides |
| `positional-arguments` | Access `$1`, `$2` in recipes |
| `default` recipe | `just` shows the menu, does nothing |

---

## The Decision Heuristic

Before adding a recipe, ask:

| Signal | Action |
|--------|--------|
| Recipe needs logic or text | Script |
| Recipe emits information | Markdown file + renderer (glow, bat) |
| Recipe runs multiple commands | Script |
| Recipe needs env vars or complex quoting | Script |
| Recipe is a one-liner with no deps | Just is fine |
| Recipe is getting clever | Move it to a script |

---

## Recipes That Should Never Be In The justfile

- Multi-line echo blocks with formatted text → Markdown file + renderer
- Complex env var assembly in shell → Python/JS script reads it internally
- Inline loops, conditionals, or state → Script
- Anything that breaks the parser (em dashes, `$$` gotchas) → Script

---

## Facade Pattern (correct usage)

```just
# justfile — thin interface, no logic
help:
    @glow docs/help.md 2>/dev/null || cat docs/help.md

info:
    @python scripts/gen-info-md.py | glow - 2>/dev/null || cat -
```

```python
# scripts/gen-info-md.py — implementation, fully testable
#!/usr/bin/env python3
"""Generate project state report from subprocess calls."""
import subprocess

branch = subprocess.run(
    ["git", "branch", "--show-current"], capture_output=True, text=True
).stdout.strip()
print(f"# Branch: {branch}")
```

---

## Shebang vs Inline

**Shebang** — use for any logic, or when `cd` must persist across lines:
```just
build:
    #!/usr/bin/env bash
    set -euo pipefail
    cd src && ./build.sh
```

**Inline** — one-liners only:
```just
clean:
    rm -rf dist/
```

---

## Groups

Syntax: `[group("name")]` immediately above the recipe (no blank lines).

```just
[group("bun")]
lint:
    bunx biome check .

[group("meta")]
help:
    @glow docs/help.md 2>/dev/null || cat docs/help.md
```

---

## Parameters

```just
# Optional with default
analyze TICKER="SPY":
    ./scripts/analyze.sh {{TICKER}}

# Variadic
watch patterns...:
    watchexec -e {{patterns}} -- just build
```

---

## Aliases

```just
alias a := analyze
alias l := lint
alias h := help
```

---

## Common Commands

```bash
just                    # Show menu (default recipe)
just --list             # List all recipes
just --list --groups    # List by group
just --show <recipe>    # Show recipe source
just --summary          # One-line per recipe
```

---

## TUI Tools

**Glow** — render Markdown (use as fallback to cat):
```just
help:
    @glow docs/help.md 2>/dev/null || cat docs/help.md
```

**Bat** — syntax-highlighted file viewer:
```just
logs:
    @bat logs/app.log
```

---

## Anti-Patterns

```just
# BAD — logic in justfile
lint:
    @echo "Running..."
    bunx biome check . | head -20

# BAD — embedded text (em dash breaks parser)
help:
    @echo "tradingagents — Python CLI — analyze"

# GOOD — thin delegation
lint:
    bunx biome check .

help:
    @glow docs/help.md 2>/dev/null || cat docs/help.md
```

---

## Quick Reference

| Need | Syntax |
|------|--------|
| Quiet (no command echo) | `@command` |
| Shebang recipe | `#!` at body start |
| Dependency | `build: setup` |
| Group | `[group("name")]` above recipe |
| Alias | `alias x := recipe` |
| Default param | `param="default"` |
| Env var | `env("VAR", "default")` |
| Private (hidden) | `_recipe:` |
| Working dir | `invocation_directory()` |
---

## Convention Hygiene

**Rule:** The justfile is named `justfile` (lowercase). No exceptions.

**Why:** `just` accepts both `justfile` and `Justfile`, but the built-in
formatter (`just --unstable --fmt`) writes to `justfile`. Fighting the tool
creates friction. We previously maintained `Justfile` (capitalized) as a
"convention" — it served no purpose, created duplicate-file bugs on macOS, and
forced manual renaming after every format. It was a barnacle. We scraped it off.

**General principle for conventions:**
1. If it fights the tool default, suspect it.
2. If you cannot justify it in one sentence, delete it.
3. If it causes friction twice, it is already a barnacle.
