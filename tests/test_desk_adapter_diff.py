"""Unit tests for the dependency-free snapshot->events diff (desk_adapter.diff).

These import only ``desk_adapter.diff`` (no ``tradingagents``), so they run on
any interpreter. Under CI they run via pytest; locally they can also be run
directly: ``PYTHONPATH=. python3 tests/test_desk_adapter_diff.py``.
"""

from __future__ import annotations

from desk_adapter.diff import (
    SnapshotDiffer,
    extract_content_string,
    extract_sentiment_score,
)


class _Msg:
    """Minimal duck-typed stand-in for a LangChain message."""

    def __init__(self, type, content="", id=None, tool_calls=None, tool_call_id=None, name=None):
        self.type = type
        self.content = content
        self.id = id
        if tool_calls is not None:
            self.tool_calls = tool_calls
        if tool_call_id is not None:
            self.tool_call_id = tool_call_id
        if name is not None:
            self.name = name


def _types(events):
    return [e["type"] for e in events]


def _of(events, type_):
    return [e for e in events if e["type"] == type_]


def test_extract_content_string_variants():
    assert extract_content_string("  hi  ") == "hi"
    assert extract_content_string("") is None
    assert extract_content_string("   ") is None
    assert extract_content_string([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]) == "a b"
    assert extract_content_string({"text": "x"}) == "x"
    # A bare "[]" is empty per literal_eval; real prose is kept.
    assert extract_content_string("[]") is None


def test_debate_quoted_opponent_does_not_create_phantom_turn():
    # A bear turn that quotes the bull by name at line start must NOT be split into
    # a phantom Bull turn or shift the round numbering (the previous combined-history
    # parser did exactly that).
    d = SnapshotDiffer(["market"])
    s = {"messages": [], "investment_debate_state": {
        "bull_history": "\nBull Analyst: growth is strong",
        "bear_history": "\nBear Analyst: rebuttal\nBull Analyst: claimed growth is strong but margins are thin",
        "count": 2,
    }}
    turns = _of(d.process(s), "debate_turn")
    assert [t["speaker"] for t in turns] == ["Bull Analyst", "Bear Analyst"]
    assert turns[1]["text"].startswith("rebuttal")
    assert "claimed growth is strong" in turns[1]["text"]  # quote stays inside the bear's turn
    assert turns[0]["round"] == 1 and turns[1]["round"] == 1


def test_sentiment_score_extraction():
    assert extract_sentiment_score("**Overall Sentiment: Bullish (Score: 7.5/10)**") == 7.5
    assert extract_sentiment_score("no score here") is None


def test_report_section_emitted_once_and_marks_finalized():
    d = SnapshotDiffer(["market"])
    ev1 = d.process({"messages": [], "market_report": "MKT"})
    rs = _of(ev1, "report_section")
    assert len(rs) == 1
    assert rs[0]["section"] == "market_report"
    assert rs[0]["finalized"] is True  # only analyst selected -> Market Analyst completed
    # Same content again -> no duplicate report_section.
    ev2 = d.process({"messages": [], "market_report": "MKT"})
    assert _of(ev2, "report_section") == []


def test_node_status_transitions_across_analysts():
    d = SnapshotDiffer(["market", "news"])
    # First snapshot: market becomes in_progress (news stays pending).
    ev1 = d.process({"messages": []})
    market = [e for e in _of(ev1, "node_status") if e["node"] == "Market Analyst"]
    assert market and market[0]["state"] == "in_progress"
    assert market[0]["group"] == "analyst"
    # Market report arrives -> market completed, news in_progress.
    ev2 = d.process({"messages": [], "market_report": "done"})
    states = {e["node"]: e["state"] for e in _of(ev2, "node_status")}
    assert states.get("Market Analyst") == "completed"
    assert states.get("News Analyst") == "in_progress"


