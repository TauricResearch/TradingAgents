"""Backtest units: costs, broker semantics, replay lookahead, metrics."""

from datetime import timedelta

import pytest

from tests.pro_fakes import BASE_TS, make_bars
from tests.test_pro_memory_facade import make_recommendation
from tradingagents.contracts import AssetClass, OHLCVBar, TakeProfitLevel, Timeframe, TradeAction
from tradingagents.pro.backtest import (
    BarReplay,
    ClosedTrade,
    CommissionModel,
    LiquidityModel,
    SimBroker,
    SlippageModel,
    max_drawdown,
    performance_report,
)


def bar(open_, high, low, close, volume=1_000.0, day=0) -> OHLCVBar:
    return OHLCVBar(
        timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=day),
        open=open_, high=high, low=low, close=close, volume=volume,
    )


class TestCosts:
    def test_slippage_is_side_aware(self):
        model = SlippageModel(bps=10)
        assert model.fill_price(100.0, "BUY") == pytest.approx(100.10)
        assert model.fill_price(100.0, "SELL") == pytest.approx(99.90)

    def test_commission_known_value(self):
        assert CommissionModel(rate_bps=1.0).cost(10, 100.0) == pytest.approx(0.10)

    def test_liquidity_participation_cap(self):
        model = LiquidityModel(max_participation=0.1)
        assert model.cap_quantity(100.0, bar_volume=100.0) == pytest.approx(10.0)
        assert model.cap_quantity(5.0, bar_volume=100.0) == pytest.approx(5.0)


def buy_rec(entry=100.0, stop=95.0, tps=((105.0, 0.5), (110.0, 0.5)), qty=10.0):
    return make_recommendation(action=TradeAction.BUY).model_copy(update={
        "entry_price": entry,
        "stop_loss": stop,
        "take_profits": [TakeProfitLevel(price=p, size_fraction=f) for p, f in tps],
        "position_size": make_recommendation().position_size.model_copy(
            update={"quantity": qty}
        ),
        "risk_reward": None,
    })


def make_broker(**kw) -> SimBroker:
    defaults = {
        "slippage": SlippageModel(bps=0),
        "commission": CommissionModel(rate_bps=0),
        "liquidity": LiquidityModel(max_participation=1.0),
    }
    defaults.update(kw)
    return SimBroker(initial_equity=10_000.0, **defaults)


class TestSimBroker:
    def test_entry_fills_at_bar_open_with_slippage_and_fee(self):
        broker = make_broker(slippage=SlippageModel(bps=10),
                             commission=CommissionModel(rate_bps=1))
        assert broker.open_from_recommendation(buy_rec(qty=10), bar(100, 101, 99, 100))
        assert broker.position.entry_price == pytest.approx(100.10)
        # entry fee deducted immediately
        assert broker.cash_pnl == pytest.approx(-10 * 100.10 * 1e-4)

    def test_liquidity_can_reject_entry_entirely(self):
        broker = make_broker(liquidity=LiquidityModel(max_participation=0.1))
        assert not broker.open_from_recommendation(
            buy_rec(qty=10), bar(100, 101, 99, 100, volume=0.0)
        )
        assert broker.position is None

    def test_stop_fills_before_tp_when_both_touched(self):
        broker = make_broker()
        broker.open_from_recommendation(buy_rec(), bar(100, 101, 99, 100))
        trade = broker.process_bar(bar(100, 120, 90, 110, day=1))  # touches both
        assert trade is not None and trade.reason == "stop"
        assert trade.exit_price == pytest.approx(95.0)
        assert trade.pnl == pytest.approx((95 - 100) * 10)

    def test_tp_ladder_closes_fractions_then_finalizes(self):
        broker = make_broker()
        broker.open_from_recommendation(buy_rec(qty=10), bar(100, 101, 99, 100))
        assert broker.process_bar(bar(104, 106, 103, 105, day=1)) is None  # TP1 only
        assert broker.position.quantity == pytest.approx(5.0)
        trade = broker.process_bar(bar(109, 111, 108, 110, day=2))  # TP2
        assert trade is not None and trade.reason == "take_profit"
        # exits: 5@105 + 5@110 -> weighted 107.5; pnl = 5*5 + 5*10 = 75
        assert trade.exit_price == pytest.approx(107.5)
        assert trade.pnl == pytest.approx(75.0)
        assert broker.position is None

    def test_short_side_mirrors(self):
        broker = make_broker()
        rec = make_recommendation(action=TradeAction.SELL).model_copy(update={
            "entry_price": 100.0, "stop_loss": 105.0,
            "take_profits": [TakeProfitLevel(price=90.0, size_fraction=1.0)],
            "risk_reward": None,
        })
        broker.open_from_recommendation(rec, bar(100, 101, 99, 100))
        trade = broker.process_bar(bar(95, 96, 89, 90, day=1))
        assert trade.reason == "take_profit"
        assert trade.pnl == pytest.approx((100 - 90) * 1.0)

    def test_mark_to_market_equity(self):
        broker = make_broker()
        broker.open_from_recommendation(buy_rec(qty=10), bar(100, 101, 99, 100))
        assert broker.equity(mark_price=103.0) == pytest.approx(10_000 + 30.0)

    def test_end_of_data_close(self):
        broker = make_broker()
        broker.open_from_recommendation(buy_rec(qty=10), bar(100, 101, 99, 100))
        trade = broker.close_all(bar(101, 102, 100, 101.5, day=5))
        assert trade.reason == "end_of_data"
        assert trade.pnl == pytest.approx(15.0)


