# Final Fix: Alpaca Execution Boundary

## Outcome

- `AlpacaBroker.account()` now accepts finite negative cash. This preserves the
  approved margin/leverage behavior while retaining positive-equity and
  nonnegative buying-power validation. Cash still passes through
  `_required_decimal()`, so missing, malformed, `NaN`, and infinite values fail
  closed. Cash-secured-put collateral and sufficiency policy remain unchanged
  outside the adapter.
- Every actual option `submit_order` and `cancel_order_by_id` call is now
  immediately preceded by an authoritative client endpoint assertion. Paper
  mode accepts only `https://paper-api.alpaca.markets`; live mode accepts only
  `https://api.alpaca.markets`. Missing, custom, and mismatched endpoints raise
  the sanitized `RuntimeError("Alpaca trading endpoint cannot be verified")`
  before mutation.
- Existing live-order and live-options acknowledgements remain required before
  live option mutation. Existing paper fakes that reach mutation now declare
  their SDK `_base_url` explicitly. The non-owned cancellation fixture leaves
  the endpoint unknown, preserving proof that strategy ownership is rejected
  before endpoint inspection.

## API and Compatibility

No public API or dataclass shape changed. The implementation adds one private
adapter assertion:

```python
AlpacaBroker._assert_trading_endpoint_matches_mode() -> None
```

The assertion reads Alpaca-py's `RESTClient._base_url`, which the installed
`TradingClient` initializes from `BaseURL.TRADING_PAPER` or
`BaseURL.TRADING_LIVE`. It does not perform a network request.

## Commits

- `a35af7e` — implementation, account regression, endpoint match/mismatch/
  unknown regressions, and explicit mutation-capable fake endpoints.
- `08159ab` — isolated test refinement preserving ownership validation before
  endpoint inspection.

The pre-existing fractional-short implementation and test hunks remain
unstaged and are not contained in either commit.

## TDD and Verification Evidence

- RED: `.venv/bin/python -m pytest -q tests/test_alpaca_execution.py -k
  'negative_cash or authoritative_endpoint or unverified_endpoint'` produced
  five expected failures and two passes. The failures showed negative cash was
  rejected and mismatched/unknown endpoints reached mutation or ambiguous
  submission handling.
- GREEN regression slice: the same command produced 7 passes.
- Focused suite after implementation: `.venv/bin/python -m pytest -q
  tests/test_alpaca_execution.py` produced 118 passes in the shared working
  tree.
- Clean execution-commit checkout: detached `a35af7e` produced 117 focused
  passes (the one additional shared-tree test is the preserved pre-existing
  fractional-short regression), followed by Ruff success and successful
  `compileall`.
- Static checks: `.venv/bin/ruff check tradingagents/execution.py
  tests/test_alpaca_execution.py` reported `All checks passed!`;
  `.venv/bin/python -m compileall -q tradingagents/execution.py
  tests/test_alpaca_execution.py` and `git diff --check` exited successfully.
- No network, broker, submission, or cancellation endpoint was contacted; all
  mutation tests use local fakes and assert mutation call counts.

No `AGENTS.md` exists in the repository or its enclosing task directory; the
repository options safety design and Task 4 execution brief were used as the
authoritative local instructions.
