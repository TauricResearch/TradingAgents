"""Tests for action extraction types and regex-based extraction."""

import pytest


def test_extraction_result_importable():
    """Verify ExtractionResult dataclass can be imported and instantiated."""
    from tradingagents.agents.utils.output_validation import (
        ActionExtractionError,
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
