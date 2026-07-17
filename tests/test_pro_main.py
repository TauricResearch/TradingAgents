"""Production entrypoint assembly (tradingagents.pro.main)."""

import pytest

fastapi = pytest.importorskip("fastapi")

from tests.test_pro_pipeline_graph import FakePipelineLLM  # noqa: E402
from tradingagents.pro.main import has_llm_key, loop_enabled  # noqa: E402


class TestLoopEnabled:
    def test_disabled_flag_wins(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
        monkeypatch.setenv("PRO_LOOP_DISABLED", "1")
        assert loop_enabled() is False

    def test_requires_provider_key(self, monkeypatch):
        monkeypatch.delenv("PRO_LOOP_DISABLED", raising=False)
        monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "deepseek")
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        assert loop_enabled() is False
        monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
        assert loop_enabled() is True

    def test_has_llm_key_ignores_loop_disabled(self, monkeypatch):
        # PRO_LOOP_DISABLED=1 must only gate the periodic thread — the
        # service (and on-demand runs) still need has_llm_key() to see the
        # real key so main() wires state.trigger regardless (Cloud Run
        # hosting: no automatic loop, but "Run pipeline now" still works).
        monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "deepseek")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
        monkeypatch.setenv("PRO_LOOP_DISABLED", "1")
        assert has_llm_key() is True
        assert loop_enabled() is False


class TestBuildService:
    def test_assembles_full_stack_and_runs_one_iteration(self, tmp_path, monkeypatch):
        # snapshot source must not hit the network: patch the builder
        import tradingagents.pro.main as main_module
        from tests.test_pro_pipeline_graph import pipeline_snapshot
        from tradingagents.pro.ingestion import builder as builder_module

        seen = {}

        class FakeBuilder:
            def build(self, symbol, asset, **kwargs):
                seen["symbol"] = symbol
                return pipeline_snapshot()

        monkeypatch.setattr(builder_module, "build_gold_pipeline",
                            lambda *a, **k: FakeBuilder())
        monkeypatch.setattr(main_module, "build_service",
                            main_module.build_service)  # keep reference

        service, state = main_module.build_service(
            llm=FakePipelineLLM(), data_dir=tmp_path
        )
        assert state.router is service.router
        assert (tmp_path / "dashboard_prefs.json").exists() is False  # lazy
        summary = service.run_once()
        # venue-tradable display symbol, never the vendor ticker (first
        # container run was refused at validation with GC=F)
        assert seen["symbol"] == "XAUUSD"
        assert summary["run_id"]
        assert state.latest_run() is not None
        assert (tmp_path / "audit.jsonl").exists()
        assert service.router.audit.verify()


class TestPipelineTrigger:
    """On-demand runs: routing, validation, single-flight, loop lock."""

    def _trigger(self):
        from tests.test_pro_pipeline_graph import CONFIG, pipeline_snapshot
        from tradingagents.pro.main import PipelineTrigger

        calls = {}

        class FakeService:
            config = CONFIG
            run_lock = None

            def run_once(self, snapshot=None, config=None, trigger="loop"):
                calls["config"] = config
                calls["trigger"] = trigger
                return {"symbol": snapshot.symbol, "run_id": "r1"}

        class FakeSnapshotTrigger(PipelineTrigger):
            def _build_snapshot(self, symbol, asset, tf):
                calls["build"] = (symbol, asset, tf)
                return pipeline_snapshot()

        return FakeSnapshotTrigger(FakeService()), calls

    def test_gold_intraday_routing(self):
        from tradingagents.contracts import AssetClass, Timeframe

        trigger, calls = self._trigger()
        out = trigger.run("XAUUSD", "4h")
        assert out["run_id"] == "r1"
        assert calls["build"] == ("XAUUSD", AssetClass.GOLD, Timeframe("4h"))
        assert calls["config"].asset is AssetClass.GOLD

    def test_bitcoin_routing(self):
        from tradingagents.contracts import AssetClass, Timeframe

        trigger, calls = self._trigger()
        trigger.run("BTC-USD", "1h")
        assert calls["build"] == ("BTC-USD", AssetClass.BITCOIN, Timeframe("1h"))
        assert calls["config"].asset is AssetClass.BITCOIN

    def test_rejects_unknown_symbol_and_timeframe(self):
        trigger, _ = self._trigger()
        with pytest.raises(ValueError):
            trigger.run("DOGE", "1h")
        with pytest.raises(ValueError):
            trigger.run("XAUUSD", "5m")
        assert trigger.busy() is False  # rejection never leaves the lock held

    def test_single_flight(self):
        from tradingagents.pro.main import TriggerBusy

        trigger, _ = self._trigger()
        assert trigger._busy.acquire(blocking=False)
        try:
            with pytest.raises(TriggerBusy):
                trigger.run("XAUUSD", "1h")
        finally:
            trigger._busy.release()
        trigger.run("XAUUSD", "1h")  # released → next run proceeds
        assert trigger.busy() is False

    def test_run_once_serializes_on_shared_lock(self):
        """The loop and the trigger share service.run_lock: while one run
        holds it, run_once for the other must hold it too (no interleaved
        pipeline+execution)."""
        import threading

        from tests.test_pro_pipeline_graph import (
            CONFIG,
            FakePipelineLLM,
            pipeline_snapshot,
        )
        from tradingagents.contracts import RiskLimits
        from tradingagents.pro.execution import (
            VENUES,
            AuditLog,
            CircuitBreaker,
            ExecutionRouter,
            KillSwitch,
            PaperVenueAdapter,
        )
        from tradingagents.pro.memory import ProMemory
        from tradingagents.pro.service import PaperTradingService

        limits = RiskLimits()
        router = ExecutionRouter(
            adapter=PaperVenueAdapter(VENUES["mt5"], starting_cash=100_000.0),
            limits=limits,
            kill_switch=KillSwitch(),
            breaker=CircuitBreaker(limits, equity_base=100_000.0),
            audit=AuditLog(),
        )
        lock = threading.Lock()
        service = PaperTradingService(
            FakePipelineLLM(), CONFIG, pipeline_snapshot,
            router=router, memory=ProMemory(), run_lock=lock,
        )
        held_during_run = []
        original = service._run_once

        def spy(*args, **kwargs):
            held_during_run.append(lock.locked())
            return original(*args, **kwargs)

        service._run_once = spy
        service.run_once()
        assert held_during_run == [True]
        assert lock.locked() is False
