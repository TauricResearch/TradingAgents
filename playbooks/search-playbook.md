# Search Playbook — Code Search in TradingAgents

> When searching code, `rg` is primary. `ag` is for specialist tasks only.
> This playbook covers conventions, tool selection, and project-specific nuances.

---

## Tool Selection

| Task | Tool | Reason |
|------|------|--------|
| General content search | `rg` | Faster, JSON output, better type detection |
| IDE integration (Sublime/AckMate) | `ag --ackmate` | AckMate format only `ag` supports |
| Compressed archive search | `ag --search-zip` | `rg` cannot search inside `.gz`/`.bz2`/`.zip` |
| Custom project ignore list | `ag -p .ignore` | `rg` has no equivalent |
| Filename search | `rg -g "*.tsx"` | Both work; `rg` is consistent |

---

## Ripgrep (`rg`) — Primary Tool

`rg` is faster, has better output formats, and integrates with the broader toolchain (VSCode, Neovim, `$EDITOR`). It respects `.gitignore` by default.

### Common patterns

```bash
# Basic search (case-sensitive if pattern has uppercase, smart-case otherwise)
rg "TradingAgentsGraph"

# Case-insensitive
rg -i "databasefactory"

# Files with matches only
rg -l "DatabaseFactory"

# Files WITHOUT matches (inverted)
rg -L "TODO" src/

# With context (before + after)
rg -C 3 "DatabaseFactory"

# Only matching lines (no surrounding context)
rg -o "DatabaseFactory"

# Type-specific (TypeScript)
rg --ts-embedded "tsx"

# Filename search
rg -g "*.tsx" -l "PortfolioSummary"
rg -g "!**/node_modules" -g "!**/__pycache__" "pattern"

# JSON output (for scripting)
rg "pattern" --json | jq '.'
```

### Project-specific search paths

Avoid searching `tradingagents/` core — it is the vendored package, not the project codebase.

```bash
# Search dashboard/server code only (TypeScript/Bun)
rg "pattern" src/

# Search CLI commands only
rg "pattern" src/cli/

# Search everything except vendored Python package
rg "pattern" --glob '!tradingagents/' .

# Search routes + views
rg "pattern" src/server/routes/ src/server/views/
```

---

## Silver Searcher (`ag`) — Specialist Tool

`ag` is installed but not the default. Use it only when `rg` cannot do the job.

### When to reach for `ag`

**1. Searching compressed archives**

```bash
ag "pattern" --search-zip backups/
```

Will find `pattern` inside `.gz`, `.bz2`, `.xz`, `.zip` files. Useful for hunting through old log backups without decompressing.

**2. Custom `.ignore` file per project**

If you want a project-specific ignore list separate from `.gitignore`, create `.ignore` in the project root:

```bash
# ag respects .ignore alongside .gitignore
ag "pattern" -p .ignore

# Override: ignore .gitignore, use only .ignore
ag "pattern" --skip-vcs-ignores -p .ignore
```

Add generated/derived files here that you never want to search or see in results.

**3. AckMate format (Sublime Text)**

If you use Sublime Text with the AckMate plugin:

```bash
ag "pattern" --ackmate -C 2
```

Produces output in Sublime's expected format. No `rg` equivalent.

### `ag` gotchas

- **`--noaffect` is not `--noignore`.** `--noaffect` limits line output, not file traversal. Use `-u` to bypass all ignores.
- **Smart-case is different from `rg`.** `ag "databasefactory"` finds matches; `rg "databasefactory"` may not (depends on invocation). Use `-i` when in doubt.
- **No `--json` output.** If you need machine-parseable results, use `rg`.
- **`--depth` default is 25.** Increase with `--depth NUM` for deep directory traversals.

```bash
# ag skips .gitignore files (not .ignore) without -u
ag "pattern" -u              # unrestricted: search all files
ag "pattern" --skip-vcs-ignores  # skip .gitignore only, keep .ignore

# Depth limit
ag "pattern" --depth 50
```

---

## GitNexus — Semantic Search (AI-assisted)

For understanding code relationships, not raw text search:

```bash
# Find all execution flows involving a symbol
gitnexus_query({query: "concept"})

# Get full context: callers, callees, execution flows
gitnexus_context({name: "symbolName"})

# Impact analysis before refactoring
gitnexus_impact({target: "symbolName", direction: "upstream"})
```

**Use GitNexus when:**
- Exploring unfamiliar code
- Assessing blast radius before changing a function signature
- Finding all callers of a function across the codebase
- Understanding which execution flows a symbol participates in

**Do NOT use GitNexus when:**
- You need raw text search (use `rg`)
- You need to search inside compressed files (use `ag --search-zip`)
- You need machine-parseable output (use `rg --json`)

See `playbooks/gitnexus-playbook.md` for full details.

---

## Practical Workflows

### Finding where a function is used

```bash
rg "DatabaseFactory" -C 1
```

### Finding all TypeScript files

```bash
rg -g "*.tsx" -g "*.ts" -l "." | head -20
```

### Searching for TODO/FIXME comments

```bash
rg -i "TODO\|FIXME\|XXX\|HACK" src/
```

### Counting occurrences

```bash
rg "DatabaseFactory" --count | sort -t: -k2 -rn | head -10
```

### Searching a specific commit or diff

```bash
rg "pattern" $(git diff HEAD~3 --name-only)
```

### Hunting through old backups

```bash
ag "TradingAgentsGraph" --search-zip backups/
```

---

## Tool Availability

| Tool | Path | Version |
|------|------|---------|
| `rg` | `$HOME/.amp/bin/rg` | 13.0.0 |
| `ag` | `/opt/homebrew/bin/ag` | 2.2.0 |

If neither is found: `brew install ripgrep` or `brew install the_silver_searcher`.