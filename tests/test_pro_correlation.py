"""Correlation-exposure filter (roadmap P3 / track T4): the pure Pearson +
CorrelationGuard math, and the engine vetoing a fresh entry when the candidate
is too correlated with an already-open symbol (look-ahead-safe)."""

from datetime import timedelta

import pytest

from tests.pro_fakes import BASE_TS
from tradingagents.contracts import (
    AssetClass,
    OHLCVBar,
    ProConfig,
    RiskLimits,
    Timeframe,
    TradingMode,
)
from tradingagents.pro.backtest import (
    BarReplay,
    CorrelationGuard,
    PortfolioEngine,
    PortfolioReplay,
    SimBroker,
    build_strategy,
    pearson,
)

CONFIG = ProConfig(asset=AssetClass.BITCOIN, mode=TradingMode.BACKTEST,
                   max_debate_rounds=1,
                   risk=RiskLimits(max_position_pct_equity=50.0))


class TestPearson:
    def test_perfect_positive_and_negative(self):
        assert pearson([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)
        assert pearson([1, 2, 3, 4], [8, 6, 4, 2]) == pytest.approx(-1.0)

    def test_undefined_cases_return_zero(self):
        assert pearson([1, 2, 3], [1, 1, 1]) == 0.0   # constant series
        assert pearson([1, 2], [1, 2, 3]) == 0.0        # length mismatch
        assert pearson([1], [1]) == 0.0                 # too short


class TestGuard:
    def test_vetoes_when_correlated_above_threshold(self):
        g = CorrelationGuard(max_correlation=0.8, lookback=3)
        series = {"BTC": [0.01, 0.02, -0.01, 0.03], "ETH": [0.01, 0.02, -0.01, 0.03]}
        assert g.allow("ETH", ["BTC"], series) is False  # corr 1.0 > 0.8

    def test_allows_when_uncorrelated(self):
        g = CorrelationGuard(max_correlation=0.8, lookback=4)
        # a steady trend vs an oscillator → correlation near zero
        series = {"BTC": [1.0, 2.0, 3.0, 4.0, 5.0], "ETH": [1.0, -1.0, 1.0, -1.0, 1.0]}
        assert abs(pearson(series["BTC"], series["ETH"])) < 0.8
        assert g.allow("ETH", ["BTC"], series) is True

    def test_allows_on_insufficient_history(self):
        g = CorrelationGuard(max_correlation=0.5, lookback=3)
        assert g.allow("ETH", ["BTC"], {"BTC": [0.01, 0.02, 0.03]}) is True  # no ETH
        assert g.allow("ETH", ["BTC"], {"ETH": [0.01], "BTC": [0.01]}) is True

    def test_rejects_bad_config(self):
        with pytest.raises(ValueError):
            CorrelationGuard(max_correlation=1.5)
        with pytest.raises(ValueError):
            CorrelationGuard(lookback=1)


# --- engine applies the guard -----------------------------------------------


def _uptrend(n, p0, start=BASE_TS):
    bars, price = [], p0
    for i in range(n):
        price += 2.0
        bars.append(OHLCVBar(
            timeframe=Timeframe.D1, start=start + timedelta(days=i),
            open=price, high=price + 0.5, low=price - 0.5, close=price,
            volume=1_000_000.0))
    return bars


def _lagged_portfolio():
    # identical price SHAPE (→ ~perfect return correlation) but ETH's bars are
    # calendar-shifted 5 days later, so its breakout fires ~5 steps after BTC's
    # — when ETH breaks out, BTC's trend position is still open → guard bites.
    btc = _uptrend(160, 1000.0)
    eth = _uptrend(160, 1000.0, start=BASE_TS + timedelta(days=5))
    return PortfolioReplay({
        "BTC-USD": BarReplay("BTC-USD", AssetClass.BITCOIN, btc, window=40,
                             precompute_indicators=True),
        "ETH-USD": BarReplay("ETH-USD", AssetClass.BITCOIN, eth, window=40,
                             precompute_indicators=True),
    })


def _strategy():
    return build_strategy("trend_following_v1", {
        "donchian_period": 20, "stop_atr_mult": 2.0, "trail_pct": 0.05,
        "risk_pct": 1.0, "allow_short": "no"})


def _broker():
    return SimBroker(initial_equity=100_000.0, max_gross_exposure_pct=100.0)


def _overlap_pairs(trades):
    """Count BTC/ETH trade pairs whose holding intervals overlap in time —
    i.e. moments the portfolio held both correlated bets at once."""
    btc = [(t.opened_at, t.closed_at) for t in trades if t.symbol == "BTC-USD"]
    eth = [(t.opened_at, t.closed_at) for t in trades if t.symbol == "ETH-USD"]
    return sum(1 for bo, bc in btc for eo, ec in eth if bo <= ec and eo <= bc)


def test_guard_reduces_simultaneous_correlated_exposure():
    guarded = PortfolioEngine(
        _lagged_portfolio(), _strategy(), CONFIG, broker=_broker(),
        min_history=40,
        corr_guard=CorrelationGuard(max_correlation=0.5, lookback=30)).run()
    unguarded = PortfolioEngine(
        _lagged_portfolio(), _strategy(), CONFIG, broker=_broker(),
        min_history=40).run()
    # the guard fired (blocked entries while a correlated symbol was open) and
    # cut the time the two correlated bets were held simultaneously
    assert guarded.rejections.get("correlation", 0) > 0
    assert _overlap_pairs(guarded.trades) < _overlap_pairs(unguarded.trades)
