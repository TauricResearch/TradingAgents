# Debrief: The Lab-First Pivot

## Context

While building the server lifecycle CLI (`scripts/server-lifecycle.ts`), we attempted to add
Gum-style formatted output directly to the production script. The result:

- Broke the status display (garbled output, misaligned columns)
- Required 3+ iterations of "fix, check, still broken, fix again"
- Each iteration touched production code, creating risk of further breakage
- The user's intervention: "STOP, once again we are thrashing a tad"

## The Pivot

Instead of fixing forward in production, we created `scripts/lab-gum.ts` — a standalone
experiment script with no production dependencies. Result:

- First attempt: `execSync` with `input` option → broken (`"2"` rendered inside box)
- Second attempt: `Bun.spawn` with `stdin.write()` → working perfectly
- Total time to working solution: ~3 minutes
- Zero risk to production code

## Lessons Learned

1. **Lab-first is faster.** 3 iterations in a lab script beats 3 iterations in production.
   No `just check` cycle, no commit anxiety, no regression risk.

2. **Node vs Bun APIs matter.** `child_process.execSync` with `input` failed silently
   (gum interpreted `"2"` from `--padding "1 2"` as text). `Bun.spawn` with `stdin.write()`
   worked immediately. The lab exposed this without polluting production.

3. **ASCII boxes are fragile.** Unicode box-drawing characters depend on terminal font,
  character width, and alignment math. They "always look broken" (user's words).
  Gum uses terminal escape codes — works everywhere, looks consistent.

4. **User intervention is a signal.** When the user says "STOP, we are thrashing,"
   the correct response is not to try harder. It is to step back and change the approach.
   The lab-first pivot was the user's idea. Listen to it.

## Counterfactual

If we had continued fixing forward in `server-lifecycle.ts`:
- Would have needed 2-3 more commits
- Each commit would need `just check` pass
- Each commit would be in the PR history forever
- Risk of breaking the already-working status command

## Action Items

- [x] Create `scripts/lab-gum.ts` — working Gum output experiment
- [ ] Write `playbooks/lab-first-playbook.md` — codify the process
- [ ] Write `playbooks/gum-playbook.md` — Gum patterns for this codebase
- [ ] Only port working patterns from lab to production
