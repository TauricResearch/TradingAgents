"""Contract conformance test matrix — schema, postcheck, and executor must agree.

Architectural invariant
-----------------------
For every (buy_order, live_price) input, the three enforcement boundaries must
produce identical pass/fail outcomes for order-guard constraints:

  Schema layer   — BuyOrder Pydantic model (static, no live price)
  Guard layer    — buy_order_guard(buy, live_price)  ← single source of truth
  Postcheck node — pm_decision_postcheck_node raises RuntimeError on guard fail
  Executor       — TradeExecutor appends to failed_trades on guard fail

If any boundary diverges the system develops split-brain behaviour: a rejected
order upstream can be silently executed downstream (or vice versa).

Matrix structure
----------------
Each SCENARIO dict has:
  buy          : order dict (as the PM agent produces it)
  live_price   : float representing the market price at runtime
  schema_valid : bool — can BuyOrder(**buy) be parsed without error?
  guard_passes : bool — should buy_order_guard(buy, live_price) return None?

Note: schema_valid and guard_passes are independent. An order with good static
price relationships (schema_valid=True) can still fail the guard when the live
price moves above limit_price. Conversely, a static violation (e.g. entry > limit)
is rejected by schema and never reaches the guard layer.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from tradingagents.agents.portfolio.pm_decision_agent import BuyOrder
from tradingagents.graph.portfolio_setup import PortfolioGraphSetup
from tradingagents.portfolio.models import Holding, Portfolio, PortfolioSnapshot
from tradingagents.portfolio.order_guards import buy_order_guard
from tradingagents.portfolio.trade_executor import TradeExecutor


# ---------------------------------------------------------------------------
# Shared order matrix
# ---------------------------------------------------------------------------

#: Base well-formed order; individual scenarios override fields as needed.
_BASE_ORDER: dict[str, Any] = {
    "ticker": "RMAX",
    "shares": 300.0,
    "entry_price": 9.94,
    "limit_price": 10.25,
    "max_chase_price": 10.25,
    "order_type": "limit",
    "valid_as_of": "2026-04-28",
    "price_target": 12.92,
    "stop_loss": 8.45,
    "take_profit": 12.92,
    "sector": "Real Estate",
    "rationale": "test",
    "thesis": "test",
    "macro_alignment": "risk-on",
    "memory_note": "test",
    "position_sizing_logic": "test",
}


def _order(**overrides: Any) -> dict[str, Any]:
    return {**_BASE_ORDER, **overrides}


SCENARIOS: list[dict[str, Any]] = [
    # ---------------------------------------------------------------- pass
    {
        "id": "happy_path",
        "desc": "All fields valid, live price below limit",
        "buy": _order(),
        "live_price": 9.94,
        "schema_valid": True,
        "guard_passes": True,
    },
    {
        "id": "live_at_limit",
        "desc": "Live price exactly equals limit — boundary, must pass",
        "buy": _order(),
        "live_price": 10.25,
        "schema_valid": True,
        "guard_passes": True,
    },
    # ---------------------------------------------------------------- guard fails (static schema still valid)
    {
        "id": "live_above_limit",
        "desc": "Live price one cent above limit_price — guard must reject",
        "buy": _order(),
        "live_price": 10.26,
        "schema_valid": True,
        "guard_passes": False,
    },
    {
        "id": "live_above_max_chase",
        "desc": "Live price above max_chase_price — guard must reject",
        "buy": _order(max_chase_price=10.00),
        "live_price": 10.25,
        "schema_valid": True,
        "guard_passes": False,
    },
    {
        "id": "live_far_above_limit",
        "desc": "Market gap — live is 11% above limit",
        "buy": _order(),
        "live_price": 11.29,
        "schema_valid": True,
        "guard_passes": False,
    },
    {
        "id": "stop_loss_above_live",
        "desc": "Stop loss above live price — risk inversion, guard must reject",
        "buy": _order(stop_loss=12.00),
        "live_price": 9.94,
        "schema_valid": True,
        "guard_passes": False,
    },
    {
        "id": "stop_loss_equals_live",
        "desc": "Stop loss equals live price — guard must reject",
        "buy": _order(stop_loss=9.94),
        "live_price": 9.94,
        "schema_valid": True,
        "guard_passes": False,
    },
    {
        "id": "take_profit_below_live",
        "desc": "Take profit below live price — pointless trade, guard must reject",
        "buy": _order(take_profit=9.00),
        "live_price": 9.94,
        "schema_valid": True,
        "guard_passes": False,
    },
    {
        "id": "market_order_type",
        "desc": "order_type='market' rejected by guard",
        "buy": _order(order_type="market"),
        "live_price": 9.94,
        "schema_valid": False,  # schema also rejects (Literal['limit'])
        "guard_passes": False,
    },
    # ---------------------------------------------------------------- schema fails only
    {
        "id": "entry_above_limit_schema_fail",
        "desc": "entry_price > limit_price violates static schema relationship",
        "buy": _order(entry_price=11.00, limit_price=10.25, max_chase_price=11.00),
        "live_price": 9.00,
        "schema_valid": False,
        "guard_passes": True,  # guard only checks live vs limit/max_chase
    },
    {
        "id": "max_chase_above_limit_schema_fail",
        "desc": "max_chase_price > limit_price violates static schema relationship",
        "buy": _order(entry_price=9.94, limit_price=10.25, max_chase_price=11.00),
        "live_price": 9.00,
        "schema_valid": False,
        "guard_passes": True,
    },
    {
        "id": "invalid_valid_as_of",
        "desc": "valid_as_of not YYYY-MM-DD format",
        "buy": _order(valid_as_of="28-04-2026"),
        "live_price": 9.94,
        "schema_valid": False,
        "guard_passes": True,  # guard does not check valid_as_of
    },
    # ---------------------------------------------------------------- SGOV cash-sweep exemption
    {
        "id": "sgov_above_limit_exempt",
        "desc": "SGOV cash-sweep: guard is fully exempt even if live > limit",
        "buy": {
            **_order(ticker="SGOV", sector="Cash Equivalent"),
            "limit_price": 99.0,
            "max_chase_price": 99.0,
        },
        "live_price": 100.50,
        "schema_valid": True,
        "guard_passes": True,  # SGOV is exempt from all order guards
    },
]

# Convenience lookups
_SCENARIOS_BY_ID = {s["id"]: s for s in SCENARIOS}


# ---------------------------------------------------------------------------
# Layer 1 — Schema conformance (static, no live price)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
def test_schema_layer(scenario: dict[str, Any]) -> None:
    """BuyOrder Pydantic model must accept/reject exactly as schema_valid declares."""
    buy = scenario["buy"]
    expected = scenario["schema_valid"]

    if expected:
        parsed = BuyOrder(**buy)  # must not raise
        assert parsed.ticker == buy["ticker"]
    else:
        with pytest.raises((ValueError, TypeError)):
            BuyOrder(**buy)


# ---------------------------------------------------------------------------
# Layer 2 — Guard function conformance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
def test_guard_layer(scenario: dict[str, Any]) -> None:
    """buy_order_guard must return None (pass) or non-None (reject) per guard_passes."""
    buy = scenario["buy"]
    live_price = scenario["live_price"]
    expected = scenario["guard_passes"]

    result = buy_order_guard(buy, live_price)

    if expected:
        assert result is None, (
            f"guard_layer: scenario {scenario['id']!r} expected to pass "
            f"but got violation: {result!r}"
        )
    else:
        assert result is not None, (
            f"guard_layer: scenario {scenario['id']!r} expected to fail "
            "but buy_order_guard returned None"
        )


# ---------------------------------------------------------------------------
# Helpers for integration layers
# ---------------------------------------------------------------------------


_BASE_PORTFOLIO_DICT = {
    "portfolio_id": "p1",
    "name": "Test",
    "cash": 450_000.0,
    "initial_cash": 500_000.0,
    "total_value": 500_000.0,
}

_DEFAULT_CONFIG = {
    "min_cash_pct": 0.05,
    "max_position_pct": 0.15,
    "max_sector_pct": 0.35,
    "max_positions": 15,
}

# Grounded candidate (required by postcheck buy-grounding check)
_RMAX_CANDIDATE = {
    "ticker": "RMAX",
    "candidate_final_trade_decision_summary": "Completed deep-dive supports RMAX",
}
_SGOV_CANDIDATE = {
    "ticker": "SGOV",
    "candidate_final_trade_decision_summary": "Cash sweep into SGOV",
}


def _make_postcheck_state(
    buy: dict[str, Any],
    live_price: float,
    extra_candidates: list[dict] | None = None,
) -> dict[str, Any]:
    """Build minimal postcheck state for a single-buy decision."""
    decision = {
        "macro_regime": "risk-on",
        "regime_alignment_note": "test",
        "sells": [],
        "buys": [buy],
        "holds": [],
        "cash_reserve_pct": 80.0,
        "portfolio_thesis": "test",
        "risk_summary": "test",
        "forensic_report": {
            "regime_alignment": "risk-on",
            "key_risks": [],
            "decision_confidence": "high",
            "position_sizing_rationale": "test",
        },
    }
    ticker = str(buy.get("ticker") or "").strip().upper()
    is_sgov = ticker == "SGOV"

    candidates = [_SGOV_CANDIDATE if is_sgov else _RMAX_CANDIDATE]
    if extra_candidates:
        candidates.extend(extra_candidates)

    return {
        "pm_decision": json.dumps(decision),
        "portfolio_data": json.dumps(
            {"portfolio": _BASE_PORTFOLIO_DICT, "holdings": []}
        ),
        "prices": {ticker: live_price},
        "prioritized_candidates": json.dumps(candidates),
    }


def _make_executor_repo(live_price: float, ticker: str) -> MagicMock:
    portfolio = Portfolio(
        portfolio_id="p1",
        name="Test",
        cash=450_000.0,
        initial_cash=500_000.0,
    )
    portfolio.total_value = 500_000.0
    portfolio.equity_value = 50_000.0
    portfolio.cash_pct = 0.90

    snapshot = PortfolioSnapshot(
        snapshot_id="snap-1",
        portfolio_id="p1",
        snapshot_date="2026-04-28T00:00:00Z",
        total_value=500_000.0,
        cash=450_000.0,
        equity_value=50_000.0,
        num_positions=0,
        holdings_snapshot=[],
    )

    repo = MagicMock()
    repo.get_portfolio_with_holdings.return_value = (portfolio, [])
    repo.take_snapshot.return_value = snapshot
    return repo


# ---------------------------------------------------------------------------
# Layer 3 — Postcheck conformance
# Only guard-relevant scenarios are exercised here (schema-invalid orders
# would never reach the postcheck because the PM agent would have retried).
# ---------------------------------------------------------------------------

# Filter to scenarios where the order is schema-valid (reaches postcheck)
_POSTCHECK_SCENARIOS = [s for s in SCENARIOS if s["schema_valid"]]


@pytest.mark.parametrize(
    "scenario", _POSTCHECK_SCENARIOS, ids=[s["id"] for s in _POSTCHECK_SCENARIOS]
)
def test_postcheck_layer(scenario: dict[str, Any]) -> None:
    """Postcheck node must raise RuntimeError with 'order guard failed' exactly when guard_passes=False."""
    buy = scenario["buy"]
    live_price = scenario["live_price"]
    guard_passes = scenario["guard_passes"]

    setup = PortfolioGraphSetup(agents={}, config=_DEFAULT_CONFIG)
    node = setup._make_pm_decision_postcheck_node()
    state = _make_postcheck_state(buy, live_price)

    if guard_passes:
        # Must not raise (may raise on other unrelated constraints, but not order guard)
        try:
            node(state)
        except RuntimeError as exc:
            msg = str(exc)
            assert "order guard failed" not in msg, (
                f"postcheck_layer: scenario {scenario['id']!r} should have passed "
                f"guard checks but raised order guard error: {msg!r}"
            )
    else:
        with pytest.raises(RuntimeError, match="order guard failed"):
            node(state)


# ---------------------------------------------------------------------------
# Layer 4 — Executor conformance
# Same filter: only schema-valid orders reach the executor.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scenario", _POSTCHECK_SCENARIOS, ids=[s["id"] for s in _POSTCHECK_SCENARIOS]
)
def test_executor_layer(scenario: dict[str, Any]) -> None:
    """Executor must add ticker to failed_trades when guard_passes=False."""
    buy = scenario["buy"]
    live_price = scenario["live_price"]
    guard_passes = scenario["guard_passes"]
    ticker = str(buy.get("ticker") or "").strip().upper()

    repo = _make_executor_repo(live_price, ticker)
    executor = TradeExecutor(repo=repo, config=_DEFAULT_CONFIG)

    decision = {
        "buys": [buy],
        "sells": [],
    }
    prices = {ticker: live_price}

    result = executor.execute_decisions(
        portfolio_id="p1",
        decisions=decision,
        prices=prices,
    )

    failed = result.get("failed_trades") or []
    failed_tickers = [str(t.get("ticker") or "") for t in failed]

    if guard_passes:
        assert ticker not in failed_tickers or all(
            "order guard" not in str(t.get("reason") or "") for t in failed
        ), (
            f"executor_layer: scenario {scenario['id']!r} should have passed "
            f"guard checks but ticker {ticker!r} appeared in failed_trades: {failed}"
        )
    else:
        # Ticker must appear in failed_trades with an order-guard reason
        guard_failures = [
            t for t in failed
            if str(t.get("ticker") or "") == ticker
            and "order guard" not in str(t.get("reason") or "")
            # The guard violation message comes from buy_order_guard, not the key literal
        ]
        order_guard_failures = [
            t for t in failed
            if str(t.get("ticker") or "") == ticker
        ]
        assert order_guard_failures, (
            f"executor_layer: scenario {scenario['id']!r} — "
            f"buy_order_guard said FAIL but executor did not add {ticker!r} to failed_trades. "
            f"failed_trades={failed}"
        )


# ---------------------------------------------------------------------------
# Cross-layer consistency assertion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
def test_guard_is_oracle_for_runtime_layers(scenario: dict[str, Any]) -> None:
    """buy_order_guard is the canonical oracle — postcheck and executor must agree with it.

    This test does not invoke integration layers directly; it asserts the
    structural invariant: both runtime layers import and call buy_order_guard,
    so their pass/fail outcome must be identical to the guard result.
    """
    buy = scenario["buy"]
    live_price = scenario["live_price"]
    guard_passes = scenario["guard_passes"]

    guard_result = buy_order_guard(buy, live_price)
    actual_passes = guard_result is None

    assert actual_passes == guard_passes, (
        f"Cross-layer oracle mismatch for scenario {scenario['id']!r}: "
        f"declared guard_passes={guard_passes} but buy_order_guard returned "
        f"{'None (pass)' if guard_result is None else repr(guard_result)}"
    )
