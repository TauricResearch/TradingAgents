"""Sizing, stop and drawdown rules, as pure functions of prices and positions.

Positions are signed coin quantities (positive long, negative short) and
notionals are signed USDT amounts. The constants come from ``trader.settings``.
"""

from __future__ import annotations

import math

from trader.settings import (
    ATR_DAYS,
    BUDGET_HEADROOM,
    MAX_COIN_EXPOSURE,
    MAX_GROSS_EXPOSURE,
    RATING_WEIGHTS,
    REBALANCE_THRESHOLD,
    RISK_PER_UNIT,
    SLIPPAGE,
    STOP_ATR_MULT,
    TAKER_FEE,
)


def atr(highs: list[float], lows: list[float], closes: list[float], days: int = ATR_DAYS) -> float:
    """Simple mean of the true ranges of the last ``days`` bars.

    Inputs are oldest first and need at least ``days + 1`` bars, since a true
    range uses the previous close: max(high - low, |high - prev close|, |low - prev close|).
    Raises ValueError when there are too few bars.
    """
    if len(closes) < days + 1:
        raise ValueError(f"ATR over {days} days needs {days + 1} bars, got {len(closes)}")
    ranges = [
        max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        for i in range(len(closes) - days, len(closes))
    ]
    return sum(ranges) / days


def usable_prices(*values: float) -> bool:
    """Whether every one of ``values``, prices from OKX or an ATR, is a positive finite
    number, as anything traded, stopped or marked on them needs. A price of 0 would fill
    a long's stop at 0, a NaN one carry into the cash and the equity for good, an
    infinite one make the equity infinite; an ATR of 0 would divide ``unit_notional``
    by zero."""
    return all(math.isfinite(x) and x > 0 for x in values)


def usable_quote(price: float, atr_value: float) -> bool:
    """Whether a contract can be traded on a last price and an ATR (``usable_prices``).
    Every executor leaves a contract whose quote is not usable out of the round: not
    traded, its stop not moved, its position not marked at that price."""
    return usable_prices(price, atr_value)


def usable_rate(rate: float) -> bool:
    """Whether a funding rate from OKX can be settled: a finite number, 0 and below 0
    as well (``usable_prices`` is for prices). A NaN rate makes a NaN payment, which the
    funding table refuses (its amount is NOT NULL), so the replay booking it would fail
    every time; an infinite one makes the cash infinite."""
    return math.isfinite(rate)


def unit_notional(
    equity: float, atr_value: float, price: float, *,
    risk: float = RISK_PER_UNIT, stop_mult: float = STOP_ATR_MULT,
) -> float:
    """USDT notional of a full position unit: the size that loses ``risk`` of equity
    when price moves ``stop_mult`` * atr_value against it. The defaults are the daily
    account's constants; another account passes its own."""
    return risk * equity * price / (stop_mult * atr_value)


def target_notional(
    rating: str | None, unit: float, current: float, *, weights: dict = RATING_WEIGHTS
) -> float:
    """Signed target notional: ``weights[rating]`` * unit. A rating missing from
    ``weights`` (Hold, REVIEW, None) keeps ``current``. The default weights are the
    daily account's RATING_WEIGHTS."""
    weight = weights.get(rating)
    return current if weight is None else weight * unit


def apply_caps(targets: dict[str, float], currents: dict[str, float], equity: float) -> dict[str, float]:
    """Cap the targets that differ from their current notional.

    A target equal to its current notional is held as is. Every other target is
    clamped to +/- MAX_COIN_EXPOSURE * equity; then, if the gross notional (held
    plus changing) would exceed MAX_GROSS_EXPOSURE * equity, the changing targets
    are scaled down by one common factor so the gross equals the cap, or to zero
    when the held targets alone exceed it. A key missing from ``currents`` counts as 0.
    """
    coin_cap = MAX_COIN_EXPOSURE * equity
    held = {k: t for k, t in targets.items() if t == currents.get(k, 0.0)}
    changing = {
        k: max(-coin_cap, min(coin_cap, t)) for k, t in targets.items() if k not in held
    }
    room = max(MAX_GROSS_EXPOSURE * equity - sum(abs(t) for t in held.values()), 0.0)
    gross = sum(abs(t) for t in changing.values())
    if gross > room:
        changing = {k: t * room / gross for k, t in changing.items()}
    return {k: held[k] if k in held else changing[k] for k in targets}


