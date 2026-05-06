# Tidy-First: Why Quality Is the Constraint on Velocity

> *"Delivery is fast, quality is key, so iterating on quality becomes a virtue."*

This document records the operational philosophy governing how this codebase evolves. It is not about being virtuous. It is about being rational in a system where execution speed is high and error cost compounds.

---

## 1. The Compounding Error Principle

Fast execution does not just produce features faster — it produces *errors* faster. When the team chose string-concat templates over JSX, the failure was not gradual. It was exponential. A slow team would have built three template routes, noticed friction, and stopped. This team built twelve, discovered the pattern was structurally wrong, and had to forward-port an entire PR because the merge base had become toxic.

**The cost of a wrong turn is not proportional to the mistake. It is proportional to how far you travelled before correcting.**

In this codebase:
- Execution cost is low (small team, fast feedback, `just check`)
- Error cost is high (template → JSX refactor: 672 lines removed, 1,200 added, 3-hour PR forward-port)
- Therefore: the optimal strategy is to front-load correctness

This is the inverse of standard software engineering anxiety. Most teams fear moving too slowly. This team should fear moving incorrectly — because the speed makes errors compound at the same rate as features.

---

## 2. Refactoring as Discovery

Refactoring is not maintenance. It is **reverse archaeology** — you dig into the structure to see how the thing was actually built, not how it was specified.

The template → JSX refactor surfaced problems that were invisible in the template code:

