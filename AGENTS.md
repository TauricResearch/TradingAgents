# AGENTS.md — TradingAgents Development Contract

> Repository-wide instructions for coding agents (GitHub Copilot Agent, Codex, Claude Code).
> These instructions control **how** to work. The technical requirements and acceptance criteria live in `docs/specs/TRADINGAGENTS_RELIABILITY_CONTRACT.md`.

## 1. Mission and scope

Maintain and incrementally improve the **existing** TradingAgents-based analysis and paper-trading application. Do not rebuild it from scratch or assume paths, libraries, broker integrations, model providers, or CI commands before inspecting the repository.

The reliability specification is the source of truth for the target behavior:
`docs/specs/TRADINGAGENTS_RELIABILITY_CONTRACT.md`.

Implement the specification **one phase and one reviewable feature branch at a time**. The existence of multiple tasks in that specification does not authorize a single massive commit or an all-at-once rewrite.

## 2. Mandatory inspection before work

1. Read this `AGENTS.md`, the relevant specification, `README.md`, `CHANGELOG.md` (if present), and existing project configuration.
2. Inspect the real codebase: entrypoints, trading workflow, data providers, model selection, broker adapter, test suite, application state, dashboards, deployment and CI.
3. Run the existing tests when practical and document the baseline (including failures that already existed).
4. Identify the smallest set of modules needed for the requested phase; preserve unrelated functionality.
5. If the specification conflicts with real code or earlier requirements, explain the discrepancy and choose the least disruptive solution that preserves safety.

Do not fabricate execution results, measurements, source timestamps, paths, tools, APIs or tests.

## 3. Branch policy — integration branch `custom`

- The stable integration branch for this repository is **`custom`**, **not `main`**.
- All new task branches must branch from the latest verified `origin/custom` (or an up-to-date local `custom` when safe).
- All Pull Requests must use `custom` as their **base/target branch**.
- Never use `main` as the base branch, assume it is the default branch, or change GitHub's default branch automatically.
- If `custom` is missing locally or on the remote, report the blocker; do not silently fall back to another branch.
- Treat `custom` as protected: no direct pushes, no force-push, and no autonomous merges.

## 4. Automated Git workflow

The agent should manage routine Git operations autonomously **when tooling and permissions allow it**.

