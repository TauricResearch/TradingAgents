"""Tests for fundamentals risk metrics injection into research packet."""

from tradingagents.agents.utils.summary_context import build_research_packet


def test_research_packet_includes_pe_ratio_when_present():
    """Test that P/E ratio and other metrics appear in research packet when present."""
    state = {
        "company_of_interest": "AAPL",
        "trade_date": "2026-05-05",
        "market_report": "price positive",
        "sentiment_report": "neutral",
        "news_report": "earnings beat",
        "fundamentals_report": "full fundamentals text",
        "fundamentals_report_structured": {
            "key_metrics": {
                "pe_ratio": "83.2",
                "debt_equity_ratio": "15.63",
                "fcf_trend": "declining -73% YoY",
                "operating_margin": "-3.0%",
                "current_ratio": "0.70",
            }
        },
        "investment_debate_state": {},
        "scanner_graph_context_text": "",
    }
    packet = build_research_packet(state)
    assert "83.2" in packet or "PE" in packet, "PE ratio must appear in research packet"
    assert "15.63" in packet or "D/E" in packet or "debt" in packet.lower()


def test_research_packet_no_risk_block_when_key_metrics_missing():
    """Test that no risk block is added when key_metrics are missing."""
    state = {
        "fundamentals_report_structured": {},
        "fundamentals_report": "some text",
    }
    packet = build_research_packet(state)
    assert "Fundamentals Risk Metrics" not in packet


def test_research_packet_no_risk_block_when_key_metrics_empty():
    """Test that no risk block is added when key_metrics dict is empty."""
    state = {
        "fundamentals_report_structured": {
            "key_metrics": {}
        },
        "fundamentals_report": "some text",
    }
    packet = build_research_packet(state)
    assert "Fundamentals Risk Metrics" not in packet


def test_research_packet_includes_all_available_metrics():
    """Test that all available risk metrics are included in the packet."""
    state = {
        "fundamentals_report": "full fundamentals text",
        "fundamentals_report_structured": {
            "key_metrics": {
                "pe_ratio": "83.2",
                "debt_equity_ratio": "15.63",
                "fcf_trend": "declining -73% YoY",
                "operating_margin": "-3.0%",
                "current_ratio": "0.70",
                "working_capital": "$2.3B negative",
            }
        },
    }
    packet = build_research_packet(state)
    assert "Fundamentals Risk Metrics" in packet
    assert "P/E Ratio: 83.2" in packet
    assert "D/E Ratio: 15.63" in packet
    assert "FCF Trend: declining -73% YoY" in packet
    assert "Operating Margin: -3.0%" in packet
    assert "Current Ratio: 0.70" in packet
    assert "Working Capital: $2.3B negative" in packet
    assert "both researchers MUST address" in packet


def test_research_packet_partial_metrics():
    """Test that block is created even with only some metrics present."""
    state = {
        "fundamentals_report": "text",
        "fundamentals_report_structured": {
            "key_metrics": {
                "pe_ratio": "25.3",
            }
        },
    }
    packet = build_research_packet(state)
    assert "Fundamentals Risk Metrics" in packet
    assert "P/E Ratio: 25.3" in packet
    # Should not include labels for missing metrics
    assert "D/E Ratio:" not in packet
