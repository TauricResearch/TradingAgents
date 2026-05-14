# Conventions Playbook

## What This Is

A living record of the project's **active conventions** — the rules we follow
because they solve real problems — and a process for identifying and removing
**barnacles**: conventions that have lost their purpose but live on in docs,
scripts, and agent context, misleading everyone who follows them.

## What Is a Barnacle?

A barnacle is a document fragment, script comment, or supposed "convention"
that:
1. **Misdirects** — tells an agent to do the wrong thing
2. **Perpetuates bad practice** — the more it is followed, the worse things get
3. **Has no living justification** — nobody can explain why it exists

Barnacles are an **emergent property** of any silo. Documents drift. Tools
change. What once made sense becomes noise, then harm. They accumulate silently
until an agent spends an hour debugging a problem caused by following a
barnacle.

## The Justfile Barnacle (Case Study)

**What it was:** A "convention" that the file must be named `Justfile`
(capitalized).

**Why it formed:** Someone capitalized it once. It looked official. It stuck.

**Why it became a barnacle:** The tool `just` writes to `justfile` (lowercase)
when you run `just --unstable --fmt`. Every formatter run created a second file
on macOS (case-insensitive filesystem, same inode). Agents kept manually
renaming it back. The "convention" created recurring friction with no benefit.

**The scrape:** We deleted `Justfile`, kept `justfile`, updated all docs, and
added this playbook entry so the next agent does not recreate it.

**Lesson:** If a convention fights the tool default, suspect it. If you cannot
justify it in one sentence, delete it.

## Active Conventions

| Convention | Justification | Since |
|------------|---------------|-------|
| `justfile` lowercase | Tool default; formatter compatibility | 2026-05-07 |
| `.tsx` for JSX files | Biome parser requirement (JSX in `.ts` fails) | 2026-04-28 |
| `bun` over `node` where both work | Project standard; faster; native TS | 2026-04-20 |
| `Bun.spawn` over `execSync` | Streaming stdin support; no shell quoting bugs | 2026-05-07 |
| Unicode literals over `\uXXXX` in JSX | Hono emits raw HTML; JS escapes only work in `{}` | 2026-05-07 |
| No `new Database()` outside `db.ts` | Factory enforces WAL + pragmas consistently | 2026-05-06 |
| Every deliberate folder has a `README.md` | Prevents mystery; draws boundaries between adjacent dirs | 2026-05-07 |
| **Directory hierarchy** | | |
| `src/` = production TS (strict) | `tsc --noEmit` enforced; tested code only | 2026-05-07 |
| `src/lib/` = shared modules | Imported by `src/server/` and `src/cli/` | 2026-05-07 |
| `src/server/lib/` = server-only | NOT imported outside `src/server/` | 2026-05-07 |
| PRs ≤ 30 files per concern | Reviewable, bisectable, merges fast; stack branches for dependencies | 2026-05-08 |
| Pre-PR self-review checklist | 3-gate checklist (mechanical, semantic, docs) before opening PR; catches ~1 real bug per 3 bot flags | 2026-05-08 |
| td ↔ current.md sync at startup | `td list` must match `debriefs/plans/current.md`; stale planning docs are process barnacles | 2026-05-08 |
| `scripts/` = support TS (loose) | Tooling, automation, not shipped | 2026-05-07 |
| `scripts/lab/` = experiments | Loosest types; disposable | 2026-05-07 |
| `scripts/lib/` = shared helpers | Reusable across scripts; pass `just check` | 2026-05-07 |
| Refactor before patching complex state | A "surgical fix" to a tangled state machine usually makes it worse; linearise the logic first | 2026-05-13 |
| Test against real code, not mental models | Verify the actual extraction/import path before writing assertions; a false failure costs an hour | 2026-05-13 |
| `pos` + array slicing is a footgun | Tracking indices against a shrinking array causes off-by-one errors; prefer direct array indexing where possible | 2026-05-13 |

## Barnacle Removal Record

| Date | Barnacle | Where Found | Why Removed | Removed By |
|------|----------|-------------|-------------|------------|
| 2026-05-07 | `Justfile` (capitalized) | `playbooks/just-playbook.md`, `ci-cd-playbook.md` | Fought `just` formatter; created duplicate file on macOS | claude |
| 2026-05-13 | `agent-orient.ts` crash on `prs.map is not a function` | `scripts/agent-orient.ts:190` | GitHub API/CLI returned unexpected format; script crashes on all sessions | ses_208dea |

## Process Barnacles

Barnacles aren't just in documents. The development process itself accumulates
drift: tasks marked `in_review` on a merged PR, planning docs that don't match
the td database, handoff files referencing work that's been done for days.

**Process barnacles are more dangerous than doc barnacles** because they
mislead agents about what work actually remains. An agent that reads
`current.md` listing 5 "open" tasks and skips a td sync will spend an hour
investigating work that's already shipped.

| Process Barnacle | Symptom | Fix |
|------------------|---------|-----|
| Stale planning docs | `current.md` says "5 open" but `td list` shows them closed | Update `current.md` immediately; add sync to startup ritual |
| Orphaned in_review tasks | Tasks in `in_review` with merged PRs | `td approve` or `td close` the tasks; log the cleanup |
| Handoff doc drift | `handoff-next-session.md` references a branch that's been deleted | Delete or rewrite the handoff; it's worse than no handoff |
| Zombie branches | Local branches for merged/deleted PRs | `git branch -d`; they confuse `git branch --show-current` |

