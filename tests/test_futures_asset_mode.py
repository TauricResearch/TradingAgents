from unittest.mock import MagicMock, call, patch

import pytest

from tradingagents.graph.trading_graph import TradingAgentsGraph


@pytest.mark.unit
def test_programmatic_run_promotes_resolved_future_before_execution():
    graph = MagicMock(spec=TradingAgentsGraph)
    graph.config = {"checkpoint_enabled": False}
    graph._checkpointer_ctx = None
    graph._run_graph.return_value = ("final-state", "signal")

    with patch(
        "tradingagents.graph.trading_graph.resolve_instrument_identity",
        return_value={"quote_type": "FUTURE"},
    ):
        result = TradingAgentsGraph.propagate(graph, "YGZ26", "2026-07-20")

    assert result == ("final-state", "signal")
    graph._configure_workflow.assert_called_once_with("futures")
    graph._run_graph.assert_called_once_with(
        "YGZ26",
        "2026-07-20",
        asset_type="futures",
    )


@pytest.mark.unit
def test_programmatic_graph_reconfigures_across_asset_types():
    graph = object.__new__(TradingAgentsGraph)
    graph.selected_analysts = ("market", "fundamentals")
    graph._active_analysts = ("market", "fundamentals")
    graph.graph_setup = MagicMock()

    futures_workflow = MagicMock(name="futures_workflow")
    futures_graph = MagicMock(name="futures_graph")
    futures_workflow.compile.return_value = futures_graph
    stock_workflow = MagicMock(name="stock_workflow")
    stock_graph = MagicMock(name="stock_graph")
    stock_workflow.compile.return_value = stock_graph
    graph.graph_setup.setup_graph.side_effect = [futures_workflow, stock_workflow]

    graph._configure_workflow("futures")
    assert graph._active_analysts == ("market",)
    assert graph.workflow is futures_workflow
    assert graph.graph is futures_graph

    graph._configure_workflow("stock")
    assert graph._active_analysts == ("market", "fundamentals")
    assert graph.workflow is stock_workflow
    assert graph.graph is stock_graph
    assert graph.graph_setup.setup_graph.call_args_list == [
        call(("market", "fundamentals"), asset_type="futures"),
        call(("market", "fundamentals"), asset_type="stock"),
    ]


@pytest.mark.unit
def test_futures_checkpoint_signature_uses_effective_analysts():
    graph = object.__new__(TradingAgentsGraph)
    graph.selected_analysts = ("market", "news", "fundamentals")
    graph.config = {"max_debate_rounds": 1, "max_risk_discuss_rounds": 1}

    signature = graph._run_signature("futures")

    assert signature == "analysts=market,news|debate=1|risk=1|asset=futures"
