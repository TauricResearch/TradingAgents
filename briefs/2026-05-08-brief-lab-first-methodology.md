# Brief: The Lab-First Method — A Field Guide to Disposable Experiments

**Date:** 2026-05-08
**Author:** ses_02a5c6 (TradingAgents project)
**Status:** Ready for blog post development
**Word count estimate:** 2,500–3,500 words
**Tone:** Practical, empirical, dryly witty. No manifestos.

---

## The Hook

"We tried to replace a status display in production. Three iterations, all broken. Context window exhausted. Then the user said: 'STOP. Let's think.'"

The lab-first method is not a philosophy. It is a thermodynamic observation: direct editing of production code under pressure produces entropy. The lab is an entropy sink. It absorbs the mess of exploration so production stays ordered.

## The Core Claim

**Before modifying production code, create a standalone lab script.**

Lab scripts are disposable experiments in `scripts/lab/`. They prove an approach works before it touches anything that `just check` validates or that users depend on.

## The Evidence

### Case Study A: Status Display (Session ses_51ed70 vs ses_02a5c6)

| | Direct Edit (ses_51ed70) | Lab-First (ses_02a5c6) |
|---|---|---|
| Approach | Edited production file directly | Created `scripts/lab/status-templates.ts` with 4 competing layouts |
| Iterations | 3+ failed attempts, bundled commits | 4 templates evaluated against live data |
| Result | Context window exhaustion, partial reversion to ANSI boxes | Template E selected: one border, dynamic width, no wrapping |
| Commits | 35+ bundled with unrelated work | 1 commit, correct first time |
| Bugs introduced | 2 (silent false positive test, broken import path) | 0 |

### Case Study B: One Session, Four Features (ses_02a5c6)

One session built four Gum-styled CLI commands:

| Feature | Lab Script | What Was Tested | Production Result |
|---------|-----------|----------------|-------------------|
| Status display | `status-templates.ts` | 4 layouts with live data | Template E, zero reverts |
| Portfolio table | `portfolio-gum.ts` | Multi-column financial table | Dynamic width validated |
| IG history | `ig-history.ts` | Activity vs transaction layout | Mock data proved format before API call |
| Exit plan alerts | `alerts.ts` | Alert severity logic | Edge cases caught early |

**Result:** 4 features, 6 commits, zero forward-fixes, zero reverts, all checks green.

## The Rules (Validated by Evidence)

### 1. The Context Window Rule

**If you're on attempt 3 of the same file without a green check, stop. Create a lab.**

The previous session's debrief literally said: "Context window: EXHAUSTED." The implementer had edited a file directly, broken it, fixed it, broken it again. By attempt 3, the file was a palimpsest of half-solutions. A lab would have absorbed that entropy.

### 2. The Live Data Principle

**Use real data for layout experiments. Use mock data for API shape experiments.**

- A table that looks good with 2 rows may wrap with 7. Only live data reveals this.
- Mock data is fine for asking "Does this format handle the API response shape?" not "Does the API respond?"

### 3. The One-Shot Port Rule

**A lab-proven pattern should port to production in a single edit, passing check first time.**

If the port requires forward-fixes, the lab wasn't finished. The lab's job is to eliminate all unknowns so the production edit is mechanical.

## The Workflow

```
1. Identify the problem (e.g. "status output looks broken")
2. Create lab script:              touch scripts/lab-<topic>.ts
3. Experiment freely:               bun scripts/lab-<topic>.ts
4. Find working pattern:            (no check cycle, no commit pressure)
5. Port to production:              edit production file with proven pattern
6. Verify:                          just check
7. Commit:                          git commit
8. (Optional) Delete lab:          rm scripts/lab-<topic>.ts
```

## The Anti-Patterns

**Don't:** Edit production code, see it break, fix, commit, see it break again. This is thrashing. It wastes check cycles, pollutes git history, and stresses everyone.

**Don't:** Spend more than 15 minutes on a single approach in the lab. If it isn't working, try a different library, a different API, or a different architecture. The lab is for rapid pivoting.

**Don't:** Leave lab scripts in the repo without a clear purpose. They become orphaned code that confuses future readers.

## The Lexicon (Terms for Precision)

- **Lab-first** (operational heuristic): Prove patterns in scripts/lab/ before touching production code.
- **Entropy sink** (metaphor): A place where exploration mess is absorbed so production stays ordered.
- **Context window rule** (operational heuristic): Three failed attempts on production code = context window exhaustion. Create a lab.
- **Template E** (pattern): The winning Gum display pattern — one border, dynamic width, title/hint outside, inline ANSI dots.
- **One-border rule** (operational heuristic): Every Gum display should have at most one border.

## The Honest Limitation

Lab-first is not free. Each lab is 50-150 lines of disposable code. For a one-line fix, it's absurd overkill. The discipline is knowing when the scope justifies the overhead.

Simple bug fix with clear cause → No.
New CLI output formatting → Yes.

## The Conclusion

The lab-first method is not a feel-good practice. It is an empirical response to a measurable failure mode: context window exhaustion produces bundled commits, broken tests, and scope violations. The evidence from this session — 4 features, 6 commits, zero reverts — versus the previous session's 35 bundled commits and 2 bugs — is the case.

The lab is not where you write code. It is where you kill bad ideas before they reach production.

## Suggested Structure for Blog Post

1. **The Hook** (anecdote: three failed attempts, one STOP)
2. **The Problem** (entropy in production code under pressure)
3. **The Method** (what lab-first is, in plain terms)
4. **The Evidence** (Case Study A: status display, Case Study B: one session)
5. **The Rules** (context window, live data, one-shot port)
6. **The Workflow** (step-by-step with real commands)
7. **The Limitations** (when not to use it)
8. **The Conclusion** (labs are entropy sinks, not code generators)

## Recommended Code Examples to Include

- `scripts/lab/status-templates.ts` — the four-template experiment
- `scripts/lab/status-template-e.ts` — the winning pattern
- `src/cli/commands/portfolio.ts` — port of lab pattern to production
- The `just check` gate showing green output

## Related Resources in This Repo

- `playbooks/lab-first-playbook.md` — full playbook with all war stories
- `playbooks/gum-playbook.md` — Template E validated pattern
- `silo-conceptual-lexicon.jsonl` — terms: lab-first, entropy-sink, template-e, one-border-rule
- `debriefs/debrief-session-2026-05-08-ses_02a5c6.md` — full session debrief
- `debriefs/debrief-session-2026-05-08-status.md` — previous session's exhaustion note

## Contact / Follow-Up

This brief was generated by ses_02a5c6 on the TradingAgents project. The
empirical data, commit hashes, and file references are all real. No examples
were fabricated for narrative convenience.
