# Review: td-f42750 — DOCS-CLEANUP: Fix path drift in documentation

**Reviewer:** ses_02a5c6
**Date:** 2026-05-08
**Verdict:** REJECTED → reopened as td-a67291 (follow-up)
**Implementer:** ses_51ed70

---

## Summary

The task "Fix path drift in documentation" was bundled with 35+ commits and 42
files of unrelated work (new CLI commands, IG client, benchmark, server lifecycle
fixes, etc.). While the main docs (AGENTS.md, ARCHITECTURE.md, README.md) were
correctly updated, several files were missed. Two of the missed paths cause
actual bugs (silent false positive test, broken script default).

---

## What Was Done Well

1. **AGENTS.md** — Correctly updated file map: `src/cli/` vs `cli/`, `src/server/`
   paths, new CLI commands in the startup commands table.
2. **ARCHITECTURE.md** — Path references updated (per handoff notes).
3. **README.md** — Path references updated (per handoff notes).
4. **New CLI commands** appear functional (`just check` passes, tests pass).
5. **Server lifecycle** improvements are genuine fixes (start/stop PID handling).

---

## Scope Violation

| Rule from AGENTS.md | What Happened |
|---------------------|---------------|
| "One concern per PR" | Docs cleanup + 12 new CLI commands + IG client + benchmark + server lifecycle + hledger updates + portfolio seeding |
| "Hard cap: 30 files per PR" | 42 files changed |
| "Stack branches, don't bundle" | All committed directly to `main` |

**35+ commits across a single TD task.** This is the pattern PR #9 was
documented as a cautionary example for. The implementer was likely context
window exhausted and thrashing — the handoff log shows repeated "Started"
entries and conflation of multiple epics (UNIFIED-CLI-001, DEBATE-001) into
one task.

---

## Remaining Path Drift (Not Fixed)

### 1. `docs/help.md` line 10 — `server/` → `src/server/`

```
| `server/` | Bun/Hono | Web dashboard on port 3000 |
```

Should read `src/server/`.

**Severity:** Low — documentation only, but users may look here.

### 2. `tests/test_currency_consistency.py` — `server/views` and `server/routes`

Lines 36 and 51 use `Path("server/views").glob("*.tsx")` and
`Path("server/routes").glob("*.ts")`. These directories no longer exist at
`server/` — they moved to `src/server/`.

**Severity: HIGH** — This is a **silent false positive**. The glob returns an
empty iterator (directory doesn't exist), so the test passes trivially (no files
to check for € symbols). The test is not checking anything.

Fix: `Path("src/server/views").glob("*.tsx")` and `Path("src/server/routes").glob("*.ts")`.

### 3. `tests/ig-instruments.test.ts` — broken import path

Line 13: `from "../cli/trading/lib/ig-instruments.ts"`

The file is at `src/cli/lib/ig-instruments.ts`. The import path resolves to
`cli/trading/lib/ig-instruments.ts` which does not exist. Test fails with:

```
error: Cannot find module '../cli/trading/lib/ig-instruments.ts'
```

**Severity: HIGH** — Broken test. Not caught by `just check` because this test
file is not referenced in any just recipe.

Fix: `from "../src/cli/lib/ig-instruments.ts"` (or adjust based on actual test runner root).

### 4. `scripts/color-tools/README.md` and `convert-hex-to-oklch.ts`

README line 20 and script line 71 reference `server/static/style.css` as the
default input path. The file is at `src/server/static/style.css`.

**Severity: MEDIUM** — Script crashes when run without arguments:

```
ENOENT: no such file or directory, open 'server/static/style.css'
```

The `just convert-hex-oklch` recipe calls the script without arguments, so it
will fail.

Fix: Change default to `src/server/static/style.css`.

### 5. `scripts/seed_test_journal.sh` lines 12, 171

Comments reference `bun run server/index.tsx`. Should be `bun run src/server/index.tsx`.

**Severity:** Low — documentation in comments, but copy-paste risk.

---

## Recommendation

Reject this task. The scope violation makes it impossible to review properly,
and the remaining path drift includes two real bugs (silent false positive test,
broken script default).

Create a focused follow-up task (`td-a67291`) with a tight scope:
- Fix the 5 remaining path drift items above
- Verify each fix (run the test, run the script, read the doc)
- `just check` must pass
- One commit, one concern.

---

## System Note

The implementer (ses_51ed70) was context window exhausted per its own handoff:
"Context window: EXHAUSTED. New session required." This is a systems issue, not
a competence issue. The failure mode is: **tired agent bundles everything into
one commit stream because it lacks the mental bandwidth to separate concerns.**

The preventive fix is already in the playbook: **lab-first + one concern per
commit + `just check` gate**. The implementer followed the gate (checks passed)
but missed the scope discipline. The td review process caught it. This is the
system working as designed.