def test_tool_call_result_join_and_no_data_flag():
    d = SnapshotDiffer(["news"])
    ai = _Msg("ai", content="checking news", id="a1", tool_calls=[{"name": "get_news", "args": {"q": "AAPL"}, "id": "c1"}])
    tool_ok = _Msg("tool", content="headline A\nheadline B", id="t1", tool_call_id="c1")
    events = d.process({"messages": [ai, tool_ok]})
    calls = _of(events, "tool_call")
    results = _of(events, "tool_result")
    assert calls[0]["name"] == "get_news" and calls[0]["args"] == {"q": "AAPL"}
    assert results[0]["name"] == "get_news"  # joined via tool_call_id
    assert results[0]["data_status"] == "ok" and results[0]["ok"] is True
    # agent_step carries the reasoning text attributed to the active node.
    steps = _of(events, "agent_step")
    assert steps and steps[0]["text"] == "checking news"

    # NO_DATA sentinel flips the flag.
    ai2 = _Msg("ai", id="a2", tool_calls=[{"name": "get_news", "args": {}, "id": "c2"}])
    tool_nd = _Msg("tool", content="NO_DATA_AVAILABLE: reddit down", id="t2", tool_call_id="c2")
    ev2 = d.process({"messages": [ai2, tool_nd]})
    r2 = _of(ev2, "tool_result")[0]
    assert r2["data_status"] == "no_data" and r2["ok"] is False


def test_message_dedup_by_id():
    d = SnapshotDiffer(["market"])
    ai = _Msg("ai", content="hello", id="dup1")
    first = d.process({"messages": [ai]})
    second = d.process({"messages": [ai]})  # same id in a later snapshot
    assert len(_of(first, "agent_step")) == 1
    assert _of(second, "agent_step") == []


def test_investment_debate_turns_then_judge():
    d = SnapshotDiffer(["market"])
    s1 = {"messages": [], "investment_debate_state": {
        "bull_history": "\nBull Analyst: up", "bear_history": "\nBear Analyst: down", "count": 2}}
    turns = _of(d.process(s1), "debate_turn")
    assert [t["speaker"] for t in turns] == ["Bull Analyst", "Bear Analyst"]
    assert turns[0]["round"] == 1 and turns[1]["round"] == 1
    assert all(t["debate"] == "investment" for t in turns)
    # A new bull turn appended -> only the new one is emitted (round 2).
    s2 = {"messages": [], "investment_debate_state": {
        "bull_history": "\nBull Analyst: up\nBull Analyst: still up", "bear_history": "\nBear Analyst: down", "count": 3}}
    new = _of(d.process(s2), "debate_turn")
    assert len(new) == 1 and new[0]["index"] == 3 and new[0]["round"] == 2
    # Judge decision emits one is_judge turn from the Research Manager.
    s3 = {"messages": [], "investment_debate_state": {
        "bull_history": s2["investment_debate_state"]["bull_history"],
        "bear_history": "\nBear Analyst: down", "judge_decision": "BUY", "count": 3}}
    judge = _of(d.process(s3), "debate_turn")
    assert len(judge) == 1 and judge[0]["is_judge"] is True and judge[0]["speaker"] == "Research Manager"


def test_risk_debate_three_way_rounds():
    d = SnapshotDiffer(["market"])
    s = {"messages": [], "risk_debate_state": {
        "aggressive_history": "\nAggressive Analyst: a",
        "conservative_history": "\nConservative Analyst: c",
        "neutral_history": "\nNeutral Analyst: n",
        "latest_speaker": "Neutral", "count": 3}}
    turns = _of(d.process(s), "debate_turn")
    assert [t["speaker"] for t in turns] == ["Aggressive Analyst", "Conservative Analyst", "Neutral Analyst"]
    assert all(t["round"] == 1 for t in turns)  # 3 speakers per round
    assert all(t["debate"] == "risk" for t in turns)


if __name__ == "__main__":
    import sys
    import traceback

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
