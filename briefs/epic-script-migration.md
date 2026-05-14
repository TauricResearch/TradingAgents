# Epic: Migrate Business-Logic Scripts to src/

**Date:** 2026-05-12
**Epic ID:** SCRIPTS-001
**Status:** Superseded — migration was already complete
**Priority:** P2
**Language:** TypeScript (Bun runtime)
**Location:** `scripts/` → `src/`

---

## Objective

Migrate `trade-calculator.ts` from `scripts/` to `src/lib/`. This makes it a proper shared library — importable by `src/server/lib/`, `src/cli/commands/`, and the `scripts/` operational layer alike. The trade calculator is business logic, not project meta. It belongs in the project.

---

## Classification: Why Move

The `scripts/` directory holds two kinds of things:

| Kind | Examples | Stays in scripts/ |
|------|----------|-------------------|
| **Project meta** — tooling *on* the project | `agent-*.ts`, `reg-*.ts`, `td-orphans.ts`, `barnacle-scan.ts` | Yes |
| **Business logic** — logic *of* the project | `trade-calculator.ts` | No — move to `src/lib/` |

`trade-calculator.ts` computes entry, stop, target, and position size from price data. It is not a script that orchestrates or inspects — it is a function that could be used by:
- `src/server/routes/trade-plan.tsx` (already imports it)
- `src/cli/commands/plan.ts` (could import it)
- The analysis pipeline output

Moving it makes it a proper dependency rather than a standalone invocation.

---

## Scope

### Move: `scripts/trade-calculator.ts` → `src/lib/trade-calculator.ts`

- Move the file to `src/lib/`
- Update all imports:
  - `src/server/routes/trade-plan.tsx`
  - `src/cli/commands/plan.ts` (if it imports from scripts/)
  - Any other references found via grep
- Update `just trade-calc` recipe (if any) to invoke from `src/lib/`
- Verify `just check` still passes
- Regenerate `scripts/INDEX.jsonl` (the self-index) and `code/INDEX.jsonl` via `reg-sync-scripts.ts --fix`

### Do Not Move (stay in scripts/)

| Script | Reason |
|--------|--------|
| `agent-*.ts`, `td-orphans.ts` | Agent coordination meta — operates *on* the project |
| `reg-*.ts` | Registry tooling — operates *on* the project |
| `barnacle-scan.ts` | Project hygiene — operates *on* the project |
| `gitnexus-*.ts` | Knowledge graph tooling — operates *on* the project |
| `check-database-usage.ts` | Required gate in `just check` — must stay accessible |
| `render_diagrams.ts` | Diagram generation — operates *on* the project |
| `worktree-init.ts`, `pr-summarize.ts` | Git/GitHub meta tools |
| `seed_database.ts`, `db-backup.ts` | Database operations — borderline, but currently invoked via just recipes that reach into scripts/ |

The borderline scripts (`seed_database.ts`, `db-backup.ts`) are operations on the project state (the database) rather than business logic. Keep them in `scripts/` for now. If they later gain importable sub-functions used by `src/`, revisit.

---

## Verification

- [ ] `just check` passes after move
- [ ] `bun scripts/reg-sync-scripts.ts --fix` updates scripts/INDEX.jsonl
- [ ] `bun scripts/reg-sync.ts code` still passes (code/INDEX.jsonl auto-updates)
- [ ] No remaining imports from `scripts/trade-calculator.ts`

---

## Notes

The `scripts/` directory remains the operational surface for project management. The migration is about *correctness of location* — business logic belongs in `src/`, not in the tooling layer. The Justfile facade makes both locations equally accessible from the command line.
