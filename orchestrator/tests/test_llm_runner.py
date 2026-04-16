"""Tests for LLMRunner."""
import logging
import sys
from types import ModuleType

import pytest

from orchestrator.config import OrchestratorConfig
from orchestrator.contracts.error_taxonomy import ReasonCode
from orchestrator.llm_runner import LLMRunner


def _clear_runtime_llm_env(monkeypatch):
    for env_name in (
        "TRADINGAGENTS_LLM_PROVIDER",
        "TRADINGAGENTS_BACKEND_URL",
        "TRADINGAGENTS_MODEL",
        "TRADINGAGENTS_DEEP_MODEL",
        "TRADINGAGENTS_QUICK_MODEL",
        "ANTHROPIC_BASE_URL",
        "OPENAI_BASE_URL",
        "ANTHROPIC_API_KEY",
        "MINIMAX_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(env_name, raising=False)


@pytest.fixture
def runner(tmp_path, monkeypatch):
    _clear_runtime_llm_env(monkeypatch)
    cfg = OrchestratorConfig(
        cache_dir=str(tmp_path),
        trading_agents_config={
            "llm_provider": "anthropic",
            "backend_url": "https://api.minimaxi.com/anthropic",
            "deep_think_llm": "MiniMax-M2.7-highspeed",
            "quick_think_llm": "MiniMax-M2.7-highspeed",
        },
    )
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
    _clear_runtime_llm_env(monkeypatch)
    class BrokenGraph:
        def propagate(self, ticker, date):
            raise RuntimeError("graph unavailable")

    cfg = OrchestratorConfig(
        cache_dir=str(tmp_path),
        trading_agents_config={
            "llm_provider": "anthropic",
            "backend_url": "https://api.minimaxi.com/anthropic",
            "deep_think_llm": "MiniMax-M2.7-highspeed",
            "quick_think_llm": "MiniMax-M2.7-highspeed",
        },
    )
    runner = LLMRunner(cfg)
    monkeypatch.setattr(runner, "_get_graph", lambda: BrokenGraph())

    signal = runner.get_signal("AAPL", "2024-01-02")

    assert signal.degraded is True
    assert signal.reason_code == ReasonCode.LLM_SIGNAL_FAILED.value
    assert signal.metadata["error"] == "graph unavailable"


def test_get_signal_classifies_provider_auth_failure(monkeypatch, tmp_path):
    _clear_runtime_llm_env(monkeypatch)

    class BrokenGraph:
        def propagate(self, ticker, date):
            raise RuntimeError(
                "Error code: 401 - {'type': 'error', 'error': {'type': 'authentication_error', 'message': \"login fail: Please carry the API secret key in the Authorization field\"}}"
            )

    cfg = OrchestratorConfig(
        cache_dir=str(tmp_path),
        trading_agents_config={
            "llm_provider": "anthropic",
            "backend_url": "https://api.minimaxi.com/anthropic",
            "deep_think_llm": "MiniMax-M2.7-highspeed",
            "quick_think_llm": "MiniMax-M2.7-highspeed",
        },
    )
    runner = LLMRunner(cfg)
    monkeypatch.setattr(runner, "_get_graph", lambda: BrokenGraph())

    signal = runner.get_signal("AAPL", "2024-01-02")

    assert signal.degraded is True
    assert signal.reason_code == ReasonCode.PROVIDER_AUTH_FAILED.value
    assert signal.metadata["data_quality"]["state"] == "provider_auth_failed"


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
    _clear_runtime_llm_env(monkeypatch)
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
                ,
                "final_trade_decision_structured": {
                    "rating": "BUY",
                    "hold_subtype": "N/A",
                },
            }, "BUY"

    cfg = OrchestratorConfig(
        cache_dir=str(tmp_path),
        trading_agents_config={
            "llm_provider": "anthropic",
            "backend_url": "https://api.minimaxi.com/anthropic",
            "deep_think_llm": "MiniMax-M2.7-highspeed",
            "quick_think_llm": "MiniMax-M2.7-highspeed",
        },
    )
    runner = LLMRunner(cfg)
    monkeypatch.setattr(runner, "_get_graph", lambda: SuccessfulGraph())

    signal = runner.get_signal("AAPL", "2024-01-02")

    assert signal.degraded is False
    assert signal.metadata["research"]["research_status"] == "degraded"
    assert signal.metadata["sample_quality"] == "degraded_research"
    assert signal.metadata["data_quality"]["state"] == "research_degraded"
    assert signal.metadata["decision_structured"]["rating"] == "BUY"


