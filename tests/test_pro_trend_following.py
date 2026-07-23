"""trend_following_v1 — native Donchian-breakout strategy (roadmap P1 / the
research's top systematic pattern): signal logic, registry build, and an
end-to-end engine run that trades an uptrend and rides the trailing stop."""

from datetime import timedelta

from tests.pro_fakes import BASE_TS
from tradingagents.contracts import (
    AssetClass,
    OHLCVBar,
    ProConfig,
    Timeframe,
    TradingMode,
)
from tradingagents.pro.backtest import (
    BacktestEngine,
    BarReplay,
    SimBroker,
    build_strategy,
    list_strategies,
)

CONFIG = ProConfig(asset=AssetClass.GOLD, mode=TradingMode.BACKTEST,
                   max_debate_rounds=1)


def _series(fn, n=120):
    # tight intrabar range (±0.5) so a steady drift's close actually clears the
    # prior-N-bar high/low — i.e. the Donchian channel really breaks
    bars, price = [], 1000.0
    for i in range(n):
        price = fn(i, price)
        bars.append(OHLCVBar(
            timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
            open=price, high=price + 0.5, low=price - 0.5, close=price,
            volume=1_000_000.0))
    return bars


class TestRegistration:
    def test_registered_with_schema(self):
        info = next((s for s in list_strategies() if s.id == "trend_following_v1"), None)
        assert info is not None
        names = [p["name"] for p in info.params]
        assert "donchian_period" in names and "stop_atr_mult" in names

    def test_build_with_defaults(self):
        strat = build_strategy("trend_following_v1")
        assert strat.id == "trend_following_v1"
        assert strat.params["donchian_period"] == 20


class _Ctx:
    """Minimal StrategyContext stand-in for unit-testing on_bar."""
    def __init__(self, bars, positions=()):
        from types import SimpleNamespace
        self.snapshot = SimpleNamespace(bars=bars)
        self.positions = positions
        self.equity = 100_000.0
        self.params = {}


class TestSignalLogic:
    def test_breakout_above_channel_goes_long(self):
        strat = build_strategy("trend_following_v1", {"donchian_period": 20})
        bars = _series(lambda i, p: p + 2.0)  # steady uptrend → new highs
        intents = strat.on_bar(_Ctx(bars))
        assert len(intents) == 1
        intent = intents[0]
        assert intent.side == "BUY" and intent.kind == "market"
        assert intent.bracket.stop_loss < bars[-1].close  # stop below entry
        assert intent.bracket.trailing == "pct"

    def test_no_breakout_holds(self):
        strat = build_strategy("trend_following_v1", {"donchian_period": 20})
        # flat/oscillating series → last close not above the prior-N high
        bars = _series(lambda i, p: 1000.0 + (2.0 if i % 2 else -2.0))
        assert strat.on_bar(_Ctx(bars)) == []

    def test_one_position_per_side(self):
        from types import SimpleNamespace
        strat = build_strategy("trend_following_v1", {"donchian_period": 20})
        bars = _series(lambda i, p: p + 2.0)
        held = SimpleNamespace(side="BUY")
        assert strat.on_bar(_Ctx(bars, positions=(held,))) == []  # already long


class TestEngineRun:
    def test_trades_an_uptrend_and_wins(self):
        bars = _series(lambda i, p: p + 1.0, n=120)
        engine = BacktestEngine(
            None, CONFIG,
            BarReplay("XAUUSD", AssetClass.GOLD, bars, window=60,
                      precompute_indicators=True),
            broker=SimBroker(initial_equity=100_000.0),
            memory=None, min_history=60, decide_every=1,
            strategy=build_strategy("trend_following_v1",
                                    {"donchian_period": 20, "trail_pct": 0.03}))
        result = engine.run()
        assert result.executed >= 1
        assert {t.side for t in result.trades} == {"BUY"}
        # a persistent uptrend with a trailing stop → net positive
        assert result.report.total_return > 0

    def test_downtrend_goes_short(self):
        bars = _series(lambda i, p: p - 1.0, n=120)
        engine = BacktestEngine(
            None, CONFIG,
            BarReplay("XAUUSD", AssetClass.GOLD, bars, window=60,
                      precompute_indicators=True),
            broker=SimBroker(initial_equity=100_000.0),
            memory=None, min_history=60, decide_every=1,
            strategy=build_strategy("trend_following_v1", {"donchian_period": 20}))
        result = engine.run()
        assert result.executed >= 1
        assert {t.side for t in result.trades} == {"SELL"}
