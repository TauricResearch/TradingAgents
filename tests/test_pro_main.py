"""Production entrypoint assembly (tradingagents.pro.main)."""

import pytest

fastapi = pytest.importorskip("fastapi")

from tests.test_pro_pipeline_graph import FakePipelineLLM  # noqa: E402
from tradingagents.pro.main import loop_enabled  # noqa: E402


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


class TestBuildService:
    def test_assembles_full_stack_and_runs_one_iteration(self, tmp_path, monkeypatch):
        # snapshot source must not hit the network: patch the builder
        import tradingagents.pro.main as main_module
        from tests.test_pro_pipeline_graph import pipeline_snapshot
        from tradingagents.pro.ingestion import builder as builder_module

        class FakeBuilder:
            def build(self, symbol, asset, **kwargs):
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
        assert summary["run_id"]
        assert state.latest_run() is not None
        assert (tmp_path / "audit.jsonl").exists()
        assert service.router.audit.verify()
