# Cash and Leverage Policy Integration Report

## Scope

- Raised the signed-conviction gross cash allocation ceiling from 30% to 90%.
- Added the environment-backed `$70,000` best-effort maximum cash-reserve target.
- Scaled only positive convictions toward the reserve, preserving shorts and never inventing longs for Hold/short-only decisions.
- Kept volatility and gross-risk scaling after reserve sizing, with broker buying power enforced before submission.
- Required whole-share quantities for opening equity shorts, including fractionable assets.
- Documented that leverage and negative cash are permitted, while the 15% target volatility, 20% ceiling, 2x gross ceiling, and buying power take precedence.

## TDD and Review Evidence

- RED: the new numeric-validation and composed-policy tests initially produced 11 failures (invalid cash/equity/reserve handling, non-finite configuration, and the then-unset reserve default).
- GREEN: `.venv/bin/pytest -q tests/test_allocation.py tests/test_automation_config.py tests/test_env_overrides.py tests/test_alpaca_execution.py` passed with 205 tests.
- Integrated after the coordinator commits: `.venv/bin/pytest -q tests/test_allocation.py tests/test_risk.py tests/test_automation_config.py tests/test_env_overrides.py tests/test_alpaca_execution.py tests/test_automation_cycle.py` passed with 306 tests; warnings were limited to pytest temporary-directory cleanup.
- Staged-only: the same 306-test integrated suite passed from a temporary archive of `git write-tree`, proving the cached tree independently of unrelated unstaged files.
- Full: `.venv/bin/pytest -q` passed with 1,025 tests and 69 subtests; one optional `langchain_aws` test was skipped and the run emitted known model/temporary-directory warnings.

## Isolation

The commit was patch-staged to exclude unrelated Alpaca market-data, Yahoo fallback, date-boundary, and other concurrent worktree changes.
