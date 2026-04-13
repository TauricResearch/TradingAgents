"""Tests for LLMRunner."""
import sys
from types import ModuleType

import pytest

from orchestrator.config import OrchestratorConfig
from orchestrator.contracts.error_taxonomy import ReasonCode
from orchestrator.llm_runner import LLMRunner


@pytest.fixture
def runner(tmp_path):
    cfg = OrchestratorConfig(cache_dir=str(tmp_path))
    return LLMRunner(cfg)


# All 5 known ratings
@pytest.mark.parametrize("rating,expected", [
    ("BUY",         (1,  0.9)),
    ("OVERWEIGHT",  (1,  0.6)),
    ("HOLD",        (0,  0.5)),
    ("UNDERWEIGHT", (-1, 0.6)),
    ("SELL",        (-1, 0.9)),
])
def test_map_rating_known(runner, rating, expected):
    assert runner._map_rating(rating) == expected


# Unknown rating → (0, 0.5)
def test_map_rating_unknown(runner):
    assert runner._map_rating("STRONG_BUY") == (0, 0.5)


# Case-insensitive
def test_map_rating_lowercase(runner):
    assert runner._map_rating("buy") == (1, 0.9)
    assert runner._map_rating("sell") == (-1, 0.9)
    assert runner._map_rating("hold") == (0, 0.5)


# Empty string → (0, 0.5)
def test_map_rating_empty_string(runner):
    assert runner._map_rating("") == (0, 0.5)


def test_get_graph_preserves_explicit_empty_selected_analysts(monkeypatch, tmp_path):
    captured_kwargs = {}

    class FakeTradingAgentsGraph:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

    fake_module = ModuleType("tradingagents.graph.trading_graph")
    fake_module.TradingAgentsGraph = FakeTradingAgentsGraph
    monkeypatch.setitem(sys.modules, "tradingagents.graph.trading_graph", fake_module)

    cfg = OrchestratorConfig(
        cache_dir=str(tmp_path),
        trading_agents_config={"selected_analysts": [], "llm_provider": "anthropic"},
    )

    runner = LLMRunner(cfg)
    graph = runner._get_graph()

    assert isinstance(graph, FakeTradingAgentsGraph)
    assert captured_kwargs["config"] == cfg.trading_agents_config
    assert captured_kwargs["selected_analysts"] == []


def test_get_signal_returns_reason_code_on_propagate_failure(monkeypatch, tmp_path):
    class BrokenGraph:
        def propagate(self, ticker, date):
            raise RuntimeError("graph unavailable")

    cfg = OrchestratorConfig(cache_dir=str(tmp_path))
    runner = LLMRunner(cfg)
    monkeypatch.setattr(runner, "_get_graph", lambda: BrokenGraph())

    signal = runner.get_signal("AAPL", "2024-01-02")

    assert signal.degraded is True
    assert signal.reason_code == ReasonCode.LLM_SIGNAL_FAILED.value
    assert signal.metadata["error"] == "graph unavailable"


def test_get_signal_returns_provider_mismatch_before_graph_init(tmp_path):
    cfg = OrchestratorConfig(
        cache_dir=str(tmp_path),
        trading_agents_config={
            "llm_provider": "anthropic",
            "backend_url": "https://api.openai.com/v1",
        },
    )
    runner = LLMRunner(cfg)

    signal = runner.get_signal("AAPL", "2024-01-02")

    assert signal.degraded is True
    assert signal.reason_code == ReasonCode.PROVIDER_MISMATCH.value
    assert signal.metadata["data_quality"]["state"] == "provider_mismatch"


def test_get_signal_persists_research_provenance_on_success(monkeypatch, tmp_path):
    class SuccessfulGraph:
        def propagate(self, ticker, date):
            return {
                "investment_debate_state": {
                    "research_status": "degraded",
                    "research_mode": "degraded_synthesis",
                    "timed_out_nodes": ["Bull Researcher"],
                    "degraded_reason": "bull_researcher_timeout",
                    "covered_dimensions": ["market"],
                    "manager_confidence": None,
                }
            }, "BUY"

    cfg = OrchestratorConfig(cache_dir=str(tmp_path))
    runner = LLMRunner(cfg)
    monkeypatch.setattr(runner, "_get_graph", lambda: SuccessfulGraph())

    signal = runner.get_signal("AAPL", "2024-01-02")

    assert signal.degraded is False
    assert signal.metadata["research"]["research_status"] == "degraded"
    assert signal.metadata["sample_quality"] == "degraded_research"
    assert signal.metadata["data_quality"]["state"] == "research_degraded"
