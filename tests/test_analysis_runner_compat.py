"""Compatibility contracts that a future shared AnalysisRunner must preserve."""

from unittest.mock import MagicMock, patch

import pytest

from tradingagents.graph.trading_graph import TradingAgentsGraph


pytestmark = pytest.mark.unit


def _bare_graph(*, checkpoint_enabled: bool = False) -> TradingAgentsGraph:
    """Build a graph shell without constructing providers or the real workflow."""
    graph = object.__new__(TradingAgentsGraph)
    graph.config = {
        "checkpoint_enabled": checkpoint_enabled,
        "data_cache_dir": "/tmp/tradingagents-test-cache",
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
    }
    graph.selected_analysts = ("market",)
    graph.debug = False
    graph.curr_state = None
    graph.ticker = None
    graph._checkpointer_ctx = None
    graph.memory_log = MagicMock()
    graph.propagator = MagicMock()
    graph.graph = MagicMock()
    graph.workflow = MagicMock()
    graph._log_state = MagicMock()
    graph.resolve_instrument_context = MagicMock(return_value={"symbol": "AAPL"})
    graph.signal_processor = MagicMock()
    graph.save_reports = MagicMock()
    graph._resolve_pending_entries = MagicMock()
    return graph


def test_run_graph_returns_legacy_tuple_and_preserves_side_effect_order():
    graph = _bare_graph()
    initial_state = {"company_of_interest": "AAPL"}
    final_state = {"final_trade_decision": "Rating: Buy"}
    graph.memory_log.get_past_context.return_value = "prior lesson"
    graph.propagator.create_initial_state.return_value = initial_state
    graph.propagator.get_graph_args.return_value = {"stream_mode": "updates"}
    graph.graph.invoke.return_value = final_state
    graph.signal_processor.process_signal.return_value = "BUY"

    result = TradingAgentsGraph._run_graph(graph, "AAPL", "2026-07-17")

    assert isinstance(result, tuple)
    assert len(result) == 2
    assert result[0] is final_state
    assert result[1] == "BUY"
    assert graph.curr_state is final_state
    graph.memory_log.get_past_context.assert_called_once_with("AAPL")
    graph.resolve_instrument_context.assert_called_once_with("AAPL", "stock")
    graph.propagator.create_initial_state.assert_called_once_with(
        "AAPL",
        "2026-07-17",
        asset_type="stock",
        past_context="prior lesson",
        instrument_context={"symbol": "AAPL"},
    )
    graph.graph.invoke.assert_called_once_with(initial_state, stream_mode="updates")
    graph._log_state.assert_called_once_with("2026-07-17", final_state)
    graph.memory_log.store_decision.assert_called_once_with(
        ticker="AAPL",
        trade_date="2026-07-17",
        final_trade_decision="Rating: Buy",
    )
    graph.signal_processor.process_signal.assert_called_once_with("Rating: Buy")
    graph.save_reports.assert_not_called()


def test_run_graph_re_raises_original_failure_before_completion_side_effects():
    graph = _bare_graph()
    graph.memory_log.get_past_context.return_value = ""
    graph.propagator.create_initial_state.return_value = {"input": True}
    graph.propagator.get_graph_args.return_value = {}
    original = RuntimeError("provider exploded")
    graph.graph.invoke.side_effect = original

    with pytest.raises(RuntimeError, match="provider exploded") as exc_info:
        TradingAgentsGraph._run_graph(graph, "AAPL", "2026-07-17")

    assert exc_info.value is original
    assert graph.curr_state is None
    graph._log_state.assert_not_called()
    graph.memory_log.store_decision.assert_not_called()
    graph.signal_processor.process_signal.assert_not_called()
    graph.save_reports.assert_not_called()


@pytest.mark.parametrize("fails", [False, True])
def test_propagate_always_closes_checkpoint_context_and_restores_plain_graph(fails):
    graph = _bare_graph(checkpoint_enabled=True)
    saver = object()
    compiled_with_saver = object()
    restored_graph = object()
    graph.workflow.compile.side_effect = [compiled_with_saver, restored_graph]
    context = MagicMock()
    context.__enter__.return_value = saver
    legacy_result = ({"final_trade_decision": "Rating: Hold"}, "HOLD")
    original = RuntimeError("graph failed")
    graph._run_graph = MagicMock(side_effect=original if fails else None)
    if not fails:
        graph._run_graph.return_value = legacy_result

    with (
        patch(
            "tradingagents.graph.trading_graph.get_checkpointer",
            return_value=context,
        ),
        patch(
            "tradingagents.graph.trading_graph.checkpoint_step",
            return_value=None,
        ),
    ):
        if fails:
            with pytest.raises(RuntimeError, match="graph failed") as exc_info:
                TradingAgentsGraph.propagate(graph, "AAPL", "2026-07-17")
            assert exc_info.value is original
        else:
            result = TradingAgentsGraph.propagate(graph, "AAPL", "2026-07-17")
            assert result is legacy_result

    assert graph.ticker == "AAPL"
    graph._resolve_pending_entries.assert_called_once_with("AAPL")
    assert context.__exit__.call_count == 1
    assert graph._checkpointer_ctx is None
    assert graph.graph is restored_graph


def test_success_clears_checkpoint_after_state_and_memory_are_persisted():
    graph = _bare_graph(checkpoint_enabled=True)
    graph.memory_log.get_past_context.return_value = ""
    graph.propagator.create_initial_state.return_value = {"input": True}
    graph.propagator.get_graph_args.return_value = {}
    graph.graph.invoke.return_value = {"final_trade_decision": "Rating: Hold"}
    graph.signal_processor.process_signal.return_value = "HOLD"

    with patch("tradingagents.graph.trading_graph.clear_checkpoint") as clear:
        TradingAgentsGraph._run_graph(graph, "AAPL", "2026-07-17")

    graph._log_state.assert_called_once()
    graph.memory_log.store_decision.assert_called_once()
    clear.assert_called_once_with(
        "/tmp/tradingagents-test-cache",
        "AAPL",
        "2026-07-17",
        "analysts=market|debate=1|risk=1|asset=stock",
    )
