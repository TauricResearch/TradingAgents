"""Tests for _extract_action_llm — all LLM calls are mocked."""
import json
from unittest.mock import MagicMock

import pytest


def _make_llm_response(payload: dict) -> MagicMock:
    msg = MagicMock()
    msg.content = json.dumps(payload)
    return msg


def _make_llm(response_msg):
    llm = MagicMock()
    llm.invoke.return_value = response_msg
    return llm


def test_llm_high_confidence_buy():
    from tradingagents.agents.utils.output_validation import _extract_action_llm

    llm = _make_llm(_make_llm_response({"action": "BUY", "confidence": "high", "evidence_quote": "Rating: Buy"}))
    result = _extract_action_llm("some text", llm=llm)
    assert result.action == "BUY"
    assert result.confidence == "high"
    assert result.source == "llm"
    assert result.evidence_quote == "Rating: Buy"


def test_llm_med_confidence_sell():
    from tradingagents.agents.utils.output_validation import _extract_action_llm

    llm = _make_llm(_make_llm_response({"action": "SELL", "confidence": "med", "evidence_quote": "bearish view"}))
    result = _extract_action_llm("some text", llm=llm)
    assert result.action == "SELL"
    assert result.confidence == "med"


def test_llm_low_confidence_returns_sentinel():
    """Low confidence must return sentinel, not raise — caller decides."""
    from tradingagents.agents.utils.output_validation import _extract_action_llm

    llm = _make_llm(_make_llm_response({"action": "HOLD", "confidence": "low", "evidence_quote": None}))
    result = _extract_action_llm("ambiguous", llm=llm)
    assert result.confidence == "low"
    assert result.source == "llm"


def test_llm_invalid_json_returns_sentinel():
    from tradingagents.agents.utils.output_validation import _extract_action_llm

    msg = MagicMock()
    msg.content = "not json at all"
    llm = _make_llm(msg)
    result = _extract_action_llm("text", llm=llm)
    assert result.confidence == "low"
    assert result.action == "HOLD"


def test_llm_invalid_action_enum_returns_sentinel():
    from tradingagents.agents.utils.output_validation import _extract_action_llm

    llm = _make_llm(_make_llm_response({"action": "MAYBE", "confidence": "high", "evidence_quote": "x"}))
    result = _extract_action_llm("text", llm=llm)
    assert result.confidence == "low"


def test_llm_timeout_returns_sentinel():
    from tradingagents.agents.utils.output_validation import _extract_action_llm

    llm = MagicMock()
    llm.invoke.side_effect = TimeoutError("timed out")
    result = _extract_action_llm("text", llm=llm)
    assert result.confidence == "low"


def test_llm_evidence_quote_propagated():
    from tradingagents.agents.utils.output_validation import _extract_action_llm

    quote = "The final rating is Buy given strong earnings momentum"
    llm = _make_llm(_make_llm_response({"action": "BUY", "confidence": "high", "evidence_quote": quote}))
    result = _extract_action_llm("...", llm=llm)
    assert result.evidence_quote == quote


# Orchestrator tests


def test_extract_action_uses_regex_first_no_llm_call():
    """When regex matches, LLM is never called."""
    from tradingagents.agents.utils.output_validation import extract_action

    llm = MagicMock()
    result = extract_action("FINAL TRANSACTION PROPOSAL: **BUY**", llm=llm)
    assert result.action == "BUY"
    assert result.source == "regex"
    llm.invoke.assert_not_called()


def test_extract_action_falls_back_to_llm_on_regex_miss():
    from tradingagents.agents.utils.output_validation import extract_action

    llm = _make_llm(_make_llm_response({"action": "SELL", "confidence": "high", "evidence_quote": "sell"}))
    result = extract_action("Some prose without a clear label.", llm=llm)
    assert result.action == "SELL"
    assert result.source == "llm"


def test_extract_action_raises_on_low_confidence():
    from tradingagents.agents.utils.output_validation import ActionExtractionError, extract_action

    llm = _make_llm(_make_llm_response({"action": "HOLD", "confidence": "low", "evidence_quote": None}))
    with pytest.raises(ActionExtractionError) as exc_info:
        extract_action("ambiguous text", llm=llm)
    assert "ambiguous text" in str(exc_info.value)


def test_extract_action_raises_when_llm_errors():
    from tradingagents.agents.utils.output_validation import ActionExtractionError, extract_action

    llm = MagicMock()
    llm.invoke.side_effect = TimeoutError("timed out")
    with pytest.raises(ActionExtractionError):
        extract_action("ambiguous text", llm=llm)

