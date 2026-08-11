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


def conviction_targets(decisions, cash, max_cash_allocation):
    max_cash_allocation = Decimal(str(max_cash_allocation))
    if not Decimal("0") < max_cash_allocation <= Decimal("0.30"):
        raise ValueError("max_cash_allocation must be greater than 0 and at most 0.30")

    try:
        scores = {symbol: RATING_SCORES[rating] for symbol, rating in decisions.items()}
    except KeyError as error:
        raise ValueError(f"unsupported rating: {error.args[0]}") from error

    gross_budget = max(Decimal(str(cash)), Decimal("0")) * max_cash_allocation
    score_total = sum(abs(score) for score in scores.values())
    if score_total == 0:
        return {symbol: Decimal("0") for symbol in decisions}
    return {
        symbol: gross_budget * score / score_total
        for symbol, score in scores.items()
    }


def reconcile_targets(targets, positions, open_orders, threshold):
    threshold = Decimal(str(threshold))
    intents = []
    for symbol, raw_target in targets.items():
        target = Decimal(str(raw_target))
        effective = Decimal(str(positions.get(symbol, 0))) + Decimal(
            str(open_orders.get(symbol, 0))
        )
        delta = target - effective
        if abs(delta) >= threshold and delta != 0:
            intents.append(
                OrderIntent(symbol, "buy" if delta > 0 else "sell", abs(delta), target)
            )
    return intents
