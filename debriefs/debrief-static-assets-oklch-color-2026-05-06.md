# Debrief: Static Assets Fix, oklch Conversion, Language Preference Directive

**Date:** 2026-05-06
**Goal:** Fix broken static assets, convert palette to oklch, establish TypeScript-first tooling culture
**Outcome:** All checks green. tsc ✓ lint ✓ 15 smoke tests pass. Server serving assets correctly.

---

## What We Planned

1. Fix 404s on `/static/style.css`, `/static/scripts/layout.js`, `/static/favicon.svg`
2. Fix 404 on `/api/analyses/list/html` (HTMX route)
3. Fix dark-on-dark platform badge in Exits view
4. Convert `:root` hex palette to oklch (with original hex in comments)
5. Add language preference directive to AGENTS.md
6. Fix TS18003 `tsc` error + Bun type declarations
7. Clean last 2 Biome `!` assertion warnings

---

## What Actually Happened

### 1. Static Assets 404 ✅

**Root cause:** Hono's `serveStatic` joins `root` with `c.req.path` (the full request path). For `/static/style.css`, it resolved to `staticDir + "/static/style.css"` instead of `staticDir + "/style.css"`.

**Fix (two changes):**

```ts
// server/index.tsx
const staticDir = resolve(import.meta.dir, "static");

app.use("/static/*", serveStatic({
  root: staticDir,
  rewriteRequestPath: (path) => path.replace(/^\/static/, ""),
  onFound: (_path, c) => {
    c.header("Cache-Control", "public, max-age=31536000, immutable");
  },
}));
```

1. Absolute path via `resolve(import.meta.dir, "static")` — eliminates cwd sensitivity.
2. `rewriteRequestPath` strips `/static` prefix so the middleware resolves correctly.

**Verification:**
```
style.css: 200
layout.js: 200
favicon.svg: 200
fonts/Datatype.woff2: 200
```

---

### 2. `/api/analyses/list/html` 404 ✅

**Root cause:** Route collision. `analysesFsRouter` (mounted first) had `/:ticker/:date` which greedily matched `/list/html` (treating `list` as ticker, `html` as date) before `analysesDbRouter`'s exact `/list/html` could be reached.

**Fix:** Swapped mount order in `server/routes/analyses/index.ts`:

```ts
// DB router FIRST — exact routes take priority
analysesRouter.route("/", analysesDbRouter)  // /list, /list/html, /:id, /:id/card
analysesRouter.route("/", analysesFsRouter)   // /, /:ticker/:date/*
```

Hono's Trie router registers exact-match routes before parameterized ones when sharing the same parent.

---

### 3. Exits platform badge dark-on-dark ✅

**Root cause:** Two `.platform-tag` definitions existed. The second (at line ~635) with `background: var(--bg)` was overriding the first, making the badge near-invisible against the card background.

**Fix:**
1. Removed the duplicate definition.
2. Added `.exit-card .platform-tag` override with `background: var(--border)` and `color: var(--text)` for clear contrast inside exit cards.

---

### 4. oklch Palette Conversion ✅

**Tool:** `colorizr` npm package (662KB, focused on oklch/oklab).

**New script:** `scripts/color-tools/convert-hex-to-oklch.ts`
- Reads a CSS file, finds `:root` block
- Converts hex values to `oklch()` via `convertCSS(hex, "oklch")`
- Appends original hex as trailing comment

**Usage:**
```bash
bun scripts/color-tools/convert-hex-to-oklch.ts [input.css] [output.css]
just convert-hex-oklch  # converts server/static/style.css in-place
```

**Result:**
```css
:root {
  --bg: oklch(17.833% 0.01281 270.6); /* #0f1117 */
  --surface: oklch(23.23% 0.01988 271.76); /* #1a1d27 */
  /* ... */
}
```

---

### 5. Language Preference Directive ✅

**Added to AGENTS.md:**

```markdown
## MANDATORY: Language Preference

- **Dashboard/server work** (routes, views, scripts, tooling): **TypeScript with Bun only.**
- **Python is reserved for:** the `tradingagents/` core package, the CLI entry point, and the bridge script (`scripts/py/analyze_stream.py`).
- **No Python for auxiliary tasks.** Do not reach for Python for one-off conversions, data transforms, or code-generation scripts.
- **Never add a Python dependency** to solve a problem that a 20-line TypeScript snippet or an npm package can handle.
```

---

### 6. TS18003 + Bun Types ✅

**TS18003 fix:** `tsconfig.json` had `include: ["src/**/*.ts"]` but the project uses `server/` not `src/`. Updated to `include: ["server/**/*.ts", "server/**/*.tsx"]`.

**Bun types fix:** Added `"types": ["bun"]` to both `tsconfig.json` and `tsconfig.server.json` `compilerOptions`. This loads `@types/bun`, which declares `import.meta.dir` and `bun:sqlite`.

**Result:** Both `tsc --project tsconfig.json --noEmit` and `tsc --project tsconfig.server.json --noEmit` pass with zero errors.

---

### 7. Last 2 Biome Warnings ✅

Both were `noNonNullAssertion` (`!`) on array accesses within loops:

- `signals.ts:106` — `tickerSignals[i]!` → `const s = tickerSignals[i]; if (!s) continue`
- `workflow.ts:297` — `targets[ti]!` → `const tp = targets[ti]; if (!tp) continue`

Dead-code paths in practice (index bounded by `length`), but the guards satisfy the linter without the `!` sledgehammer.

---

## Files Changed

| File | What Changed |
|------|-------------|
| `server/index.tsx` | Absolute `staticDir` + `rewriteRequestPath` for serveStatic |
| `server/routes/analyses/index.ts` | Mount order: DB router before FS router |
| `server/static/style.css` | `:root` palette → oklch; removed duplicate `.platform-tag`; added `.exit-card .platform-tag` |
| `server/routes/signals.ts` | Removed `!` assertion, added null guard |
| `server/routes/workflow.ts` | Removed `!` assertion, added null guard |
| `tsconfig.json` | `include` → `server/`, added `"types": ["bun"]` |
| `tsconfig.server.json` | Added `"types": ["bun"]` |
| `AGENTS.md` | New "Language Preference" mandatory section |
| `Justfile` | New `convert-hex-oklch` verb |
| `scripts/color-tools/convert-hex-to-oklch.ts` | New conversion script |
| `scripts/color-tools/README.md` | Documentation for tool |
| `package.json` / `bun.lock` | Added `colorizr` dev dependency |

---

## Stats

- **Commits this session:** ~12
- **New files:** 3 (`scripts/color-tools/convert-hex-to-oklch.ts`, `scripts/color-tools/README.md`, package dep)
- **Config files touched:** 4 (`tsconfig.json`, `tsconfig.server.json`, `Justfile`, `AGENTS.md`)
- **Checks:** Biome clean, tsc clean (both configs)

---

## Playbooks Updated

| Playbook | What Added |
|----------|-----------|
| `playbooks/htmx-playbook.md` | `serveStatic` with `rewriteRequestPath` + absolute path pattern |
| `playbooks/tsconfig-tiered-playbook.md` | `"types": ["bun"]` for Bun runtime types |
