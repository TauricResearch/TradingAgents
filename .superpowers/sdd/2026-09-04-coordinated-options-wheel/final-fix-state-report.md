# Final Fix: Durable Automation State

## Outcome

- Equity and option unresolved-intent lookup now includes both `pending` and
  `error`, excludes `planned` and `submitted`, and survives database reopen.
- A lookup with no durable client ID or with conflicting durable IDs is explicit
  state-boundary ambiguity. A single durable ID remains available for broker
  reconciliation even when a newer matching pending row has not yet stored it.
- Equity status updates preserve an existing client ID when the caller omits the
  optional ID. Successful equity and option reuse retires older matching
  `pending`/`error` rows.
- Wheel reservations are stored atomically as a snapshot header and normalized
  per-underlying rows. This preserves exact decimal strings, the cycle ID, and
  the aware capture timestamp. An empty recorded snapshot is distinct from no
  snapshot. Invalid, non-finite, and negative amounts are rejected before any
  snapshot is written.

## Public API

```python
@dataclass(frozen=True)
class UnresolvedOrderLookup:
    client_order_id: str | None
    ambiguous: bool

@dataclass(frozen=True)
class WheelReservationSnapshot:
    cycle_id: str
    captured_at: datetime
    put_collateral: Mapping[str, Decimal]
    covered_shares: Mapping[str, Decimal]

AutomationState.lookup_unresolved_order_intent(
    intent: OrderIntent,
) -> UnresolvedOrderLookup | None

AutomationState.lookup_unresolved_option_intent(
    contract_symbol: str,
    position_intent: str,
    quantity: Decimal,
    limit_price: Decimal,
) -> UnresolvedOrderLookup | None

AutomationState.unresolved_client_order_id(
    intent: OrderIntent,
) -> str | None

AutomationState.unresolved_option_client_order_id(
    contract_symbol: str,
    position_intent: str,
    quantity: Decimal,
    limit_price: Decimal,
) -> str | None

AutomationState.record_wheel_reservations(
    cycle_id: str,
    captured_at: datetime,
    put_collateral: Mapping[str, Decimal],
    covered_shares: Mapping[str, Decimal],
) -> None

AutomationState.latest_wheel_reservations(
) -> WheelReservationSnapshot | None
```

The legacy `unresolved_*_client_order_id` helpers return the unique reconcilable
ID and otherwise return `None`. Coordinators that must distinguish absence from
ambiguity should use the new `lookup_unresolved_*` methods: `None` means no
unresolved state; a result with `ambiguous=True` must block; and a result with
`ambiguous=False` provides the one client ID to reconcile.

## TDD and Verification Evidence

- RED: focused state tests produced 9 expected missing-API failures while 25
  pre-existing tests passed.
- GREEN: `.venv/bin/python -m pytest -q tests/test_automation_state.py` produced
  35 passes.
- Compatibility: `.venv/bin/python -m pytest -q tests/test_automation_cycle.py
  tests/test_automation_state.py` produced 84 passes. Pytest also emitted six
  unrelated temporary-directory cleanup warnings.
- Static: `.venv/bin/ruff check tradingagents/automation_state.py
  tests/test_automation_state.py` reported `All checks passed!`.
- Compile: `.venv/bin/python -m compileall -q tradingagents/automation_state.py
  tests/test_automation_state.py` exited successfully.
- Whitespace: `git diff --check -- tradingagents/automation_state.py
  tests/test_automation_state.py` exited successfully.
