import inspect
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.setup import GraphSetup
from tradingagents.graph.trading_graph import TradingAgentsGraph


def test_graph_uses_configured_recursion_limit(tmp_path):
    base = tmp_path / "graph-config"
    cfg = DEFAULT_CONFIG.copy()
    cfg["results_dir"] = str(base / "results")
    cfg["data_cache_dir"] = str(base / "cache")
    cfg["memory_log_path"] = str(base / "memory.md")
    cfg["max_recur_limit"] = 7

    fake_client = MagicMock()
    fake_client.get_llm.return_value = MagicMock()

    with patch("tradingagents.graph.trading_graph.create_llm_client", return_value=fake_client):
        graph = TradingAgentsGraph(config=cfg, selected_analysts=["market"])

    args = graph.propagator.get_graph_args()
    assert args["config"]["recursion_limit"] == 7


def test_graph_rejects_non_string_required_config(tmp_path):
    cfg = DEFAULT_CONFIG.copy()
    cfg["results_dir"] = 123

    with pytest.raises(ValueError, match="results_dir must be a string"):
        TradingAgentsGraph(config=cfg, selected_analysts=["market"])


def test_graph_rejects_non_int_round_config(tmp_path):
    cfg = DEFAULT_CONFIG.copy()
    cfg["max_debate_rounds"] = "1"

    with pytest.raises(ValueError, match="max_debate_rounds must be an int"):
        TradingAgentsGraph(config=cfg, selected_analysts=["market"])


def test_graph_allows_backend_url_to_be_none(tmp_path):
    cfg = DEFAULT_CONFIG.copy()
    cfg["results_dir"] = str(tmp_path / "results")
    cfg["data_cache_dir"] = str(tmp_path / "cache")
    cfg["memory_log_path"] = str(tmp_path / "memory.md")
    cfg["backend_url"] = None

    fake_client = MagicMock()
    fake_client.get_llm.return_value = MagicMock()

    with patch("tradingagents.graph.trading_graph.create_llm_client", return_value=fake_client):
        TradingAgentsGraph(config=cfg, selected_analysts=["market"])

    assert fake_client.get_llm.call_count == 2


def test_graph_normalizes_llm_provider_before_factory_call(tmp_path):
    cfg = DEFAULT_CONFIG.copy()
    cfg["results_dir"] = str(tmp_path / "results")
    cfg["data_cache_dir"] = str(tmp_path / "cache")
    cfg["memory_log_path"] = str(tmp_path / "memory.md")
    cfg["llm_provider"] = "OpenAI"

    fake_client = MagicMock()
    fake_client.get_llm.return_value = MagicMock()

    with patch("tradingagents.graph.trading_graph.create_llm_client", return_value=fake_client) as create_client:
        TradingAgentsGraph(config=cfg, selected_analysts=["market"])

    assert create_client.call_args_list[0].kwargs["provider"] == "openai"
    assert create_client.call_args_list[1].kwargs["provider"] == "openai"


def test_graph_selected_analysts_defaults_are_not_mutable_lists():
    graph_default = inspect.signature(TradingAgentsGraph).parameters["selected_analysts"].default
    setup_default = inspect.signature(GraphSetup.setup_graph).parameters["selected_analysts"].default

    assert graph_default is None
    assert setup_default is None


def test_graph_propagate_rejects_unsafe_ticker_before_work():
    graph = MagicMock()
    graph.config = {"checkpoint_enabled": False}
    graph._checkpointer_ctx = None

    with pytest.raises(ValueError, match="ticker contains characters"):
        TradingAgentsGraph.propagate(graph, "../NVDA", "2026-01-10")

    graph._resolve_pending_entries.assert_not_called()
    graph._run_graph.assert_not_called()


def test_graph_propagate_rejects_unsafe_trade_date_before_work():
    graph = MagicMock()
    graph.config = {"checkpoint_enabled": False}
    graph._checkpointer_ctx = None

    with pytest.raises(ValueError, match="trade_date must use YYYY-MM-DD format"):
        TradingAgentsGraph.propagate(graph, "NVDA", "2026-01-10/evil")

    graph._resolve_pending_entries.assert_not_called()
    graph._run_graph.assert_not_called()


def test_graph_propagate_passes_run_exception_to_checkpointer_exit():
    class RecordingCheckpointer:
        def __init__(self):
            self.exit_args = None

        def __enter__(self):
            return "saver"

        def __exit__(self, exc_type, exc, traceback):
            self.exit_args = (exc_type, exc, traceback)
            return False

    graph = MagicMock()
    graph.config = {
        "checkpoint_enabled": True,
        "data_cache_dir": "cache-dir",
    }
    graph._checkpointer_ctx = None
    graph.workflow.compile.side_effect = ["compiled-with-checkpointer", "compiled-clean"]
    graph._run_graph.side_effect = RuntimeError("graph failed")
    checkpointer = RecordingCheckpointer()

    with (
        patch("tradingagents.graph.trading_graph.get_checkpointer", return_value=checkpointer),
        patch("tradingagents.graph.trading_graph.checkpoint_step", return_value=None),
        pytest.raises(RuntimeError, match="graph failed"),
    ):
        TradingAgentsGraph.propagate(graph, "NVDA", "2026-01-10")

    assert checkpointer.exit_args[0] is RuntimeError
    assert str(checkpointer.exit_args[1]) == "graph failed"
    assert checkpointer.exit_args[2] is not None
    assert graph.workflow.compile.call_args_list[0].kwargs == {"checkpointer": "saver"}
    assert graph.workflow.compile.call_args_list[1].kwargs == {}
