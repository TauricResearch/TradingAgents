# Just Playbook

**Just as a facade pattern for silos.** Keep logic in scripts, just as interface.

---

## Critical Settings

**Always include these:**

```just
set shell := ["bash", "-o", "pipefail", "-c"]
set positional-arguments := true
```

| Setting | Purpose |
|---------|---------|
| `pipefail` | Pipeline fails on first error, not last |
| `positional-arguments` | Access `$0`, `$1`, `$2` in recipes |
| `export` | Export recipe variables as env vars |

---

## Shebang vs Inline Recipes

**Shebang recipes** (preferred for complex logic):
```just
process:
    #!/usr/bin/env bash
    set -euo pipefail
    ./scripts/process.sh
```
- Single shell instance
- `set -euo pipefail` persists
- `cd` changes directory for all lines

**Inline recipes** (simple one-liners):
```just
clean:
    rm -rf data.jsonl output/
```
- New shell per line
- `cd` only affects that line
- No `set` persistence

**Your scripts should also use `set -euo pipefail`:**
```bash
#!/usr/bin/env bash
set -euo pipefail
```

---

## Dotenv

Load environment variables from `.env` file:

```just
set dotenv-load := true
```

```env
# .env
DATABASE_URL=postgres://localhost/db
API_KEY=secret123
```

---

## Aliases

Shorter command shortcuts:

```just
alias b := build
alias t := test
alias s := status
```

```bash
just b      # same as just build
```

---

## Groups

Organize recipes in `just --list`:

```just
[group("docs")]
docs-readme:
    glow README.md

[group("docs")]
docs-manual:
    glow Silo-Manual.md

[group("ops")]
silo-harvest:
    @cd templates/basic && just harvest
```

```bash
$ just --groups
Recipe groups:
    docs
    ops

$ just --list
Available recipes:
    [docs]
    docs-manual
    docs-readme

    [ops]
    silo-harvest

$ just --group docs --list   # filter by group
Available recipes:
    [docs]
    docs-manual
    docs-readme
```

**Rules:**
- Syntax is `[group("name")]` — parentheses, **not** colon
- Attribute must be **immediately** above the recipe — no comments or blank lines between
- Comments go inline: `[group("docs")]\nhello:  # say hi`

---

## Private Recipes

Prefix with `_` to hide from `just --list`:

```just
_common:
    #!/usr/bin/env bash
    echo "shared logic"

public-task: _common
    @./scripts/public.sh
```

```bash
$ just --list
Available recipes:
    public-task
    # _common is hidden
```

---

## Recipe Groups

Organize recipes into groups for `just --list`:

```just
[group("silo")]
# Verify prerequisites
silo-verify:
    cd templates/basic && just verify

[group("silo")]
silo-harvest:
    cd templates/basic && just harvest

[group("td")]
td-status:
    td status
```

**Note:** Group syntax uses parentheses: `[group("name")]` — not `[group: "name"]`.

## Recipe Comments

Comments show in `just --list` when:

1. **Immediately before recipe** (no blank line):
```just
# Build the project
build:
    echo building
```

2. **Inline with recipe name**:
```just
build: # Build the project
    echo building
```

**Does NOT work:**
- Comment with blank line between it and recipe
- Section headers (comments on their own lines)

## Common Commands

```bash
just --list                  # List all recipes
just --summary               # One-line summary
just --show <recipe>         # Show recipe code
just --usage <recipe>        # Show usage info
just --list --groups         # Show groups

# Running
just build                   # Single recipe
just build prod              # With arguments
just test serve lint         # Multiple recipes
```

---

## Parameters

```just
# Required parameter
deploy target:
    @./scripts/deploy.sh {{target}}

# Optional parameter (default)
greet name "World":
    echo "Hello, {{name}}!"

# Variadic (accepts multiple)
watch patterns...:
    watchexec -e {{patterns}} -- just build

# Aliases in parameters
deploy target (T="prod"):
    echo "Deploying to $T"
```

---

## Patterns We Use

### Facade Pattern (recommended)
```just
# Justfile: thin interface
about:
    @./scripts/about.sh

# scripts/about.sh: implementation
#!/usr/bin/env bash
set -euo pipefail
glow -p README.md 2>/dev/null || cat README.md
```

### Delegation Pattern (template silos)
```just
silo-verify:
    @cd templates/basic && just verify

silo-harvest:
    @cd templates/basic && just harvest
```

### Help Navigation Pattern
```just
help topic:
    @./scripts/help.sh {{topic}}
```

---

## Anti-Patterns

**Logic in justfile instead of scripts:**
```just
# BAD
build:
    for f in src/*.ts; do
        bun build $f
    done

# GOOD
build:
    @./scripts/build.sh
```

**Missing error handling:**
```just
# BAD - fails silently
build:
    ./scripts/build.sh

# GOOD
build:
    #!/usr/bin/env bash
    set -euo pipefail
    ./scripts/build.sh
```

**Overriding built-ins unnecessarily:**
```just
# Avoid unless there's good reason
help:
    @echo "custom help"
```

---

## Dependencies

Dependencies run once (deduplication):

```just
setup:
    npm install

test: setup
    bun test

build: setup
    bun build
```

Running `just test build` runs `setup` once.

---

## TUI Tools (Charm.sh)

### Glow — Markdown Renderer

```bash
glow README.md           # Paginated view
glow -p README.md        # Inline (no pager)
glow -s docs/           # Browse directory
```

```just
about:
    @command -v glow >/dev/null 2>&1 && glow -p README.md || cat README.md
```

### Gum — Interactive Components

```bash
gum confirm "Proceed?"              # Yes/No prompt
gum choose "dev" "prod"            # Selection
gum input "Enter name:"             # Text input
gum pager < file.md                # Paginated view
gum spin -- "loading..."          # Loading spinner
```

```just
confirm:
    @#!/usr/bin/env bash
    gum confirm "Proceed with deployment?" && ./scripts/deploy.sh

select:
    @#!/usr/bin/env bash
    CHOICE=$(gum choose "dev" "staging" "prod")
    echo "Deploying to $CHOICE..."
```

### Skate — Secret Manager

```bash
skate set API_KEY "secret"          # Store
skate get API_KEY                   # Retrieve
skate list                          # List all keys
skate delete API_KEY               # Remove
```

---

## Environment Variables

```just
set export

DATABASE_URL := "postgres://localhost/db"
API_KEY := env("API_KEY", "dev-key")

deploy:
    @echo "Deploying with DB: $DATABASE_URL"
    ./deploy.sh $DATABASE_URL
```

### Secrets with Skate

Use [skate](https://github.com/charmbracelet/skate) for secret management:

```bash
# Store a secret
skate set API_KEY "secret-value"

# Get a secret (for scripts)
API_KEY=$(skate get API_KEY)

# Use in justfile
deploy:
    @#!/usr/bin/env bash
    set -euo pipefail
    API_KEY=$(skate get API_KEY) ./deploy.sh
```

**Note:** Never commit secrets. Use `skate` or environment variables, not hardcoded values.

---

## Quick Reference

| Pattern | Syntax |
|---------|--------|
| Quiet (no echo) | `@echo foo` |
| Shebang recipe | `#!` at start of body |
| Dependency | `build: setup` |
| Group | `[group("name")]` directly above recipe |
| Private | `_recipe:` |
| Alias | `alias x := recipe` |
| Env var | `env("VAR", "default")` |
| Working dir | `invocation_directory()` |
