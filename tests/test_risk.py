from datetime import date, timedelta
from decimal import Decimal

import pytest

from tradingagents.risk import close_returns, forecast_volatility, scale_equity_targets


def _history(changes):
    prices = [Decimal("100")]
    for change in changes:
        prices.append(prices[-1] * (Decimal("1") + Decimal(str(change))))
    start = date(2026, 1, 2)
    return tuple((start + timedelta(days=index), price) for index, price in enumerate(prices))


def test_close_returns_requires_forty_aligned_observations():
    with pytest.raises(ValueError, match="40 aligned return observations"):
        close_returns({"AAPL": _history([0.01] * 39)})


def test_forecast_uses_signed_equity_and_option_exposure():
    history = {
        "AAPL": _history([0.01, -0.01] * 20),
        "MSFT": _history([-0.01, 0.01] * 20),
    }
    returns = close_returns(history)
    unhedged = forecast_volatility(
        {"AAPL": Decimal("50000")}, Decimal("100000"), returns
    )
    hedged = forecast_volatility(
        {"AAPL": Decimal("50000"), "MSFT": Decimal("50000")},
        Decimal("100000"),
        returns,
    )
    assert hedged < unhedged


def test_scaling_preserves_equity_target_ratios_and_respects_limits():
    history = {
        "AAPL": _history([0.02, -0.02] * 20),
        "MSFT": _history([0.01, -0.01] * 20),
    }
    result = scale_equity_targets(
        {"AAPL": Decimal("80000"), "MSFT": Decimal("-40000")},
        {"AAPL": Decimal("10000")},
        Decimal("100000"),
        history,
        Decimal("0.15"),
        Decimal("0.20"),
        Decimal("2.0"),
    )
    assert result.targets["AAPL"] == -Decimal("2") * result.targets["MSFT"]
    assert result.forecast_volatility <= Decimal("0.15") + Decimal("0.000001")
    assert result.gross_leverage <= Decimal("2.0")


def test_forecast_rejects_exposure_without_aligned_market_history():
    returns = close_returns({"AAPL": _history([0.01, -0.01] * 20)})

    with pytest.raises(ValueError, match="missing return history"):
        forecast_volatility({"MISSING": Decimal("50000")}, Decimal("100000"), returns)


def test_scaling_rejects_gross_cap_below_hedging_minimum():
    history = {"AAPL": _history([0.01, -0.01] * 20)}

    with pytest.raises(ValueError, match="portfolio volatility target is infeasible"):
        scale_equity_targets(
            {"AAPL": Decimal("-100000")},
            {"AAPL": Decimal("100000")},
            Decimal("100000"),
            history,
            Decimal("0.05"),
            Decimal("0.20"),
            Decimal("1.2"),
        )


@pytest.mark.parametrize(
    ("target", "maximum", "gross", "message"),
    [
        (Decimal("0"), Decimal("0.20"), Decimal("2.0"), "target volatility must be positive"),
        (Decimal("0.20"), Decimal("0"), Decimal("2.0"), "maximum volatility must be positive"),
        (Decimal("0.20"), Decimal("0.25"), Decimal("0"), "maximum gross leverage must be positive"),
    ],
)
def test_scaling_rejects_non_positive_risk_limits(target, maximum, gross, message):
    with pytest.raises(ValueError, match=message):
        scale_equity_targets(
            {"AAPL": Decimal("100000")},
            {},
            Decimal("100000"),
            {"AAPL": _history([0.01, -0.01] * 20)},
            target,
            maximum,
            gross,
        )


def test_scaling_preserves_trailing_zero_target():
    history = {
        "AAPL": _history([0.01, -0.01] * 20),
        "ZERO": _history([0.01, -0.01] * 20),
    }

    result = scale_equity_targets(
        {"AAPL": Decimal("80000"), "ZERO": Decimal("0")},
        {},
        Decimal("100000"),
        history,
        Decimal("0.15"),
        Decimal("0.20"),
        Decimal("2.0"),
    )

    assert result.targets["ZERO"] == Decimal("0")
