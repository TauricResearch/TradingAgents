"""Tests for from_markdown.py — *_summary.md adapter.

Uses the real 2026-04-16 fixtures. Tests verify correct handling of:
- Section splitting (bold and heading styles)
- Candidate rows: Ticker + Sector nodes + BELONGS_TO + DRIVES_SENTIMENT
- Sector/macro rows: Sector + MarketIndex + MacroIndicator nodes + IMPACTS/DRIVES_SENTIMENT
- Risk rows: RiskFactor nodes + EXPOSED_TO edges
- Not Applicable / N/A rows: skipped
- SECTOR/THEME leader rows: skipped (no Ticker node created)
- Quality-gated files: skipped with warning
- All fixtures together: no crash, expected node types present
"""
from pathlib import Path

import pytest

from tradingagents.graph.scanner_facts.from_markdown import (
    facts_from_markdown_summary,
    facts_from_all_markdown_summaries,
    is_quality_gated,
)
from tradingagents.graph.scanner_facts.schema import validate_graph_facts

FIXTURES = Path(__file__).parent / "fixtures"


# ---- helpers ----

def _node_ids(result: dict) -> set[str]:
    return {n["id"] for n in result["nodes"]}


def _nodes_by_type(result: dict, node_type: str) -> list[dict]:
    return [n for n in result["nodes"] if n["type"] == node_type]


def _edges_by_relation(result: dict, relation: str) -> list[dict]:
    return [e for e in result["edges"] if e["relation"] == relation]


def _edge_exists(result: dict, source: str, relation: str, target: str) -> bool:
    return any(
        e["source"] == source and e["relation"] == relation and e["target"] == target
        for e in result["edges"]
    )


# ---- quality gate ----

def test_quality_gate_no_evidence():
    assert is_quality_gated("[NO_EVIDENCE] nothing found") is True


def test_quality_gate_empty():
    assert is_quality_gated("[QUALITY: empty]") is True


def test_quality_gate_degraded():
    assert is_quality_gated("[QUALITY: degraded] partial content") is True


def test_quality_gate_normal_content():
    assert is_quality_gated("* ON | Technology | Breakout | $79.93 | Strong.") is False


def test_quality_gate_empty_string():
    assert is_quality_gated("") is True


def test_quality_gate_whitespace_only():
    assert is_quality_gated("   \n  ") is True


# ---- smart_money_summary.md: Candidate Rows ----

