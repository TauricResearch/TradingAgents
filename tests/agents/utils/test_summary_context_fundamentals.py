"""Tests for fundamentals risk metrics injection into research packet."""

from tradingagents.agents.utils.summary_context import build_research_packet


def test_research_packet_includes_pe_ratio_from_report_text():
    """P/E and D/E extracted from raw fundamentals_report text must appear in packet."""
    state = {
        "fundamentals_report": (
            "P/E ratio: 83.2x — elevated vs peers.\n"
            "D/E ratio: 15.63 — high leverage.\n"
            "Free cash flow declined -73% YoY.\n"
        ),
    }
    packet = build_research_packet(state)
    assert "83.2" in packet, "PE ratio must appear in research packet"
    assert "15.63" in packet, "D/E ratio must appear in research packet"


def test_research_packet_no_risk_block_when_fundamentals_report_empty():
    """No risk block when fundamentals_report is empty or absent."""
    state = {
        "fundamentals_report": "",
        "fundamentals_report_structured": {"key_metrics": {"pe_ratio": "83.2"}},
    }
    packet = build_research_packet(state)
    assert "Fundamentals Risk Metrics" not in packet


def test_research_packet_no_risk_block_when_no_recognisable_metrics():
    """No block emitted when report text contains no extractable metrics."""
    state = {
        "fundamentals_report": "Revenue grew. No ratio data available.",
    }
    packet = build_research_packet(state)
    assert "Fundamentals Risk Metrics" not in packet


def test_research_packet_includes_all_extractable_metrics():
    """All six metric patterns extracted when present in report text."""
    state = {
        "fundamentals_report": (
            "P/E ratio: 83.2x\n"
            "D/E ratio: 15.63\n"
            "Free cash flow margin declined -73%\n"
            "Operating margin: -3.0%\n"
            "Current ratio: 0.70\n"
            "Working capital $2.3B negative\n"
        ),
    }
    packet = build_research_packet(state)
    assert "Fundamentals Risk Metrics" in packet
    assert "83.2" in packet
    assert "15.63" in packet
    assert "-73%" in packet
    assert "-3.0%" in packet
    assert "0.70" in packet
    assert "MUST be addressed" in packet


def test_research_packet_partial_metrics_from_text():
    """Block is emitted with only the metrics found in text."""
    state = {
        "fundamentals_report": "P/E ratio: 25.3x. Revenue up.",
    }
    packet = build_research_packet(state)
    assert "Fundamentals Risk Metrics" in packet
    assert "25.3" in packet
    assert "D/E:" not in packet
