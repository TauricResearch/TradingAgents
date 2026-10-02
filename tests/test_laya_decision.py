"""Tests for the optional Ollaya decision-model shadow adapter."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import requests

from tradingagents.graph.laya_decision import (
    LAYA_STATE_BUDGET_BYTES,
    LayaDecisionAdapter,
    create_laya_assessment_node,
    render_laya_assessments,
)


def _response(data):
    return SimpleNamespace(
        headers={"X-Request-Id": "req-test"},
        raise_for_status=lambda: None,
        json=lambda: data,
    )


def _adapter():
    return LayaDecisionAdapter("http://127.0.0.1:11435", "laya:latest", 45)


@pytest.mark.unit
def test_assess_sends_typed_choice_and_returns_probabilities(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        requests,
        "post",
        lambda url, **kwargs: captured.update(url=url, **kwargs)
        or _response({
            "model": "laya:en",
            "answers": {
                "research_direction": {
                    "type": "choice",
                    "choice": "bullish",
                    "confidence": 0.7,
                    "probabilities": {"bullish": 0.8, "bearish": 0.1, "insufficient_evidence": 0.1},
                }
            },
            "routing": {"router": "laya:latest", "model": "laya:en"},
            "state_truncated": False,
            "created_at": "2026-09-28T10:00:00Z",
            "total_duration": 123,
            "usage": {"input_tokens": 20, "output_tokens": 0},
        }),
    )

    assessment = _adapter().assess(
        "research",
        {"company_of_interest": "TEST", "trade_date": "2026-09-28", "market_report": "evidence"},
    )

    assert captured["url"] == "http://127.0.0.1:11435/api/decide"
    assert captured["json"]["model"] == "laya:latest"
    assert captured["json"]["extras"] == ["laya"]
    assert captured["json"]["questions"]["research_direction"]["criteria"] == [
        "bullish", "bearish", "insufficient_evidence"
    ]
    assert assessment["status"] == "ok"
    assert assessment["model"] == "laya:en"
    assert assessment["answer"]["probabilities"]["bullish"] == 0.8
    assert assessment["input_snapshot"]["market_report"] == "evidence"
    assert assessment["request_id"] == "req-test"
    assert len(assessment["input_sha256"]) == 64


@pytest.mark.unit
def test_truncated_assessment_is_marked_unusable(monkeypatch):
    monkeypatch.setattr(
        requests,
        "post",
        lambda *args, **kwargs: _response({
            "model": "laya:en",
            "answers": {"portfolio_action": {"choice": "Buy"}},
            "state_truncated": True,
        }),
    )

    assessment = _adapter().assess("portfolio", {"final_trade_decision": "Hold"})

    assert assessment["status"] == "truncated"
    assert assessment["state_truncated"] is True


@pytest.mark.unit
@pytest.mark.parametrize(
    ("phase", "question"),
    [
        ("research", "research_direction"),
        ("trader", "proposal_support"),
        ("risk", "risk_response"),
        ("portfolio", "portfolio_action"),
    ],
)
def test_oversized_state_is_compacted_for_laya_only(monkeypatch, phase, question):
    captured = {}

    def post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return _response({
            "model": "laya:en",
            "answers": {question: {"choice": "Hold"}},
            "state_truncated": False,
        })

    monkeypatch.setattr(requests, "post", post)
    original_market_report = "Market evidence. " * 500
    state = {
        "company_of_interest": "TEST",
        "trade_date": "2026-10-02",
        "market_report": original_market_report,
        "investment_plan": "Investment plan. " * 500,
        "investment_debate_state": {
            "history": ["old debate. " * 100, "recent debate. " * 100],
        },
        "trader_investment_plan": "Trader plan. " * 500,
        "risk_debate_state": {
            "history": ["old position. " * 100, "recent position. " * 100],
        },
        "final_trade_decision": "Hold",
    }

    assessment = _adapter().assess(phase, state)

    sent_state = captured["json"]["state"]
    sent_size = len(json.dumps(sent_state, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    assert sent_size <= LAYA_STATE_BUDGET_BYTES
    assert sent_state["company_of_interest"] == "TEST"
    assert " ... " in sent_state["investment_plan"]
    if "risk_debate_state" in sent_state:
        assert sent_state["risk_debate_state"]["history"][-1].endswith("recent position. ")
    assert assessment["input_compacted"] is True
    assert assessment["input_bytes"] == sent_size
    assert assessment["original_input_bytes"] > sent_size
    assert state["market_report"] == original_market_report


@pytest.mark.unit
def test_final_action_uses_buy_hold_trim_sell_and_abstain_options():
    from tradingagents.graph.laya_decision import _PHASES

    final_options = _PHASES["portfolio"]["criteria"]
    assert final_options == [
        "Buy", "Overweight", "Hold", "Trim", "Sell", "Insufficient evidence"
    ]
    instructions = _PHASES["portfolio"]["instructions"].lower()
    assert "instrument-specific sentiment" in instructions
    assert "sector-level" in instructions
    assert "broad or indirect news" in instructions
    assert "fundamentals" in instructions and "risk controls" in instructions


@pytest.mark.unit
def test_assessment_renderer_shows_probabilities_and_shadow_caveat():
    rendered = render_laya_assessments({
        "portfolio": {
            "status": "ok",
            "model": "laya:en",
            "answer": {
                "choice": "Trim",
                "probabilities": {
                    "Buy": 0.1,
                    "Overweight": 0.05,
                    "Hold": 0.2,
                    "Trim": 0.55,
                    "Sell": 0.1,
                    "Insufficient evidence": 0.05,
                },
            },
        }
    })

    assert "Final portfolio action:** Trim" in rendered
    assert "Trim: 55.0%" in rendered
    assert "Overweight: 5.0%" in rendered
    assert "Insufficient evidence: 5.0%" in rendered
    assert "not probabilities of profit" in rendered
    assert "shadow-only" in rendered


@pytest.mark.unit
def test_transport_failure_is_fail_open(monkeypatch):
    def fail(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests, "post", fail)
    assessment = _adapter().assess("risk", {"trade_date": "2026-09-28"})

    assert assessment["status"] == "error"
    assert assessment["error_code"] is None


@pytest.mark.unit
def test_disabled_node_does_not_change_graph_state():
    node = create_laya_assessment_node(None, "research")

    assert node({"investment_plan": "Buy"}) == {}


@pytest.mark.unit
def test_graph_places_assessments_at_decision_boundaries(monkeypatch):
    from langchain_core.runnables import RunnableLambda

    import tradingagents.graph.setup as graph_setup
    from tradingagents.graph.conditional_logic import ConditionalLogic

    def empty_node(*args):
        return RunnableLambda(lambda state: {})

    for name in (
        "create_market_analyst",
        "create_sentiment_analyst",
        "create_news_analyst",
        "create_fundamentals_analyst",
        "create_bull_researcher",
        "create_bear_researcher",
        "create_research_manager",
        "create_trader",
        "create_aggressive_debator",
        "create_neutral_debator",
        "create_conservative_debator",
        "create_portfolio_manager",
        "create_msg_delete",
    ):
        monkeypatch.setattr(graph_setup, name, empty_node)

    tool_nodes = {
        name: RunnableLambda(lambda state: {})
        for name in ("market", "social", "news", "fundamentals")
    }
    workflow = graph_setup.GraphSetup(
        object(),
        object(),
        tool_nodes,
        ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1),
    ).setup_graph()
    edges = {
        (edge.source, edge.target)
        for edge in workflow.compile().get_graph().edges
    }

    assert ("Research Manager", "Laya Research Assessment") in edges
    assert ("Laya Research Assessment", "Trader") in edges
    assert ("Trader", "Laya Trader Assessment") in edges
    assert ("Laya Trader Assessment", "Aggressive Analyst") in edges
    assert ("Laya Risk Assessment", "Portfolio Manager") in edges
    assert ("Portfolio Manager", "Laya Portfolio Assessment") in edges