| Issue | Hidden in templates | Visible in JSX |
|-------|-------------------|----------------|
| `dangerouslySetInnerHTML` proliferation | Script blocks rendered as strings | Non-cacheable, unlintable, duplicated across 13 views |
| `serveStatic` path leak | `"./server"` root looked fine | Could expose source files outside `static/` |
| `.ts` vs `.tsx` extension | Biome treated JSX as TypeScript class syntax | Parse errors: "expected `>` but found `data"` |
| DOCTYPE omission | String builders never emitted `<!DOCTYPE html>` | Browsers fell into Quirks Mode, breaking CSS |

None of these were flagged during template development. They only emerged when the same behaviour had to be expressed in a stricter system. The refactor was a diagnostic tool, not just a cleanup.

**Lesson:** If a refactor does not surface at least one hidden problem, it was either trivial or unnecessary.

---

## 3. The Tidy-First Heuristic

"Tidy-first" means investing in structural correctness before building on top of a questionable foundation. It is the damping mechanism that prevents fast execution from producing fast technical debt.

### When it works

Tidy-first is rational when three conditions are met:

1. **Empirical data about the current approach.** You have observed specific failures, not just a vague feeling that something could be better. (Template experiment: 1,500 lines of duplicated inline JS, uncacheable responses, XSS risk.)

2. **Scoped tidy step.** The refactor is mechanical and bounded. (Extract JS to external files. Rename `.ts` → `.tsx`. Fix DOCTYPE. Not: "rewrite the entire view layer.")

3. **Known destination.** You have a concrete, proven pattern to move toward. (JSX + `pageOrPartial` + external scripts — per `playbooks/htmx-playbook.md`.)

### When it fails

Tidy-first becomes **premature abstraction** when applied before domain understanding exists. If you had "tidied" the template approach by building a *better* template engine, you would have produced tidy garbage — elegant, consistent, and still the wrong abstraction.

The boundary is timing. Tidy-first applied *before* experimentation produces abstractions for problems you do not yet understand. Tidy-first applied *after* experimentation consolidates the winning pattern and enforces it.

---

## 4. The Empirical Test

After each tidy step, ask: **does the next feature take less work?**

| Tidy step | Next feature impact |
|-----------|-------------------|
| Extract `scripts/lib/llm.ts` | Next PR summary: 30 min → 10 min |
| DatabaseFactory gate | No more WAL mode debugging |
| htmx-playbook refactor | Faster onboarding (hypothetical but plausible) |
| Re-hex CSS variables to oklch | No measurable improvement |

The last item is the warning signal. Refactoring that does not reduce the cost of the *next* change is polishing, not engineering. It may feel like progress because the code is visibly cleaner. But if the business problem sits untouched, you are rearranging quality, not creating it.

**Rule:** If a tidy step takes longer than 30 minutes and does not unblock a known next feature, it is procrastination with better aesthetics.

---

## 5. Mechanical Enforcement

Philosophy without enforcement is a suggestion. This codebase uses three layers:

1. **Codified standards** (`playbooks/*.md`) — Rules are written down, versioned, and cross-referenced. Prevents "oh we used to do it this way" drift.

2. **Build gates** (`just check`) — `biome` + `tsc` + custom gates (`check-database-usage.ts`, `check-view-scripts.ts`). The gate fails the build before the commit.

3. **Retrospective honesty** (`debriefs/*.md`) — What was learned, what was decided, what failed. Institutional memory that outlasts any single session.

A rule enforced by a gate is not a burden. It is a **cognitive offload**. The agent does not need to remember "never use `new Database()`" — the gate remembers, and fails the build if they forget.

---

## 6. Quality as Constraint, Not Virtue

The user framed this as "iterating on quality becomes a virtue." The more precise framing: **quality becomes the constraint that governs velocity.**

Adam Smith's pin factory only produces surplus when the operations are *the right operations*. A factory that optimizes the wrong process does not make more pins — it makes more scrap metal faster.

In this codebase:
- **Velocity is not scarce.** `bun`, `just`, HTMX + SSR, rapid agent sessions.
- **Correctness is scarce.** Wrong abstractions (templates, inline JS, raw DB connections) compound faster than they can be unwound.
- **Therefore:** Quality is the binding constraint. Invest in it first.

This is not moralism. It is systems thinking. When the cheap resource is execution and the expensive resource is correction, the rational strategy is to spend execution on ensuring correctness before building the next layer.

---

## 7. The Refactor Taxonomy

Not all tidying is equal. Categorize before executing:

| Category | Definition | Example |
|----------|-----------|---------|
| **Structural** | Extracts shared substrate, enforces boundaries, eliminates duplication | `llm.ts`, DatabaseFactory gate |
| **Diagnostic** | Reveals hidden problems by forcing expression in a stricter system | Template → JSX refactor |
| **Consolidating** | Migrates scattered implementations to a single standard | HTML builders → JSX components |
| **Cosmetic** | Reformats, renames, reorders without changing behaviour or reducing future cost | Re-hexing CSS, variable renaming |

**Do structural and diagnostic first. Cosmetic only when it is free.**

---

## 8. The Forward-Port Heuristic

When a PR was written against old architecture that you've since refactored:

| Conflict count × semantic distance | Action |
|-----------------------------------|--------|
| <5 conflict regions | Resolve the merge |
| 5–15 conflict regions | Evaluate forward-port vs. merge |
| >15 conflict regions | **Always forward-port** |

The threshold is not just conflict count but *semantic distance*. String-concat vs JSX is a chasm, not a gap. PR #5 had 9 conflict regions in `seed_database.ts` alone and was written against pre-JSX architecture. Forward-porting the *ideas* (not the code) into the clean structure was faster and produced better code than resolving a 3-way merge would have.

---

## 9. Session Discipline

The observable pattern of this codebase:

1. **Execute fast** — build the feature, test it, ship it.
2. **Observe friction** — where did it hurt? What was duplicated? What was fragile?
3. **Tidy the pattern** — extract substrate, write gate, update playbook.
4. **Document the lesson** — debrief: what was learned, what was decided, what to watch for next time.

Step 3 is not a separate phase. It is the *completion* of step 1. A feature is not done when it works. It is done when the *next* feature can build on it without repeating the same friction.

---

## Summary

This codebase improves with every session because it has a **feedback loop on quality**, not just on features. The loop is:

> Execute → Observe friction → Tidy the pattern → Enforce mechanically → Document the lesson

The critical insight is that **fast execution without fast correction produces fast technical debt**. Tidy-first is not a luxury. It is the damping mechanism that keeps a fast system stable.

Watch for the boundary where "tidy" stops being structural and becomes cosmetic. The former is engineering. The latter is procrastination.
