---
date: 2026-05-07
tags: [playbook, ci-cd, git, hooks, automation, diagrams]
---

# CI/CD Playbook: Automate Where Possible

## Principle

> **Never let a human remember what a hook can enforce.**

If a process step is required for correctness (diagrams in sync, checks passing), it must be automated. Humans forget. Scripts don't.

---

## The Diagram Synchronisation Problem

**The bug that motivates this playbook:**

You refactor `calculateTradePlan`, changing its call graph. The documentation still shows the old graph. A new developer reads the docs, sees `estimateATR` as a callee, but the code now calls `calculateATR` directly. Confusion. Mistrust. Docs rot.

**Root cause:** Generated diagrams are only correct at the moment of generation. One commit later, they're stale.

**Solution:** Regenerate diagrams automatically on every push where source files changed.

---

## Workflow Overview

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Edit      │ → │   Commit    │ → │   Push      │ → │  Hook fires  │
│   code      │    │   (human)   │    │  (human)    │    │  (automated) │
└─────────────┘    └─────────────┘    └─────────────┘    └──────┬──────┘
                                                               │
                                                               ▼
                                                    ┌─────────────────────┐
                                                    │ 1. Detect source    │
                                                    │    changes in       │
                                                    │    pushed commits   │
                                                    └──────────┬──────────┘
                                                               │
                                                               ▼
                                                    ┌─────────────────────┐
                                                    │ 2. Run regen-diagrams │
                                                    │    (gitnexus + dot)   │
                                                    └──────────┬──────────┘
                                                               │
                                                               ▼
                                                    ┌─────────────────────┐
                                                    │ 3. Commit diagrams  │
                                                    │    if changed       │
                                                    └──────────┬──────────┘
                                                               │
                                                               ▼
                                                    ┌─────────────────────┐
                                                    │ 4. Push proceeds    │
                                                    │    with diagrams    │
                                                    │    in sync          │
                                                    └─────────────────────┘
