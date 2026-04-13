from datetime import datetime
from pathlib import Path

from orchestrator.config import OrchestratorConfig
from orchestrator.contracts.error_taxonomy import ReasonCode
from orchestrator.llm_runner import LLMRunner


class _SuccessfulGraph:
    def propagate(self, ticker: str, date: str):
        return {"ticker": ticker, "date": date}, "BUY"


class _FailingGraph:
    def propagate(self, _ticker: str, _date: str):
        raise RuntimeError("graph offline")


def test_llm_runner_persists_result_contract_v1alpha1(monkeypatch, tmp_path):
    runner = LLMRunner(OrchestratorConfig(cache_dir=str(tmp_path)))
    monkeypatch.setattr(runner, "_get_graph", lambda: _SuccessfulGraph())

    signal = runner.get_signal("BRK/B", "2026-04-11")

    assert signal.ticker == "BRK/B"
    assert signal.direction == 1
    assert signal.confidence == 0.9
    assert signal.source == "llm"
    assert signal.metadata["rating"] == "BUY"
    assert signal.metadata["ticker"] == "BRK/B"
    assert signal.metadata["date"] == "2026-04-11"
    assert datetime.fromisoformat(signal.metadata["timestamp"])

    cache_path = Path(tmp_path) / "BRK_B_2026-04-11.json"
    assert cache_path.exists()


def test_llm_runner_returns_error_contract_when_graph_fails(monkeypatch, tmp_path):
    runner = LLMRunner(OrchestratorConfig(cache_dir=str(tmp_path)))
    monkeypatch.setattr(runner, "_get_graph", lambda: _FailingGraph())

    signal = runner.get_signal("AAPL", "2026-04-11")

    assert signal.ticker == "AAPL"
    assert signal.direction == 0
    assert signal.confidence == 0.0
    assert signal.source == "llm"
    assert signal.metadata["error"] == "graph offline"
    assert signal.metadata["reason_code"] == ReasonCode.LLM_SIGNAL_FAILED.value
    assert signal.metadata["contract_version"]
    assert signal.metadata["source"] == "llm"
    assert not (Path(tmp_path) / "AAPL_2026-04-11.json").exists()
