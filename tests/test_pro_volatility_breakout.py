"""volatility_breakout_v1 (SDK strategy library) — Bollinger-squeeze breakout.
Registered + engine-runnable; the squeeze gate must actually require a
low-volatility coil before the breakout."""

from datetime import timedelta

from tests.pro_fakes import BASE_TS
from tradingagents.contracts import (
    AssetClass,
    OHLCVBar,
    ProConfig,
    Timeframe,
    TradingMode,
)
from tradingagents.pro.backtest import BarReplay, build_strategy, is_registered
from tradingagents.pro.backtest.engine import BacktestEngine
from tradingagents.pro.backtest.registry import strategy_param_space

CONFIG = ProConfig(asset=AssetClass.BITCOIN, mode=TradingMode.BACKTEST,
                   max_debate_rounds=1)


def _bar(close, day):
    return OHLCVBar(timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=day),
                   open=close, high=close + 0.3, low=close - 0.3, close=close,
                   volume=1_000_000.0)


def _coil_then_break(n_flat=60, n_run=60):
    """A long low-volatility coil (tiny noise → tight bands) followed by a
    sustained breakout — the squeeze-then-expand happy path."""
    bars, day = [], 0
    for i in range(n_flat):
        bars.append(_bar(100.0 + (0.15 if i % 2 else -0.15), day))
        day += 1
    price = 100.0
    for _ in range(n_run):
        price += 2.0
        bars.append(_bar(price, day))
        day += 1
    return bars


def _flat(n=140):
    """No coil-then-break — a persistent trend with steady width never squeezes
    below the threshold, so nothing should fire."""
    bars, price = [], 100.0
    for day in range(n):
        price += 2.0
        bars.append(_bar(price, day))
    return bars


def _strategy(**overrides):
    params = {"lookback": 20, "squeeze_pct": 0.05, "stop_atr_mult": 2.0,
              "trail_pct": 0.05, "risk_pct": 1.0, "allow_short": "yes"}
    params.update(overrides)
    return build_strategy("volatility_breakout_v1", params)


def _run(bars, **overrides):
    replay = BarReplay("BTC-USD", AssetClass.BITCOIN, bars, window=40,
                       precompute_indicators=True)
    return BacktestEngine(None, CONFIG, replay, strategy=_strategy(**overrides),
                          min_history=40).run()


class TestRegistration:
    def test_registered(self):
        assert is_registered("volatility_breakout_v1")
        names = [p.name for p in strategy_param_space("volatility_breakout_v1")]
        assert "squeeze_pct" in names and "lookback" in names


class TestEngineRun:
    def test_squeeze_then_breakout_goes_long(self):
        res = _run(_coil_then_break())
        assert len(res.trades) >= 1
        assert any(t.side == "BUY" for t in res.trades)

    def test_no_squeeze_no_trades(self):
        # a steady trend (width never contracts below squeeze_pct) → no entries
        assert _run(_flat()).trades == []

    def test_deterministic(self):
        a, b = _run(_coil_then_break()), _run(_coil_then_break())
        assert [(t.side, t.pnl) for t in a.trades] == [(t.side, t.pnl) for t in b.trades]
