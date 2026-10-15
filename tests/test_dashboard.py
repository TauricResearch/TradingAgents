from datetime import date

import pytest

from tradingagents.dashboard import (
    DecisionThresholds,
    Holding,
    PortfolioStore,
    action_for_holding,
    holding_metrics,
)


def make_holding(**overrides):
    values = {
        "ticker": "AAPL",
        "market": "USA",
        "shares": 2,
        "average_purchase_price": 100,
        "currency": "USD",
        "purchase_date": date(2026, 1, 2),
    }
    values.update(overrides)
    return Holding.model_validate(values)


@pytest.mark.unit
def test_portfolio_store_round_trip_and_schema(tmp_path):
    store = PortfolioStore(tmp_path / "logs" / "portfolio.json")
    saved = store.add(make_holding())
    assert saved.holdings[0].ticker == "AAPL"
    assert store.load().version == 1
    assert store.load().holdings[0].currency == "USD"


@pytest.mark.unit
def test_validation_rejects_unknown_market_and_non_positive_shares():
    with pytest.raises(ValueError):
        make_holding(market="DE")
    with pytest.raises(ValueError):
        make_holding(shares=0)


@pytest.mark.unit
def test_metrics_and_threshold_actions_are_grounded():
    item = make_holding()
    metrics = holding_metrics(item, 110)
    assert metrics["profit_loss"] == 20
    assert metrics["profit_loss_pct"] == pytest.approx(10)
    thresholds = DecisionThresholds()
    assert action_for_holding(item, 110, thresholds) == "TAKE PROFIT"
    assert action_for_holding(item, 97, thresholds) == "REVIEW SELL"
    assert action_for_holding(item, None, thresholds) == "WATCH"


@pytest.mark.unit
def test_duplicate_and_missing_holding_operations_are_explicit(tmp_path):
    store = PortfolioStore(tmp_path / "portfolio.json")
    store.add(make_holding())
    with pytest.raises(ValueError):
        store.add(make_holding())
    with pytest.raises(KeyError):
        store.remove("MSFT")
