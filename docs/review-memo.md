# Review memos

### CHG-001 — src layout alignment
- Operator: JHB11Hinson
- Requirement: D1-REQ-GOV-001
- What changed: `tradingagents/` -> `src/tradingagents/`, `cli/` -> `src/cli/`, `tests/` ->
  `test/offline/`, new `test/live/`; pyproject declares the src layout, the build floor and
  `testpaths`; three inherited tests had their repository-root lookup updated (no assertions
  changed)
- Why: the brief (section 5 / D8) requires `src/` and a split offline/live test layout
- Covered by: the full inherited suite (`pytest -q`: 1262 passed, 1 skipped, 1 deselected,
  9.55 s) + `import tradingagents, cli.main` + a wheel containing both in-package resources
- Records: ADR-001, ADR-002, change card in PR #<n>
- Rollback: `git revert <squash sha>`