1. Check `git status`, current branch, remotes and local changes.
2. If there are unrelated uncommitted changes, do **not** delete, stash, overwrite or commit them without a safe explicit plan. Report the blocker.
3. For a new feature, start from an up-to-date local `custom` tracking `origin/custom` only if the tree is clean and pulling is safe; use fast-forward-only updates. Check that the branch actually exists.
4. Create a branch automatically, named `feature/<short-scope>`, `fix/<short-scope>` or `test/<short-scope>`.
5. Implement a single coherent phase, add tests and run available validations.
6. Review diffs; commit only files related to the task with meaningful messages (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`).
7. If authenticated GitHub access is available and the user has authorized remote operations, push the feature branch and open a Pull Request **targeting `custom`**; verify the actual PR base and report its URL. Otherwise provide the exact commands to finish.
8. **Never merge or push directly to `custom`.** Never force-push, reset destructive history, delete remote branches, alter security settings, or bypass branch protection.
9. Do not auto-create releases or publish packages without explicit authorization.

If no GitHub integration or terminal permission exists, work locally to the extent available and describe the remaining manual steps. A prompt cannot grant missing permissions.

## 5. Implementation phases and branch names

Complete and integrate each phase before beginning dependent phases. Branch names are suggestions; avoid name conflicts.

| Phase | Branch | Deliverable | Main validation |
|---|---|---|---|
| 0 | `test/reliability-baseline` | Stable fixtures and baseline regression suite, including BRK-B 2026-11-08 | Repeatable tests, frozen clocks, no live orders |
| 1 | `feature/data-validation` | Provenance, shared as-of snapshot, causal event/price guard, vendor reconciliation | Invalid/outdated/conflicting data cannot silently pass |
| 2 | `feature/risk-engine` | Deterministic sizing, stops, volatility, slippage/gap checks | Missing risk budget or invalid stop blocks trading |
| 3 | `feature/execution-gate` | Final policy checks and paper-order idempotency | `WAIT/BLOCK` causes zero orders |
| 4 | `feature/portfolio-decision` | Separate strategic rating from execution action | `OVERWEIGHT` may coexist with `WAIT` |
| 5 | `feature/fact-check-debate` | Independent claim checks, bounded debate, refreshed triggers | Refuted critical claims do not become approved facts |
| 6 | `feature/reliability-observability` | Structured audit, UI/status, lineage and structured report | Every decision is explainable and reproducible |
| 7 | `test/walk-forward-validation` | Historical out-of-sample validation and monitoring | No look-ahead; honest performance results |

The specification defines the acceptance details and P0/P1/P2 severity. Dependencies may require adjusting the order; explain any change.

## 6. Safety and risk — non-negotiable

- The target is **paper trading / simulation only**. Never enable or route orders to live accounts.
- LLM generated recommendations are **proposals**, not authorization to execute.
- Every possible paper order must go through deterministic validation and an Execution Gate.
- **Fail closed** on absent timestamps, stale data, missing portfolio context, invalid schema, provider timeout, contradictory material evidence or an unresolved risk check.
- Never interpret strategic `BUY`/`OVERWEIGHT` as an immediate executable order without explicit triggers and policy approval.
- Require deterministic position sizing and risk budgets. Include gap/slippage exposure in stress tests; a stop is not a guaranteed execution price.
- Use stable idempotency keys to prevent duplicate simulated orders on retries.
- Revalidate signals and policies at execution time rather than trusting a historical report.
- Never store or print tokens, API keys, portfolio credentials or other secrets. Preserve `.gitignore` and `.env.example` hygiene.
- Avoid external market orders, account mutations or other irreversible actions. Ask explicit authorization for any real-world action not covered here.

## 7. Compatibility and code quality

- Preserve existing model provider selection, local/custom providers, data integrations, reports, dashboards and persisted history.
- Use existing project conventions, dependency management, formatter and test framework; inspect them first.
- Prefer typed validation schemas and pure, deterministic functions for critical risk/decision rules.
- Avoid unnecessary large refactors, framework replacements and new dependencies.
- Add schema migrations and backward-compatibility handling if persistence changes.
- Do not hardcode decisions or safety logic for BRK-B; BRK-B is only a regression fixture.

## 8. Tests and gates

- Before a phase: record baseline outcomes.
- During a phase: add unit tests for deterministic rules, integration tests for critical paths, and a regression fixture for known failures.
- Use mocked market/provider responses and frozen time; unit tests must not depend on live prices or LLM prose.
- P0 examples: post-event temporal consistency, Q2/Q3 mismatches, ticker-share-class errors, invalid risk stop buffer, portfolio sizing unavailable, `OVERWEIGHT` + `WAIT`, no duplicate paper orders, fail-closed on bad data.
- Verify no accidental calls to live broker endpoints.
- Run the relevant CI checks. If something cannot be executed, label it **NOT RUN** with the reason, never **PASS**.
- A phase is complete only when its relevant acceptance criteria and regression tests pass or explicit blockers are documented.

## 9. Required output at the end of each phase

1. **Branch and scope**: name and goal.
2. **Changes**: exact modules/files changed and why.
3. **Tests**: exact commands, pass/fail/not-run counts and known baseline failures.
4. **Safety**: proof that live trading remains disabled; Gate behavior where relevant.
5. **Compatibility**: migration or API impacts, if any.
6. **Version and CHANGELOG**: the `X.Y.Z` digit chosen and why, the dated release section it closed, and the entries it holds; do not list planned features as delivered.
7. **Git**: commit(s), tag `vX.Y.Z`, push status and PR URL if created.
8. **Open issues and next phase**: concise prioritized blockers.

Do not claim a Pull Request was created without a real URL or tool confirmation. Do not claim CI passed without its actual result.

## 10. Versioning, changelog and release

### 10.1 The version scheme

The version is `X.Y.Z` and every development changes it. The three digits are not decoration: they say how big the change is.

| Digit | Name | Scope of the change | Examples |
|---|---|---|---|
| `Z` | small change (PATCH) | Fixes, documentation, internal refactors, copy and styling, a UI tweak — nothing new to learn | Wrong stop price shown, a typo in a hint, a faster query |
| `Y` | medium change (MINOR) | A new capability or a compatible extension — new endpoint, new validation, new panel, a completed reliability phase | Version pill in the console, a new data-quality gate |
| `X` | large change (MAJOR) | Something a user must adapt to — removed or renamed API, changed config/env contract, changed on-disk format, changed decision vocabulary, a rewritten subsystem | Removing an endpoint, renaming a `TRADINGAGENTS_*` variable |

Choose the digit from the change itself, not from its line count: a one-line rename of a public env var is `X`, a thousand-line internal refactor that no user notices is `Z`. When a change fits two levels, take the higher one.

Nothing accumulates in `[Unreleased]` across sessions: each development closes its own dated release section, so `CHANGELOG.md` and the version always describe the same code. Do not bump a digit without saying which one and why in the commit body.

### 10.2 Keeping the version and the release in step

The version has one source, `tradingagents.__version__` (read by the build through `dynamic` in `pyproject.toml`), and every consumer follows it. A version change touches **all** of these in the same commit or Pull Request:

1. **`tradingagents/__init__.py`**: `__version__` — the only place the number is written. Never add a second literal elsewhere.
2. **`CHANGELOG.md`**: the new dated section (`## [X.Y.Z] — YYYY-MM-DD`) holding the entries this change delivers, with a fresh empty `[Unreleased]` left above it for the next one.
3. **The webapp**: nothing to edit — the page header pill and the `/api/health` / `/api/options` `version` field read `__version__`, so they show the new value as soon as the file changes. Verify they do.
4. **Git**: commit `release: X.Y.Z` (or include the bump in the feature commit with `feat:`/`fix:` and name the version in the body), then an annotated tag `vX.Y.Z`. The tag is local until the user authorizes the push; never invent or move a published tag.

`run_settings()["version"]` writes the same value into every saved report and state log, so a report can always be traced to the code that produced it.

### 10.3 Changelog rules

- Maintain the repository-root `CHANGELOG.md` using the **Keep a Changelog** categories (`Added`, `Changed`, `Fixed`, `Security`, etc.).
- Document only behaviour actually implemented in that change, not the roadmap or merely requested work.
- If a PR is not merged, its changelog entry remains part of that branch; `custom` must describe only merged changes.
- Preserve existing history: never rewrite, renumber or re-date a section that has already shipped.
- Prefer concise, user-impacting entries and link to PRs/issues when known; never invent PR identifiers, links or release dates.
- Do not create or advance a published version, tag or release without explicit authorization.

## 11. Recommended starting task

Begin with **Phase 0**, not all phases together. Inspect the existing repository, record baseline behavior, add reproducible test fixtures for the BRK-B report of 2026-11-08 and related temporal/risk errors, and prepare the `test/reliability-baseline` branch for review. Do **not** modify trading behavior in the baseline phase unless necessary to make tests reproducible and explicitly scoped.
