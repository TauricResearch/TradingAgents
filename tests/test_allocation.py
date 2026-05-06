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
