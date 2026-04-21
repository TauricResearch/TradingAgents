"""Tests for search.py — ticker lookup and 1/2-hop subgraph retrieval.

Uses small inline facts dicts rather than full fixtures to keep tests fast
and isolated. One integration test uses the full fixture set via the builder.
"""
from pathlib import Path

import pytest

from tradingagents.graph.scanner_facts.search import retrieve_ticker_subgraph

FIXTURES = Path(__file__).parent / "fixtures"

# ---------- minimal facts dict used across most tests ----------

_ON = {"id": "ON", "type": "Ticker", "label": "ON",
       "aliases": ["ON Semiconductor", "Onsemi"], "provenance": ["s"], "evidence": [], "confidence": 0.95}
_TECH = {"id": "Technology", "type": "Sector", "label": "Technology",
         "aliases": [], "provenance": ["s"], "evidence": [], "confidence": 0.90}
_AI = {"id": "AI Infrastructure", "type": "Theme", "label": "AI Infrastructure",
       "aliases": [], "provenance": ["s"], "evidence": [], "confidence": 0.85}
_RISK = {"id": "Concentration risk", "type": "RiskFactor", "label": "Concentration risk",
         "aliases": [], "provenance": ["s"], "evidence": [], "confidence": 0.80}
_NVDA = {"id": "NVDA", "type": "Ticker", "label": "NVDA",
         "aliases": ["Nvidia"], "provenance": ["s"], "evidence": [], "confidence": 0.95}

_FACTS = {
    "schema_version": "scanner_graph_facts.v1",
    "scan_date": "2026-04-16",
    "run_id": "test",
    "source_dir": "test",
    "global_regime": {"summary": "Risk-On", "bullets": [], "source": "macro_scan_summary.json"},
    "nodes": [_ON, _TECH, _AI, _RISK, _NVDA],
    "edges": [
        {"source": "ON", "relation": "BELONGS_TO", "target": "Technology",
         "polarity": "", "provenance": "s1", "evidence": "ev", "confidence": 0.95},
        {"source": "NVDA", "relation": "BELONGS_TO", "target": "Technology",
         "polarity": "", "provenance": "s1", "evidence": "ev", "confidence": 0.95},
        {"source": "Technology", "relation": "DRIVES_SENTIMENT", "target": "AI Infrastructure",
         "polarity": "bullish", "provenance": "s2", "evidence": "ev2", "confidence": 0.85},
        {"source": "Technology", "relation": "EXPOSED_TO", "target": "Concentration risk",
         "polarity": "bearish", "provenance": "s3", "evidence": "ev3", "confidence": 0.80},
    ],
    "metadata": {"node_count": 5, "edge_count": 4, "generated_at": "T", "inputs": []},
}


# ---- exact ticker lookup ----

def test_exact_ticker_found():
    result = retrieve_ticker_subgraph(_FACTS, "ON")
    assert result["ticker"] == "ON"
    ids = {n["id"] for n in result["nodes"]}
    assert "ON" in ids


def test_exact_ticker_uppercase_normalisation():
    result = retrieve_ticker_subgraph(_FACTS, "on")
    assert result["ticker"] == "ON"
    ids = {n["id"] for n in result["nodes"]}
    assert "ON" in ids


def test_unknown_ticker_raises_key_error():
    with pytest.raises(KeyError, match="UNKNOWN"):
        retrieve_ticker_subgraph(_FACTS, "UNKNOWN")


# ---- alias lookup ----

def test_alias_lookup_on_semiconductor():
    result = retrieve_ticker_subgraph(_FACTS, "ON Semiconductor")
    assert result["ticker"] == "ON"
    ids = {n["id"] for n in result["nodes"]}
    assert "ON" in ids


def test_alias_lookup_nvidia():
    result = retrieve_ticker_subgraph(_FACTS, "Nvidia")
    assert result["ticker"] == "NVDA"


def test_alias_unknown_raises():
    with pytest.raises(KeyError):
        retrieve_ticker_subgraph(_FACTS, "Completely Unknown Company")


# ---- 1-hop subgraph ----

def test_1hop_includes_direct_neighbours():
    result = retrieve_ticker_subgraph(_FACTS, "ON", hops=1)
    ids = {n["id"] for n in result["nodes"]}
    assert "ON" in ids
    assert "Technology" in ids
    # AI Infrastructure is 2-hop away; must NOT be included at 1-hop
    assert "AI Infrastructure" not in ids


def test_1hop_edges_only_direct():
    result = retrieve_ticker_subgraph(_FACTS, "ON", hops=1)
    relations = {e["relation"] for e in result["edges"]}
    assert "BELONGS_TO" in relations
    # DRIVES_SENTIMENT is from Technology→AI; may appear if Technology is 1-hop seed
    # key check: no edges whose both endpoints are not in the subgraph nodes
    node_ids = {n["id"] for n in result["nodes"]}
    for e in result["edges"]:
        assert e["source"] in node_ids, f"Edge source {e['source']} not in subgraph nodes"
        assert e["target"] in node_ids, f"Edge target {e['target']} not in subgraph nodes"


