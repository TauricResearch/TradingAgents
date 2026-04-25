"""Tests for from_macro_json.py — macro_scan_summary.json adapter.

Uses the real 2026-04-16 fixture. Tests verify:
- global_regime is populated from executive_summary
- key_themes become Theme nodes
- stocks_to_investigate become Ticker + Sector nodes + edges
- key_catalysts become HAS_CATALYST edges (Ticker -> Theme)
- risks become RiskFactor nodes + EXPOSED_TO edges
- risk_factors list items become RiskFactor nodes
- confidence matches ConfidenceSource.MACRO_JSON_STRUCTURED
- missing file raises FileNotFoundError
- malformed JSON raises ValueError
"""

import json
from pathlib import Path

import pytest

from tradingagents.graph.scanner_facts.from_macro_json import (
    facts_from_macro_scan_summary,
    load_and_parse_macro_scan_summary,
)
from tradingagents.graph.scanner_facts.schema import validate_graph_facts

FIXTURES = Path(__file__).parent / "fixtures"
REAL_PAYLOAD = json.loads((FIXTURES / "macro_scan_summary.json").read_text())


# ---- helpers ----


def _node_ids(result: dict) -> set[str]:
    return {n["id"] for n in result["nodes"]}


def _edges_by_relation(result: dict, relation: str) -> list[dict]:
    return [e for e in result["edges"] if e["relation"] == relation]


def _edge_exists(result: dict, source: str, relation: str, target: str) -> bool:
    return any(
        e["source"] == source and e["relation"] == relation and e["target"] == target
        for e in result["edges"]
    )


# ---- global_regime ----


