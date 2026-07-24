"""Capital allocators (roadmap P3 / track T4): per-symbol notional budgets
layered on the shared broker caps, plus the engine trimming an entry to the
budget (0 → vetoed)."""

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
    EqualWeightAllocator,
    PortfolioEngine,
    PortfolioReplay,
    SimBroker,
    WeightedAllocator,
    build_strategy,
)

CONFIG = ProConfig(asset=AssetClass.BITCOIN, mode=TradingMode.BACKTEST,
                   max_debate_rounds=1,
                   risk=RiskLimits(max_position_pct_equity=50.0))


class TestEqualWeight:
    def test_splits_equity_evenly_and_nets_existing(self):
        alloc = EqualWeightAllocator(n_symbols=4)
        # 1/4 of 100k = 25k budget; 10k already open → 15k headroom
        assert alloc.max_notional("BTC", 100_000, 0) == 25_000
        assert alloc.max_notional("BTC", 100_000, 10_000) == 15_000

    def test_full_symbol_gets_zero_headroom(self):
        alloc = EqualWeightAllocator(n_symbols=2)
        assert alloc.max_notional("BTC", 100_000, 60_000) == 0.0  # over its 50k

    def test_max_weight_pct_can_tighten_below_equal_share(self):
        alloc = EqualWeightAllocator(n_symbols=2, max_weight_pct=30.0)
        # equal share 50% but capped at 30%
        assert alloc.max_notional("BTC", 100_000, 0) == 30_000

    def test_rejects_bad_config(self):
        with pytest.raises(ValueError):
            EqualWeightAllocator(n_symbols=0)
        with pytest.raises(ValueError):
            EqualWeightAllocator(n_symbols=2, max_weight_pct=150)


class TestWeighted:
    def test_per_symbol_caps_and_uncapped_default(self):
        alloc = WeightedAllocator({"BTC": 0.6})
        assert alloc.max_notional("BTC", 100_000, 0) == 60_000
        assert alloc.max_notional("ETH", 100_000, 0) == float("inf")  # uncapped

    def test_rejects_out_of_range_weight(self):
        with pytest.raises(ValueError):
            WeightedAllocator({"BTC": 1.5})


# --- engine applies the budget ----------------------------------------------


def _uptrend(n, p0):
    bars, price = [], p0
    for i in range(n):
        price += 2.0
        bars.append(OHLCVBar(
            timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
            open=price, high=price + 0.5, low=price - 0.5, close=price,
            volume=1_000_000.0))
    return bars


def _portfolio():
    return PortfolioReplay({
        "BTC-USD": BarReplay("BTC-USD", AssetClass.BITCOIN, _uptrend(160, 1000.0),
                             window=40, precompute_indicators=True),
        "ETH-USD": BarReplay("ETH-USD", AssetClass.BITCOIN, _uptrend(160, 2000.0),
                             window=40, precompute_indicators=True),
    })


def _strategy():
    # high risk_pct so sizing WANTS more than the allocator allows → the cap bites
    return build_strategy("trend_following_v1", {
        "donchian_period": 20, "stop_atr_mult": 2.0, "trail_pct": 0.05,
        "risk_pct": 3.0, "allow_short": "no"})


def _broker():
    # generous gross cap so the ALLOCATOR (not the broker gross cap) is what
    # binds position size in these tests
    return SimBroker(initial_equity=100_000.0, max_gross_exposure_pct=100.0)


def test_allocator_caps_per_symbol_notional_in_the_engine():
    # a tight 15%/symbol budget: no entry's notional may exceed 15% of equity
    # at its open (bounded above by 15% of PEAK equity across the run)
    alloc = EqualWeightAllocator(n_symbols=2, max_weight_pct=15.0)
    res = PortfolioEngine(_portfolio(), _strategy(), CONFIG, broker=_broker(),
                          min_history=40, allocator=alloc).run()
    assert res.trades  # it still traded
    peak_equity = max(res.equity_curve)
    for t in res.trades:
        assert t.entry_price * t.quantity <= 0.15 * peak_equity + 1.0


def test_no_allocator_allows_larger_positions_than_a_tight_budget():
    unbudgeted = PortfolioEngine(_portfolio(), _strategy(), CONFIG,
                                 broker=_broker(), min_history=40).run()
    budgeted = PortfolioEngine(_portfolio(), _strategy(), CONFIG,
                               broker=_broker(), min_history=40,
                               allocator=EqualWeightAllocator(2, max_weight_pct=10.0)).run()
    biggest_unbudgeted = max(t.entry_price * t.quantity for t in unbudgeted.trades)
    biggest_budgeted = max(t.entry_price * t.quantity for t in budgeted.trades)
    assert biggest_budgeted < biggest_unbudgeted  # the budget shrank positions


# --- volatility-aware allocators (track T2 / risk realism) -------------------


def test_inverse_vol_weights_are_risk_parity():
    from tradingagents.pro.backtest import InverseVolAllocator

    # symbol "a" is half as volatile as "b" → twice the notional (equal risk)
    alloc = InverseVolAllocator(vol_by_symbol={"a": 0.01, "b": 0.02})
    a = alloc.max_notional("a", 90_000.0, 0.0)
    b = alloc.max_notional("b", 90_000.0, 0.0)
    assert a == pytest.approx(60_000.0)   # weight 2/3 of 90k
    assert b == pytest.approx(30_000.0)   # weight 1/3 of 90k
    # existing notional is netted out of the remaining budget
    assert alloc.max_notional("a", 90_000.0, 50_000.0) == pytest.approx(10_000.0)


def test_inverse_vol_unknown_symbol_is_uncapped():
    from tradingagents.pro.backtest import InverseVolAllocator

    alloc = InverseVolAllocator(vol_by_symbol={"a": 0.01})
    assert alloc.max_notional("unknown", 100_000.0, 0.0) == float("inf")


def test_volatility_target_scales_inverse_to_vol():
    from tradingagents.pro.backtest import VolatilityTargetAllocator

    alloc = VolatilityTargetAllocator(
        vol_by_symbol={"a": 0.02, "b": 0.04}, target_vol_pct=2.0)
    # a: 0.02 target / 0.02 vol → weight 1.0 → full equity
    assert alloc.max_notional("a", 100_000.0, 0.0) == pytest.approx(100_000.0)
    # b: 0.02 / 0.04 → weight 0.5 → half equity
    assert alloc.max_notional("b", 100_000.0, 0.0) == pytest.approx(50_000.0)


def test_update_refreshes_vols_from_returns():
    from tradingagents.pro.backtest import InverseVolAllocator

    alloc = InverseVolAllocator()
    alloc.update({"a": [0.01, -0.01, 0.01, -0.01], "b": [0.0, 0.0]})
    assert alloc.vol_by_symbol["a"] > 0
    # a single-element series is ignored (needs >= 2 points)
    alloc.update({"c": [0.05]})
    assert "c" not in alloc.vol_by_symbol


def test_static_allocators_have_no_update_hook():
    # the engine's refresh is hasattr-gated; the static allocators must not
    # expose update (so their behaviour is byte-identical to before)
    assert not hasattr(EqualWeightAllocator(2), "update")
    assert not hasattr(WeightedAllocator({"a": 0.5}), "update")
