# Brief: Blog Registry + Multi-Agent Worktree Test

**Date**: 2026-05-11
**Status**: Open — blog registry implemented, multi-agent test in progress
**Epic**: UNIFIED-CLI-001

## Part 1: Problem (Blog Registry)

`docs/blog/` was created to hold draft blog posts. It has its own `docs/blog/INDEX.jsonl` (created manually) but it is not a first-class registry — `scripts/reg-sync.ts` doesn't know about it. It was detected as a subdirectory of `docs/` and lumped into `docs/INDEX.jsonl`, which is wrong.

The blog needs:
- Its own entry in the `REGISTRIES` map in `scripts/reg-sync.ts`
- Its own `docs/blog/INDEX.jsonl` (separate from `docs/INDEX.jsonl`)
- A schema that reflects blog-specific metadata: `author`, `tags`, `status` (`draft` | `published` | `archived`)

## Part 2: Infrastructure — Worktree Model (Multi-Agent Test)

After reviewing `playbooks/td-playbook.md`, `debriefs/debrief-td-worktree-infrastructure-2026-05-11.md`, and `briefs/2026-05-11-td-worktree-test-results.md`, the correct approach for multi-agent testing is:

- Each epic gets its own worktree via `just wt-create <name>`
- Each worktree has a `.td-root` file pointing to the repo root
- All worktrees share the same `.todos/` database (`.td-root` resolution)
- Cross-write confirmed: task created in worktree appears immediately in main

The infrastructure is already built (`scripts/worktree-init.ts`, `scripts/agent-*.ts`, `Justfile` worktree group).

See `playbooks/td-playbook.md` for the full coordination protocol (claim-before-touch, session startup, handoff).

## Proposed Changes

### 1. `scripts/reg-sync.ts` — Add blog to REGISTRIES

Add a `blog` entry with `exclude: [/blog\//]` in the `docs/` registry to prevent double-indexing:

```typescript
docs: {
  indexPath: "docs/INDEX.jsonl",
  dirPath: "docs",
  filePattern: /\.md$/,
  exclude: [/INDEX\.jsonl/, /blog\//],
},
blog: {
  indexPath: "docs/blog/INDEX.jsonl",
  dirPath: "docs/blog",
  filePattern: /\.md$/,
  exclude: [/INDEX\.jsonl/],
},
```

### 2. `just wt-create blog-registry --base main`

Create a worktree for the multi-agent test:
```bash
just wt-create blog-registry --base main
cd ../TradingAgents-blog-registry
td usage --new-session
```

### 3. Multi-Agent Coordination Test

Verify the shared `.todos/` database works across two sessions:
- Agent A (main): implements blog registry → done
- Agent B (worktree): verify collision detection, claim protocol, cross-write
- Manual confirmation: task created in worktree appears in main

## Blog Entry Schema

```json
{
  "file": "YYYY-MM-DD-slug.md",
  "date": "YYYY-MM-DD",
  "status": "draft | published | archived",
  "summary": "Post summary",
  "meta": {
    "type": "blog-post",
    "topic": "...",
    "tags": ["...", "..."],
    "author": "petersmith"
  }
}
```

## Verification

- `bun scripts/reg-sync.ts blog` returns ✓ up to date
- `docs/blog/INDEX.jsonl` is separate from `docs/INDEX.jsonl`
- `docs/blog/` entries do NOT appear in `docs/INDEX.jsonl`
- `just wt-create blog-registry --base main` creates worktree with `.td-root`
- `td whoami` in worktree shows different session, same database
- Cross-write: task created in worktree appears in main (and vice versa)