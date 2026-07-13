"""Emergency flatten (go-live Phase 4).

The single sanctioned write path from an operator to execution besides
the ordinary gated pipeline: cancel every resting order, close every open
position at market (reduce-only), and disarm all pairs. Shared by the CLI
(`tradingagents-pro flatten`) and the authenticated dashboard control
(`POST /api/flatten`), so both do exactly the same audited thing.

Rationale (documented in DASHBOARD.md): in live trading the ABSENCE of a
one-press stop is more dangerous than its presence. This is the only
dashboard→execution write; everything else stays read-only.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def emergency_flatten(router, arming=None, *, operator: str,
                      reference_prices: dict[str, float] | None = None,
                      alerts=None) -> dict:
    """Cancel-all + flatten-all + disarm. Returns a summary of what it did.

    Works whether or not an OMS is wired: with an OMS it cancels resting
    orders and places reduce-only market closes through the journaled
    path; without one it falls back to the router adapter's
    ``close_position``. Idempotent enough to run twice safely — a second
    call on a flat book cancels nothing and closes nothing."""
    reference_prices = reference_prices or {}
    summary: dict = {"operator": operator, "cancelled": [], "flattened": [],
                     "errors": []}
    oms = getattr(router, "oms", None)
    adapter = router.adapter

    if oms is not None:
        for order in list(oms.orders.values()):
            if order.sent and not order.state.terminal:
                try:
                    oms._apply(order, adapter.cancel_order(order.client_order_id))
                    summary["cancelled"].append(order.client_order_id)
                except Exception as exc:
                    logger.exception("flatten: cancel failed")
                    summary["errors"].append(f"cancel {order.client_order_id}: {exc}")

    for position in adapter.positions():
        ref = reference_prices.get(position.symbol, position.avg_price)
        try:
            if oms is not None:
                oms.flatten_position(
                    symbol=position.symbol, quantity=position.quantity,
                    side=position.side, reference_price=ref,
                    reason=f"emergency_flatten:{operator}")
            else:
                adapter.close_position(position.symbol, ref)
            summary["flattened"].append(position.symbol)
        except Exception as exc:
            logger.exception("flatten: close failed for %s", position.symbol)
            summary["errors"].append(f"close {position.symbol}: {exc}")

    router.kill_switch.engage(f"emergency flatten by {operator}")
    router.audit.append("emergency_flatten", summary)
    if arming is not None:
        arming.disarm_all(f"emergency flatten by {operator}", operator=operator)
    if alerts is not None:
        alerts.emit("critical", "emergency_flatten",
                    f"emergency flatten executed by {operator}: "
                    f"{len(summary['flattened'])} position(s) closed")
    return summary
