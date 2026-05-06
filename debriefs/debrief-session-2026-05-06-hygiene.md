# Debrief: Playbook Hygiene + Shared LLM Substrate + DatabaseFactory Enforcement

**Date:** 2026-05-06
**Scope:** Refactor htmx-playbook.md; extract shared OpenRouter LLM client; enforce DatabaseFactory-only SQLite connections via build gate
**Outcome:** Three commits on `feat/price-freshness`. `just check` now covers biome + tsc + db-usage gate. Zero raw `new Database()` outside `server/lib/db.ts`.

---

## What We Did

### 1. htmx-playbook.md Refactor (30 min)

The playbook had accumulated 600+ lines of "war story" narrative — migration tales, historical bans, line counts of removed code, and retrospective prose. It was 4× longer than it needed to be and buried the rules under narrative.

**Approach:** Used `gemini-2.5-flash` via a purpose-built script (`scripts/refactor-playbook.ts`) to strip narrative and restructure as direct imperatives.

**Result:**
- 528 deletions, 130 insertions
- Direct imperatives: "Do X", "Never do Y", "Always Z"
- Forbidden Patterns table with architectural (not historical) rationales
- Added Edge Cases section preserving two critical runtime traps:
  - `var` hoisting in loops (helper undefined when called before assignment)
  - `split('\n')` vs actual newlines (literal backslash-n is two characters)
- Proper YAML frontmatter per `playbooks-playbook.md`

**Verdict:** The LLM refactor was ~90% correct. Lost two edge cases that had to be manually restored. Worth doing but requires human review for technical completeness.

### 2. Shared LLM Substrate: `scripts/lib/llm.ts` (45 min)

Three scripts (`pr-summarize.ts`, `summarize_analyses.ts`, `refactor-playbook.ts`) each had 30-40 lines of identical OpenRouter `fetch()` boilerplate: API URL, key check, headers, payload assembly, error handling, JSON extraction.

**Created:** `scripts/lib/llm.ts`
- Single `llm(messages, opts)` function
- Auto-loads `.env` once at module init (no more per-script manual parsing)
- Sensible defaults: gemini-2.5-flash-lite, temp 0.2, max_tokens 4000
- Optional `title` and `referer` for OpenRouter telemetry headers

**Refactored callers:**
- `pr-summarize.ts`: 40 lines of boilerplate → 10-line wrapper
- `summarize_analyses.ts`: 30 lines of inline fetch → single `llm()` call
- `refactor-playbook.ts`: 40 lines + manual `.env` loader → single `llm()` call

**Net:** ~120 lines of duplicated fetch logic eliminated.

**Gotcha:** `.gitignore` had `lib/` (Python packaging standard) which silently excluded `scripts/lib/`. Already had `!server/lib/` but needed `!scripts/lib/` added.

### 3. DatabaseFactory Enforcement (30 min)

`server/lib/db.ts` already had a singleton `DatabaseFactory` with hardened pragmas (WAL, busy_timeout, foreign_keys, mmap_size=0, synchronous=NORMAL). But two standalone scripts had their own `connectDb()` helpers with raw `new Database(path)`:

| Script | WAL | busy_timeout | foreign_keys | mmap_size | synchronous |
|--------|-----|-------------|------------|-----------|-------------|
| `seed_database.ts` | ✓ | ✓ | ✓ | ✗ | ✗ |
| `sync-prices.ts` | ✓ | ✓ | ✗ | ✗ | ✗ |
| **Factory** | ✓ | ✓ | ✓ | ✓ | ✓ |

**This is the exact failure mode the rule exists to prevent.** Different scripts connecting to the same DB with different pragma sets = undefined SQLite state depending on which script ran last.