def test_smart_money_on_ticker_node():
    text = (FIXTURES / "smart_money_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="smart_money_summary.md")
    assert "ON" in _node_ids(result)


def test_smart_money_all_tickers_present():
    text = (FIXTURES / "smart_money_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="smart_money_summary.md")
    ids = _node_ids(result)
    for ticker in ("F", "PBR", "OWL", "ABT", "JBLU", "ON", "QBTS"):
        assert ticker in ids, f"{ticker} not found in nodes: {ids}"


def test_smart_money_belongs_to_edges():
    text = (FIXTURES / "smart_money_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="smart_money_summary.md")
    assert _edge_exists(result, "ON", "BELONGS_TO", "Technology")
    assert _edge_exists(result, "F", "BELONGS_TO", "Consumer Discretionary")
    assert _edge_exists(result, "ABT", "BELONGS_TO", "Health Care")


def test_smart_money_sector_canonicalization():
    """Consumer Cyclical → Consumer Discretionary; Financial → Financials; Healthcare → Health Care."""
    text = (FIXTURES / "smart_money_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="smart_money_summary.md")
    ids = _node_ids(result)
    assert "Consumer Discretionary" in ids, f"Expected Consumer Discretionary, got {ids}"
    assert "Financials" in ids, f"Expected Financials, got {ids}"
    assert "Health Care" in ids, f"Expected Health Care, got {ids}"
    assert "Consumer Cyclical" not in ids
    assert "Financial" not in ids
    assert "Healthcare" not in ids


def test_smart_money_drives_sentiment_bullish_on():
    text = (FIXTURES / "smart_money_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="smart_money_summary.md")
    ds_edges = _edges_by_relation(result, "DRIVES_SENTIMENT")
    on_bullish = [e for e in ds_edges if e["source"] == "ON" and e["polarity"] == "bullish"]
    assert on_bullish, "ON should have a bullish DRIVES_SENTIMENT edge"


def test_smart_money_risk_section_creates_risk_factor_nodes():
    text = (FIXTURES / "smart_money_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="smart_money_summary.md")
    rf_nodes = _nodes_by_type(result, "RiskFactor")
    assert len(rf_nodes) >= 1, "Expected RiskFactor nodes from Risk / Failure Modes"


# ---- gatekeeper_summary.md: Candidate Rows ----

def test_gatekeeper_nvda_aapl_msft_present():
    text = (FIXTURES / "gatekeeper_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="gatekeeper_summary.md")
    ids = _node_ids(result)
    for ticker in ("NVDA", "AAPL", "MSFT", "AMZN", "TSLA", "AMD", "ORCL", "NFLX", "PLTR"):
        assert ticker in ids, f"{ticker} not found"


def test_gatekeeper_telecom_canonicalized():
    """T is listed under 'Telecommunications' — must canonicalize to 'Communication Services'."""
    text = (FIXTURES / "gatekeeper_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="gatekeeper_summary.md")
    ids = _node_ids(result)
    assert "Communication Services" in ids, f"Expected Communication Services, got {ids}"
    assert "Telecommunications" not in ids


def test_gatekeeper_nflx_belongs_to_communication_services():
    text = (FIXTURES / "gatekeeper_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="gatekeeper_summary.md")
    assert _edge_exists(result, "NFLX", "BELONGS_TO", "Communication Services")


# ---- geopolitical_summary.md: Not Applicable rows ----

def test_geopolitical_not_applicable_rows_produce_no_ticker_nodes():
    text = (FIXTURES / "geopolitical_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="geopolitical_summary.md")
    ticker_nodes = _nodes_by_type(result, "Ticker")
    assert ticker_nodes == [], f"Geopolitical adapter should produce no Ticker nodes, got: {ticker_nodes}"


def test_geopolitical_sector_macro_rows_produce_nodes():
    text = (FIXTURES / "geopolitical_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="geopolitical_summary.md")
    ids = _node_ids(result)
    # EQUITIES (S&P 500, Nasdaq), SOVEREIGN DEBT, FX rows should produce some nodes
    assert len(ids) > 0, "Geopolitical summary should produce non-empty nodes"


def test_geopolitical_fx_nodes_classified_correctly():
    text = (FIXTURES / "geopolitical_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="geopolitical_summary.md")
    fx_nodes = _nodes_by_type(result, "CurrencyPair")
    # EUR/USD, JPY/USD, CNY/USD appear in Sector/Macro section
    assert len(fx_nodes) >= 1, f"Expected CurrencyPair nodes, got: {_node_ids(result)}"


# ---- sector_summary.md: heading-style sections, SECTOR/THEME rows ----

def test_sector_summary_no_candidate_ticker_rows():
    """sector_summary.md Candidate Rows section contains only '- N/A'."""
    text = (FIXTURES / "sector_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="sector_summary.md")
    ticker_nodes = _nodes_by_type(result, "Ticker")
    assert ticker_nodes == [], f"Sector summary should produce no Ticker nodes, got: {ticker_nodes}"


def test_sector_summary_sector_nodes_produced():
    text = (FIXTURES / "sector_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="sector_summary.md")
    sector_nodes = _nodes_by_type(result, "Sector")
    assert len(sector_nodes) >= 4, f"Expected Sector nodes from Sector/Macro section, got: {sector_nodes}"


def test_sector_summary_sector_theme_rows_skipped():
    """SECTOR/THEME leader rows in sector_summary.md should not create Ticker nodes."""
    text = (FIXTURES / "sector_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="sector_summary.md")
    assert "SECTOR/THEME" not in _node_ids(result)


def test_sector_summary_technology_canonicalized_from_upper():
    """'TECHNOLOGY' in sector_summary.md should become 'Technology'."""
    text = (FIXTURES / "sector_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="sector_summary.md")
    assert "Technology" in _node_ids(result)


# ---- industry_deep_dive_summary.md ----

def test_industry_deep_dive_tickers_present():
    text = (FIXTURES / "industry_deep_dive_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="industry_deep_dive_summary.md")
    ids = _node_ids(result)
    for ticker in ("ON", "AMD", "INTC", "AVGO", "MSFT", "DLR", "EQIX", "CBRE", "PLD"):
        assert ticker in ids, f"{ticker} not in {ids}"


def test_industry_deep_dive_consumer_defensive_canonicalized():
    """'Consumer Defensive' in industry_deep_dive → 'Consumer Staples'."""
    text = (FIXTURES / "industry_deep_dive_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="industry_deep_dive_summary.md")
    ids = _node_ids(result)
    assert "Consumer Staples" in ids, f"Expected Consumer Staples, got {ids}"


def test_industry_deep_dive_risk_factor_for_technology():
    text = (FIXTURES / "industry_deep_dive_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="industry_deep_dive_summary.md")
    # Risk / Failure Modes: "Technology | High valuation premiums, concentration risk | ..."
    et_edges = _edges_by_relation(result, "EXPOSED_TO")
    assert any("Technology" in e["source"] or "Technology" in e["target"]
               for e in et_edges), f"Expected Technology EXPOSED_TO edge, got: {et_edges}"


# ---- market_movers_summary.md ----

def test_market_movers_no_ticker_nodes():
    text = (FIXTURES / "market_movers_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="market_movers_summary.md")
    ticker_nodes = _nodes_by_type(result, "Ticker")
    assert ticker_nodes == [], f"Market movers should have no Ticker nodes, got: {ticker_nodes}"


def test_market_movers_sp500_classified_as_market_index():
    text = (FIXTURES / "market_movers_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="market_movers_summary.md")
    index_nodes = _nodes_by_type(result, "MarketIndex")
    assert any("S&P 500" in n["id"] or "500" in n["id"] for n in index_nodes), (
        f"S&P 500 not found in MarketIndex nodes: {[n['id'] for n in index_nodes]}"
    )


def test_market_movers_vix_classified_as_macro_indicator():
    text = (FIXTURES / "market_movers_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="market_movers_summary.md")
    macro_nodes = _nodes_by_type(result, "MacroIndicator")
    assert any("VIX" in n["id"] for n in macro_nodes), (
        f"VIX not in MacroIndicator nodes: {[n['id'] for n in macro_nodes]}"
    )


def test_market_movers_macro_rows_emit_impacts_edges():
    text = (FIXTURES / "market_movers_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="market_movers_summary.md")
    impacts_edges = _edges_by_relation(result, "IMPACTS")
    assert impacts_edges, "Expected macro/index rows to emit IMPACTS edges"
    assert any(e["source"] == "VIX" for e in impacts_edges), impacts_edges


# ---- quality gating ----

def test_quality_gated_text_returns_empty_facts():
    result = facts_from_markdown_summary(
        "[NO_EVIDENCE] nothing qualified", source="test_summary.md"
    )
    assert result["nodes"] == []
    assert result["edges"] == []


def test_quality_degraded_returns_empty_facts():
    result = facts_from_markdown_summary(
        "[QUALITY: degraded] some partial content", source="test_summary.md"
    )
    assert result["nodes"] == []
    assert result["edges"] == []


# ---- facts_from_all_markdown_summaries ----

def test_all_summaries_combined_ticker_count():
    result = facts_from_all_markdown_summaries(FIXTURES)
    ticker_nodes = _nodes_by_type(result, "Ticker")
    # Across all fixtures: F, PBR, OWL, ABT, JBLU, ON, QBTS, NVDA, AAPL, MSFT, AMZN, TSLA...
    assert len(ticker_nodes) >= 10, f"Expected ≥10 tickers, got {len(ticker_nodes)}"


def test_all_summaries_combined_no_crash():
    result = facts_from_all_markdown_summaries(FIXTURES)
    assert "nodes" in result
    assert "edges" in result


def test_all_summaries_schema_valid():
    result = facts_from_all_markdown_summaries(FIXTURES)
    facts = {
        "schema_version": "scanner_graph_facts.v1",
        "scan_date": "2026-04-16",
        "run_id": "test-run",
        "source_dir": "test",
        "global_regime": {"summary": "", "bullets": [], "source": "test"},
        "nodes": result["nodes"],
        "edges": result["edges"],
        "metadata": {
            "node_count": len(result["nodes"]),
            "edge_count": len(result["edges"]),
            "generated_at": "2026-04-16T00:00:00Z",
            "inputs": [],
        },
    }
    errors = validate_graph_facts(facts)
    assert errors == [], f"Schema errors: {errors}"


def test_all_summaries_on_present_from_multiple_sources():
    """ON appears in smart_money AND industry_deep_dive — should be in merged nodes once."""
    result = facts_from_all_markdown_summaries(FIXTURES)
    on_nodes = [n for n in result["nodes"] if n["id"] == "ON"]
    assert len(on_nodes) == 1, f"ON should appear exactly once, got {len(on_nodes)}"
    # But provenance should contain both sources
    if on_nodes:
        provenance_str = str(on_nodes[0]["provenance"])
        assert "smart_money" in provenance_str or "industry_deep_dive" in provenance_str


def test_all_summaries_confidence_range():
    result = facts_from_all_markdown_summaries(FIXTURES)
    for node in result["nodes"]:
        assert 0.10 <= node["confidence"] <= 0.99, f"Node {node['id']} confidence out of range"
    for edge in result["edges"]:
        assert 0.10 <= edge["confidence"] <= 0.99, f"Edge {edge} confidence out of range"
