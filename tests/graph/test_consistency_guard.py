import json
import pytest
from unittest.mock import MagicMock, patch

from tradingagents.graph._consistency_guard import (
    extract_rm_claims,
    check_claims_via_llm,
)


# ---------------------------------------------------------------------------
# extract_rm_claims
# ---------------------------------------------------------------------------

def test_extract_square_bracket_high():
    text = "- [HIGH] Revenue grew +15% YoY, increasing from $906M to $1,043M."
    assert extract_rm_claims(text) == ["Revenue grew +15% YoY, increasing from $906M to $1,043M."]


def test_extract_parenthesis_high():
    text = "*   (HIGH) Asset price breakout at $79.93 on 11.54x relative volume."
    assert extract_rm_claims(text) == ["Asset price breakout at $79.93 on 11.54x relative volume."]


def test_extract_bullet_dot():
    text = "• [MED] Sector momentum tailwind: Technology leads +9.08% monthly."
    assert extract_rm_claims(text) == ["Sector momentum tailwind: Technology leads +9.08% monthly."]


def test_extract_low_confidence_included():
    text = "  - [LOW] Analyst projects price target at $5.68."
    assert extract_rm_claims(text) == ["Analyst projects price target at $5.68."]


def test_extract_all_confidence_levels():
    text = (
        "- [HIGH] Revenue expanded +15.1% YoY.\n"
        "- [MED] Volume surged to 62M shares vs 30M average.\n"
        "- [LOW] Analyst asserts price target of $5.68.\n"
    )
    claims = extract_rm_claims(text)
    assert len(claims) == 3
    assert claims[0] == "Revenue expanded +15.1% YoY."
    assert claims[1] == "Volume surged to 62M shares vs 30M average."
    assert claims[2] == "Analyst asserts price target of $5.68."


def test_extract_ignores_non_claim_lines():
    text = (
        "**Strongest Bull Evidence**\n"
        "  - [HIGH] Revenue grew.\n"
        "Some narrative line without a marker.\n"
        "  - [MED] Margin expanded.\n"
    )
    claims = extract_rm_claims(text)
    assert len(claims) == 2


def test_extract_empty_text_returns_empty():
    assert extract_rm_claims("") == []
    assert extract_rm_claims("  \n  ") == []


def test_extract_nok_real_output():
    """Validate against actual NOK RM output from run 01KQNKJ4PF4D4XN7GXN6YEQHV4."""
    text = (
        "• **Strongest Bull Evidence**\n"
        "  - [HIGH] NOK revenue accelerated from $4.39B in Q1 2025 to $6.13B in Q4 2025, "
        "recording +27.0% YoY growth and sequential QoQ expansion of +3.5%, +6.2%, and +26.9%.\n"
        "  - [HIGH] NOK registered breakout accumulation on unusual volume alongside a "
        "52-week high print at $12.92.\n"
        "  - [MED] NOK price consolidation holds above $10.76 support.\n"
        "• **Strongest Bear Evidence**\n"
        "  - [HIGH] NOK sequential revenue expansion from $4.39B to $6.13B imposes a "
        "$1.74B absolute quarterly variance.\n"
        "  - [MED] Macro regime degradation below +3/6 introduces volatility risk.\n"
    )
    claims = extract_rm_claims(text)
    assert len(claims) == 5
    assert any("$4.39B" in c and "$6.13B" in c for c in claims)
