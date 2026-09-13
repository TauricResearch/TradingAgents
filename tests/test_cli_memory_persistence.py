from unittest.mock import Mock

import pytest

from cli.main import _finalize_streamed_run


@pytest.mark.unit
def test_finalize_streamed_run_persists_decision_before_clearing_checkpoint():
    graph = Mock()

    events = []

    graph.memory_log.store_decision.side_effect = (
        lambda **kwargs: events.append(("store", kwargs))
    )
    graph.clear_checkpoint_on_success.side_effect = (
        lambda *args: events.append(("clear", args))
    )

    selections = {
        "ticker": "AAPL",
        "analysis_date": "2026-09-11",
        "asset_type": "stock",
    }

    trace = [
        {"market_report": "technical analysis"},
        {
            "trader_investment_plan": "Action: Hold",
            "final_trade_decision": "Rating: Hold",
        },
    ]

    final_state = _finalize_streamed_run(graph, selections, trace)

    assert final_state["market_report"] == "technical analysis"
    assert final_state["final_trade_decision"] == "Rating: Hold"

    graph.memory_log.store_decision.assert_called_once_with(
        ticker="AAPL",
        trade_date="2026-09-11",
        final_trade_decision="Rating: Hold",
    )

    graph.clear_checkpoint_on_success.assert_called_once_with(
        "AAPL",
        "2026-09-11",
        "stock",
    )

    assert events[0][0] == "store"
    assert events[1][0] == "clear"
