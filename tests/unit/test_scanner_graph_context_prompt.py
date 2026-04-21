"""Tests that analyst/trader prompts consume scanner_graph_context_text and not scanner_context_packet."""
import pytest
from unittest.mock import MagicMock, patch


GRAPH_CTX = (
    "## Global Market Regime\n- Risk-On\n\n"
    "## Ticker Graph Context: ON\n- ON belongs to Technology."
)
RAW_PACKET = "RAW PACKET SHOULD NOT APPEAR"


def _make_state(ticker="ON", graph_ctx=GRAPH_CTX, raw_packet=RAW_PACKET):
    return {
        "company_of_interest": ticker,
        "trade_date": "2026-04-16",
        "scanner_graph_context_text": graph_ctx,
        "scanner_context_packet": raw_packet,
        "portfolio_context": "candidate",
        "run_id": "TESTRUN",
        "market_report": "",
        "market_report_structured": {},
        "sentiment_report": "",
        "news_report": "",
        "news_report_structured": {},
        "fundamentals_report": "",
        "fundamentals_report_structured": {},
        "investment_plan": "",
        "trader_investment_plan": "",
        "macro_regime_report": "",
        "messages": [],
        "instrument_key": "ON",
        "asset_class": "equity",
        "instrument_type": "stock",
        "is_etf": False,
        "is_inverse": False,
        "is_leveraged": False,
    }


def _extract_prompt_text(mock_llm):
    """Extract all text passed to the mock LLM."""
    texts = []
    for call in mock_llm.call_args_list:
        args, kwargs = call
        for arg in args:
            if isinstance(arg, list):
                for msg in arg:
                    if hasattr(msg, "content"):
                        texts.append(msg.content)
                    elif isinstance(msg, (list, tuple)) and len(msg) >= 2:
                        texts.append(str(msg[1]))
                    else:
                        texts.append(str(msg))
            else:
                texts.append(str(arg))
    return "\n".join(texts)


def test_summary_context_uses_graph_context_header():
    """build_research_packet must emit ## Scanner Graph Context section."""
    from tradingagents.agents.utils.summary_context import build_research_packet
    state = _make_state()
    result = build_research_packet(state)
    assert "Scanner Graph Context" in result or "Ticker Graph Context: ON" in result


def test_summary_context_does_not_use_raw_packet():
    """build_research_packet must not include raw scanner_context_packet."""
    from tradingagents.agents.utils.summary_context import build_research_packet
    state = _make_state()
    result = build_research_packet(state)
    assert RAW_PACKET not in result


def test_debate_evidence_brief_uses_graph_context():
    """build_debate_evidence_brief must include scanner graph context."""
    from tradingagents.agents.utils.summary_context import build_debate_evidence_brief
    state = _make_state()
    result = build_debate_evidence_brief(state)
    assert "Ground Truth" in result or "Ticker Graph Context" in result


def test_context_summaries_has_context_with_graph_text():
    """create_research_packet_summary must consider scanner_graph_context_text when deciding if context exists."""
    from tradingagents.agents.managers.context_summaries import create_research_packet_summary
    # With graph context set: has_context should produce non-empty output
    state_with = _make_state(graph_ctx=GRAPH_CTX, raw_packet="")
    node = create_research_packet_summary(None)
    result = node(state_with)
    assert result["research_packet_summary"]


def test_context_summaries_no_context_without_either():
    """create_research_packet_summary returns empty when neither scanner field has content."""
    from tradingagents.agents.managers.context_summaries import create_research_packet_summary
    state_empty = _make_state(graph_ctx="", raw_packet="")
    # Remove other report fields too
    state_empty["market_report"] = ""
    state_empty["fundamentals_report"] = ""
    state_empty["sentiment_report"] = ""
    state_empty["news_report"] = ""
    state_empty["market_report_structured"] = {}
    state_empty["fundamentals_report_structured"] = {}
    state_empty["sentiment_report_structured"] = {}
    state_empty["news_report_structured"] = {}
    state_empty["macro_regime_report"] = ""
    node = create_research_packet_summary(None)
    result = node(state_empty)
    assert not result["research_packet_summary"]
