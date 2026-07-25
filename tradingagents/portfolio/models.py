"""Pure portfolio domain rules; no LLM, API, or provider dependencies."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

Action = Literal["buy", "sell", "hold"]


def _positive_finite(value: float, name: str, *, allow_zero: bool = False) -> None:
    if not math.isfinite(value) or (value < 0 if allow_zero else value <= 0):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{name} must be a finite {qualifier} number")


@dataclass(frozen=True)
class Position:
    ticker: str
    quantity: int
    average_cost: float
    sellable_quantity: int | None = None

    def __post_init__(self) -> None:
        if not self.ticker.strip():
            raise ValueError("position ticker is required")
        if self.quantity < 0:
            raise ValueError("position quantity must be non-negative")
        if self.sellable_quantity is not None and not 0 <= self.sellable_quantity <= self.quantity:
            raise ValueError("sellable_quantity must be between zero and quantity")
        _positive_finite(self.average_cost, "average_cost", allow_zero=True)


@dataclass(frozen=True)
class PortfolioLimits:
    max_position_weight: float = 0.10
    lot_size: int = 1
    fee_rate: float = 0.0005
    minimum_fee: float = 0.0
    allow_short: bool = False

    def __post_init__(self) -> None:
        if not 0 < self.max_position_weight <= 1:
            raise ValueError("max_position_weight must be in (0, 1]")
        if self.lot_size < 1:
            raise ValueError("lot_size must be at least one")
        if not 0 <= self.fee_rate < 1:
            raise ValueError("fee_rate must be in [0, 1)")
        _positive_finite(self.minimum_fee, "minimum_fee", allow_zero=True)


@dataclass(frozen=True)
class PortfolioContext:
    """The non-secret facts required to make an executable recommendation."""

    cash: float
    positions: tuple[Position, ...] = ()
    mark_prices: Mapping[str, float] = field(default_factory=dict)
    currency: str = "CNY"
    limits: PortfolioLimits = field(default_factory=PortfolioLimits)

    def __post_init__(self) -> None:
        _positive_finite(self.cash, "cash", allow_zero=True)
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError("currency must be a three-letter code")
        tickers = [position.ticker for position in self.positions]
        if len(set(tickers)) != len(tickers):
            raise ValueError("portfolio positions must not contain duplicate tickers")
        for ticker, price in self.mark_prices.items():
            if not ticker.strip():
                raise ValueError("mark price ticker is required")
            _positive_finite(float(price), f"mark price for {ticker}")


@dataclass(frozen=True)
class AllowedAction:
    action: Action
    max_quantity: int
    price: float | None
    reason: str


@dataclass(frozen=True)
class ClampEvent:
    requested_action: str
    requested_quantity: int
    applied_action: Action
    applied_quantity: int
    limit: str
    reason: str


def compute_allowed_actions(
    context: PortfolioContext | None,
    ticker: str,
    reference_price: float | None,
) -> tuple[AllowedAction, ...]:
    """Compute executable actions before an LLM sees a decision prompt.

    No context means research-only mode, so Hold is the only truthful action.
    A caller must supply every held position's current mark to claim a
    portfolio-weight limit; otherwise the calculation fails closed.
    """
    if context is None:
        return (AllowedAction("hold", 0, None, "portfolio_not_provided"),)
    if not ticker.strip():
        raise ValueError("ticker is required")
    if reference_price is None:
        reference_price = context.mark_prices.get(ticker)
    if reference_price is None:
        raise ValueError(f"reference price is required for {ticker}")
    _positive_finite(float(reference_price), "reference_price")
    price = float(reference_price)
    positions = {position.ticker: position for position in context.positions}
    current = positions.get(ticker)
    current_quantity = current.quantity if current else 0
    current_value = current_quantity * price
    portfolio_value = context.cash
    for position in context.positions:
        mark = price if position.ticker == ticker else context.mark_prices.get(position.ticker)
        if mark is None:
            raise ValueError(f"mark price is required for held position {position.ticker}")
        portfolio_value += position.quantity * float(mark)

    max_position_value = portfolio_value * context.limits.max_position_weight
    max_buy_by_weight = max(0.0, max_position_value - current_value)
    max_buy_by_cash = _max_affordable_quantity(context.cash, price, context.limits)
    max_buy = min(max_buy_by_cash, _round_down(max_buy_by_weight / price, context.limits.lot_size))
    sellable = current.sellable_quantity if current and current.sellable_quantity is not None else current_quantity
    max_sell = _round_down(sellable, context.limits.lot_size)

    actions = [AllowedAction("hold", 0, price, "always_available")]
    if max_buy > 0:
        actions.append(AllowedAction("buy", max_buy, price, "cash_and_position_limit"))
    if max_sell > 0:
        actions.append(AllowedAction("sell", max_sell, price, "sellable_position_limit"))
    return tuple(actions)


def portfolio_context_from_dict(value: Mapping[str, object] | None) -> PortfolioContext | None:
    """Rehydrate a JSON-safe graph-state portfolio context into domain objects."""
    if value is None:
        return None
    raw_positions = value.get("positions", ())
    raw_limits = value.get("limits", {})
    if not isinstance(raw_positions, (list, tuple)) or not isinstance(raw_limits, Mapping):
        raise ValueError("portfolio context has an invalid serialized shape")
    positions = tuple(
        Position(
            ticker=str(position["ticker"]),
            quantity=int(position["quantity"]),
            average_cost=float(position["average_cost"]),
            sellable_quantity=(
                int(position["sellable_quantity"])
                if position.get("sellable_quantity") is not None
                else None
            ),
        )
        for position in raw_positions
        if isinstance(position, Mapping)
    )
    if len(positions) != len(raw_positions):
        raise ValueError("portfolio positions must be objects")
    prices = value.get("mark_prices", {})
    if not isinstance(prices, Mapping):
        raise ValueError("portfolio mark_prices must be an object")
    return PortfolioContext(
        cash=float(value["cash"]),
        positions=positions,
        mark_prices={str(ticker): float(price) for ticker, price in prices.items()},
        currency=str(value.get("currency", "CNY")),
        limits=PortfolioLimits(
            max_position_weight=float(raw_limits.get("max_position_weight", 0.10)),
            lot_size=int(raw_limits.get("lot_size", 1)),
            fee_rate=float(raw_limits.get("fee_rate", 0.0005)),
            minimum_fee=float(raw_limits.get("minimum_fee", 0.0)),
            allow_short=bool(raw_limits.get("allow_short", False)),
        ),
    )


def clamp_execution(
    requested_action: str,
    requested_quantity: int,
    actions: tuple[AllowedAction, ...],
) -> tuple[Action, int, ClampEvent | None]:
    """Clamp an LLM request to the precomputed legal action set."""
    normalized = requested_action.lower()
    allowed = next((action for action in actions if action.action == normalized), None)
    if allowed is None:
        return "hold", 0, ClampEvent(
            requested_action=requested_action,
            requested_quantity=requested_quantity,
            applied_action="hold",
            applied_quantity=0,
            limit="allowed_actions",
            reason="requested_action_not_allowed",
        )
    quantity = max(0, int(requested_quantity))
    applied = min(quantity, allowed.max_quantity)
    if allowed.action == "hold":
        applied = 0
    if applied != quantity:
        return allowed.action, applied, ClampEvent(
            requested_action=requested_action,
            requested_quantity=requested_quantity,
            applied_action=allowed.action,
            applied_quantity=applied,
            limit="max_quantity",
            reason="requested_quantity_clamped",
        )
    return allowed.action, applied, None


def _max_affordable_quantity(cash: float, price: float, limits: PortfolioLimits) -> int:
    lot = limits.lot_size
    upper = _round_down(cash / (price * (1 + limits.fee_rate)), lot)
    while upper > 0:
        gross = upper * price
        total_cost = gross + max(gross * limits.fee_rate, limits.minimum_fee)
        if total_cost <= cash:
            return upper
        upper -= lot
    return 0


def _round_down(quantity: float | int, lot_size: int) -> int:
    return max(0, int(math.floor(float(quantity) / lot_size)) * lot_size)
