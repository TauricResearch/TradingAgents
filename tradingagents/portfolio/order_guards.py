"""Shared executable buy-order guards.

Single source of truth for order-level constraints enforced at every
runtime boundary: postcheck projection, and trade execution.

Rules enforced
--------------
1. live_price must be present and positive for every non-SGOV buy.
2. live_price must not exceed limit_price when set.
3. live_price must not exceed max_chase_price when set.
4. stop_loss must be strictly below live_price when set.
5. take_profit must be strictly above live_price when set.
6. order_type must be 'limit' when set.

Usage
-----
    from tradingagents.portfolio.order_guards import (
        resolve_buy_execution_price,
        buy_order_guard,
    )

    price = resolve_buy_execution_price(buy, prices)    # raises RuntimeError if missing
    violation = buy_order_guard(buy, price)             # returns str or None
    if violation:
        fail(violation)
"""

from __future__ import annotations

from typing import Any

_CASH_SWEEP_TICKER = "SGOV"
_CASH_SWEEP_SECTOR = "cash equivalent"


def _is_cash_sweep(buy: dict[str, Any]) -> bool:
    ticker = str(buy.get("ticker") or "").strip().upper()
    sector = str(buy.get("sector") or "").strip().casefold()
    return ticker == _CASH_SWEEP_TICKER and sector == _CASH_SWEEP_SECTOR


def resolve_buy_execution_price(
    buy: dict[str, Any],
    prices: dict[str, Any],
) -> float:
    """Return the live execution price for a buy order.

    For cash-sweep SGOV orders the live price is still required — the
    exception is only that order guards (limit/stop checks) are skipped.

    Raises
    ------
    RuntimeError
        If the ticker has no live price in *prices* or the price is
        non-positive.
    """
    ticker = str(buy.get("ticker") or "").strip().upper()
    if not ticker:
        raise RuntimeError("order_guards: buy has empty ticker")

    raw = prices.get(ticker)
    if raw is None:
        raise RuntimeError(
            f"order_guards: missing live price for {ticker} — "
            "cannot project buy cost without a real market price"
        )

    price = float(raw)
    if price <= 0:
        raise RuntimeError(
            f"order_guards: non-positive live price {price} for {ticker}"
        )
    return price


def buy_order_guard(buy: dict[str, Any], live_price: float) -> str | None:
    """Return a rejection reason string when the buy violates order guards.

    Returns *None* when the order passes all checks.

    Cash-sweep (SGOV) orders are exempt from limit/max-chase/stop/take-profit
    checks because they are system-generated and priced at market.

    Parameters
    ----------
    buy:
        The buy-order dict as produced by the PM agent.
    live_price:
        The confirmed live market price for the ticker.
    """
    if _is_cash_sweep(buy):
        return None

    ticker = str(buy.get("ticker") or "").strip().upper()

    order_type = str(buy.get("order_type") or "").strip().lower()
    if order_type and order_type != "limit":
        return (
            f"order_type for {ticker} must be 'limit', got {order_type!r}"
        )

    limit_price_raw = buy.get("limit_price")
    if limit_price_raw is not None:
        limit_price = float(limit_price_raw)
        if limit_price <= 0:
            return f"limit_price must be positive for {ticker}"
        if live_price > limit_price:
            return (
                f"limit_price violated for {ticker} — "
                f"live={live_price:.4f} > limit={limit_price:.4f}"
            )

    max_chase_raw = buy.get("max_chase_price")
    if max_chase_raw is not None:
        max_chase = float(max_chase_raw)
        if max_chase <= 0:
            return f"max_chase_price must be positive for {ticker}"
        if live_price > max_chase:
            return (
                f"max_chase_price violated for {ticker} — "
                f"live={live_price:.4f} > max_chase={max_chase:.4f}"
            )

    stop_loss_raw = buy.get("stop_loss")
    if stop_loss_raw is not None:
        stop_loss = float(stop_loss_raw)
        if stop_loss > 0 and stop_loss >= live_price:
            return (
                f"stop_loss must be below live price for {ticker} — "
                f"stop={stop_loss:.4f} >= live={live_price:.4f}"
            )

    take_profit_raw = buy.get("take_profit")
    if take_profit_raw is not None:
        take_profit = float(take_profit_raw)
        if take_profit > 0 and take_profit <= live_price:
            return (
                f"take_profit must be above live price for {ticker} — "
                f"take_profit={take_profit:.4f} <= live={live_price:.4f}"
            )

    return None
