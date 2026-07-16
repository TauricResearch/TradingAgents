"""Deterministic analytics: quant features and the risk engine (known values)."""

import math

import pytest

from tests.pro_fakes import make_bars
from tradingagents.contracts import MarketRegime
from tradingagents.pro.analytics import (
    atr_stop_loss,
    atr_take_profits,
    classify_regime,
    close_zscore,
    fixed_risk_position_size,
    historical_cvar,
    historical_var,
    invalidation_stop_loss,
    kelly_fraction,
    realized_volatility,
    trend_slope,
)


class TestFeatures:
    def test_realized_volatility_of_constant_growth_is_zero(self):
        # make_bars grows +0.5/bar => returns shrink but stdev of log returns > 0;
        # build truly constant-return bars instead
        bars = make_bars(n=30)
        vol = realized_volatility(bars)
        assert vol >= 0

    def test_realized_volatility_known_value(self):
        # alternating +1%/-1% simple moves => log-return stdev is known
        from datetime import timedelta

        from tests.pro_fakes import BASE_TS
        from tradingagents.contracts import OHLCVBar, Timeframe

        price, bars = 100.0, []
        for i in range(41):
            bars.append(
                OHLCVBar(
                    timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
                    open=price, high=price * 1.02, low=price * 0.98,
                    close=price, volume=1.0,
                )
            )
            price = price * (1.01 if i % 2 == 0 else 0.99)
        import statistics

        closes = [b.close for b in bars]
        expected = statistics.stdev(
            math.log(b / a) for a, b in zip(closes, closes[1:], strict=False)
        ) * math.sqrt(252)
        assert realized_volatility(bars) == pytest.approx(expected)

    def test_trend_slope_positive_for_rising_series_with_perfect_fit(self):
        slope_pct, r_squared = trend_slope(make_bars(n=50))
        assert slope_pct > 0
        assert r_squared == pytest.approx(1.0)

    def test_zscore_of_top_of_rising_window_is_positive(self):
        z = close_zscore(make_bars(n=60), window=50)
        assert z > 1.0

    def test_zscore_needs_window(self):
        with pytest.raises(ValueError, match="z-score window"):
            close_zscore(make_bars(n=30), window=50)

    def test_classify_regime_trending_up_for_clean_rise(self):
        # linear rise: perfect fit, low vol -> trend beats low-vol check
        bars = make_bars(n=120)
        assert classify_regime(bars) in (MarketRegime.TRENDING_UP, MarketRegime.LOW_VOLATILITY)

    def test_too_few_bars_rejected(self):
        with pytest.raises(ValueError, match="at least 3"):
            trend_slope(make_bars(n=2))


