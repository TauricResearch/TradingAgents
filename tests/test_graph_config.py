from unittest.mock import MagicMock, patch

import pytest

from tradingagents.default_config import DEFAULT_CONFIG
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