# ---- 2-hop subgraph ----

def test_2hop_includes_second_degree_neighbours():
    result = retrieve_ticker_subgraph(_FACTS, "ON", hops=2)
    ids = {n["id"] for n in result["nodes"]}
    assert "ON" in ids
    assert "Technology" in ids
    assert "AI Infrastructure" in ids    # 2 hops: ON → Technology → AI Infrastructure
    assert "Concentration risk" in ids   # 2 hops: ON → Technology → Concentration risk


def test_2hop_nvda_shares_technology_node():
    """NVDA is also connected to Technology, so at 2 hops from ON, NVDA should appear."""
    result = retrieve_ticker_subgraph(_FACTS, "ON", hops=2)
    ids = {n["id"] for n in result["nodes"]}
    assert "NVDA" in ids


def test_2hop_edges_preserve_direction():
    result = retrieve_ticker_subgraph(_FACTS, "ON", hops=2)
    # BELONGS_TO edges must be Ticker→Sector, not reversed
    bt_edges = [e for e in result["edges"] if e["relation"] == "BELONGS_TO"]
    for e in bt_edges:
        assert e["source"] in ("ON", "NVDA")
        assert e["target"] == "Technology"


def test_hops_clamped_to_1_minimum():
    """hops=0 should be treated as hops=1."""
    result = retrieve_ticker_subgraph(_FACTS, "ON", hops=0)
    assert result["hops"] >= 1


def test_hops_clamped_to_3_maximum():
    result = retrieve_ticker_subgraph(_FACTS, "ON", hops=10)
    assert result["hops"] <= 3


# ---- max_edges ----

def test_max_edges_limits_output():
    result = retrieve_ticker_subgraph(_FACTS, "ON", hops=2, max_edges=1)
    assert len(result["edges"]) <= 1


def test_max_edges_preserves_closest_first():
    """When max_edges is hit, edges closest to the seed must be retained."""
    result = retrieve_ticker_subgraph(_FACTS, "ON", hops=2, max_edges=1)
    # The one edge kept should be ON→Technology BELONGS_TO (direct hop)
    if result["edges"]:
        assert result["edges"][0]["source"] == "ON" or result["edges"][0]["target"] == "ON"


# ---- result shape ----

def test_result_has_required_keys():
    result = retrieve_ticker_subgraph(_FACTS, "ON")
    assert "ticker" in result
    assert "nodes" in result
    assert "edges" in result
    assert "hops" in result


def test_result_nodes_all_in_facts():
    result = retrieve_ticker_subgraph(_FACTS, "ON")
    facts_node_ids = {n["id"] for n in _FACTS["nodes"]}
    for node in result["nodes"]:
        assert node["id"] in facts_node_ids


def test_result_edges_all_in_facts():
    result = retrieve_ticker_subgraph(_FACTS, "ON")
    facts_edges = {
        (e["source"], e["relation"], e["target"]) for e in _FACTS["edges"]
    }
    for edge in result["edges"]:
        assert (edge["source"], edge["relation"], edge["target"]) in facts_edges


def test_ticker_with_no_edges_returns_ticker_node_only():
    isolated_facts = dict(_FACTS, edges=[])
    result = retrieve_ticker_subgraph(isolated_facts, "ON")
    assert len(result["nodes"]) == 1
    assert result["nodes"][0]["id"] == "ON"
    assert result["edges"] == []


# ---- integration: build real facts and search ----

def test_integration_search_on_in_real_facts():
    """Build from real fixtures and retrieve ON 2-hop subgraph."""
    from tradingagents.graph.scanner_facts.builder import (
        build_scanner_graph_facts_from_market_dir,
    )
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-search-int"
    )
    result = retrieve_ticker_subgraph(facts, "ON", hops=2)
    ids = {n["id"] for n in result["nodes"]}
    assert "ON" in ids
    assert "Technology" in ids


def test_integration_search_alias_in_real_facts():
    """Searching by 'ON Semiconductor' should resolve to ON ticker."""
    from tradingagents.graph.scanner_facts.builder import (
        build_scanner_graph_facts_from_market_dir,
    )
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-search-alias"
    )
    result = retrieve_ticker_subgraph(facts, "ON Semiconductor", hops=2)
    assert result["ticker"] == "ON"


def test_integration_search_registry_alias_in_real_facts():
    """Searching by a curated alias should work even for Markdown-only ticker nodes."""
    from tradingagents.graph.scanner_facts.builder import (
        build_scanner_graph_facts_from_market_dir,
    )
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-search-registry-alias"
    )
    result = retrieve_ticker_subgraph(facts, "Nvidia", hops=2)
    assert result["ticker"] == "NVDA"


def test_integration_unknown_ticker_raises_in_real_facts():
    from tradingagents.graph.scanner_facts.builder import (
        build_scanner_graph_facts_from_market_dir,
    )
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-search-unknown"
    )
    with pytest.raises(KeyError):
        retrieve_ticker_subgraph(facts, "ZZZNOTTICKER", hops=2)