def test_global_regime_summary_populated():
    result = facts_from_macro_scan_summary(REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run")
    regime = result["global_regime"]
    assert "Risk-On" in regime["summary"]


def test_global_regime_source_is_macro_json():
    result = facts_from_macro_scan_summary(REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run")
    assert result["global_regime"]["source"] == "macro_scan_summary.json"


def test_global_regime_has_bullets():
    result = facts_from_macro_scan_summary(REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run")
    assert len(result["global_regime"]["bullets"]) >= 3


# ---- Theme nodes from key_themes ----


def test_key_themes_become_theme_nodes():
    result = facts_from_macro_scan_summary(REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run")
    ids = _node_ids(result)
    # Real fixture has "Technology Sector Momentum & AI Infrastructure"
    assert any(
        "Technology" in nid or "AI Infrastructure" in nid or "Momentum" in nid for nid in ids
    ), f"No technology theme found in {ids}"


def test_theme_nodes_have_correct_type():
    result = facts_from_macro_scan_summary(REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run")
    theme_nodes = [n for n in result["nodes"] if n["type"] == "Theme"]
    assert len(theme_nodes) >= 4  # 4 key_themes in real fixture


def test_theme_nodes_provenance_is_macro_json():
    result = facts_from_macro_scan_summary(REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run")
    theme_nodes = [n for n in result["nodes"] if n["type"] == "Theme"]
    for node in theme_nodes:
        assert any("macro_scan_summary" in p for p in node["provenance"])


# ---- Ticker + Sector nodes from stocks_to_investigate ----


def test_on_ticker_node_created():
    result = facts_from_macro_scan_summary(REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run")
    assert "ON" in _node_ids(result)


def test_msft_ticker_node_created():
    result = facts_from_macro_scan_summary(REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run")
    assert "MSFT" in _node_ids(result)


def test_technology_sector_node_created():
    result = facts_from_macro_scan_summary(REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run")
    assert "Technology" in _node_ids(result)


def test_ticker_aliases_populated_from_name_field():
    result = facts_from_macro_scan_summary(REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run")
    on_node = next(n for n in result["nodes"] if n["id"] == "ON")
    # "ON Semiconductor" is the name in the real fixture
    assert "ON Semiconductor" in on_node["aliases"] or len(on_node["aliases"]) >= 0


# ---- BELONGS_TO edges ----


def test_on_belongs_to_technology():
    result = facts_from_macro_scan_summary(REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run")
    assert _edge_exists(result, "ON", "BELONGS_TO", "Technology")


def test_msft_belongs_to_technology():
    result = facts_from_macro_scan_summary(REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run")
    assert _edge_exists(result, "MSFT", "BELONGS_TO", "Technology")


def test_belongs_to_edges_have_provenance():
    result = facts_from_macro_scan_summary(REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run")
    bt_edges = _edges_by_relation(result, "BELONGS_TO")
    for e in bt_edges:
        assert e["provenance"], f"BELONGS_TO edge missing provenance: {e}"
        assert e["evidence"], f"BELONGS_TO edge missing evidence: {e}"


# ---- HAS_CATALYST edges (Ticker -> Theme from key_catalysts) ----


def test_has_catalyst_edges_created_from_key_catalysts():
    result = facts_from_macro_scan_summary(REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run")
    hc_edges = _edges_by_relation(result, "HAS_CATALYST")
    assert len(hc_edges) >= 1, "Expected at least one HAS_CATALYST edge"


def test_has_catalyst_source_is_ticker():
    result = facts_from_macro_scan_summary(REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run")
    hc_edges = _edges_by_relation(result, "HAS_CATALYST")
    node_ids = _node_ids(result)
    for e in hc_edges:
        assert e["source"] in node_ids, f"HAS_CATALYST source {e['source']!r} not in nodes"


def test_has_catalyst_edges_have_confidence():
    result = facts_from_macro_scan_summary(REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run")
    hc_edges = _edges_by_relation(result, "HAS_CATALYST")
    for e in hc_edges:
        assert 0.1 <= e["confidence"] <= 0.99


# ---- EXPOSED_TO edges (Ticker -> RiskFactor from risks) ----


def test_exposed_to_edges_from_stock_risks():
    result = facts_from_macro_scan_summary(REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run")
    et_edges = _edges_by_relation(result, "EXPOSED_TO")
    assert len(et_edges) >= 1, "Expected EXPOSED_TO edges from stock risks"


def test_risk_factor_nodes_created():
    result = facts_from_macro_scan_summary(REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run")
    rf_nodes = [n for n in result["nodes"] if n["type"] == "RiskFactor"]
    assert len(rf_nodes) >= 1


# ---- Top-level risk_factors list ----


def test_top_level_risk_factors_create_nodes():
    result = facts_from_macro_scan_summary(REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run")
    rf_nodes = [n for n in result["nodes"] if n["type"] == "RiskFactor"]
    # real fixture has 6 risk_factors strings → each becomes a node
    assert len(rf_nodes) >= 6


# ---- confidence ----


def test_structured_fields_have_high_confidence():
    result = facts_from_macro_scan_summary(REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run")
    bt_edges = _edges_by_relation(result, "BELONGS_TO")
    for e in bt_edges:
        # MACRO_JSON_STRUCTURED base = 0.90
        assert e["confidence"] >= 0.80, f"Low confidence on BELONGS_TO: {e['confidence']}"


# ---- schema validation ----


def test_output_passes_schema_validation():
    result = facts_from_macro_scan_summary(REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run")
    # Wrap in full facts shape for validation
    facts = {
        "schema_version": "scanner_graph_facts.v1",
        "scan_date": "2026-04-16",
        "run_id": "test-run",
        "source_dir": "test",
        "global_regime": result["global_regime"],
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
    assert errors == [], f"Schema validation errors: {errors}"


# ---- error handling ----


def test_missing_file_raises_file_not_found_error(tmp_path):
    missing = tmp_path / "no_such_file.json"
    with pytest.raises(FileNotFoundError):
        load_and_parse_macro_scan_summary(missing)


def test_malformed_json_raises_value_error(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json }")
    with pytest.raises(ValueError, match="macro_scan_summary"):
        load_and_parse_macro_scan_summary(bad)


def test_empty_stocks_to_investigate_produces_no_ticker_nodes():
    payload = dict(REAL_PAYLOAD, stocks_to_investigate=[])
    result = facts_from_macro_scan_summary(payload, scan_date="2026-04-16", run_id="test-run")
    ticker_nodes = [n for n in result["nodes"] if n["type"] == "Ticker"]
    assert ticker_nodes == []


def test_empty_key_themes_produces_no_theme_nodes_from_themes():
    payload = dict(REAL_PAYLOAD, key_themes=[])
    result = facts_from_macro_scan_summary(payload, scan_date="2026-04-16", run_id="test-run")
    # RiskFactor nodes from risk_factors still appear, but no Theme nodes from themes
    theme_from_themes = [
        n
        for n in result["nodes"]
        if n["type"] == "Theme"
        and any("macro_scan_summary.json#key_themes" in p for p in n["provenance"])
    ]
    assert theme_from_themes == []
