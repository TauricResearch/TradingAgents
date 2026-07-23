"""Square-root market impact + spread (roadmap P4 / track T5): the extended
SlippageModel and the broker charging size-dependent impact at entries and
exits. Byte-identical to the old fixed-bps model when spread/impact are 0."""

import math
from datetime import timedelta

import pytest

from tests.pro_fakes import BASE_TS
from tradingagents.contracts import OHLCVBar, Timeframe
from tradingagents.pro.backtest import PendingOrder, SimBroker
from tradingagents.pro.backtest.costs import CommissionModel, LiquidityModel, SlippageModel


class TestSlippageModel:
    def test_zero_spread_impact_matches_fixed_bps(self):
        m = SlippageModel(bps=2.0)
        # fill_price_at with participation 0 == the legacy fixed-bps fill
        assert m.fill_price_at(100.0, "BUY", 0.0) == m.fill_price(100.0, "BUY")
        assert m.fill_price(100.0, "BUY") == pytest.approx(100.0 * 1.0002)
        assert m.fill_price(100.0, "SELL") == pytest.approx(100.0 * 0.9998)

    def test_spread_adds_a_fixed_half_spread_each_side(self):
        m = SlippageModel(bps=0.0, spread_bps=5.0)
        assert m.fill_price_at(100.0, "BUY", 0.0) == pytest.approx(100.0 * 1.0005)
        assert m.fill_price_at(100.0, "SELL", 0.0) == pytest.approx(100.0 * 0.9995)

    def test_impact_scales_with_sqrt_of_participation(self):
        m = SlippageModel(bps=0.0, impact_bps=10.0)
        # participation 0.25 → impact 10*sqrt(0.25)=5 bps
        assert m.fill_price_at(100.0, "BUY", 0.25) == pytest.approx(100.0 * 1.0005)
        # participation 1.0 → impact 10 bps; larger order costs strictly more
        p_small = m.fill_price_at(100.0, "BUY", 0.09)
        p_big = m.fill_price_at(100.0, "BUY", 0.64)
        assert p_big > p_small
        assert m.fill_price_at(100.0, "BUY", 1.0) == pytest.approx(100.0 * (1 + 10 / 10_000))

    def test_components_add(self):
        m = SlippageModel(bps=1.0, spread_bps=2.0, impact_bps=10.0)
        adverse = 1.0 + 2.0 + 10.0 * math.sqrt(0.16)  # 1 + 2 + 4 = 7 bps
        assert m.fill_price_at(100.0, "BUY", 0.16) == pytest.approx(
            100.0 * (1 + adverse / 10_000))


# --- broker charges impact by order size ------------------------------------


def _bar(open_, high, low, close, volume, day=0):
    return OHLCVBar(timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=day),
                    open=open_, high=high, low=low, close=close, volume=volume)


def _entry_price(volume, quantity, impact_bps):
    """Open one market order and read back the realized entry price."""
    b = SimBroker(slippage=SlippageModel(bps=0.0, impact_bps=impact_bps),
                  commission=CommissionModel(rate_bps=0),
                  liquidity=LiquidityModel(max_participation=1.0),
                  initial_equity=10_000_000.0, max_gross_exposure_pct=100.0)
    b.submit(PendingOrder(id="o", kind="market", side="BUY", quantity=quantity,
                          stop_loss=1.0, symbol="BTC-USD"))
    b.match_pending(_bar(100.0, 100.0, 100.0, 100.0, volume, day=1), 1)
    return b.positions["o"].entry_price


def test_bigger_orders_pay_more_impact_at_entry():
    small = _entry_price(volume=10_000, quantity=100, impact_bps=50.0)   # 1% ADV
    big = _entry_price(volume=10_000, quantity=2_500, impact_bps=50.0)   # 25% ADV
    assert big > small > 100.0  # both slipped up; the larger order slipped more


def test_zero_impact_leaves_entry_at_reference():
    assert _entry_price(volume=10_000, quantity=2_500, impact_bps=0.0) == 100.0


# --- per-asset cost profiles ------------------------------------------------


class TestCostProfiles:
    def test_each_asset_gets_a_tuned_profile(self):
        from tradingagents.contracts import AssetClass
        from tradingagents.pro.backtest import cost_profile_for

        gold = cost_profile_for(AssetClass.GOLD)[0]
        sol = cost_profile_for(AssetClass.SOLANA)[0]
        # gold (deep, liquid) is cheaper to cross than an alt-coin
        assert gold.spread_bps < sol.spread_bps
        assert gold.impact_bps < sol.impact_bps

    def test_returns_three_models_and_crypto_commission(self):
        from tradingagents.contracts import AssetClass
        from tradingagents.pro.backtest import (
            CommissionModel,
            LiquidityModel,
            SlippageModel,
            cost_profile_for,
        )

        slip, commission, liq = cost_profile_for(AssetClass.BITCOIN)
        assert isinstance(slip, SlippageModel)
        assert isinstance(commission, CommissionModel) and commission.rate_bps > 0
        assert isinstance(liq, LiquidityModel)

    def test_unknown_asset_falls_back_to_cautious_default(self):
        from tradingagents.pro.backtest import cost_profile_for

        slip, commission, _ = cost_profile_for("MYSTERY")
        assert slip.impact_bps > 0 and commission.rate_bps > 0
