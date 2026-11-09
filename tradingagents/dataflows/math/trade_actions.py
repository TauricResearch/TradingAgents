"""Trade actions (§6): a rating is not an order.

The 19:24 report proposed a SELL at 573.10 with a 546 stop and a "30-40%
exposure reduction". None of that is executable, because it does not say what
the book holds: selling 40% of nothing is not a trade, and a SELL rating on a
flat account is not a short either.

This module makes the missing distinction explicit. A strategic rating
(OVERWEIGHT / NEUTRAL / UNDERWEIGHT) says what the analyst thinks; a
``TradeAction`` says what to do to the book, and each action carries its own
preconditions. Deriving one from the other silently is the defect: SELL does
not mean OPEN_SHORT, and UNDERWEIGHT does not mean CLOSE_LONG.

The rules, in the order the gate applies them:

``OPEN_LONG`` / ``REDUCE_LONG`` / ``CLOSE_LONG``
    Require a position. A reduction cannot sell more than is held, and the
    quantity comes from the held amount, never from a percentage of an
    unknown base.
``OPEN_SHORT`` / ``REDUCE_SHORT`` / ``CLOSE_SHORT``
    Require explicit short authorization; paper trading only.
``WAIT``
    The honest default when the book is unknown.

With no portfolio the answer is WAIT or BLOCK — never an invented quantity.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TradeAction(StrEnum):
    """What to do to the book. Distinct from a strategic rating by design."""

    OPEN_LONG = "OPEN_LONG"
    REDUCE_LONG = "REDUCE_LONG"
    CLOSE_LONG = "CLOSE_LONG"
    OPEN_SHORT = "OPEN_SHORT"
    REDUCE_SHORT = "REDUCE_SHORT"
    CLOSE_SHORT = "CLOSE_SHORT"
    WAIT = "WAIT"


# Actions that only make sense against an existing position.
_REQUIRES_LONG = frozenset({TradeAction.REDUCE_LONG, TradeAction.CLOSE_LONG})
_REQUIRES_SHORT = frozenset({TradeAction.REDUCE_SHORT, TradeAction.CLOSE_SHORT})
_SHORT_ACTIONS = frozenset({
    TradeAction.OPEN_SHORT, TradeAction.REDUCE_SHORT, TradeAction.CLOSE_SHORT,
})

# The one deterministic mapping from a strategic rating to a *candidate*
# action, and only in the direction that is safe: an UNDERWEIGHT rating may
# reduce or close a long, never open a short. A SELL rating is not here at
# all, because "sell" does not name a book operation.
_RATING_TO_ACTIONS = {
    "OVERWEIGHT": (TradeAction.OPEN_LONG, TradeAction.REDUCE_SHORT,
                   TradeAction.CLOSE_SHORT),
    "NEUTRAL": (TradeAction.WAIT,),
    "UNDERWEIGHT": (TradeAction.REDUCE_LONG, TradeAction.CLOSE_LONG,
                    TradeAction.WAIT),
}


@dataclass(frozen=True)
class PositionState:
    """What the book actually holds, in the instrument being analysed.

    ``known`` is separate from ``quantity == 0`` on purpose: an absent
    portfolio is not a flat one, and treating them alike is how a quantity
    gets invented.
    """

    known: bool
    quantity: float = 0.0
    average_price: float | None = None
    stop_price: float | None = None

    @property
    def is_flat(self) -> bool:
        return self.known and self.quantity == 0

    @property
    def is_long(self) -> bool:
        return self.known and self.quantity > 0

    @property
    def is_short(self) -> bool:
        return self.known and self.quantity < 0


@dataclass(frozen=True)
class TradeIntent:
    """A validated intent: the action, the quantity, and why it is refused."""

    action: TradeAction
    quantity: float = 0.0
    reason_code: str = ""
    reason: str = ""
    blocks: bool = False

    @property
    def is_executable(self) -> bool:
        """An intent reaches the gate only with a real quantity and no refusal."""
        return (not self.blocks and self.action is not TradeAction.WAIT
                and self.quantity > 0)

    def summary(self) -> dict:
        return {
            "trade_action": str(self.action),
            "quantity": self.quantity,
            "reason_code": self.reason_code or None,
            "reason": self.reason or None,
            "blocks": self.blocks,
            "is_executable": self.is_executable,
        }


def actions_for_rating(rating: str | None) -> tuple[TradeAction, ...]:
    """The candidate actions a strategic rating permits, never implies.

    ``WAIT`` is appended to every rating: not acting now is always legitimate,
    and a gate that could not say "wait" would have to choose between acting
    and blocking on a valid plan.

    Returns an empty tuple for a rating outside the three-tier vocabulary, or
    for a bare "SELL"/"BUY" label: those name a direction, not a book
    operation, and mapping them to one automatically is what §6 forbids.
    """
    if not rating:
        return ()
    permitted = _RATING_TO_ACTIONS.get(str(rating).strip().upper())
    if not permitted:
        return ()
    if TradeAction.WAIT in permitted:
        return permitted
    return (*permitted, TradeAction.WAIT)


def resolve_trade_intent(
    action: TradeAction,
    position: PositionState,
    *,
    reduce_fraction: float | None = None,
    short_authorized: bool = False,
    entry_price: float | None = None,
) -> TradeIntent:
    """Turn an action plus the real book into a quantity, or refuse it.

    Every refusal here is a *block*, not a warning: an intent that cannot be
    quantified must not reach the Execution Gate as a plausible-looking
    order, and §7 requires zero broker calls in that case.

    ``reduce_fraction`` is how much of the position to sell, as a fraction.
    It is applied to the **held quantity**, so "sell 40%" of 10 shares is 4 —
    never 40% of an unknown base.
    """
    if action is TradeAction.WAIT:
        return TradeIntent(TradeAction.WAIT, reason_code="WAIT",
                           reason="no book operation requested")

    # A book operation needs a book.
    if not position.known:
        return TradeIntent(
            action, reason_code="PORTFOLIO_UNKNOWN", blocks=True,
            reason=("the portfolio is unavailable, so no quantity can be "
                    "determined; a held amount is never invented"),
        )

    if action in _SHORT_ACTIONS and not short_authorized:
        return TradeIntent(
            action, reason_code="SHORT_NOT_AUTHORIZED", blocks=True,
            reason=("short actions require explicit strategy authorization; "
                    "a SELL rating is not one"),
        )

    if action is TradeAction.OPEN_LONG:
        if not position.is_flat:
            return TradeIntent(
                action, reason_code="POSITION_ALREADY_OPEN", blocks=True,
                reason=(f"OPEN_LONG on a book holding {position.quantity} "
                        "units: that is an addition, not an opening"),
            )
        if not entry_price or entry_price <= 0:
            return TradeIntent(
                action, reason_code="NO_ENTRY_PRICE", blocks=True,
                reason="an opening needs a valid entry price",
            )
        return TradeIntent(action, quantity=0.0, reason_code="SIZE_REQUIRED",
                           reason="quantity comes from the risk engine")

    if action is TradeAction.OPEN_SHORT:
        if not position.is_flat:
            return TradeIntent(
                action, reason_code="POSITION_ALREADY_OPEN", blocks=True,
                reason=(f"OPEN_SHORT on a book holding {position.quantity} "
                        "units"),
            )
        return TradeIntent(action, quantity=0.0, reason_code="SIZE_REQUIRED",
                           reason="quantity comes from the risk engine")

    if action in _REQUIRES_LONG:
        if not position.is_long:
            return TradeIntent(
                action, reason_code="NO_LONG_POSITION", blocks=True,
                reason=(f"{action} requires a long position and the book holds "
                        f"{position.quantity:g} units"),
            )
        held = position.quantity
        if action is TradeAction.CLOSE_LONG:
            return TradeIntent(action, quantity=held, reason_code="OK")
        fraction = 1.0 if reduce_fraction is None else float(reduce_fraction)
        if not (0 < fraction <= 1):
            return TradeIntent(
                action, reason_code="INVALID_REDUCTION_FRACTION", blocks=True,
                reason=f"a reduction of {fraction} of the position is not a size",
            )
        to_sell = held * fraction
        # Never sell more than is held, whatever the fraction implies.
        to_sell = min(to_sell, held)
        if to_sell <= 0:
            return TradeIntent(
                action, reason_code="NON_POSITIVE_QUANTITY", blocks=True,
                reason=f"a reduction of {fraction} of {held:g} units rounds to 0",
            )
        return TradeIntent(action, quantity=to_sell, reason_code="OK")

    if action in _REQUIRES_SHORT:
        if not position.is_short:
            return TradeIntent(
                action, reason_code="NO_SHORT_POSITION", blocks=True,
                reason=(f"{action} requires a short position and the book holds "
                        f"{position.quantity:g} units"),
            )
        held = abs(position.quantity)
        if action is TradeAction.CLOSE_SHORT:
            return TradeIntent(action, quantity=held, reason_code="OK")
        fraction = 1.0 if reduce_fraction is None else float(reduce_fraction)
        if not (0 < fraction <= 1):
            return TradeIntent(
                action, reason_code="INVALID_REDUCTION_FRACTION", blocks=True,
                reason=f"a reduction of {fraction} of the position is not a size",
            )
        return TradeIntent(action, quantity=min(held * fraction, held),
                           reason_code="OK")

    return TradeIntent(action, reason_code="UNKNOWN_ACTION", blocks=True,
                       reason=f"unrecognised action {action}")


def validate_trade_against_rating(action: TradeAction, rating: str | None,
                                  *, position: PositionState) -> TradeIntent:
    """Check that an action is one the rating could justify, and is sized.

    This is the guard §6 asks for: an action that no rating permits is
    refused rather than executed, so a SELL rating cannot silently become an
    OPEN_SHORT even if some caller constructs one.
    """
    permitted = actions_for_rating(rating)
    if not permitted:
        return TradeIntent(
            action, reason_code="RATING_NOT_TRADEABLE", blocks=True,
            reason=(f"the rating {rating!r} does not name a book operation; "
                    "'SELL' is a direction, not an action"),
        )
    if action not in permitted:
        return TradeIntent(
            action, reason_code="ACTION_NOT_PERMITTED_BY_RATING", blocks=True,
            reason=(f"{action} is not among the actions a {rating} rating "
                    f"permits ({', '.join(str(a) for a in permitted)})"),
        )
    return resolve_trade_intent(action, position)