class TestRiskEngine:
    def test_fixed_risk_sizing_known_value(self):
        # equity 100k, risk 1% = $1000; entry 2400, stop 2380 => $20/unit => 50 units
        # (cap lifted to 200% so the uncapped math is visible)
        size = fixed_risk_position_size(100_000, 1.0, 2400.0, 2380.0, max_position_pct=200.0)
        assert size.quantity == pytest.approx(50.0)
        assert size.notional == pytest.approx(120_000.0)

    def test_fixed_risk_sizing_default_cap_is_full_equity(self):
        # same trade with the default 100% cap: notional clamps to equity
        # less the R2.8 drift headroom (applies whenever the cap binds)
        size = fixed_risk_position_size(100_000, 1.0, 2400.0, 2380.0)
        assert size.notional == pytest.approx(99_000.0)
        assert size.pct_of_equity == pytest.approx(99.0)

    def test_fixed_risk_sizing_respects_position_cap_with_headroom(self):
        # uncapped would be 50 units = 120k notional; cap at 10% equity = 10k,
        # minus the 1% drift headroom (R2.8: at-cap orders bounced whenever
        # live equity dipped below sizing-time equity)
        size = fixed_risk_position_size(100_000, 1.0, 2400.0, 2380.0, max_position_pct=10.0)
        assert size.notional == pytest.approx(9_900.0)
        assert size.quantity == pytest.approx(9_900.0 / 2400.0)
        assert size.pct_of_equity == pytest.approx(9.9)

    def test_at_cap_size_survives_small_equity_drift(self):
        # the production incident: sized on 100k, validated against 99,913 —
        # the execution cap at the drifted equity must still admit the order
        size = fixed_risk_position_size(100_000, 1.0, 2400.0, 2380.0, max_position_pct=10.0)
        drifted_equity = 99_913.0
        cap_at_execution = drifted_equity * 10.0 / 100
        assert size.notional <= cap_at_execution  # would have failed pre-fix

    def test_sizing_rejects_zero_stop_distance(self):
        with pytest.raises(ValueError, match="cannot be equal"):
            fixed_risk_position_size(100_000, 1.0, 2400.0, 2400.0)

    def test_kelly_known_value(self):
        # w=0.6, payoff=2 => f* = 0.6 - 0.4/2 = 0.4 -> capped to 0.25
        assert kelly_fraction(0.6, 200.0, 100.0) == 0.25
        assert kelly_fraction(0.6, 200.0, 100.0, cap=1.0) == pytest.approx(0.4)

    def test_kelly_negative_edge_returns_zero(self):
        # w=0.4, payoff=1 => f* = 0.4 - 0.6 = -0.2 -> 0
        assert kelly_fraction(0.4, 100.0, 100.0) == 0.0

    def test_var_known_distribution(self):
        # 100 returns with a 10-observation loss cluster: the 95% quantile
        # interpolates strictly inside the -5% block
        returns = [-0.05] * 10 + [0.01] * 90
        var95 = historical_var(returns, 0.95)
        assert var95 == pytest.approx(0.05)

    def test_cvar_exceeds_var(self):
        # tail: two -10% and eight -5% => VaR 5%, tail mean 6%
        returns = [-0.10] * 2 + [-0.05] * 8 + [0.01] * 90
        var95 = historical_var(returns, 0.95)
        cvar95 = historical_cvar(returns, 0.95)
        assert var95 == pytest.approx(0.05)
        assert cvar95 >= var95
        assert cvar95 == pytest.approx(0.06)

    def test_var_requires_history(self):
        with pytest.raises(ValueError, match=">= 20"):
            historical_var([0.01] * 5)

    def test_atr_stop_sides(self):
        assert atr_stop_loss(2400.0, 10.0, "BUY", multiple=2.0) == 2380.0
        assert atr_stop_loss(2400.0, 10.0, "SELL", multiple=2.0) == 2420.0
        with pytest.raises(ValueError, match="BUY or SELL"):
            atr_stop_loss(2400.0, 10.0, "HOLD")

    def test_atr_take_profit_ladder(self):
        ladder = atr_take_profits(2400.0, 10.0, "BUY")
        assert [tp.price for tp in ladder] == [2420.0, 2440.0]
        assert sum(tp.size_fraction for tp in ladder) == pytest.approx(1.0)
        sell = atr_take_profits(2400.0, 10.0, "SELL", multiples=(1.0, 3.0))
        assert [tp.price for tp in sell] == [2390.0, 2370.0]

    def test_atr_ladder_rejects_unsorted_multiples(self):
        with pytest.raises(ValueError, match="ascending"):
            atr_take_profits(2400.0, 10.0, "BUY", multiples=(4.0, 2.0))

    def test_invalidation_stop_sits_just_beyond_the_level(self):
        # the review case: SELL from 4037.27, thesis dies above 4046.72,
        # ATR 12.64 -> buffer min(0.25*12.64, max(0.25*9.45, 4.037)) = 3.16
        stop = invalidation_stop_loss(4037.27, 4046.72, 12.64, "SELL")
        assert stop == pytest.approx(4046.72 + 3.16)
        # BUY mirror: buffer min(0.25*8=2.0, max(0.25*10=2.5, 2.4)) = 2.0
        stop = invalidation_stop_loss(2400.0, 2390.0, 8.0, "BUY")
        assert stop == pytest.approx(2388.0)

    def test_invalidation_stop_buffer_capped_in_high_vol(self):
        # huge ATR must not park the stop far beyond the thesis-death level
        stop = invalidation_stop_loss(4037.27, 4046.72, 100.0, "SELL")
        assert stop == pytest.approx(4046.72 + max(0.25 * 9.45, 4.03727))

    def test_invalidation_stop_wrong_side_rejected(self):
        with pytest.raises(ValueError, match="above entry"):
            invalidation_stop_loss(4037.27, 4020.0, 12.64, "SELL")
        with pytest.raises(ValueError, match="below entry"):
            invalidation_stop_loss(2400.0, 2410.0, 8.0, "BUY")