```

---

## Setup (One Time)

### Option 1: Pre-push Hook (Recommended)

Install the hook. From repo root:

```bash
just install-hooks
```

Or manually:

```bash
bash scripts/install-pre-push-hook.sh
```

**What it does:**
- Installs `.git/hooks/pre-push`
- On every `git push`, checks if pushed commits modify source files
- If yes: runs `just regen-diagrams`, commits updated diagrams, then pushes
- If no: skips silently, push proceeds immediately

**What gets checked:**
- Any `.ts`, `.tsx`, `.py`, `.sql` file changed in pushed commits
- Excludes: `docs/`, `*.svg`, `*.png`, `*.dot`, `*.md`

**Commit message:**
```
chore(diagrams): auto-regenerate from pre-push hook
```

### Option 2: Explicit `just push`

If you prefer not to use git hooks (e.g., you sometimes push without network, or hooks interfere with other tools):

```bash
just push
```

**What it does:**
- Runs `just regen-diagrams`
- Commits any diagram changes
- Runs `git push`

**Use this when:**
- You want full control over when diagrams regenerate
- Pre-push hooks conflict with your git client or IDE
- You're pushing from a CI environment without hook support

---

## How It Works

### The Hook Logic

The pre-push hook reads the refs being pushed from stdin:

```
<local_ref> <local_sha> <remote_ref> <remote_sha>
```

For each ref, it computes `git diff --name-only <remote_sha>..<local_sha>` and filters for source files. If any match, it triggers regeneration.

**Why not `git diff --name-only HEAD`?**

After you commit, the working tree matches HEAD. The hook must check the *commits being pushed*, not the working tree.

### The Regeneration Pipeline

```bash
just regen-diagrams
```

Runs three steps:

1. **Clean:** `rm docs/diagrams/*.svg` — removes stale SVGs
2. **Generate GitNexus graphs:**
   ```bash
   bun scripts/gitnexus-batch.ts --render
   ```
   Reads `.tradingagents/gitnexus-diagrams.json` and generates all configured
   impact graphs (symbols) and file graphs. Writes: `docs/diagrams/gn-impact-*.dot`,
   `gn-file-*.dot`, `.svg`, `.png`
3. **Render static diagrams:**
   ```bash
   bun scripts/render_diagrams.ts
   ```
   Converts all `.dot` and `.mmd` files in `docs/diagrams/` to `.svg`

### Adding a New GitNexus Diagram

Edit `.tradingagents/gitnexus-diagrams.json`:

```json
{
  "symbols": [
    {"name": "calculateTradePlan", "depth": 1},
    {"name": "DatabaseFactory", "depth": 2},
    {"name": "calculateATR", "depth": 1},
    {"name": "NewSymbol", "depth": 1}
  ],
  "files": [
    "src/server/index.tsx",
    "src/cli/trading/main.ts"
  ]
}
```

Then run `just regen-diagrams`. No justfile changes needed.

### Committing

If any generated files changed:

```bash
git add docs/diagrams/gn-*.dot docs/diagrams/gn-*.svg docs/diagrams/gn-*.png
git add docs/diagrams/*.svg
git commit -m "chore(diagrams): auto-regenerate from pre-push hook" --no-verify
```

The `--no-verify` prevents infinite loops (the hook won't re-fire on its own commit).

---

## Directory Layout

```
docs/diagrams/
├── README.md                          # How to link, how to regen
├── langgraph-workflow.dot             # Hand-crafted source
├── langgraph-workflow.svg             # Generated from .dot
├── persistence.dot                    # Hand-crafted source
├── persistence.svg                    # Generated from .dot
├── system-overview.dot                # Hand-crafted source
├── system-overview.svg                # Generated from .dot
├── gn-impact-calculateTradePlan.dot   # Auto-generated from gitnexus
├── gn-impact-calculateTradePlan.svg   # Rendered from .dot
├── gn-impact-calculateTradePlan.png   # Raster fallback
├── gn-impact-DatabaseFactory.dot      # Auto-generated from gitnexus
├── gn-impact-DatabaseFactory.svg
├── gn-impact-DatabaseFactory.png
├── gn-impact-calculateATR.dot         # Auto-generated from gitnexus
├── gn-impact-calculateATR.svg
└── gn-impact-calculateATR.png
```

**Naming convention:**
- Hand-crafted: `<topic>.dot` — edited by humans
- GitNexus impact: `gn-impact-<symbol>.dot` — auto-generated
- GitNexus file: `gn-file-<path>.dot` — auto-generated (slashes → underscores)

---

## Linking Diagrams in Documentation

Once diagrams are committed, link them from any Markdown file:

### Inline image

```markdown
![calculateTradePlan impact graph](docs/diagrams/gn-impact-calculateTradePlan.png)
```

### Table with caption

```markdown
| Impact of `calculateTradePlan` |
|:--:|
| ![Impact graph](docs/diagrams/gn-impact-calculateTradePlan.png) |
| *12 nodes, 11 edges. Callers: tests, routes, CLI. Callees: ATR, swing detection, rounding.* |
```

### In playbooks or READMEs

```markdown
See the [impact graph](docs/diagrams/gn-impact-calculateTradePlan.png) for the full call tree.
```

---

## Adding New Diagrams to Auto-Regeneration

Edit the `gn-diagrams` recipe in `justfile`:

```makefile
[group("gn")]
gn-diagrams:
    @echo "Generating GitNexus impact graphs..."
    bun scripts/gitnexus-to-dot.ts --symbol calculateTradePlan --depth 1 --render
    bun scripts/gitnexus-to-dot.ts --symbol DatabaseFactory --depth 2 --render
    bun scripts/gitnexus-to-dot.ts --symbol calculateATR --depth 1 --render
    bun scripts/gitnexus-to-dot.ts --symbol NEW_SYMBOL --depth 1 --render
    @echo ""
    @echo "Generated:"
    @ls -1 docs/diagrams/gn-impact-*.dot 2>/dev/null || echo "  (no files yet)"
```

**When to add a new symbol:**
- It's a hotspot (many callers or callees)
- It's referenced in documentation
- It changes frequently and its graph is worth tracking

---

## Troubleshooting

### Hook doesn't fire

```bash
ls -la .git/hooks/pre-push
# Should show executable permissions (-rwxr-xr-x)

# If missing, reinstall:
just install-hooks
```

### Hook fires but diagrams don't change

This is normal. If the call graph hasn't changed (e.g., you only modified comments), the generated DOT will be identical. The hook skips the commit in this case.

### "just not found" in hook

The hook runs in a non-interactive shell that may not have `just` in PATH. Two fixes:

1. Install `just` in a standard location (e.g., `/opt/homebrew/bin/just`)
2. Or edit the hook to use the full path:
   ```bash
   /opt/homebrew/bin/just regen-diagrams
   ```

### Duplicate diagram commits

If you push multiple times without pulling, the hook may generate the same diagrams each time. This is harmless — the commit will be empty and git will skip it.

### I want to skip the hook for one push

```bash
git push --no-verify
```

**Warning:** This skips ALL pre-push hooks, not just diagram regen. Use sparingly.

### Diagrams look wrong after refactor

1. Check the graph is actually stale: `cat docs/diagrams/gn-impact-<symbol>.dot`
2. Force regeneration: `just regen-diagrams`
3. If still wrong, the GitNexus index may be stale: `just gn-analyze`, then `just regen-diagrams`

---

## Philosophy: Automate Where Possible

| Task | Manual | Automated | Why |
|------|--------|-----------|-----|
| Run checks before commit | `just check` | Pre-commit hook | Prevents broken commits |
| Regenerate diagrams after code change | `just regen-diagrams` | Pre-push hook | Docs stay in sync |
| Update AGENTS.md cross-references | Hand-edit | ??? | Not yet automated — requires semantic understanding |
| Type-check views | `tsc` | `just check` | Part of check pipeline |
| Lint code | `biome check` | `just check` | Part of check pipeline |

**Rule:** If a step is required for correctness and it's boring, automate it. If it's required for quality and humans forget, automate it. Only manual steps should be those requiring judgment.

---

## References

- `docs/diagrams/README.md` — How to link and regenerate diagrams
- `scripts/install-pre-push-hook.sh` — Hook installer
- `scripts/gitnexus-to-dot.ts` — GitNexus → Graphviz exporter
- `scripts/render_diagrams.ts` — `.dot`/`.mmd` → `.svg` renderer
- `playbooks/gitnexus-usage-guide.md` — Using GitNexus for code analysis
