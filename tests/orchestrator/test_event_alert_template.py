import pytest


@pytest.mark.unit
def test_render_event_alert_includes_terse_structure():
    from tradingagents.secretary.service import render_event_alert
    md = render_event_alert(
        ticker="AAPL",
        event={
            "event_id": "ev1",
            "source": "polygon_news",
            "ingested_ts": "2026-05-27T12:34:56+00:00",
            "raw_text": "Apple beats Q3 earnings by 12%.",
        },
        synthesis={
            "consensus": "Strong upside surprise.",
            "divergence": "Macro flags rate-sensitivity.",
            "recommendation": "BUY (high confidence)",
        },
        persona_runs=[
            {"persona_id": "macro", "decision": "HOLD", "final_trade_decision": "..."},
            {"persona_id": "value", "decision": "BUY",  "final_trade_decision": "..."},
            {"persona_id": "momentum", "decision": "BUY", "final_trade_decision": "..."},
        ],
    )
    # Terse structure: header, event, consensus/divergence/recommendation, links
    assert "AAPL" in md
    assert "Apple beats Q3 earnings by 12%." in md
    assert "Consensus" in md and "Strong upside surprise." in md
    assert "Divergence" in md
    assert "Recommendation" in md
    assert "BUY (high confidence)" in md
    # Per-persona table or list
    assert "macro" in md and "value" in md and "momentum" in md


@pytest.mark.unit
def test_render_event_alert_word_count_is_terse():
    """Per spec §6: ~200–400 words target. Verify lower bound."""
    from tradingagents.secretary.service import render_event_alert
    md = render_event_alert(
        ticker="AAPL",
        event={"event_id": "ev1", "source": "rss",
               "ingested_ts": "2026-05-27T12:34:56+00:00",
               "raw_text": "Short event text."},
        synthesis={"consensus": "x", "divergence": "y", "recommendation": "BUY"},
        persona_runs=[{"persona_id": "macro", "decision": "BUY",
                       "final_trade_decision": "z"}],
    )
    # Template chrome alone is non-empty.
    assert len(md.split()) >= 20
