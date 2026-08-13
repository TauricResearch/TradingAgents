# Residual idempotency fix report

## Scope

- Match unresolved order intents by symbol, side, delta notional, and target notional.
- Atomically retire historical unresolved rows only when a reused client ID resolves successfully.
- Keep ambiguous submission failures unresolved for restart reuse.
- Ignore unmanaged open orders before validating quantity and fill fields.

## RED evidence

Command:

```text
.venv/bin/pytest -q tests/test_automation_cycle.py::test_resolved_reused_id_retires_historical_error tests/test_automation_cycle.py::test_ambiguous_reused_id_remains_reusable tests/test_automation_cycle.py::test_later_rebalance_with_different_delta_gets_fresh_id tests/test_alpaca_execution.py::test_open_order_exposure_ignores_malformed_order_outside_priced_universe
```

Result: 3 failed, 1 passed. The intended failures were historical status remaining `error`, a different-delta rebalance reusing the old client ID, and a malformed unmanaged order raising before filtering.

## GREEN evidence

Focused regression command included the existing restart-reuse test. Result: 5 passed.

Affected feature suite:

```text
.venv/bin/pytest -q tests/test_automation_cycle.py tests/test_automation_state.py tests/test_alpaca_execution.py tests/test_allocation.py
```

Result after final production edit: 96 passed.

Full suite:

```text
.venv/bin/pytest -q
```

Result: 711 passed, 2 skipped, 18 warnings, 69 subtests passed in 117.87s. Skips were missing optional `langchain_aws` and an unset live `DEEPSEEK_API_KEY`; warnings were existing unknown-model warnings.

Quality gates: Ruff check passed; Ruff format check passed for all five changed Python files; `git diff --check` passed.

## Files

- `tradingagents/automation_state.py`
- `tradingagents/automation.py`
- `tradingagents/execution.py`
- `tests/test_automation_cycle.py`
- `tests/test_alpaca_execution.py`

## Safety self-review

- ID-before-submit persistence is unchanged.
- `AlpacaBroker.submit_idempotent` remains unchanged: one pre-submit lookup, one post-submit lookup only after a submit exception, and no blind resubmit.
- Different delta notionals cannot reuse a historical ID even when symbol, side, and target are identical.
- Successful broker resolution and historical retirement share one SQLite transaction with the current submitted-state update.
- Ambiguous exceptions leave the historical and current rows unresolved; no current intent is marked submitted without a broker-returned order ID.
- No schema migration, network call, real broker order, or new dependency was added.

## Commit

Recorded in Git commit for this report and the five changed Python files.