Treat these the same as doc barnacles: scrape on sight. The barnacle removal
record below tracks them.

## Barnacle Inspection Prompt

**Run this at the start of every session.** If you find a barnacle, either
remove it or add it to the record above with a note explaining why it persists.

```
## Barnacle Inspection

### Document barnacles
Scan the project's documents (playbooks, docs, READMEs, AGENTS.md) and
scripts for fragments that:

1. Direct the reader to do something that contradicts an active convention
2. Reference a tool, path, or process that no longer exists
3. Insist on a naming or formatting rule that conflicts with the tool default
4. Describe a workflow that has been superseded by automation
5. Contain copy-paste from another project (wrong names, wrong paths)

For each candidate found, judge:
- Does it have a one-sentence justification?
- Does following it create friction?
- Is it referenced anywhere other than the document itself?

Also inspect the directory tree:
- Any folder with more than one file and no `README.md`? Suspicious.
- Adjacent folders with similar names but no boundary drawn? Likely barnacles.

If it fails two of three: it is a barnacle. Scrape it. Update the record.
If it passes: add it to the Active Conventions table with its justification.

### Process barnacles
After the doc scan, run these checks:

1. `td list` → compare against `debriefs/plans/current.md`. Mismatches? Fix current.md.
2. `td list` → any tasks in `in_review` with merged PRs? Approve/close them.
3. `debriefs/handoff-next-session.md` → still references a live branch? Still accurate?
4. `git branch` → any local branches for deleted/merged PRs? Delete them.
```

## Startup Ritual

When you begin work on this silo, run:

```bash
# 1. Check silo status
just status

# 2. Read the barnacle record (this file, last section)
cat playbooks/conventions-playbook.md | sed -n '/Barnacle Removal Record/,/Barnacle Inspection Prompt/p'

# 3. Note any new barnacles in the session log
```

If you scraped a barnacle, commit with message:
```
fix(conventions): scrape <name> barnacle

<one sentence why it was misleading>
```

## Agent Note

You are not maintaining conventions for their own sake. You are preventing
the accumulation of misdirection. Every barnacle you scrape saves the next
agent an hour. Every barnacle you leave costs the next agent an hour.

The learning loop is only virtuous if it does not foul the silo.

---

## Environment Variables

Canonical source is `scripts/just-check.ts`. Keep this table in sync with it.

| Variable | Default | Purpose |
|----------|---------|---------|
| `TA_DASHBOARD_PORT` | `3000` | Dashboard HTTP port |
| `PORTFOLIO_DB` | `./portfolio.db` | SQLite database path (dev) |
| `TEST_MODE` | `0` | Set to `1` to use `test_portfolio.db` |
| `TEST_PORTFOLIO_DB` | `./test_portfolio.db` | Test SQLite DB (active when `TEST_MODE=1`) |
| `TRADINGAGENTS_MEMORY_LOG_PATH` | `~/.tradingagents/memory/trading_memory.md` | Decision memory log |
| `TRADINGAGENTS_CACHE_DIR` | `~/.tradingagents/cache` | Checkpoint cache base |
| `HLEDGER_FILE` | `~/.hledger.journal` | hLedger journal path (DEV) |
| `TEST_HLEDGER_FILE` | `~/.tradingagents/test_hledger.journal` | hLedger journal path (TEST) |

## Known Failure Modes

### Static JS copies of TypeScript
The canonical client-side runtime lives in `src/server/static/scripts/*.js` — the single source of truth. Views reference them via `<script src="/static/scripts/xxx.js" />`. Biome linting for this directory is disabled. Do not maintain a second inline copy in views.

### Biome config changes must be validated immediately
If you add a key that doesn't exist (`files.ignore` is not valid at v2.4.14), biome fails with a parse error before running any checks. Run `just lint` immediately after any `biome.json` change.

### Template literals inside template literals break silently
Backtick-quoted strings inside template literals are a syntax error. The JSX compiler won't catch it. Fix: use `String.fromCharCode(34)` for embedded quotes.

### Revert is faster than forward-fix
If a change breaks checks and the fix isn't obvious, revert to the last known-good commit. Three failed forward-attempts burned 45 minutes. One revert took 5. Trust the revert.

### Route file with JSX retaining `.ts` extension
Biome produces cryptic parse errors: "expected `>` but instead found `data"`. The parser treats JSX as TypeScript class syntax. Fix: rename to `.tsx` and update all imports in `src/server/index.tsx`.

### Forward-porting vs merging
When a PR was written against old architecture, evaluate conflict count × semantic distance. String-concat vs JSX is a chasm. If >15 conflict regions: abort merge, cherry-pick ideas, rewrite.

### Script path unification
When a script moves (e.g. `scripts/` → `scripts/py/`), update ALL references in a single commit. Piecemeal updates create "file not found" errors that surface only in production.

### No test coverage for views
`pytest -m smoke` only covers Python. TypeScript views have no automated test. Until route-level tests exist, the only guard is: `tsc` + `just lint` + manual browser verification.