class TestBarReplay:
    def test_snapshot_contains_no_future_bars(self):
        bars = make_bars(n=80)
        replay = BarReplay("XAUUSD", AssetClass.GOLD, bars, window=50)
        snapshot = replay.snapshot_at(60)
        assert len(snapshot.bars) == 50
        assert snapshot.bars[-1].start == bars[60].start
        assert snapshot.as_of == bars[60].start
        assert all(b.start <= bars[60].start for b in snapshot.bars)

    def test_indicators_computed_from_visible_window_only(self):
        bars = make_bars(n=80)
        replay = BarReplay("XAUUSD", AssetClass.GOLD, bars, window=60)
        snapshot = replay.snapshot_at(70)
        rsi = snapshot.get_indicator("RSI_14", Timeframe.D1)
        assert rsi is not None
        # SMA_200 cannot exist from a 60-bar window (warm-up rule)
        assert snapshot.get_indicator("SMA_200", Timeframe.D1) is None

    def test_mixed_timeframes_rejected(self):
        bars = make_bars(n=10) + make_bars(n=10, timeframe=Timeframe.H4)
        with pytest.raises(ValueError, match="single timeframe"):
            BarReplay("XAUUSD", AssetClass.GOLD, bars)


class TestMetrics:
    def test_max_drawdown_known_value(self):
        assert max_drawdown([100, 110, 99, 108]) == pytest.approx(0.1)

    def test_report_known_values(self):
        trades = [
            ClosedTrade("X", "BUY", 1, 100, 110, BASE_TS, BASE_TS, 10.0, "take_profit", "a"),
            ClosedTrade("X", "BUY", 1, 100, 95, BASE_TS, BASE_TS, -5.0, "stop", "b"),
            ClosedTrade("X", "BUY", 1, 100, 110, BASE_TS, BASE_TS, 10.0, "take_profit", "c"),
        ]
        report = performance_report([10_000, 10_010, 10_005, 10_015], trades)
        assert report.n_trades == 3
        assert report.win_rate == pytest.approx(2 / 3)
        assert report.profit_factor == pytest.approx(4.0)  # 20 gross win / 5 gross loss
        assert report.expectancy == pytest.approx(5.0)
        assert report.total_return == pytest.approx(15 / 10_000)
        assert report.sharpe != 0.0

    def test_empty_inputs_are_safe(self):
        report = performance_report([], [])
        assert report.n_trades == 0 and report.total_return == 0.0
