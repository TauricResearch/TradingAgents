"""Engine end-to-end (same pipeline as live), LLM cache, walk-forward, MC."""

import pytest

from tests.pro_fakes import make_bars
from tests.test_pro_pipeline_graph import FakePipelineLLM
from tradingagents.contracts import AssetClass, ProConfig, TradingMode
from tradingagents.pro.agents import EvidenceDraft
from tradingagents.pro.backtest import (
    BacktestEngine,
    BarReplay,
    CacheMiss,
    CachingLLM,
    SimBroker,
    monte_carlo_summary,
    run_walk_forward,
    walk_forward_windows,
)
from tradingagents.pro.memory import MemoryKind, ProMemory
from tradingagents.pro.pipeline.schemas import CriticReport

BT_CONFIG = ProConfig(asset=AssetClass.GOLD, mode=TradingMode.BACKTEST,
                      max_debate_rounds=1)


def make_engine(llm=None, memory=None, n_bars=140, **kw):
    replay = BarReplay("XAUUSD", AssetClass.GOLD, make_bars(n=n_bars), window=60)
    defaults = {"min_history": 60, "decide_every": 10}
    defaults.update(kw)
    return BacktestEngine(
        llm or FakePipelineLLM(), BT_CONFIG, replay,
        broker=SimBroker(initial_equity=100_000.0), memory=memory, **defaults,
    )


class TestEngine:
    def test_full_run_trades_profitably_in_rising_market(self):
        result = make_engine().run()
        assert result.decisions >= 1
        assert result.executed >= 1
        assert result.trades, "BUY recommendations should have produced trades"
        assert all(t.side == "BUY" for t in result.trades)
        # rising synthetic market + ATR targets above entry => wins
        assert result.report.win_rate > 0
        assert result.final_equity > 100_000.0
        assert len(result.equity_curve) >= 70

    def test_rejected_decisions_are_tallied_not_traded(self):
        llm = FakePipelineLLM(overrides={
            CriticReport: CriticReport(verdict="fail", issues=["bad citation"]),
        })
        result = make_engine(llm=llm).run()
        assert result.executed == 0
        assert result.trades == []
        assert result.rejections.get("critic", 0) == result.decisions
        assert result.final_equity == pytest.approx(100_000.0)

    def test_closed_trades_report_outcomes_to_memory(self):
        memory = ProMemory()
        result = make_engine(memory=memory, n_bars=200, decide_every=5).run()
        outcomes = [r for r in memory._records.values() if r.kind is MemoryKind.OUTCOME]
        assert len(outcomes) == len(result.trades) >= 1
        lessons = [r for r in memory._records.values()
                   if r.kind in (MemoryKind.WINNING_PATTERN, MemoryKind.MISTAKE)]
        assert len(lessons) == len(result.trades)

    def test_hold_rulings_produce_no_trades(self):
        from tradingagents.pro.pipeline.schemas import JudgeVerdict

        llm = FakePipelineLLM(overrides={
            JudgeVerdict: JudgeVerdict(action="HOLD", confidence=50, rationale="balanced"),
        })
        result = make_engine(llm=llm).run()
        assert result.executed == 0 and result.trades == []
        # HOLDs are decisions, not rejections
        assert result.rejections == {}

    def test_engine_validates_settings(self):
        with pytest.raises(ValueError):
            make_engine(min_history=2)
        with pytest.raises(ValueError):
            make_engine(decide_every=0)


class TestCachingLLM:
    class CountingLLM(FakePipelineLLM):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def with_structured_output(self, schema):
            runnable = super().with_structured_output(schema)
            outer = self
            original = runnable.invoke

            def counted(prompt):
                outer.calls += 1
                return original(prompt)

            runnable.invoke = counted
            return runnable

    def test_second_run_is_served_from_cache(self, tmp_path):
        path = tmp_path / "llm_cache.jsonl"
        inner = self.CountingLLM()
        first = make_engine(llm=CachingLLM(inner, mode="auto", path=path)).run()
        calls_after_first = inner.calls
        assert calls_after_first > 0

        cached = CachingLLM(inner, mode="auto", path=path)
        second = make_engine(llm=cached).run()
        assert inner.calls == calls_after_first  # zero new inner calls
        assert cached.hits > 0 and cached.misses == 0
        assert second.final_equity == pytest.approx(first.final_equity)

    def test_replay_mode_needs_no_inner_llm(self, tmp_path):
        path = tmp_path / "llm_cache.jsonl"
        make_engine(llm=CachingLLM(self.CountingLLM(), mode="record", path=path)).run()

        replay_llm = CachingLLM(mode="replay", path=path)
        result = make_engine(llm=replay_llm).run()
        assert result.decisions >= 1

    def test_replay_miss_raises_instead_of_mixing_fresh_output(self, tmp_path):
        replay_llm = CachingLLM(mode="replay", path=tmp_path / "empty.jsonl")
        with pytest.raises(CacheMiss):
            replay_llm.with_structured_output(EvidenceDraft).invoke("novel prompt")

    def test_mode_validation(self):
        with pytest.raises(ValueError):
            CachingLLM(mode="yolo")
        with pytest.raises(ValueError):
            CachingLLM(mode="auto")  # no inner


class TestWalkForwardAndMonteCarlo:
    def test_window_generation_known_values(self):
        windows = walk_forward_windows(100, train=50, test=25, step=25)
        assert [(w.train_start, w.train_end, w.test_end) for w in windows] == [
            (0, 50, 75), (25, 75, 100),
        ]

    def test_walk_forward_runs_each_window(self):
        bars = make_bars(n=220)

        def factory(window_bars, window):
            replay = BarReplay("XAUUSD", AssetClass.GOLD, list(window_bars), window=60)
            return BacktestEngine(
                FakePipelineLLM(), BT_CONFIG, replay,
                broker=SimBroker(initial_equity=100_000.0),
                min_history=window.train_end - window.train_start,
                decide_every=10,
            ).run()

        result = run_walk_forward(factory, bars, train=100, test=50, step=50)
        # starts at 0 and 50; a third window (100..250) would overrun 220 bars
        assert len(result.results) == len(result.windows) == 2
        summary = result.summary()
        assert summary["windows"] == 2
        assert summary["total_trades"] >= 0
        assert summary["worst_return"] <= summary["best_return"]

    def test_monte_carlo_is_deterministic_and_ordered(self):
        pnls = [120.0, -60.0, 90.0, -45.0, 150.0, -30.0]
        a = monte_carlo_summary(pnls, initial_equity=10_000, n_paths=500, seed=42)
        b = monte_carlo_summary(pnls, initial_equity=10_000, n_paths=500, seed=42)
        assert a == b
        assert a.final_equity_p5 <= a.final_equity_p50 <= a.final_equity_p95
        assert 0.0 <= a.prob_loss <= 1.0
        assert a.max_drawdown_p50 <= a.max_drawdown_p95

    def test_monte_carlo_input_validation(self):
        with pytest.raises(ValueError, match="at least 2"):
            monte_carlo_summary([1.0], initial_equity=10_000)
