"""Tests for action extraction types and regex-based extraction."""

import pytest


def test_extraction_result_importable():
    """Verify ExtractionResult dataclass can be imported and instantiated."""
    from tradingagents.agents.utils.output_validation import (
        ExtractionResult,
    )
    
    r = ExtractionResult(action="BUY", confidence="high", source="regex", evidence_quote=None)
    assert r.action == "BUY"
    assert r.confidence == "high"
    assert r.source == "regex"
    assert r.evidence_quote is None


def test_action_extraction_error_carries_context():
    """Verify ActionExtractionError stores text excerpt and last attempt."""
    from tradingagents.agents.utils.output_validation import (
        ActionExtractionError,
        ExtractionResult,
    )
    
    last = ExtractionResult(action="HOLD", confidence="low", source="llm", evidence_quote=None)
    exc = ActionExtractionError(text_excerpt="ambiguous text", last_attempt=last)
    assert "ambiguous text" in str(exc)
    assert exc.text_excerpt == "ambiguous text"
    assert exc.last_attempt == last


@pytest.mark.parametrize("text,expected_action", [
    # ── existing patterns ──────────────────────────────────────────────────
    ("FINAL TRANSACTION PROPOSAL: BUY", "BUY"),
    ("FINAL TRANSACTION PROPOSAL: **BUY**", "BUY"),
    ("FINAL RECOMMENDATION: SELL", "SELL"),
    ("RECOMMENDATION: HOLD", "HOLD"),
    ("BALANCED ASSESSMENT: BUY", "BUY"),
    ("RATING: SELL", "SELL"),
    ("ACTION: BUY", "BUY"),
    # ── new: numbered markdown headers ────────────────────────────────────
    ("**1. Rating**\n**Buy**", "BUY"),
    ("**2. Final Rating**\n**Sell**", "SELL"),
    # ── new: bold-line headers ────────────────────────────────────────────
    ("**Rating**\n**Buy**", "BUY"),
    ("**Rating**\n**SELL**", "SELL"),
    # ── new: ATX headers ─────────────────────────────────────────────────
    ("### Rating\nBuy", "BUY"),
    ("## Final Rating\nSELL", "SELL"),
    # ── new: numbered prefix variants ────────────────────────────────────
    ("1. Rating: Buy", "BUY"),
    ("1) Rating — Sell", "SELL"),
    # ── new: tolerant spacing / mixed bold ───────────────────────────────
    ("RATING:  **BUY**  ", "BUY"),
    ("RECOMMENDATION: *SELL*", "SELL"),
    # ── case insensitivity ───────────────────────────────────────────────
    ("rating: buy", "BUY"),
    ("final transaction proposal: sell", "SELL"),
])
def test_regex_extracts(text, expected_action):
    """Test that _extract_action_regex matches all expected patterns."""
    from tradingagents.agents.utils.output_validation import _extract_action_regex

    result = _extract_action_regex(text)
    assert result is not None, f"Expected match for {text!r}, got None"
    assert result.action == expected_action
    assert result.confidence == "high"
    assert result.source == "regex"
    assert result.evidence_quote is None


@pytest.mark.parametrize("text", [
    # ambiguous prose that must NOT match
    "The company performed a buyback and the outlook is cautious.",
    "Bears say sell the rally; bulls say buy the dip. Net: unclear.",
    "",
    "   ",
])
def test_regex_returns_none_on_miss(text):
    """Test that _extract_action_regex returns None for ambiguous text."""
    from tradingagents.agents.utils.output_validation import _extract_action_regex

    result = _extract_action_regex(text)
    assert result is None, f"Expected None for {text!r}, got {result}"
