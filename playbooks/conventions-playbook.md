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
| `scripts/` = support TS (loose) | Tooling, automation, not shipped | 2026-05-07 |
| `scripts/lab/` = experiments | Loosest types; disposable | 2026-05-07 |
| `scripts/lib/` = shared helpers | Reusable across scripts; pass `just check` | 2026-05-06 |

## Barnacle Removal Record

| Date | Barnacle | Where Found | Why Removed | Removed By |
|------|----------|-------------|-------------|------------|
| 2026-05-07 | `Justfile` (capitalized) | `playbooks/just-playbook.md`, `ci-cd-playbook.md` | Fought `just` formatter; created duplicate file on macOS | claude |
| 2026-05-07 | Empty `src/` directory | Project root | Claimed to be source root but contained nothing; misled every new agent | claude |

## Barnacle Inspection Prompt

**Run this at the start of every session.** If you find a barnacle, either
remove it or add it to the record above with a note explaining why it persists.

```
## Barnacle Inspection

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
