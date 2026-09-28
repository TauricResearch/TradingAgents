"""Signal -> order sizing for the crypto execution bridge (FR2/FR3).

``compute`` is the single contract: it ALWAYS returns a ``PlannedOrder`` --
never None. A case that must not trade comes back as an order with
``side=None`` and a reason; only REVIEW / unrecognized signals set
``needs_review``. The exchange precision string is deliberately absent here:
it is produced by ``execute_order`` at execute time from the planned float
quantity, so re-formatting elsewhere can never reintroduce rounding drift.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from tradingagents.agents.rating import RATINGS_5_TIER, is_review
from tradingagents.portfolio import PortfolioContext

# Exact 5-tier vocabulary, unpacked so the mapping can never drift from the
# rating module's strings (they are case-sensitive: "Buy", not "buy").
_BUY, _OVERWEIGHT, _HOLD, _UNDERWEIGHT, _SELL = RATINGS_5_TIER


class SizingRules(BaseModel):
    """Configurable FR2 mapping.

    Defaults: Buy targets 25% of free cash, Overweight adds 10%, Underweight
    reduces 10% of the held position, Sell closes it. ``min_order_cost`` is
    the plan-time floor when the exchange reports no market limit.
    """

    buy_fraction: float = 0.25
    overweight_fraction: float = 0.10
    underweight_fraction: float = 0.10
    min_order_cost: float = 10.0


class PlannedOrder(BaseModel):
    """A sized plan, executable only through ExchangeBridge.execute_order.

    ``mode`` is informational -- the double-gate value at plan time. The
    effective mode is computed at execute time, so a plan made in dry mode
    CAN execute live if both gates are open and ``confirm=True`` is passed
    at that moment. ``market``/``leverage`` default to a spot order at 1x;
    derivatives plans set them explicitly (``cost`` is the margin committed,
    notional = cost * leverage).
    """

    ticker: str
    ccxt_symbol: str
    signal: str
    side: Literal["buy", "sell"] | None = None
    quantity: float | None = None
    estimated_price: float | None = None
    cost: float | None = None
    mode: Literal["dry", "live"] = "dry"
    needs_review: bool = False
    reason: str | None = None
    market: Literal["spot", "derivatives"] = "spot"
    leverage: float = 1.0


def compute(
    rules: SizingRules,
    *,
    signal: str,
    ticker: str,
    ccxt_symbol: str,
    portfolio: PortfolioContext | None = None,
    price: float | None = None,
    min_cost: float | None = None,
) -> PlannedOrder:
    """Size ``signal`` against ``portfolio`` at ``price``; always returns a plan.

    Never raises for business reasons and never returns None: any case that
    must not trade comes back as side=None with a reason. ``min_cost``
    overrides ``rules.min_order_cost`` (the bridge passes the exchange's own
    limit when it wants the market to decide).
    """
    book = portfolio if portfolio is not None else PortfolioContext()
    floor = rules.min_order_cost if min_cost is None else min_cost

    def planned(
        side: Literal["buy", "sell"] | None = None,
        quantity: float | None = None,
        cost: float | None = None,
        *,
        needs_review: bool = False,
        reason: str | None = None,
    ) -> PlannedOrder:
        return PlannedOrder(
            ticker=ticker,
            ccxt_symbol=ccxt_symbol,
            signal=signal,
            side=side,
            quantity=quantity,
            estimated_price=price,
            cost=cost,
            needs_review=needs_review,
            reason=reason,
        )

    def no_order(reason: str, *, needs_review: bool = False) -> PlannedOrder:
        return planned(needs_review=needs_review, reason=reason)

    if is_review(signal):
        return no_order("REVIEW signal: no order without human review", needs_review=True)

    side: Literal["buy", "sell"] | None
    quantity: float | None
    cost: float | None

    if signal in (_BUY, _OVERWEIGHT):
        if price is None or price <= 0:
            return no_order("price unavailable")
        if book.cash is None:
            return no_order("cash unavailable")
        fraction = rules.buy_fraction if signal == _BUY else rules.overweight_fraction
        side = "buy"
        cost = book.cash * fraction
        quantity = cost / price
    elif signal in (_SELL, _UNDERWEIGHT):
        position = book.position_in(ticker)
        if position is None or position.quantity <= 0:
            return no_order("no position to close/reduce")
        if price is None or price <= 0:
            return no_order("price unavailable")
        fraction = 1.0 if signal == _SELL else rules.underweight_fraction
        side = "sell"
        quantity = position.quantity * fraction
        cost = quantity * price
    elif signal == _HOLD:
        return no_order("Hold: no trade")
    else:
        return no_order(
            f"unrecognized signal {signal!r}: no order without human review",
            needs_review=True,
        )

    if cost < floor:
        return no_order("cost below exchange minimum")

    return planned(side=side, quantity=quantity, cost=cost)
