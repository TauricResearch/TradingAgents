from tradingagents.agents.managers.critical_abort_terminal import create_critical_abort_terminal
from tradingagents.agents.utils.critical_abort import has_abort, raise_abort
from tradingagents.graph.conditional_logic import CRITICAL_ABORT_NODE, ConditionalLogic


def test_raise_abort_builds_structured_signal_without_report_marker():
    update = raise_abort(
        source="news_analyst",
        reason="news_prefetch_failed",
        detail="Both news feeds failed for AAPL.",
        recoverable=True,
    )

    assert set(update) == {"abort_signal"}
    signal = update["abort_signal"]
    assert signal["source"] == "news_analyst"
    assert signal["reason"] == "news_prefetch_failed"
    assert signal["detail"] == "Both news feeds failed for AAPL."
    assert signal["recoverable"] is True
    assert signal["raised_at"].endswith("+00:00")


def test_has_abort_ignores_legacy_report_marker_text():
    assert has_abort({"abort_signal": None}) is False
    assert has_abort({"market_report": "[CRITICAL ABORT] quoted text"}) is False
    assert has_abort({"abort_signal": {"reason": "market_data_unavailable"}}) is True


def test_conditional_logic_routes_only_on_abort_signal():
    cl = ConditionalLogic()
    state = {
        "abort_signal": {
            "source": "news_analyst",
            "reason": "news_prefetch_failed",
            "detail": "Both feeds failed.",
            "raised_at": "2026-04-25T00:00:00+00:00",
            "recoverable": True,
        },
        "investment_debate_state": {"count": 0, "current_response": ""},
        "risk_debate_state": {"count": 0, "latest_speaker": "Aggressive Analyst"},
    }

    assert cl.should_continue_debate(state) == CRITICAL_ABORT_NODE


def test_critical_abort_terminal_uses_structured_payload():
    node = create_critical_abort_terminal()
    state = {
        "company_of_interest": "AAPL",
        "portfolio_context": "candidate",
        "abort_signal": {
            "source": "news_analyst",
            "reason": "news_prefetch_failed",
            "detail": "Both news feeds failed for AAPL.",
            "raised_at": "2026-04-25T00:00:00+00:00",
            "recoverable": True,
        },
    }

    result = node(state)

    assert result["analysis_status"] == "aborted"
    assert result["terminal_action"] == "AVOID"
    assert result["abort_signal"] == state["abort_signal"]
    assert "news_analyst" in result["final_trade_decision"]
    assert "news_prefetch_failed" in result["final_trade_decision"]
