"""Perpetual funding (roadmap P4 / track T5): the FundingModel accrual math,
the broker charging it on open positions, and the engine accruing it per bar
when opted in (spot runs, with no FundingModel, are unaffected)."""

from datetime import timedelta

import pytest

from tests.pro_fakes import BASE_TS
from tradingagents.contracts import (
    AssetClass,
    OHLCVBar,
    ProConfig,
    Timeframe,
    TradingMode,
)
from tradingagents.pro.backtest import (
    BarReplay,
    FundingModel,
    PendingOrder,
    SimBroker,
)
from tradingagents.pro.backtest.costs import CommissionModel, LiquidityModel, SlippageModel


class TestFundingModel:
    def test_long_pays_short_receives_when_rate_positive(self):
        f = FundingModel(annual_rate_pct=10.95)  # ~0.03%/day
        # 1 year of holding 10,000 notional → ~10.95% of it
        assert f.cash_delta(10_000, "BUY", 365 * 24) == pytest.approx(-1095.0)
        assert f.cash_delta(10_000, "SELL", 365 * 24) == pytest.approx(1095.0)

    def test_scales_with_hours_and_notional(self):
        f = FundingModel(annual_rate_pct=8.0)
        base = f.cash_delta(1_000, "BUY", 24)
        assert f.cash_delta(1_000, "BUY", 48) == pytest.approx(2 * base)
        assert f.cash_delta(2_000, "BUY", 24) == pytest.approx(2 * base)

    def test_zero_rate_is_free(self):
        assert FundingModel().cash_delta(10_000, "BUY", 999) == 0.0

    def test_rejects_negative_inputs(self):
        with pytest.raises(ValueError):
            FundingModel(1.0).cash_delta(-1, "BUY", 1)


def _broker():
    return SimBroker(slippage=SlippageModel(bps=0), commission=CommissionModel(rate_bps=0),
                     liquidity=LiquidityModel(max_participation=1.0),
                     initial_equity=1_000_000.0)


def _bar(price, day):
    return OHLCVBar(timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=day),
                    open=price, high=price + 1, low=price - 1, close=price,
                    volume=1_000_000.0)


class TestBrokerAccrual:
    def test_accrue_funding_debits_a_long_and_moves_cash(self):
        b = _broker()
        b.submit(PendingOrder(id="p", kind="market", side="BUY", quantity=10,
                              stop_loss=1.0, symbol="BTC-USD"))
        b.match_pending(_bar(100.0, 1), 1)  # 1000 notional long
        before = b.cash_pnl
        delta = b.accrue_funding(FundingModel(annual_rate_pct=36.5),
                                 {"BTC-USD": 100.0}, hours=24)
        assert delta < 0                       # long pays
        assert b.cash_pnl == pytest.approx(before + delta)
        # ~0.1%/day on 1000 notional ≈ -1.0
        assert delta == pytest.approx(-1.0, abs=0.01)


# --- engine opt-in ----------------------------------------------------------


def _trend_bars(n=120, p0=1000.0):
    bars, price = [], p0
    for i in range(n):
        price += 2.0
        bars.append(OHLCVBar(timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
                             open=price, high=price + 0.5, low=price - 0.5, close=price,
                             volume=1_000_000.0))
    return bars


def _run(funding):
    from tradingagents.pro.backtest import build_strategy
    from tradingagents.pro.backtest.engine import BacktestEngine

    replay = BarReplay("BTC-USD", AssetClass.BITCOIN, _trend_bars(), window=40,
                       precompute_indicators=True)
    config = ProConfig(asset=AssetClass.BITCOIN, mode=TradingMode.BACKTEST,
                       max_debate_rounds=1)
    strat = build_strategy("trend_following_v1", {
        "donchian_period": 20, "stop_atr_mult": 2.0, "trail_pct": 0.05,
        "risk_pct": 1.0, "allow_short": "no"})
    return BacktestEngine(None, config, replay, strategy=strat, min_history=40,
                          funding=funding).run()


def test_funding_drags_returns_vs_no_funding():
    # a positive funding rate charges the (long) trend strategy while it holds,
    # so net return is strictly worse than the fee-free (no-funding) run
    base = _run(funding=None)
    charged = _run(funding=FundingModel(annual_rate_pct=50.0))
    assert base.trades and charged.trades
    assert charged.final_equity < base.final_equity