# Phase 2: Provider matrix validation tests
def test_detect_provider_mismatch_google_with_openai_url(tmp_path):
    cfg = OrchestratorConfig(
        cache_dir=str(tmp_path),
        trading_agents_config={
            "llm_provider": "google",
            "backend_url": "https://api.openai.com/v1",
        },
    )
    runner = LLMRunner(cfg)
    signal = runner.get_signal("AAPL", "2024-01-02")

    assert signal.degraded is True
    assert signal.reason_code == ReasonCode.PROVIDER_MISMATCH.value


def test_detect_provider_mismatch_xai_with_anthropic_url(tmp_path):
    cfg = OrchestratorConfig(
        cache_dir=str(tmp_path),
        trading_agents_config={
            "llm_provider": "xai",
            "backend_url": "https://api.minimaxi.com/anthropic",
        },
    )
    runner = LLMRunner(cfg)
    signal = runner.get_signal("AAPL", "2024-01-02")

    assert signal.degraded is True
    assert signal.reason_code == ReasonCode.PROVIDER_MISMATCH.value


def test_detect_provider_mismatch_ollama_with_openai_url(tmp_path):
    cfg = OrchestratorConfig(
        cache_dir=str(tmp_path),
        trading_agents_config={
            "llm_provider": "ollama",
            "backend_url": "https://api.openai.com/v1",
        },
    )
    runner = LLMRunner(cfg)
    signal = runner.get_signal("AAPL", "2024-01-02")

    assert signal.degraded is True
    assert signal.reason_code == ReasonCode.PROVIDER_MISMATCH.value


def test_detect_provider_mismatch_valid_anthropic_minimax(tmp_path):
    cfg = OrchestratorConfig(
        cache_dir=str(tmp_path),
        trading_agents_config={
            "llm_provider": "anthropic",
            "backend_url": "https://api.minimaxi.com/anthropic",
        },
    )
    runner = LLMRunner(cfg)
    mismatch = runner._detect_provider_mismatch()

    assert mismatch is None


def test_detect_provider_mismatch_valid_openai(tmp_path):
    cfg = OrchestratorConfig(
        cache_dir=str(tmp_path),
        trading_agents_config={
            "llm_provider": "openai",
            "backend_url": "https://api.openai.com/v1",
        },
    )
    runner = LLMRunner(cfg)
    mismatch = runner._detect_provider_mismatch()

    assert mismatch is None


# Phase 3: Timeout configuration validation tests
def test_timeout_validation_warns_for_multiple_analysts_low_timeout(tmp_path, caplog):
    cfg = OrchestratorConfig(
        cache_dir=str(tmp_path),
        trading_agents_config={
            "llm_provider": "anthropic",
            "backend_url": "https://api.minimaxi.com/anthropic",
            "selected_analysts": ["market", "social", "news", "fundamentals"],
            "analyst_node_timeout_secs": 75.0,
        },
    )
    with caplog.at_level(logging.WARNING):
        runner = LLMRunner(cfg)

    assert any("analyst_node_timeout_secs=75.0s may be insufficient" in record.message for record in caplog.records)


def test_timeout_validation_no_warn_for_single_analyst(tmp_path, caplog):
    cfg = OrchestratorConfig(
        cache_dir=str(tmp_path),
        trading_agents_config={
            "llm_provider": "anthropic",
            "backend_url": "https://api.minimaxi.com/anthropic",
            "selected_analysts": ["market"],
            "analyst_node_timeout_secs": 75.0,
        },
    )
    with caplog.at_level(logging.WARNING):
        runner = LLMRunner(cfg)

    assert not any("may be insufficient" in record.message for record in caplog.records)


def test_timeout_validation_no_warn_for_sufficient_timeout(tmp_path, caplog):
    cfg = OrchestratorConfig(
        cache_dir=str(tmp_path),
        trading_agents_config={
            "llm_provider": "anthropic",
            "backend_url": "https://api.minimaxi.com/anthropic",
            "selected_analysts": ["market", "social", "news", "fundamentals"],
            "analyst_node_timeout_secs": 120.0,
            "research_node_timeout_secs": 75.0,
        },
    )
    with caplog.at_level(logging.WARNING):
        runner = LLMRunner(cfg)

    assert not any("may be insufficient" in record.message for record in caplog.records)
