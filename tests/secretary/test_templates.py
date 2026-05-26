import pytest


@pytest.mark.unit
def test_deep_dive_template_renders_with_all_sections():
    from tradingagents.secretary.service import render_deep_dive
    out = render_deep_dive(
        ticker="AAPL",
        trade_date="2026-05-25",
        synthesis={
            "consensus": "Cashflow yield strong.",
            "divergence": "Macro says SELL; momentum and value say BUY.",
            "recommendation": "HOLD — low-confidence call.",
        },
        persona_runs=[
            {"persona_id": "macro", "decision": "SELL", "final_trade_decision": "macro reasoning"},
            {"persona_id": "value", "decision": "BUY", "final_trade_decision": "value reasoning"},
            {"persona_id": "momentum", "decision": "BUY", "final_trade_decision": "momentum reasoning"},
        ],
    )
    # Header
    assert "AAPL" in out
    assert "2026-05-25" in out
    # All three synthesis sections
    assert "Consensus" in out and "Cashflow yield strong" in out
    assert "Divergence" in out and "Macro says SELL" in out
    assert "Recommendation" in out and "HOLD" in out
    # Per-persona detail
    for pid in ("macro", "value", "momentum"):
        assert pid in out
