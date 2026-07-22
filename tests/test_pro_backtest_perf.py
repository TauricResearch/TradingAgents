"""Precomputed-indicator replay: look-ahead safety, decision parity with the
windowed path, and the throughput floor that keeps full-density UI runs
tractable."""

import time

import pytest

from tests.pro_fakes import make_bars
from tests.test_pro_pipeline_graph import FakePipelineLLM
from tradingagents.contracts import AssetClass, ProConfig, TradingMode
from tradingagents.pro.backtest import BacktestEngine, BarReplay, SimBroker
from tradingagents.pro.memory import ProMemory

CONFIG = ProConfig(asset=AssetClass.GOLD, mode=TradingMode.BACKTEST,
                   max_debate_rounds=1)


def replay(bars, precompute):
    return BarReplay("XAUUSD", AssetClass.GOLD, bars, window=60,
                     precompute_indicators=precompute)


class TestPrecomputedIndicators:
    def test_lookahead_safety_future_bars_do_not_change_snapshot(self):
        """The precomputed value at bar i must be a function of bars <= i
        only: two series that share a prefix but diverge afterwards must
        produce identical snapshots inside the shared prefix."""
        base = make_bars(n=200)
        # diverge hard after bar 120: replace the tail with a crash
        crashed = list(base[:120])
        price = crashed[-1].close
        for bar in base[120:]:
            low = price * 0.55
            crashed.append(bar.model_copy(update={
                "open": price, "high": price, "low": low, "close": low * 1.01,
            }))
            price = low * 1.01
        a, b = replay(base, True), replay(crashed, True)
        for i in (80, 100, 119):
            snap_a, snap_b = a.snapshot_at(i), b.snapshot_at(i)
            ind_a = {r.name: r.value for r in snap_a.indicators}
            ind_b = {r.name: r.value for r in snap_b.indicators}
            assert ind_a == ind_b, f"future bars leaked into snapshot at {i}"
            assert snap_a.bars == snap_b.bars

    def test_warmup_discipline_preserved(self):
        bars = make_bars(n=120)
        snap = replay(bars, True).snapshot_at(30)
        names = {r.name for r in snap.indicators}
        assert "SMA_200" not in names  # cannot exist from 31 bars
        assert "RSI_14" in names

    def test_decision_parity_with_windowed_mode(self):
        """Full-history indicator seeding may drift recursive indicators vs
        the 60-bar-truncated legacy mode; on this reference series the
        resulting DECISIONS must agree (guards against the fast path
        accidentally changing strategy behavior wholesale)."""
        bars = make_bars(n=400)
        results = {}
        for pre in (False, True):
            engine = BacktestEngine(
                FakePipelineLLM(), CONFIG, replay(bars, pre),
                broker=SimBroker(initial_equity=100_000.0),
                memory=ProMemory(), min_history=60, decide_every=1,
            )
            results[pre] = engine.run()
        legacy, fast = results[False], results[True]
        assert fast.decisions == legacy.decisions
        assert fast.executed == legacy.executed
        assert len(fast.trades) == len(legacy.trades)
        assert fast.final_equity == pytest.approx(legacy.final_equity)

    def test_indicator_mode_labels(self):
        bars = make_bars(n=80)
        assert replay(bars, True).indicator_mode == "full_history"
        assert replay(bars, False).indicator_mode == "windowed"

    def test_throughput_floor(self):
        """Full-density UI runs rely on this floor (measured ~109 dec/s on a
        dev laptop; the assert is deliberately loose for slow CI boxes but
        still catches an accidental return to per-decision recompute, which
        runs an order of magnitude slower)."""
        bars = make_bars(n=360)
        engine = BacktestEngine(
            FakePipelineLLM(), CONFIG, replay(bars, True),
            broker=SimBroker(initial_equity=100_000.0),
            memory=ProMemory(), min_history=60, decide_every=1,
        )
        start = time.perf_counter()
        result = engine.run()
        rate = result.decisions / (time.perf_counter() - start)
        assert rate > 25, f"throughput regressed: {rate:.0f} decisions/s"
