from unittest.mock import MagicMock


def test_initial_state_contains_market_snapshot_slots():
    from tradingagents.graph.propagation import Propagator

    state = Propagator().create_initial_state("AAPL", "2026-06-03")

    assert state["market_snapshot_text"] == ""
    assert state["market_snapshot_error"] == ""


def test_graph_prefetches_market_snapshot(monkeypatch):
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    class FakePropagator:
        def create_initial_state(
            self,
            company_name,
            trade_date,
            asset_type="stock",
            past_context="",
        ):
            return {
                "messages": [("human", company_name)],
                "company_of_interest": company_name,
                "asset_type": asset_type,
                "trade_date": trade_date,
                "past_context": past_context,
                "market_snapshot_text": "",
                "market_snapshot_error": "",
                "investment_debate_state": {},
                "risk_debate_state": {},
                "market_report": "",
                "fundamentals_report": "",
                "sentiment_report": "",
                "news_report": "",
                "derivatives_report": "",
            }

        def get_graph_args(self):
            return {}

    graph = object.__new__(TradingAgentsGraph)
    graph.memory_log = MagicMock(get_past_context=lambda ticker: "")
    graph.propagator = FakePropagator()
    graph.config = {"market_data_stale_after_seconds": 900}
    graph.run_recorder = MagicMock(start=lambda **kwargs: None)
    graph.debug = False
    graph.graph = MagicMock(
        invoke=lambda state, **kwargs: {
            **state,
            "final_trade_decision": "FINAL TRANSACTION PROPOSAL: **HOLD**",
            "trader_investment_plan": "",
            "investment_debate_state": {
                "bull_history": "",
                "bear_history": "",
                "history": "",
                "current_response": "",
                "judge_decision": "",
            },
            "risk_debate_state": {
                "aggressive_history": "",
                "conservative_history": "",
                "neutral_history": "",
                "history": "",
                "judge_decision": "",
            },
            "investment_plan": "",
        }
    )
    graph._log_state = MagicMock()
    graph.process_signal = lambda signal: "HOLD"
    graph.memory_log.store_decision = MagicMock()
    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.route_to_vendor",
        lambda method, ticker, trade_date, **kwargs: (
            "# Market snapshot for AAPL\n\n"
            "- Source: fused\n"
            "- Coverage: 5/5 expected sessions (100.00%)\n\n"
            "## Fused OHLCV Chart\n"
            "| date | open | high | low | close | volume | source |\n"
            "|---|---:|---:|---:|---:|---:|---|\n"
            "| 2026-06-05 | 14.0000 | 15.0000 | 13.0000 | 14.5000 | 140 | yfinance |\n"
        ),
    )

    final_state, decision = graph._run_graph("AAPL", "2026-06-03")

    assert decision == "HOLD"
    assert "# Market snapshot for AAPL" in final_state["market_snapshot_text"]
    assert final_state["market_snapshot_error"] == ""
    assert "## Fused OHLCV Chart" in final_state["market_snapshot_text"]
    assert "Coverage: 5/5 expected sessions" in final_state["market_snapshot_text"]
