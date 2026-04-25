"""Regression tests for PortfolioManagerState propagation through LangGraph."""

from __future__ import annotations

import json
from types import SimpleNamespace

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from tradingagents.agents.portfolio.macro_summary_agent import create_macro_summary_agent
from tradingagents.agents.portfolio.micro_summary_agent import create_micro_summary_agent
from tradingagents.agents.portfolio.pm_decision_agent import create_pm_decision_agent
from tradingagents.graph.portfolio_setup import PortfolioGraphSetup
from tradingagents.portfolio.models import Portfolio


class _FakeRepo:
    def get_portfolio_with_holdings(self, _portfolio_id, _prices):
        return (
            Portfolio(
                portfolio_id="portfolio-1",
                name="test",
                cash=0.0,
                initial_cash=0.0,
            ),
            [],
        )

    def take_snapshot(self, portfolio_id, _prices):
        return SimpleNamespace(
            to_dict=lambda: {
                "portfolio_id": portfolio_id,
                "cash": 0.0,
                "total_value": 0.0,
            }
        )


class _StructuredLLM:
    def __init__(self, capture: dict[str, str]):
        self.capture = capture

    def with_structured_output(self, schema):
        def _invoke(prompt_value):
            self.capture["pm"] = prompt_value.to_string()
            return schema(
                macro_regime="risk-on",
                regime_alignment_note="Macro and micro context present.",
                sells=[],
                buys=[],
                holds=[],
                cash_reserve_pct=100.0,
                portfolio_thesis="No execution in test.",
                risk_summary="No risk in test.",
                forensic_report={
                    "regime_alignment": "risk-on",
                    "key_risks": [],
                    "decision_confidence": "high",
                    "position_sizing_rationale": "test",
                },
            )

        return RunnableLambda(_invoke)


def test_portfolio_graph_preserves_portfolio_state_fields_for_summary_agents():
    capture: dict[str, str] = {}

    def _macro_llm(prompt_value):
        capture["macro"] = prompt_value.to_string()
        return AIMessage(content="MACRO REGIME: risk-on\nMACRO-ALIGNED TICKERS: AAPL")

    def _micro_llm(prompt_value):
        capture["micro"] = prompt_value.to_string()
        return AIMessage(
            content="CANDIDATES TABLE:\n| AAPL | high | growth | rating:Overweight | ok | no memory |"
        )

    agents = {
        "review_holdings": lambda _state: {"holding_reviews": "{}", "sender": "review_holdings"},
        "macro_summary": create_macro_summary_agent(RunnableLambda(_macro_llm)),
        "micro_summary": create_micro_summary_agent(RunnableLambda(_micro_llm)),
        "pm_decision": create_pm_decision_agent(_StructuredLLM(capture)),
    }

    graph = PortfolioGraphSetup(
        agents,
        repo=_FakeRepo(),
        config={
            "max_position_pct": 0.15,
            "max_sector_pct": 0.40,
            "min_cash_pct": 0.10,
            "max_positions": 10,
        },
    ).setup_graph()

    scan_candidate = {
        "ticker": "AAPL",
        "instrument_key": "equity:AAPL",
        "name": "Apple Inc.",
        "sector": "Technology",
        "conviction": "high",
        "thesis_angle": "growth",
        "rationale": "scan-selected",
        "key_catalysts": ["macro support"],
        "risks": ["valuation"],
    }
    ticker_analysis = {
        "analysis_status": "completed",
        "final_trade_decision": "Rating: Overweight\nExecutive Summary: durable moat",
        "trader_investment_plan": "BUY AAPL",
        "investment_plan": "BUY",
    }

    result = graph.invoke(
        {
            "portfolio_id": "portfolio-1",
            "analysis_date": "2026-04-24",
            "prices": {},
            "scan_summary": {
                "executive_summary": "Macro alive",
                "stocks_to_investigate": [scan_candidate],
                "equity_candidates": [scan_candidate],
                "key_themes": [{"theme": "Tech", "conviction": "high", "timeframe": "1 month"}],
                "risk_factors": ["valuation"],
            },
            "ticker_analyses": {"equity:AAPL": ticker_analysis},
            "messages": [],
            "portfolio_data": "",
            "risk_metrics": "",
            "holding_reviews": "",
            "prioritized_candidates": "",
            "macro_brief": "",
            "micro_brief": "",
            "macro_memory_context": "",
            "micro_memory_context": "",
            "pm_decision": "",
            "cash_sweep": "",
            "execution_result": "",
            "sender": "",
        }
    )

    assert "Macro alive" in capture["macro"]
    assert "current date is 2026-04-24" in capture["macro"]
    assert "AAPL | CANDIDATE | high | growth" in capture["micro"]
    assert "durable moat" in capture["micro"]
    assert "Input B — Direct Candidate Final Trade Decision Summaries" in capture["pm"]
    assert "durable moat" in capture["pm"]
    assert "No direct candidate final trade decision summaries available" not in capture["pm"]
    assert json.loads(result["pm_decision"])["macro_regime"] == "risk-on"
