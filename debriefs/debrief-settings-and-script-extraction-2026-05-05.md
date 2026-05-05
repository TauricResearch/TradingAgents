# Debrief: Settings + Script Extraction Attempt

**Date:** 2026-05-05  
**Goal:** Create central config module, extract inline XXXScript() functions from views, wire up static script serving  
**Outcome:** Partial success — settings.ts committed, script extraction reverted  

---

## What We Planned

1. Create `server/lib/settings.json` + `server/lib/settings.ts` — single source of truth for all env vars, paths, defaults
2. Extract all 13 inline `XXXScript()` functions from views into `server/scripts/*.ts` modules
3. Copy `.ts` scripts to `server/static/scripts/*.js` for browser serving
4. Update views to import from scripts and use `<script src>` tags instead of `dangerouslySetInnerHTML`
5. Add biome override to exclude static scripts from linting
6. All checks green throughout

---

## What Actually Happened

### Attempt 1 — Extracted scripts to `server/scripts/`, copied to `server/static/scripts/`

**What worked:** `settings.ts` + `settings.json` created and committed cleanly (fdcf985).

**What broke:**
- Copied `.ts` files to `.js` for serving
- Biome tried to lint the `.js` files as JavaScript
- TypeScript syntax in `.js` files caused parse errors: `export function`, `: string` return types, JSDoc comments
- Attempted to fix with biome `files.ignore` key — invalid key at v2.4.14, biome failed entirely
- Attempted to fix with `overrides` block — still processed the files, still failed
- Three separate forward-fix attempts over 45 minutes — each introduced new breakage
- Runtime: `intelligence.ts` script had `` `\`calt\` `` inside a `.map(\`...\`) \`` template, which is syntactically illegal — corrupted `portfolio.tsx` at runtime with no compile-time error

**Revert:** Hard reset to `3cf1821`, 5 minutes, all checks green.

### What we learned

The core insight: **inline `XXXScript()` in views is fine**. They are:
- Type-checked by tsc
- Linted by biome
- Colocated with the view (no searching for them elsewhere)
- Not causing any runtime problems

The only real bug was the `` \'calt\' `` escaping in two scripts — a one-line fix. The entire script-extraction-to-static-files approach was over-engineering a problem that didn't exist.

---

## What Worked

- `server/lib/settings.json` + `settings.ts`: clean, typed, committed
- Revert protocol: when stuck, revert to last known-good state is faster than forward-fix
- Fail-fast: recognizing at step 3 that this wasn't working and stopping

## What Didn't Work

- Copying TypeScript to JavaScript for serving — biome lints `.js` differently, TypeScript syntax breaks the parser
- `biome.json` `files.ignore` key — invalid at v2.4.14, caused total biome failure
- Overrides approach for `server/static/scripts/**` — complex, fragile, not tested until we hit it
- Script extraction epic created 12 tasks that were all closed immediately

## What We'd Do Differently

1. **Never copy TypeScript to JavaScript for serving.** If we need external scripts, keep them as TypeScript modules and reference them with `import` in the browser via a bundler, or just keep them inline.
2. **Test biome.json changes immediately** — before committing, run `just lint` to catch config errors.
3. **Validate the hypothesis before creating 12 TDs.** Ask: "Is the inline pattern actually causing problems?" If not, don't refactor it.
4. **One change at a time, check after each** — the fail-fast protocol exists for exactly this scenario.

## Commit History

| Commit | What |
|--------|------|
| `fdcf985` | `feat(settings): central config module + script extraction foundation` |
| `7d339e8` | `docs(AGENTS): add Working Principles + Known Failure Modes section` |

## Resolved TDs

- `td-1cb416` — settings.ts + settings.json ✓
- `td-e8ee98` — script extraction ✓ (as "won't fix — inline pattern works fine")
- `td-8f3075` — JSX rendering epic ✓ (superseded by td-b86d5a)
- All STATIC-001 tasks — closed as superseded
- `td-b86d5a` — new JSX refactor epic with 12 child tasks (pending)

## Next Steps

1. Start `td-41713c` — split `analyses.ts` (high value, clear structure)
2. After analyses split, start `td-08850c` — `workflow.tsx` (tiny, establish pattern)
3. Add route-level tests (`td-9dbbac`) — the only guard we have for view correctness without manual browser check