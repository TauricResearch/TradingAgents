# Epic: Architecture Hardening

**Date:** 2026-05-14
**Epic ID:** ARCH-HARDEN-001
**Status:** Done
**Stories:** ARCH-HARDEN-001-S01 through S08

---

## Vision

The codebase has gone through significant development and accumulated emergent complexity — dead code, convention violations, missing automated gates, and a flat directory structure that no longer scales. This epic flenses the barnacles, hardens the boundaries, consolidates the surface area, and reorganises the folder structure. The result is a codebase where the documented conventions match reality and the tooling enforces them.

---

## Stories (Executable Order)

The order matters. Each phase depends on the previous one being complete.

### ARCH-HARDEN-001-S01 — Flense and Harden (brief-flense-and-harden)

**What:** Remove dead code (`registry-types.ts`), merge dual-import pairs (benchmark/feedback/governance), fix `__dirname` and hardcoded `localhost:3000`, move `settings.ts` to shared layer to resolve 15 CLI import boundary violations, create `check-import-boundaries.ts` gate, catch up conceptual lexicon.

**Why first:** Until the import boundary is real (not aspirational), any reorganisation just moves violators to new paths. The gate must exist before new code is written. The dead module and dual-import pairs must be resolved before folder restructure.

**Dependencies:** None.

**Estimate:** 1d

---

### ARCH-HARDEN-001-S02 — Harden Python Bridge (brief-harden-python-bridge)

**What:** Add heartbeat + timeout to `analyze_stream.py`, stream agent reports in real-time (not batched), extract hardcoded LLM config into CLI args.

**Why now:** The bridge is the single point of failure and the most critical data flow. It has zero safety net. This is independent of the TypeScript restructuring — both streams can proceed in parallel after S01.

**Dependencies:** ARCH-HARDEN-001-S01 (the bridge code itself is independent, but the import boundary gate should exist first)

**Estimate:** 1d

---

### ARCH-HARDEN-001-S03 — Add Bridge and SSE Tests (brief-add-bridge-tests)

**What:** Add Python-side tests for `analyze_stream.py` (mocked), TypeScript-side tests for `POST /api/analyze` SSE endpoint (mocked subprocess), test for heartbeat forwarding.

**Why now:** The bridge is being actively modified in S02. Tests should be written alongside the hardening, not after. Can be executed in parallel with S02.

**Dependencies:** ARCH-HARDEN-001-S02 (tests validate the hardened bridge)

**Estimate:** 0.5d

---

### ARCH-HARDEN-001-S04 — Consolidate Server Lib (brief-consolidate-server-lib)

**What:** Extract shared Python subprocess runner, inline the 9-line `utils.ts`, kill the `-data.ts` suffix convention, verify no broken routes.

**Why now:** After S01 merges the dual-import pairs, the remaining `-data.ts` convention fix is cleaner. The consolidation should happen against a clean baseline.

**Dependencies:** ARCH-HARDEN-001-S01 (dual-import merges are S01)

**Estimate:** 0.5d

---

### ARCH-HARDEN-001-S05 — Consolidate CLI Commands (brief-consolidate-cli)

**What:** Reduce 42 top-level commands to ~15 with proper subcommand grouping. Consolidate 8 IG commands into one, 6 config commands into one, 3 alerts commands into one.

**Why now:** After S01 moves `settings.ts` to the shared layer, the CLI import paths are already being updated. Consolidating commands in the same pass reduces churn.

**Dependencies:** ARCH-HARDEN-001-S01 (import paths are already changing)

**Estimate:** 1d

---

### ARCH-HARDEN-001-S06 — Collapse Registry Tooling (brief-collapse-registry-tooling)

**What:** Reduce 10 `reg-*.ts` scripts to 1-2 with subcommands. Archive unused scripts. Remove `barnacle-scan.ts`.

**Why now:** Independent of the TypeScript codebase changes. Can be done at any point, but should precede the justfile overhaul (S07) so both can be factored into the final justfile.

**Dependencies:** None (independent)

**Estimate:** 0.5d

---

### ARCH-HARDEN-001-S07 — Justfile Overhaul (brief-justfile-overhaul)

**What:** Fix broken recipes, collapse reg/gn/agent groups, fix group boundaries, trim aliases, remove shortcuts. Target: 124→60 recipes.

**Why now:** Depends on S05 (CLI commands renamed) and S06 (registry recipes collapsed) — otherwise the justfile will need two overhauls.

**Dependencies:** ARCH-HARDEN-001-S05, ARCH-HARDEN-001-S06

**Estimate:** 0.5d

---

### ARCH-HARDEN-001-S08 — Remove Agent Ceremony (brief-remove-agent-ceremony)

**What:** Replace 5 scripts/678 lines/15 justfile recipes with `just orient` and `just sync`.

**Why now:** Completely independent of the TypeScript codebase changes. Can be done at any point. Lowest priority — the system works, it's just heavy.

**Dependencies:** None

**Estimate:** 0.25d

---

## Dependency Graph

```
S01 (Flense & Harden)
 ├── S02 (Python Bridge) ── S03 (Bridge Tests)
 ├── S04 (Consolidate Server Lib)
 ├── S05 (Consolidate CLI)
 │    └── S07 (Justfile Overhaul)
S06 (Registry Tooling) ────┘
S08 (Agent Ceremony) — independent, any time
```

## Deferred to Next Epic

These briefs are lower-priority and not included in this epic:
- `brief-add-scripts-type-check` — valuable but non-critical
- `brief-trim-justfile` — superseded by the overhaul (S07)
- Folder reorganisation — precondition is a clean codebase, which is what this epic delivers

---

## Done

| Story | Status |
|---|---|
| S01 — Flense and Harden | ✅ |
| S02 — Harden Python Bridge | ✅ |
| S03 — Bridge and SSE Tests | ✅ |
| S04 — Consolidate Server Lib | ✅ |
| S05 — Consolidate CLI | ✅ |
| S06 — Collapse Registry Tooling | ✅ |
| S07 — Justfile Overhaul | ✅ |
| S08 — Remove Agent Ceremony | ✅ |

## Exit Criteria

- `just check` passes with zero `|| true` escape hatches
- `bun scripts/check-import-boundaries.ts` reports zero violations
- 15 CLI commands no longer import from `src/server/lib/`
- Python bridge has heartbeat + timeout + real-time streaming
- CLI has ~15 commands with proper subcommand grouping
- `just --list --groups` shows ~60 recipes in clean groups
- Code registry and conceptual lexicon are up to date
- All barnacles identified in the code audit are resolved
