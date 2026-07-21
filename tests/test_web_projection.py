"""RunProjector: raw ``updates`` chunks -> slim typed events."""

from types import SimpleNamespace

import pytest

from tradingagents.web.projection import RunProjector

pytestmark = pytest.mark.unit


def _msg(content="", tool_calls=None, message_id=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls or [], id=message_id)


def _events_of(events, event_type):
    return [data for etype, data in events if etype == event_type]


def test_analyst_lifecycle_working_then_done():
    projector = RunProjector(["market", "social"])

    events = projector.feed({"Market Analyst": {"messages": [_msg("thinking")]}})
    statuses = {e["agent"]: e["status"] for e in _events_of(events, "agent_status")}
    assert statuses["Market Analyst"] == "working"

    events = projector.feed({
        "Market Analyst": {"messages": [], "market_report": "# Market\ncontent"},
    })
    statuses = {e["agent"]: e["status"] for e in _events_of(events, "agent_status")}
    assert statuses["Market Analyst"] == "done"
    sections = _events_of(events, "report_section")
    assert sections == [{"section": "market_report", "markdown": "# Market\ncontent"}]


def test_tool_node_marks_analyst_working_and_emits_tool_calls():
    projector = RunProjector(["market"])
    message = _msg(tool_calls=[{"name": "get_stock_data", "args": {"symbol": "AAPL"}}])

    events = projector.feed({"Market Analyst": {"messages": [message]}})
    tool_calls = _events_of(events, "tool_call")
    assert tool_calls[0]["name"] == "get_stock_data"
    assert "AAPL" in tool_calls[0]["args_preview"]
    assert projector.tool_call_count == 1


def test_message_ids_deduplicated():
    projector = RunProjector(["market"])
    message = _msg("hello", message_id="m1")
    first = projector.feed({"Market Analyst": {"messages": [message]}})
    second = projector.feed({"tools_market": {"messages": [message]}})
    assert len(_events_of(first, "message")) == 1
    assert len(_events_of(second, "message")) == 0


def test_debate_composes_investment_plan_and_flips_research_team():
    projector = RunProjector(["market"])
    projector.feed({"Market Analyst": {"market_report": "done"}})

    events = projector.feed({
        "Bull Researcher": {
            "investment_debate_state": {
                "bull_history": "bull case",
                "bear_history": "",
                "judge_decision": "",
            },
        },
    })
    statuses = {e["agent"]: e["status"] for e in _events_of(events, "agent_status")}
    assert statuses["Bull Researcher"] == "working"
    sections = _events_of(events, "report_section")
    assert sections[0]["section"] == "investment_plan"
    assert "### Bull Researcher Analysis" in sections[0]["markdown"]

    events = projector.feed({
        "Research Manager": {
            "investment_debate_state": {
                "bull_history": "bull case",
                "bear_history": "bear case",
                "judge_decision": "go long",
            },
            "investment_plan": "final research plan",
        },
    })
    statuses = {e["agent"]: e["status"] for e in _events_of(events, "agent_status")}
    assert statuses["Bull Researcher"] == "done"
    assert statuses["Bear Researcher"] == "done"
    assert statuses["Research Manager"] == "done"
    assert statuses["Trader"] == "working"
    sections = {e["section"]: e["markdown"] for e in _events_of(events, "report_section")}
    assert sections["investment_plan"] == "final research plan"


def test_risk_judge_completes_risk_team_and_final_section():
    projector = RunProjector(["market"])
    projector.feed({"Trader": {"trader_investment_plan": "trade plan"}})

    events = projector.feed({
        "Portfolio Manager": {
            "risk_debate_state": {
                "aggressive_history": "risk on",
                "conservative_history": "risk off",
                "neutral_history": "meh",
                "judge_decision": "BUY with stop",
            },
            "final_trade_decision": "FINAL: BUY",
        },
    })
    statuses = {e["agent"]: e["status"] for e in _events_of(events, "agent_status")}
    for agent in (
        "Aggressive Analyst", "Conservative Analyst", "Neutral Analyst", "Portfolio Manager",
    ):
        assert statuses[agent] == "done"
    sections = {e["section"]: e["markdown"] for e in _events_of(events, "report_section")}
    assert sections["final_trade_decision"] == "FINAL: BUY"


def test_section_events_only_on_change():
    projector = RunProjector(["market"])
    first = projector.feed({"Market Analyst": {"market_report": "v1"}})
    repeat = projector.feed({"tools_market": {"messages": []}})
    assert len(_events_of(first, "report_section")) == 1
    assert len(_events_of(repeat, "report_section")) == 0


def test_final_events_mark_everything_done():
    projector = RunProjector(["market"])
    projector.state.update({
        "market_report": "m",
        "investment_plan": "i",
        "trader_investment_plan": "t",
        "final_trade_decision": "f",
    })
    events = projector.final_events()
    statuses = {e["agent"] for e in _events_of(events, "agent_status")}
    assert "Portfolio Manager" in statuses
    assert all(
        e["status"] == "done" for e in _events_of(events, "agent_status")
    )
    sections = {e["section"] for e in _events_of(events, "report_section")}
    assert sections == {
        "market_report", "investment_plan", "trader_investment_plan", "final_trade_decision",
    }


def test_unselected_analysts_are_absent():
    projector = RunProjector(["news"])
    assert "Market Analyst" not in projector.agent_status
    assert "News Analyst" in projector.agent_status
    events = projector.feed({"News Analyst": {"news_report": "n"}})
    statuses = {e["agent"]: e["status"] for e in _events_of(events, "agent_status")}
    assert statuses["News Analyst"] == "done"
