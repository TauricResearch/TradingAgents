from __future__ import annotations

import json

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable

from tradingagents.agents.portfolio.holding_reviewer import create_holding_reviewer


class _CapturingRunnable(Runnable):
    def __init__(self, content: str):
        self.content = content
        self.captured_inputs = []

    def invoke(self, input, config=None, **kwargs):
        self.captured_inputs.append(input)
        return AIMessage(content=self.content)


class _CapturingLLM(Runnable):
    def __init__(self, content: str):
        self.runnable = _CapturingRunnable(content)
        self.tools_bound = None

    def invoke(self, input, config=None, **kwargs):
        return self.runnable.invoke(input, config=config, **kwargs)

    def bind_tools(self, tools):
        self.tools_bound = tools
        return self.runnable


def _review_payload(rationale: str = "Thesis intact.") -> str:
    return json.dumps(
        {
            "AAPL": {
                "ticker": "AAPL",
                "recommendation": "HOLD",
                "confidence": "high",
                "rationale": rationale + (" x" * 1200),
                "key_risks": ["valuation compression"],
            }
        }
    )


def test_holding_reviewer_injects_completed_deep_dive_context_for_holdings():
    llm = _CapturingLLM(_review_payload())
    node = create_holding_reviewer(llm)
    state = {
        "messages": [HumanMessage(content="Review holdings.")],
        "analysis_date": "2026-03-30",
        "portfolio_data": json.dumps(
            {
                "portfolio": {"name": "Core"},
                "holdings": [
                    {"ticker": "AAPL", "shares": 10, "avg_cost": 180.0, "sector": "Technology"},
                    {"ticker": "MSFT", "shares": 5, "avg_cost": 410.0, "sector": "Technology"},
                ],
            }
        ),
        "ticker_analyses": {
            "AAPL": {
                "analysis_status": "completed",
                "final_trade_decision": "Action: Hold\nRating: Strong Hold\nReason: Services growth offsets hardware softness.",
                "trader_investment_plan": "Trail but stay long.",
                "investment_plan": "Compounder with buyback support.",
                "market_report": "Relative strength remains positive.",
                "fundamentals_report": "Gross margin resilient.",
            },
            "MSFT": {
                "analysis_status": "running",
                "final_trade_decision": "This incomplete analysis should not be included.",
            },
            "TSLA": {
                "analysis_status": "completed",
                "final_trade_decision": "This non-holding ticker should not be included.",
            },
        },
    }

    result = node(state)

    assert result["sender"] == "holding_reviewer"
    assert json.loads(result["holding_reviews"])["AAPL"]["recommendation"] == "HOLD"
    assert [tool.name for tool in llm.tools_bound] == ["get_stock_data", "get_news"]

    assert llm.runnable.captured_inputs, "LLM prompt was never invoked"
    messages = llm.runnable.captured_inputs[0]
    full_text = " ".join(
        message.content if hasattr(message, "content") else str(message)
        for message in messages
    )

    assert "Completed Deep Dive Analyses (authoritative prior thesis context)" in full_text
    assert "AAPL" in full_text
    assert "Strong Hold" in full_text
    assert "Treat those tools as an update layer on top of the saved deep-dive thesis" in full_text
    assert "This incomplete analysis should not be included." not in full_text
    assert "This non-holding ticker should not be included." not in full_text


def test_holding_reviewer_calls_out_missing_deep_dive_context():
    llm = _CapturingLLM(_review_payload("No prior thesis available."))
    node = create_holding_reviewer(llm)
    state = {
        "messages": [HumanMessage(content="Review holdings.")],
        "analysis_date": "2026-03-30",
        "portfolio_data": json.dumps(
            {
                "portfolio": {"name": "Core"},
                "holdings": [
                    {"ticker": "AAPL", "shares": 10, "avg_cost": 180.0, "sector": "Technology"},
                ],
            }
        ),
        "ticker_analyses": {},
    }

    node(state)

    messages = llm.runnable.captured_inputs[0]
    full_text = " ".join(
        message.content if hasattr(message, "content") else str(message)
        for message in messages
    )

    assert "No completed deep-dive ticker analyses available for current holdings." in full_text
    assert "If a holding has no completed deep-dive analysis, say that prior thesis context is missing" in full_text