**Fix:**
- Removed `let _db`, `getDb()`, `connectDb()` from both scripts
- Replaced with `DatabaseFactory.connect()` + `DatabaseFactory.get()`
- Schema application and migrations remain after connection (not the factory's job)

**Created gate:** `scripts/check-database-usage.ts`
- Scans every `.ts/.tsx/.js` file for `new Database(`
- Skips `server/lib/db.ts` (the single allowed file)
- Uses quote-counting heuristic to avoid false positives in string literals
- Added to `just check` recipe

**Verification:**
```
$ just check
biome ✓  |  tsc ✓  |  db-gate ✓
All 99 files clean. No raw Database() instances found.
```

---

## Files Created This Session

**Shared infrastructure (2):**
- `scripts/lib/llm.ts` — shared OpenRouter LLM client
- `scripts/check-database-usage.ts` — build gate for raw Database() usage

**Refactored scripts (2):**
- `scripts/pr-summarize.ts` — uses `llm()`
- `scripts/summarize_analyses.ts` — uses `llm()`

**New scripts (1):**
- `scripts/refactor-playbook.ts` — playbook markdown refactor via LLM

## Files Modified This Session

**Playbook (1):**
- `playbooks/htmx-playbook.md` — war story → prescriptive format

**Scripts (2):**
- `scripts/seed_database.ts` — DatabaseFactory instead of raw `new Database()`
- `scripts/sync-prices.ts` — DatabaseFactory instead of raw `new Database()`

**Build config (2):**
- `justfile` — added `bun scripts/check-database-usage.ts` to `check` recipe
- `.gitignore` — added `!scripts/lib/` exception

## Stats

- **Commits this session:** 3
- **New files:** 4
- **Files modified:** 7
- **Lines removed:** ~664 (duplicated fetch logic + war story prose + connectDb helpers)
- **Lines added:** ~453 (shared lib + gate script + clean playbook)

---

## Decisions Made

### 1. Use gemini-2.5-flash for playbook refactor

A purpose-built script (`refactor-playbook.ts`) reads a markdown file, sends it to the LLM with a system prompt stripping narrative, and writes the result back. This is a reusable pattern for any playbook that has drifted into war-story territory.

**Verdict:** Correct. The script itself reuses our shared `llm.ts` substrate. The refactor saved ~30 minutes of manual editing. Loss rate: ~2 edge cases out of ~15 rules (13% false negative). Acceptable for a first pass.

### 2. Three-layer enforcement for DatabaseFactory

We didn't just fix the two scripts — we made it impossible to repeat the mistake:
1. **Mechanical gate:** `check-database-usage.ts` fails `just check` on any `new Database(`
2. **Import barrier:** `Database` from `bun:sqlite` is no longer imported anywhere except `db.ts`
3. **Documentation:** AGENTS.md already states the rule

**Verdict:** Correct. A rule without enforcement is a suggestion. The gate is fast (~50ms for 99 files) and catches the problem at build time, not in production.

### 3. Keep schema/migration application outside DatabaseFactory

The factory's job is connection + pragmas. Schema application (`schema.sql`) and ad-hoc migrations (`ALTER TABLE`) are still done by callers after `connect()`. This keeps the factory pure and avoids coupling it to schema evolution.

**Verdict:** Correct. The factory is a connection manager, not a schema manager. Separation of concerns.

---

## Lessons Learned

### 1. `.gitignore` `lib/` rule is a landmine for TypeScript projects

Python's standard `.gitignore` template includes `lib/` which matches *any* `lib/` directory. We already had `!server/lib/` but missed `scripts/lib/`. The file was created, worked locally, but was invisible to git.

**Pattern:** Any time you create a `*/lib/` directory in a repo with Python gitignore, immediately add a `!` exception.

### 2. Shared substrate extraction follows the 3-script rule

We had 3 scripts with duplicated OpenRouter logic. That's the threshold where extraction pays off. At 2 scripts it's debatable; at 3 it's mandatory. The `llm.ts` substrate eliminates ~120 lines and centralizes model defaults, error handling, and `.env` loading.

### 3. LLM refactors lose edge cases

The gemini rewrite of `htmx-playbook.md` dropped two non-obvious but important items:
- `var` hoisting in loops
- `split('\n')` vs actual newlines

Both are runtime traps that don't appear in "standard" rule sets. When using LLM for refactoring, always diff against the original for technical completeness — the LLM is good at structure, mediocre at preserving edge cases.

### 4. The "refer to a just verb" convention works, but with caveats

The user asked: "if I refer you to a just verb then presumably you can construct sufficient context from that to figure out a response."

In this case, `just pr-summarize` → `scripts/pr-summarize.ts` which is a clean script with explicit model, prompt, and I/O pattern. Reconstructable. But this only works when:
- The Justfile is a thin facade (not inline logic)
- Script names are unique and descriptive
- The pattern has been established before

If a verb embeds logic directly or is a one-off with unusual flags, the convention fails.

**Recommendation:** Use the just verb as shorthand *plus* a 5-word clause for high-stakes references.

### 5. The infrastructure invisibility problem

`defuddle` was almost missed in the flox.toml because it solves a problem most developers don't know they have. It turns "read this URL" from a manual copy-paste into a mechanical markdown extraction. Without it, `just pr-fetch` would require the agent to manually strip HTML boilerplate from GitHub PR pages.

But tools like this often *never* get packaged by mainstream repositories. The maintainer sees "niche markdown extractor." The agent operator sees "load-bearing infrastructure."

**The empirical pattern:**

| Tool category | Packaged? | Example |
|-------------|-----------|---------|
| Compilers, databases, web servers | ✅ Always | nodejs, hledger |
| `jq`, `ripgrep`, `fd` | ✅ Usually | Large UNIX-philosophy user base |
| `defuddle`, `glow`, `gum` | ❌ Often not | "Too niche" — solves a problem most devs solve with browser tabs |
| Custom scripts (`check-database-usage.ts`) | ❌ Never | Specific to this codebase's failure modes |

**The heuristic:** When you find a tool that becomes invisible infrastructure (you stop thinking about it, but removing it breaks the workflow), treat it as a hard dependency. Document it in the manifest, the justfile, and the debrief. Don't assume "it'll get packaged eventually" or "someone else will know to install it."

`defuddle` is now in the required section of flox.toml. If flox didn't have it, the right move would be to note it as a manual install — not to pretend it's optional because it's not in the repo.

**Practical utility is the measure of value, not popularity.** A tool that prevents one forward-port disaster per quarter is worth more than a tool that 10,000 people star on GitHub but never use.

---

## Verification

| Check | Status |
|-------|--------|
| `just check` | ✅ biome + tsc + db-gate all pass |
| `bun scripts/check-database-usage.ts` | ✅ 99 files clean |
| `bun -e "import('./scripts/lib/llm.ts').then(m => console.log(typeof m.llm))"` | ✅ `function` |
| `bun scripts/refactor-playbook.ts playbooks/htmx-playbook.md` | ✅ outputs clean markdown |
| Playbook frontmatter valid | ✅ YAML parses |

---

## What's Next

From `debriefs/plans/current.md`:

1. **Price freshness badge** (`td-18e84e`) — per-ticker `last_updated` in holdings table
2. **Server tests** (`td-9dbbac`) — route health checks, positions query, hledger parsing
3. **Settings extraction** (`td-56fd1b`) — `server/lib/settings.ts` consolidation
4. **Seed script split** — `scripts/seed/` directory, one seed file per domain
5. **Migration tooling** — extract ad-hoc ALTER TABLE blocks from `server/index.tsx`
