from dataclasses import dataclass
from decimal import Decimal

RATING_SCORES = {
    "Buy": Decimal("1"),
    "Overweight": Decimal("0.5"),
    "Hold": Decimal("0"),
    "Underweight": Decimal("-0.5"),
    "Sell": Decimal("-1"),
}


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: str
    notional: Decimal
    target_notional: Decimal


def conviction_targets(
    decisions,
    cash,
    max_cash_allocation,
    equity=None,
    max_cash_reserve=None,
):
    max_cash_allocation = _finite_decimal(max_cash_allocation, "max_cash_allocation")
    if not Decimal("0") < max_cash_allocation <= Decimal("0.90"):
        raise ValueError("max_cash_allocation must be greater than 0 and at most 0.90")
    cash = _finite_decimal(cash, "cash")

    reserve = None
    equity_value = None
    if max_cash_reserve is not None:
        reserve = _finite_decimal(max_cash_reserve, "max_cash_reserve")
        if reserve < 0:
            raise ValueError("max_cash_reserve must be non-negative")
        if equity is None:
            raise ValueError("equity is required when max_cash_reserve is set")
        equity_value = _finite_decimal(equity, "equity")
        if equity_value <= 0:
            raise ValueError("equity must be positive and finite")

    try:
        scores = {symbol: RATING_SCORES[rating] for symbol, rating in decisions.items()}
    except KeyError as error:
        raise ValueError(f"unsupported rating: {error.args[0]}") from error

    gross_budget = max(cash, Decimal("0")) * max_cash_allocation
    score_total = sum(abs(score) for score in scores.values())
    if score_total == 0:
        return {symbol: Decimal("0") for symbol in decisions}
    targets = {symbol: gross_budget * score / score_total for symbol, score in scores.items()}
    if max_cash_reserve is None:
        return targets

    positive_total = sum(score for score in scores.values() if score > 0)
    if positive_total == 0:
        return targets
    short_target = -sum(target for target in targets.values() if target < 0)
    required_long = max(equity_value + short_target - reserve, Decimal("0"))
    return {
        symbol: required_long * score / positive_total if score > 0 else targets[symbol]
        for symbol, score in scores.items()
    }


def _finite_decimal(value, name):
    try:
        converted = Decimal(str(value))
    except (ArithmeticError, ValueError) as error:
        raise ValueError(f"{name} must be finite") from error
    if not converted.is_finite():
        raise ValueError(f"{name} must be finite")
    return converted


def reconcile_targets(
    targets,
    positions,
    open_orders,
    threshold,
    minimum_positions=None,
):
    threshold = Decimal(str(threshold))
    minimums = {} if minimum_positions is None else minimum_positions
    intents = []
    for symbol, raw_target in targets.items():
        target = max(
            Decimal(str(raw_target)),
            Decimal(str(minimums.get(symbol, raw_target))),
        )
        effective = Decimal(str(positions.get(symbol, 0))) + Decimal(
            str(open_orders.get(symbol, 0))
        )
        delta = target - effective
        if abs(delta) >= threshold and delta != 0:
            intents.append(OrderIntent(symbol, "buy" if delta > 0 else "sell", abs(delta), target))
    return intents
