import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from tradingagents.graph.trading_graph import TradingAgentsGraph


def _make_graph(chunks):
    """Helper: build a mocked TradingAgentsGraph whose graph.stream yields chunks."""
    with patch.object(TradingAgentsGraph, '__init__', lambda self, *a, **kw: None):
        ta = TradingAgentsGraph.__new__(TradingAgentsGraph)
    ta.graph = MagicMock()
    ta.graph.stream.return_value = iter(chunks)
    ta.graph.get_state.return_value = MagicMock(next=None)  # no checkpoint to resume
    ta.quick_thinking_llm = MagicMock()
    ta.signal_processor = MagicMock()
    ta.signal_processor.process_signal.return_value = "BUY"
    ta.config = {"llm_provider": "openai", "deep_think_llm": "gpt-4",
                 "quick_think_llm": "gpt-4-mini", "max_debate_rounds": 1,
                 "max_risk_discuss_rounds": 1, "results_dir": "./results"}
    ta._last_decision = None
    ta.selected_analysts = ["market", "news", "fundamentals", "social"]
    # propagator needed by stream_propagate for initial state and graph args
    ta.propagator = MagicMock()
    ta.propagator.create_initial_state.return_value = {
        "messages": [], "company_of_interest": "NVDA", "trade_date": "2026-03-23",
        "investment_debate_state": {
            "bull_history": "", "bear_history": "", "history": "",
            "current_response": "", "judge_decision": "", "count": 0
        },
        "risk_debate_state": {
            "aggressive_history": "", "conservative_history": "", "neutral_history": "",
            "history": "", "latest_speaker": "", "current_aggressive_response": "",
            "current_conservative_response": "", "current_neutral_response": "",
            "judge_decision": "", "count": 0
        },
        "market_report": "", "fundamentals_report": "",
        "sentiment_report": "", "news_report": "",
    }
    ta.propagator.get_graph_args.return_value = {
        "stream_mode": "updates",
        "config": {"configurable": {"thread_id": "test-thread"}, "recursion_limit": 100},
    }
    # _log_state writes to disk — mock it out in all tests
    ta._log_state = MagicMock()
    return ta


def test_yields_known_node():
    ta = _make_graph([
        {"Market Analyst": {"market_report": "bullish outlook"}},
    ])
    results = list(ta.stream_propagate("NVDA", "2026-03-23"))
    assert results == [("market_analyst", "bullish outlook")]


def test_skips_tool_nodes():
    ta = _make_graph([
        {"tools_market": {"messages": []}},
        {"Market Analyst": {"market_report": "ok"}},
    ])
    results = list(ta.stream_propagate("NVDA", "2026-03-23"))
    assert len(results) == 1
    assert results[0][0] == "market_analyst"


def test_skips_msg_clear_nodes():
    ta = _make_graph([
        {"Msg Clear Market": {}},
        {"News Analyst": {"news_report": "stable"}},
    ])
    results = list(ta.stream_propagate("NVDA", "2026-03-23"))
    assert len(results) == 1
    assert results[0][0] == "news_analyst"


def test_skips_unknown_nodes_with_warning(caplog):
    import logging
    ta = _make_graph([
        {"Unknown Future Node": {"some_field": "value"}},
        {"Trader": {"trader_investment_plan": "buy 100 shares"}},
    ])
    with caplog.at_level(logging.WARNING):
        results = list(ta.stream_propagate("NVDA", "2026-03-23"))
    assert len(results) == 1
    assert results[0][0] == "trader"
    assert any("Unknown Future Node" in r.message for r in caplog.records)


def test_last_decision_set_after_exhaustion():
    ta = _make_graph([
        {"Risk Judge": {"risk_debate_state": {"judge_decision": "SELL signal strong"}}},
    ])
    # graph.get_state() is called post-loop to fetch the full final snapshot
    ta.graph.get_state.return_value = MagicMock(
        next=None,
        values={"final_trade_decision": "strong SELL signal from risk team"}
    )

    list(ta.stream_propagate("NVDA", "2026-03-23"))
    # signal_processor returns "BUY" from mock setup; _last_decision should be set
    assert ta._last_decision == "BUY"


def test_bull_researcher_extracts_bull_history():
    ta = _make_graph([
        {"Bull Researcher": {"investment_debate_state": {
            "bull_history": "bullish case round 1", "bear_history": "",
            "history": "", "current_response": "", "judge_decision": "", "count": 1
        }}},
    ])
    results = list(ta.stream_propagate("NVDA", "2026-03-23"))
    assert results[0] == ("bull_researcher", "bullish case round 1")


def test_research_manager_extracts_investment_plan():
    ta = _make_graph([
        {"Research Manager": {"investment_plan": "Invest 20% in NVDA"}},
    ])
    results = list(ta.stream_propagate("NVDA", "2026-03-23"))
    assert results[0] == ("research_manager", "Invest 20% in NVDA")


def test_missing_field_yields_empty_string():
    ta = _make_graph([
        {"Market Analyst": {}},  # no market_report key
    ])
    results = list(ta.stream_propagate("NVDA", "2026-03-23"))
    assert results[0] == ("market_analyst", "")
