import pytest
from datetime import datetime
from math import isclose


@pytest.mark.unit
@pytest.mark.parametrize("decision,expected", [
    ("BUY", 1), ("buy", 1), ("Buy", 1),
    ("HOLD", 0), ("hold", 0),
    ("SELL", -1), ("sell", -1),
])
def test_position_from_decision(decision, expected):
    from tradingagents.backtest.simulator import position_from_decision
    assert position_from_decision(decision) == expected


@pytest.mark.unit
def test_position_from_decision_rejects_unknown():
    from tradingagents.backtest.simulator import position_from_decision
    with pytest.raises(ValueError):
        position_from_decision("MOON")


@pytest.mark.unit
def test_compute_returns_long_position():
    from tradingagents.backtest.simulator import compute_returns
    from tradingagents.backtest.prices import Bars, Resolution
    bars = Bars(ticker="A", resolution=Resolution.DAILY, source="x",
                bars=[(datetime(2026, 4, 26), 100.0),
                      (datetime(2026, 4, 27), 101.0),
                      (datetime(2026, 4, 28),  99.0),
                      (datetime(2026, 4, 29), 105.0)])
    returns = compute_returns(bars, position=1)
    # day-over-day signed returns (no return for the first bar)
    assert len(returns) == 3
    assert isclose(returns[0], 0.01, rel_tol=1e-9)
    assert isclose(returns[1], (99 - 101) / 101, rel_tol=1e-9)
    assert isclose(returns[2], (105 - 99) / 99, rel_tol=1e-9)


@pytest.mark.unit
def test_compute_returns_short_position_inverts_sign():
    from tradingagents.backtest.simulator import compute_returns
    from tradingagents.backtest.prices import Bars, Resolution
    bars = Bars(ticker="A", resolution=Resolution.DAILY, source="x",
                bars=[(datetime(2026, 4, 26), 100.0),
                      (datetime(2026, 4, 27), 110.0)])
    returns = compute_returns(bars, position=-1)
    # Long would be +0.10; short flips to -0.10.
    assert isclose(returns[0], -0.10, rel_tol=1e-9)


@pytest.mark.unit
def test_compute_returns_flat_position_is_all_zeros():
    from tradingagents.backtest.simulator import compute_returns
    from tradingagents.backtest.prices import Bars, Resolution
    bars = Bars(ticker="A", resolution=Resolution.DAILY, source="x",
                bars=[(datetime(2026, 4, 26), 100.0),
                      (datetime(2026, 4, 27), 110.0)])
    returns = compute_returns(bars, position=0)
    assert returns == [0.0]


@pytest.mark.unit
def test_total_return_long_simple():
    from tradingagents.backtest.simulator import total_return
    assert isclose(total_return(entry=100.0, exit=110.0, position=1),
                   0.10, rel_tol=1e-9)


@pytest.mark.unit
def test_total_return_short_inverts():
    from tradingagents.backtest.simulator import total_return
    assert isclose(total_return(entry=100.0, exit=110.0, position=-1),
                   -0.10, rel_tol=1e-9)


@pytest.mark.unit
def test_total_return_flat_is_zero():
    from tradingagents.backtest.simulator import total_return
    assert total_return(entry=100.0, exit=110.0, position=0) == 0.0


@pytest.mark.unit
def test_sharpe_known_series():
    """Sharpe = mean(r) / stdev(r) * annualization_factor."""
    from tradingagents.backtest.simulator import sharpe_ratio
    from tradingagents.backtest.prices import Resolution
    # constant positive returns → stdev=0 → defined as 0 (no risk-free reward)
    assert sharpe_ratio([0.01] * 5, resolution=Resolution.DAILY) == 0.0
    # known series: alternating ±1% → mean=0 → Sharpe=0
    assert sharpe_ratio([0.01, -0.01] * 5, resolution=Resolution.DAILY) == 0.0
    # mean > 0, stdev > 0 → positive
    s = sharpe_ratio([0.01, 0.02, 0.005, 0.015], resolution=Resolution.DAILY)
    assert s > 0


@pytest.mark.unit
def test_max_drawdown_known_curve():
    from tradingagents.backtest.simulator import max_drawdown
    # Returns: +10%, -20%, +5%
    # Cumulative: 1.0 -> 1.10 -> 0.88 -> 0.924
    # Peak before dd: 1.10; trough: 0.88; dd = (0.88/1.10) - 1 = -0.2
    dd = max_drawdown([0.10, -0.20, 0.05])
    assert isclose(dd, -0.2, rel_tol=1e-9)


@pytest.mark.unit
def test_max_drawdown_no_drawdown_returns_zero():
    from tradingagents.backtest.simulator import max_drawdown
    assert max_drawdown([0.01, 0.02, 0.005]) == 0.0


@pytest.mark.unit
def test_win_rate():
    from tradingagents.backtest.simulator import win_rate
    assert win_rate([0.01, -0.01, 0.02, 0.0, -0.005]) == pytest.approx(2 / 5)
    assert win_rate([]) == 0.0
