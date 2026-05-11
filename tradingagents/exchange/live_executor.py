"""Live execution scaffold for Polymarket CLOB orders.

THIS MODULE IS DELIBERATELY SAFETY-GATED. It does NOT place real orders
unless ALL of the following conditions are true at the call site:

  1. `confirm_real_money=True` is passed explicitly.
  2. `POLYMARKET_LIVE=1` is set in the environment.
  3. `POLYMARKET_PRIVATE_KEY` is set in the environment.
  4. `py-clob-client` is installed (it is NOT in pyproject.toml by default).

If ANY gate fails, place_order returns a `LIVE_DISABLED` response with the
reason. The point of this module is to make the path to real execution
exist as code (so it can be reviewed and tested) while making activation
require deliberate human action across multiple surfaces.

Phase B work that still needs to happen before real execution is sane:
  - Install py-clob-client and add to pyproject deps
  - Wallet management (key storage, USDC balance check, gas)
  - Polymarket account creation flow (sign-in tx)
  - Slippage caps and order-book sanity checks before submission
  - Regulatory review for the operator's jurisdiction (US users blocked)

Until those exist, all callers should use `tradingagents.exchange.paper_fill`.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from tradingagents.agents.schemas import PolymarketDecision, PolymarketDirection
from tradingagents.exchange.binary_risk import size_order as _kelly_size

logger = logging.getLogger(__name__)


class LiveExecutionDisabled(Exception):
    """Raised when a caller attempts a live order with safety gates engaged.

    This is intentional. To execute, the caller must opt in across multiple
    surfaces (see module docstring).
    """


def _check_safety_gates(confirm_real_money: bool) -> str | None:
    """Return None if all gates pass; otherwise return the failure reason."""
    if not confirm_real_money:
        return "confirm_real_money flag not set"
    if os.environ.get("POLYMARKET_LIVE") != "1":
        return "POLYMARKET_LIVE env var not set to '1'"
    if not os.environ.get("POLYMARKET_PRIVATE_KEY"):
        return "POLYMARKET_PRIVATE_KEY env var not set"
    try:
        import py_clob_client  # noqa: F401
    except ImportError:
        return "py-clob-client not installed (pip install py-clob-client)"
    return None


def place_order(
    decision: PolymarketDecision,
    capital_usd: float,
    yes_token_id: str | None,
    no_token_id: str | None,
    confirm_real_money: bool = False,
) -> dict[str, Any]:
    """Attempt to place a real Polymarket order corresponding to `decision`.

    By default, this function does NOT submit anything. It returns a
    `LIVE_DISABLED` response describing which safety gate blocked it.

    Args:
        decision: PolymarketDecision from the research engine.
        capital_usd: total available USDC capital; Kelly sizing determines
            the fraction to bet (capped at 20%, half-Kelly by default).
        yes_token_id: Polymarket CLOB token id for YES side.
        no_token_id: Polymarket CLOB token id for NO side.
        confirm_real_money: explicit opt-in. Must be True even with env vars set.

    Returns dict with:
        status: 'LIVE_DISABLED' | 'LIVE_SKIPPED' | 'LIVE_PLACED'
        reason: explanation if disabled or skipped
        order_id: Polymarket order id if placed (otherwise None)
        decision: echo of the input decision
        sizing: Kelly sizing breakdown (fraction, usd, reason) if computed
    """
    if decision.direction == PolymarketDirection.HOLD:
        return {
            "status": "LIVE_SKIPPED",
            "reason": "decision is HOLD; no order to place",
            "order_id": None,
            "decision": decision.model_dump(mode="json"),
            "sizing": None,
        }

    # Kelly sizing — computed before safety gates so the caller can inspect
    # the sizing even in LIVE_DISABLED mode (useful for paper-trade logging).
    try:
        sizing = _kelly_size(decision, capital_usd)
    except ValueError as e:
        return {
            "status": "LIVE_DISABLED",
            "reason": f"Kelly sizing error: {e}",
            "order_id": None,
            "decision": decision.model_dump(mode="json"),
            "sizing": None,
        }
    if sizing["fraction"] == 0.0:
        return {
            "status": "LIVE_SKIPPED",
            "reason": f"Kelly sizing: {sizing['reason']}",
            "order_id": None,
            "decision": decision.model_dump(mode="json"),
            "sizing": sizing,
        }

    gate_reason = _check_safety_gates(confirm_real_money)
    if gate_reason is not None:
        logger.warning("Live execution blocked: %s", gate_reason)
        return {
            "status": "LIVE_DISABLED",
            "reason": gate_reason,
            "order_id": None,
            "decision": decision.model_dump(mode="json"),
            "sizing": sizing,
        }

    token_id = (
        yes_token_id if decision.direction == PolymarketDirection.BUY_YES else no_token_id
    )
    if not token_id:
        return {
            "status": "LIVE_DISABLED",
            "reason": f"no token_id for direction {decision.direction.value}",
            "order_id": None,
            "decision": decision.model_dump(mode="json"),
            "sizing": sizing,
        }

    # Remaining Phase B work before this stub can be removed:
    #   - Install py-clob-client and add to pyproject deps
    #   - Wallet management (key storage, USDC balance check)
    #   - Polymarket account creation flow (sign-in tx)
    #   - Slippage caps and order-book sanity checks before submission
    #   - Regulatory review for the operator's jurisdiction (US users blocked)
    raise LiveExecutionDisabled(
        f"All safety gates passed and Kelly sizing computed "
        f"({sizing['fraction']:.1%} of capital = ${sizing['usd']:.2f}) "
        f"but real order placement is not implemented. "
        f"Wire py_clob_client.create_order + post_order here once wallet "
        f"infrastructure and regulatory review are complete. See TODOS.md."
    )
