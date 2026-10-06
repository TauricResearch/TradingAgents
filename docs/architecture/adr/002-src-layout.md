# ADR-002: Adopt the src layout for D8 compliance

- Status: accepted
- Date: 2026-10-06
- Deciders: the four team members
- Related: ADR-001, CHG-001, D1-REQ-GOV-001

## Context

The brief (section 5 / D8) requires `src/` to hold the full application source and `test/` to
separate deterministic offline tests from API-dependent live tests. The inherited layout is
`tradingagents/`, `cli/`, `tests/`. The build backend is setuptools, whose `packages.find`
scans the repository root unless told otherwise, and `pytest` is configured with
`testpaths = ["tests"]`.

## Decision

Move the inherited packages to `src/tradingagents/` and `src/cli/`, and the inherited suite to
`test/offline/` with API-dependent cases split into `test/live/`. Declare the src layout in
`pyproject.toml` (add `where = ["src"]`, raise the build floor to `setuptools>=64`) and repoint
`testpaths`. No logic, assertion or public interface changes; the only source-tree edits are the
path resolution in three inherited tests (`test_version.py`, `test_layering.py`,
`test_i18n_coverage.py`), which locate the repository root with `parents[1]` and now need
`parents[2]` (one of them also needs the extra `src` segment).

## Consequences

- Complies with D8; new code goes to `src/`, new tests to `test/`.
- One large structural commit; `git blame` paths shift once.
- Three inherited test files had their path resolution updated (no assertions changed).
- The build must still ship the two in-package resources (`cli/static/welcome.txt`,
  `tradingagents/assets/tauric-logo.svg`); verified by building a wheel and listing it.

## Reconsider if

- the course explicitly accepts a mapping table instead of a physical move;
- the inherited suite cannot be split cleanly into offline/live.
