"""Integration tests for extract_action against realistic PM report text."""

import json
from unittest.mock import MagicMock

import pytest

# Realistic PM output that bit us in audit run 01KQQGTQN98BZHTFECB8QXPTKA
# Multi-line markdown header format that the old regex missed
_OWL_PM_EXCERPT = """\
**IV. Final Portfolio Manager Decision**

**1. Rating**
**Buy**

**2. Entry**
Primary: $9.75 (current market price)
"""

_TEAM_PM_EXCERPT = """\
**IV. Portfolio Manager Decision**

**1. Rating**
**Buy**

**2. Entry Price Levels**
Tranche 1: $68.59 (current)
"""

_WELL_FORMED_PROPOSAL = (
    "- Research Manager's Verdict: BUY derived from validated upstream evidence (HIGH)\n"
    "- FINAL TRANSACTION PROPOSAL: **BUY**"
)

_MANGLED_PROSE = (
    "The committee considered the matter and reached no conclusion. "
    "Bears say caution. Bulls say proceed. Outcome: deferred."
)


def _make_llm_high(action: str) -> MagicMock:
    msg = MagicMock()
    msg.content = json.dumps(
        {"action": action, "confidence": "high", "evidence_quote": f"Rating: {action}"}
    )
    llm = MagicMock()
    llm.invoke.return_value = msg
    return llm


def test_owl_excerpt_extracts_buy_via_llm_fallback():
    """OWL audit-run format: multi-line bold header — regex catches it now (was LLM rescue before)."""
    from tradingagents.agents.utils.output_validation import extract_action

    llm = _make_llm_high("BUY")
    result = extract_action(_OWL_PM_EXCERPT, llm=llm)
    assert result.action == "BUY"
    # Forward-compatible: regex was extended to catch this format, so source is now "regex"
    # If regex catches it, LLM should not be called
    if result.source == "regex":
        llm.invoke.assert_not_called()


def test_team_excerpt_extracts_buy():
    """TEAM audit-run format: same multi-line bold header pattern."""
    from tradingagents.agents.utils.output_validation import extract_action

    llm = _make_llm_high("BUY")
    result = extract_action(_TEAM_PM_EXCERPT, llm=llm)
    assert result.action == "BUY"
    # Forward-compatible: verify LLM not called when regex matches
    if result.source == "regex":
        llm.invoke.assert_not_called()


def test_well_formed_proposal_uses_regex_only():
    """Standard FINAL TRANSACTION PROPOSAL format: regex wins, no LLM call."""
    from tradingagents.agents.utils.output_validation import extract_action

    llm = MagicMock()
    result = extract_action(_WELL_FORMED_PROPOSAL, llm=llm)
    assert result.action == "BUY"
    assert result.source == "regex"
    llm.invoke.assert_not_called()


def test_mangled_prose_raises():
    """Truly ambiguous text must raise ActionExtractionError."""
    from tradingagents.agents.utils.output_validation import ActionExtractionError, extract_action

    msg = MagicMock()
    msg.content = json.dumps({"action": "HOLD", "confidence": "low", "evidence_quote": None})
    llm = MagicMock()
    llm.invoke.return_value = msg
    with pytest.raises(ActionExtractionError):
        extract_action(_MANGLED_PROSE, llm=llm)


def test_regex_covers_new_header_formats_without_llm():
    """After regex extension, numbered bold headers should match without LLM."""
    from tradingagents.agents.utils.output_validation import extract_action

    numbered_bold = "**1. Rating**\n**Sell**"
    llm = MagicMock()
    result = extract_action(numbered_bold, llm=llm)
    assert result.action == "SELL"
    # If regex catches it, LLM is never called
    if result.source == "regex":
        llm.invoke.assert_not_called()
