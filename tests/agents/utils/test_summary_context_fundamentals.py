"""Tests for fundamentals risk metrics injection into research packet.

The fundamentals analyst prompt mandates specific output phrases (P/E ratio: Xx,
D/E ratio: X, etc.). The regex in _fundamentals_risk_block is anchored to those
phrases. Tests cover: mandated format, common deviation, missing data, empty report.
"""

from tradingagents.agents.utils.summary_context import build_research_packet

# ---------------------------------------------------------------------------
# Mandated phrase format (must always match)
# ---------------------------------------------------------------------------

MANDATED_REPORT = (
    "P/E ratio: 83.2x\n"
    "D/E ratio: 15.63\n"
    "Free cash flow: -73% YoY\n"
    "Operating margin: -3.0%\n"
    "Current ratio: 0.70\n"
    "Working capital: $2.3b (negative)\n"
)


def test_mandated_phrases_all_extracted():
    """All six mandated metric lines must appear in the research packet."""
    state = {"fundamentals_report": MANDATED_REPORT}
    packet = build_research_packet(state)
    assert "Fundamentals Risk Metrics" in packet
    assert "83.2" in packet
    assert "15.63" in packet
    assert "-73%" in packet
    assert "-3.0%" in packet
    assert "0.70" in packet
    assert "2.3b" in packet
    assert "MUST be addressed" in packet


def test_mandated_phrases_pe_and_de_only():
    """Partial mandated output: only P/E and D/E — block still emitted."""
    state = {"fundamentals_report": "P/E ratio: 25.3x\nD/E ratio: 2.1\n"}
    packet = build_research_packet(state)
    assert "Fundamentals Risk Metrics" in packet
    assert "25.3" in packet
    assert "2.1" in packet
    assert "Operating Margin" not in packet


# ---------------------------------------------------------------------------
# Common deviation formats (LLM didn't follow the template exactly)
# ---------------------------------------------------------------------------


def test_price_to_earnings_variant():
    """price-to-earnings phrasing is captured."""
    state = {"fundamentals_report": "price-to-earnings: 40.5x"}
    packet = build_research_packet(state)
    assert "40.5" in packet


def test_debt_to_equity_long_form():
    """debt-to-equity long form is captured."""
    state = {"fundamentals_report": "debt-to-equity ratio: 8.2"}
    packet = build_research_packet(state)
    assert "8.2" in packet


def test_fcf_short_form():
    """FCF abbreviation is captured."""
    state = {"fundamentals_report": "FCF: -45% YoY"}
    packet = build_research_packet(state)
    assert "-45%" in packet


def test_operating_margin_short_form():
    """op margin short form is captured."""
    state = {"fundamentals_report": "op margin: -5.2%"}
    packet = build_research_packet(state)
    assert "-5.2%" in packet


# ---------------------------------------------------------------------------
# No-match cases
# ---------------------------------------------------------------------------


def test_no_block_when_fundamentals_report_empty():
    """Empty fundamentals_report produces no risk block."""
    state = {"fundamentals_report": ""}
    packet = build_research_packet(state)
    assert "Fundamentals Risk Metrics" not in packet


def test_no_block_when_no_recognisable_patterns():
    """Prose without any metric patterns produces no risk block."""
    state = {"fundamentals_report": "Revenue grew. The company looks healthy overall."}
    packet = build_research_packet(state)
    assert "Fundamentals Risk Metrics" not in packet


def test_no_block_when_fundamentals_report_absent():
    """Missing fundamentals_report key produces no risk block."""
    packet = build_research_packet({})
    assert "Fundamentals Risk Metrics" not in packet