def needs_trade(
    target: float, current: float, unit: float, *, threshold: float = REBALANCE_THRESHOLD
) -> bool:
    """Whether target and current notionals differ by at least ``threshold`` units;
    the default threshold is the daily account's REBALANCE_THRESHOLD."""
    return abs(target - current) >= threshold * unit


def to_quantity(
    notional: float, price: float, contract_value: float, lot_size: float, min_size: float
) -> float:
    """Signed coin quantity for a notional.

    The contract count is rounded toward zero to a whole number of ``lot_size``
    lots and becomes 0 below ``min_size`` contracts; the result is contracts *
    ``contract_value``, rounded to remove float noise.
    """
    # The epsilon keeps a count that float arithmetic left at 2.9999999 lots at 3.
    lots = math.floor(abs(notional) / price / contract_value / lot_size + 1e-9)
    contracts = lots * lot_size
    if contracts < min_size - 1e-12:
        return 0.0
    return math.copysign(round(contracts * contract_value, 12), notional)


def initial_stop(
    entry: float, qty: float, atr_value: float, *, stop_mult: float = STOP_ATR_MULT
) -> float:
    """Stop ``stop_mult`` * atr_value from entry: below a long, above a short. The
    default multiple is the daily account's STOP_ATR_MULT."""
    distance = stop_mult * atr_value
    return entry - distance if qty > 0 else entry + distance


def tighten(stop: float, candidate: float, qty: float) -> float:
    """The tighter of two stops: the higher for a long, the lower for a short."""
    return max(stop, candidate) if qty > 0 else min(stop, candidate)


def stop_after_trade(
    old_qty: float, new_qty: float, old_stop: float | None, fill_price: float, atr_value: float,
    *, stop_mult: float = STOP_ATR_MULT,
) -> float | None:
    """Stop for the position a trade leaves.

    None when it leaves the position flat; a fresh initial stop at ``fill_price``
    when it opens a position or flips its side; the tighter of the old stop and a
    fresh one when it adds on the same side; the old stop when it reduces. The
    fresh stop is ``stop_mult`` ATRs from the fill, the daily multiple by default.
    """
    if new_qty == 0:
        return None
    fresh = initial_stop(fill_price, new_qty, atr_value, stop_mult=stop_mult)
    if old_qty == 0 or (old_qty > 0) != (new_qty > 0):
        return fresh
    if abs(new_qty) > abs(old_qty):
        return tighten(old_stop, fresh, new_qty)
    return old_stop


def stop_fill(qty: float, stop: float, bar_open: float, bar_high: float, bar_low: float) -> float | None:
    """Price at which a bar fills the stop, before slippage; None when the bar misses it.

    A long fills at ``bar_open`` when the bar opens at or below the stop (a gap
    through it), else at the stop when the low reaches it. A short mirrors this
    with the open and high at or above the stop.
    """
    if qty > 0:
        if bar_open <= stop:
            return bar_open
        return stop if bar_low <= stop else None
    if bar_open >= stop:
        return bar_open
    return stop if bar_high >= stop else None


def slipped(price: float, side: float) -> float:
    """Fill price after SLIPPAGE against the trader: higher when buying (side > 0),
    lower when selling (side < 0)."""
    return price * (1 + SLIPPAGE) if side > 0 else price * (1 - SLIPPAGE)


def fee(notional: float) -> float:
    """TAKER_FEE on the absolute notional, as a positive amount."""
    return abs(notional) * TAKER_FEE


def funding_payment(qty: float, price: float, rate: float) -> float:
    """Cash a position receives at a funding settlement, negative when it pays.
    A positive rate has longs pay shorts: the payment is -qty * price * rate."""
    return -qty * price * rate


def drawdown(equity: float, peak: float) -> float:
    """Fraction by which equity is below peak; 0 when at or above it."""
    return max(0.0, 1 - equity / peak)


def monthly_cap(daily_costs: list[float]) -> float:
    """Monthly LLM budget in USD: mean daily cost * 30 * BUDGET_HEADROOM."""
    return sum(daily_costs) / len(daily_costs) * 30 * BUDGET_HEADROOM
