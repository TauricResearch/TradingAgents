import pytest

from tradingagents.allocation import build_allocation_plan
from tradingagents.batch import BatchTickerResult, PortfolioHolding


def _result(ticker, rating, market_value):
    return BatchTickerResult(
        ticker=ticker,
        status="success",
        rating=rating,
        holding=PortfolioHolding(ticker=ticker, market_value=market_value),
    )


def _failed_result(ticker):
    return BatchTickerResult(
        ticker=ticker,
        status="failed",
        error="provider timeout",
    )


def test_current_portfolio_value_includes_holdings_and_available_cash():
    plan = build_allocation_plan(
        [
            _result("AAPL", "Buy", 2000),
            _result("MSFT", "Hold", 3000),
        ],
        available_cash=1000,
        prices={"AAPL": 100, "MSFT": 200},
    )

    assert plan.total_current_value == 6000
    assert plan.total_projected_value == 6000
    assert plan.leftover_cash >= 0


def test_buy_and_overweight_candidates_receive_positive_target_weights():
    plan = build_allocation_plan(
        [
            _result("AAPL", "Buy", 1000),
            _result("MSFT", "Overweight", 1000),
            _result("CASH", "Hold", 0),
        ],
        available_cash=10000,
        prices={"AAPL": 100, "MSFT": 200, "CASH": 1},
    )

    assert plan.row_for("AAPL").target_weight > 0
    assert plan.row_for("MSFT").target_weight > 0
    assert plan.row_for("AAPL").recommended_action == "buy"
    assert plan.row_for("MSFT").recommended_action == "buy"


def test_hold_keeps_approximately_current_weight():
    plan = build_allocation_plan(
        [
            _result("AAPL", "Hold", 3000),
            _result("MSFT", "Buy", 1000),
        ],
        available_cash=1000,
        prices={"AAPL": 100, "MSFT": 200},
    )

    aapl = plan.row_for("AAPL")
    assert aapl.target_weight == pytest.approx(aapl.current_weight, abs=0.000001)
    assert aapl.recommended_action == "hold"


def test_sell_and_underweight_targets_are_lower_or_zero_weight():
    plan = build_allocation_plan(
        [
            _result("AAPL", "Sell", 3000),
            _result("MSFT", "Underweight", 2000),
            _result("NVDA", "Buy", 1000),
        ],
        available_cash=0,
        prices={"AAPL": 100, "MSFT": 200, "NVDA": 500},
    )

    assert plan.row_for("AAPL").target_weight == 0
    assert plan.row_for("AAPL").recommended_action == "sell"
    assert plan.row_for("MSFT").target_weight < plan.row_for("MSFT").current_weight
    assert plan.row_for("MSFT").recommended_action == "sell"


def test_target_weights_plus_cash_weight_sum_to_one_after_normalization():
    plan = build_allocation_plan(
        [
            _result("AAPL", "Buy", 1000),
            _result("MSFT", "Overweight", 1000),
            _result("TSLA", "Sell", 1000),
        ],
        available_cash=5000,
        prices={"AAPL": 100, "MSFT": 200, "TSLA": 300},
    )

    assert round(sum(row.target_weight for row in plan.rows) + plan.target_cash_weight, 6) == 1.0
    assert plan.row_for("AAPL").recommended_action == "buy"
    assert plan.leftover_cash >= 0


def test_duplicate_success_tickers_are_rejected_before_allocation():
    results = [
        _result("AAPL", "Buy", 1000),
        _result("AAPL", "Hold", 2000),
    ]

    with pytest.raises(ValueError, match="(?i)duplicate.*ticker"):
        build_allocation_plan(
            results,
            available_cash=1000,
            prices={"AAPL": 100},
        )


def test_mixed_status_duplicate_tickers_are_rejected_before_allocation():
    results = [
        _result("AAPL", "Buy", 1000),
        _failed_result("aapl"),
    ]

    with pytest.raises(ValueError, match="(?i)duplicate.*ticker"):
        build_allocation_plan(
            results,
            available_cash=1000,
            prices={"AAPL": 100},
        )


def test_negative_available_cash_is_rejected():
    with pytest.raises(ValueError, match="available_cash"):
        build_allocation_plan(
            [_result("AAPL", "Buy", 1000)],
            available_cash=-1,
            prices={"AAPL": 100},
        )


def test_buy_plan_uses_whole_shares_and_reports_leftover_cash():
    plan = build_allocation_plan(
        [
            BatchTickerResult(
                ticker="AAPL",
                status="success",
                rating="Buy",
                holding=PortfolioHolding(ticker="AAPL", market_value=0),
            )
        ],
        available_cash=250,
        prices={"AAPL": 90},
    )

    row = plan.row_for("AAPL")
    assert row.quantity_delta == 2
    assert isinstance(row.quantity_delta, int)
    assert plan.leftover_cash == 70


def test_buy_cost_never_exceeds_available_cash_plus_sell_proceeds():
    plan = build_allocation_plan(
        [
            _result("AAPL", "Buy", 0),
            _result("MSFT", "Buy", 0),
            _result("TSLA", "Sell", 500),
        ],
        available_cash=25,
        prices={"AAPL": 90, "MSFT": 80, "TSLA": 100},
    )

    buy_cost = sum(
        row.quantity_delta * row.price
        for row in plan.rows
        if row.quantity_delta is not None and row.quantity_delta > 0
    )
    sell_proceeds = sum(
        abs(row.quantity_delta) * row.price
        for row in plan.rows
        if row.quantity_delta is not None and row.quantity_delta < 0
    )

    assert all(
        float(row.quantity_delta).is_integer()
        for row in plan.rows
        if row.quantity_delta is not None
    )
    assert buy_cost <= 25 + sell_proceeds
    assert plan.leftover_cash == pytest.approx(25 + sell_proceeds - buy_cost)
    assert plan.leftover_cash >= 0


def test_missing_price_keeps_recommendation_without_quantity_delta_and_uses_market_value():
    plan = build_allocation_plan(
        [_result("AAPL", "Buy", 1200)],
        available_cash=300,
        prices={},
    )

    row = plan.row_for("AAPL")
    assert row.current_value == 1200
    assert row.rating == "Buy"
    assert row.quantity_delta is None
    assert plan.leftover_cash == 300
