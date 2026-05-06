"""Pure portfolio allocation planning helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Literal, Sequence

from tradingagents.batch import BatchTickerResult


RecommendedAction = Literal["buy", "sell", "hold"]


@dataclass(frozen=True)
class AllocationPolicy:
    buy_weight: float = 0.20
    overweight_weight: float = 0.15
    underweight_weight: float = 0.05
    max_position_weight: float = 0.25
    min_cash_weight: float = 0.0


@dataclass(frozen=True)
class AllocationRow:
    ticker: str
    rating: str
    rank: int
    current_value: float
    current_weight: float
    target_weight: float
    target_value: float
    delta_value: float
    price: float | None
    quantity_delta: float | None
    recommended_action: RecommendedAction


@dataclass(frozen=True)
class AllocationPlan:
    rows: list[AllocationRow]
    leftover_cash: float
    target_cash_weight: float
    total_current_value: float
    total_projected_value: float

    def row_for(self, ticker: str) -> AllocationRow:
        target = ticker.upper()
        for row in self.rows:
            if row.ticker.upper() == target:
                return row
        raise KeyError(ticker)


_RATING_SCORES = {
    "Buy": 2,
    "Overweight": 1,
    "Hold": 0,
    "Underweight": -1,
    "Sell": -2,
}


def build_allocation_plan(
    results: Sequence[BatchTickerResult],
    *,
    available_cash: float,
    prices: dict[str, float],
    policy: AllocationPolicy | None = None,
) -> AllocationPlan:
    _validate_inputs(results, available_cash)
    policy = policy or AllocationPolicy()
    ranked_results = sorted(
        results,
        key=lambda result: (
            -_RATING_SCORES.get(result.rating or "Hold", 0),
            result.ticker,
        ),
    )
    current_values = {
        result.ticker: _current_value(result, prices)
        for result in ranked_results
    }
    holding_quantities = {
        result.ticker: result.holding.quantity
        for result in ranked_results
        if result.holding is not None
    }
    holdings_value = sum(current_values.values())
    total_current_value = holdings_value + max(0.0, available_cash)
    current_weights = {
        ticker: value / total_current_value if total_current_value > 0 else 0.0
        for ticker, value in current_values.items()
    }

    target_weights = _target_weights(ranked_results, current_weights, policy)
    target_cash_weight = max(0.0, 1.0 - sum(target_weights.values()))
    total_projected_value = total_current_value

    rows = [
        _row_for_result(
            result=result,
            rank=index,
            current_value=current_values[result.ticker],
            current_weight=current_weights[result.ticker],
            target_weight=target_weights[result.ticker],
            total_projected_value=total_projected_value,
            prices=prices,
        )
        for index, result in enumerate(ranked_results, start=1)
    ]
    rows, leftover_cash = _apply_whole_share_order_sizing(
        rows,
        available_cash,
        holding_quantities,
    )
    return AllocationPlan(
        rows=rows,
        leftover_cash=leftover_cash,
        target_cash_weight=target_cash_weight,
        total_current_value=total_current_value,
        total_projected_value=total_projected_value,
    )


def build_allocation_markdown(plan: AllocationPlan, analysis_date: str) -> str:
    projected_cash_weight = (
        plan.leftover_cash / plan.total_projected_value
        if plan.total_projected_value > 0
        else 0.0
    )
    lines = [
        "# Portfolio Allocation Report",
        "",
        f"Analysis Date: {analysis_date}",
        "",
        "## Portfolio Allocation Plan",
        "",
        "| Rank | Ticker | Rating | Action | Current Value | Current Weight | Target Weight | Delta Value | Price | Quantity Delta |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted(plan.rows, key=lambda candidate: candidate.rank):
        lines.append(
            "| {rank} | {ticker} | {rating} | {action} | {current_value} | {current_weight} | {target_weight} | {delta_value} | {price} | {quantity_delta} |".format(
                rank=row.rank,
                ticker=row.ticker,
                rating=row.rating,
                action=row.recommended_action,
                current_value=_format_number(row.current_value),
                current_weight=_format_percent(row.current_weight),
                target_weight=_format_percent(row.target_weight),
                delta_value=_format_number(row.delta_value),
                price=_format_number(row.price),
                quantity_delta=_format_quantity(row.quantity_delta),
            )
        )

    lines.extend([
        "",
        "## Cash Projection",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Leftover Cash | {_format_number(plan.leftover_cash)} |",
        f"| Target Cash Weight | {_format_percent(plan.target_cash_weight)} |",
        f"| Projected Cash Weight | {_format_percent(projected_cash_weight)} |",
        f"| Total Current Value | {_format_number(plan.total_current_value)} |",
        f"| Total Projected Value | {_format_number(plan.total_projected_value)} |",
    ])
    return "\n".join(lines) + "\n"


def allocation_plan_to_json(plan: AllocationPlan) -> dict:
    projected_cash_weight = (
        plan.leftover_cash / plan.total_projected_value
        if plan.total_projected_value > 0
        else 0.0
    )
    data = asdict(plan)
    data["projected_cash_weight"] = projected_cash_weight
    return data


def _apply_whole_share_order_sizing(
    rows: list[AllocationRow],
    available_cash: float,
    holding_quantities: dict[str, float | None],
) -> tuple[list[AllocationRow], float]:
    sized_rows = list(rows)
    deployable_cash = max(0.0, available_cash)

    for index, row in enumerate(sized_rows):
        if row.delta_value >= 0 or row.price is None or row.price <= 0:
            continue
        quantity = int(abs(row.delta_value) / row.price)
        holding_quantity = holding_quantities.get(row.ticker)
        if holding_quantity is not None:
            quantity = min(quantity, max(0, int(holding_quantity)))
        quantity = -quantity
        if quantity == 0:
            sized_rows[index] = replace(row, quantity_delta=0)
            continue
        deployable_cash += abs(quantity) * row.price
        sized_rows[index] = replace(row, quantity_delta=quantity)

    buy_candidates: list[tuple[int, AllocationRow, float]] = []
    for index, row in enumerate(sized_rows):
        price = row.price
        if row.delta_value > 0 and price is not None and price > 0:
            buy_candidates.append((index, row, price))
    total_buy_delta = sum(row.delta_value for _, row, _ in buy_candidates)
    actual_buy_cost = 0.0

    for index, row, price in buy_candidates:
        budget = (
            deployable_cash * (row.delta_value / total_buy_delta)
            if total_buy_delta > 0
            else 0.0
        )
        quantity = int(budget / price)
        actual_buy_cost += quantity * price
        sized_rows[index] = replace(row, quantity_delta=quantity)

    for index, row in enumerate(sized_rows):
        if row.price is None or row.price <= 0:
            sized_rows[index] = replace(row, quantity_delta=None)

    leftover_cash = max(0.0, deployable_cash - actual_buy_cost)
    return sized_rows, leftover_cash


def _validate_inputs(results: Sequence[BatchTickerResult], available_cash: float) -> None:
    if available_cash < 0:
        raise ValueError("available_cash must be non-negative.")

    seen_tickers: set[str] = set()
    for result in results:
        ticker = result.ticker.upper()
        if ticker in seen_tickers:
            raise ValueError(f"Duplicate ticker in allocation results: {result.ticker}")
        seen_tickers.add(ticker)


def _current_value(result: BatchTickerResult, prices: dict[str, float]) -> float:
    if result.holding is None:
        return 0.0
    if result.holding.market_value is not None:
        return float(result.holding.market_value)
    price = prices.get(result.ticker)
    if result.holding.quantity is not None and price is not None and price > 0:
        return float(result.holding.quantity) * float(price)
    return 0.0


def _target_weights(
    results: Sequence[BatchTickerResult],
    current_weights: dict[str, float],
    policy: AllocationPolicy,
) -> dict[str, float]:
    investable_weight = max(0.0, 1.0 - policy.min_cash_weight)
    target_weights = {
        result.ticker: _capped_target_weight(result, current_weights[result.ticker], policy)
        for result in results
    }
    positive_tickers = [
        result.ticker
        for result in results
        if _RATING_SCORES.get(result.rating or "Hold", 0) > 0
    ]

    total_target = sum(target_weights.values())
    if total_target > investable_weight and total_target > 0:
        scale = investable_weight / total_target
        return {
            ticker: weight * scale
            for ticker, weight in target_weights.items()
        }

    if not positive_tickers:
        return target_weights

    remaining = investable_weight - total_target
    while remaining > 0.000000001:
        eligible = [
            ticker
            for ticker in positive_tickers
            if target_weights[ticker] < policy.max_position_weight - 0.000000001
        ]
        if not eligible:
            break
        increment = remaining / len(eligible)
        used = 0.0
        for ticker in eligible:
            room = policy.max_position_weight - target_weights[ticker]
            added = min(room, increment)
            target_weights[ticker] += added
            used += added
        if used <= 0:
            break
        remaining -= used

    return target_weights


def _base_target_weight(
    result: BatchTickerResult,
    current_weight: float,
    policy: AllocationPolicy,
) -> float:
    rating = result.rating or "Hold"
    if rating == "Buy":
        return policy.buy_weight
    if rating == "Overweight":
        return policy.overweight_weight
    if rating == "Underweight":
        return min(current_weight, policy.underweight_weight)
    if rating == "Sell":
        return 0.0
    return current_weight


def _capped_target_weight(
    result: BatchTickerResult,
    current_weight: float,
    policy: AllocationPolicy,
) -> float:
    target_weight = _base_target_weight(result, current_weight, policy)
    if _RATING_SCORES.get(result.rating or "Hold", 0) > 0:
        return min(target_weight, policy.max_position_weight)
    return target_weight


def _row_for_result(
    *,
    result: BatchTickerResult,
    rank: int,
    current_value: float,
    current_weight: float,
    target_weight: float,
    total_projected_value: float,
    prices: dict[str, float],
) -> AllocationRow:
    target_value = target_weight * total_projected_value
    delta_value = target_value - current_value
    price = prices.get(result.ticker)
    quantity_delta = delta_value / price if price and price > 0 else None
    return AllocationRow(
        ticker=result.ticker,
        rating=result.rating or "Hold",
        rank=rank,
        current_value=current_value,
        current_weight=current_weight,
        target_weight=target_weight,
        target_value=target_value,
        delta_value=delta_value,
        price=price,
        quantity_delta=quantity_delta,
        recommended_action=_recommended_action(delta_value, total_projected_value),
    )


def _recommended_action(delta_value: float, total_value: float) -> RecommendedAction:
    threshold = max(1.0, total_value * 0.001)
    if delta_value > threshold:
        return "buy"
    if delta_value < -threshold:
        return "sell"
    return "hold"


def _format_number(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}"


def _format_percent(value: float | None) -> str:
    return "" if value is None else f"{value * 100:.2f}%"


def _format_quantity(value: float | None) -> str:
    if value is None:
        return ""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.4f}"
