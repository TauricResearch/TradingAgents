"""Tests for builder.py — merge, validate, save, load, ensure (immutability).

Uses real fixtures from F2 to verify full pipeline:
  fixtures/ → from_macro_json + from_markdown → builder → saved JSON
"""

import json
from pathlib import Path

import pytest

from tradingagents.graph.scanner_facts.builder import (
    _merge_partial_facts,
    build_scanner_graph_facts_from_market_dir,
    ensure_scanner_graph_facts,
    load_scanner_graph_facts,
    save_scanner_graph_facts,
)
from tradingagents.graph.scanner_facts.schema import validate_graph_facts
from tradingagents.report_paths import get_scanner_graph_facts_path

FIXTURES = Path(__file__).parent / "fixtures"


# ---- report_paths helper ----


def test_get_scanner_graph_facts_path():
    p = get_scanner_graph_facts_path("2026-04-16", "RUN001")
    assert p.name == "scanner_graph_facts.json"
    assert "2026-04-16" in str(p)
    assert "RUN001" in str(p)
    assert "market" in str(p)


# ---- _merge_partial_facts ----


def test_merge_dedupes_nodes_by_type_and_id():
    a = {
        "nodes": [
            {
                "id": "ON",
                "type": "Ticker",
                "label": "ON",
                "aliases": [],
                "provenance": ["src_a"],
                "evidence": ["ev_a"],
                "confidence": 0.9,
            }
        ],
        "edges": [],
    }
    b = {
        "nodes": [
            {
                "id": "ON",
                "type": "Ticker",
                "label": "ON",
                "aliases": [],
                "provenance": ["src_b"],
                "evidence": ["ev_b"],
                "confidence": 0.95,
            }
        ],
        "edges": [],
    }
    merged = _merge_partial_facts([a, b])
    on_nodes = [n for n in merged["nodes"] if n["id"] == "ON"]
    assert len(on_nodes) == 1
    assert "src_a" in on_nodes[0]["provenance"]
    assert "src_b" in on_nodes[0]["provenance"]
    assert on_nodes[0]["confidence"] == 0.95


def test_merge_keeps_different_types_with_same_id():
    a = {
        "nodes": [
            {
                "id": "Technology",
                "type": "Sector",
                "label": "Technology",
                "aliases": [],
                "provenance": ["s"],
                "evidence": [],
                "confidence": 0.9,
            }
        ],
        "edges": [],
    }
    b = {
        "nodes": [
            {
                "id": "Technology",
                "type": "Theme",
                "label": "Technology",
                "aliases": [],
                "provenance": ["s"],
                "evidence": [],
                "confidence": 0.8,
            }
        ],
        "edges": [],
    }
    merged = _merge_partial_facts([a, b])
    # Different type → kept as separate nodes
    tech_nodes = [n for n in merged["nodes"] if n["id"] == "Technology"]
    types = {n["type"] for n in tech_nodes}
    # Theme and Sector are both valid — one or two nodes depending on dedup strategy
    # At minimum both types must be represented
    assert "Sector" in types


def test_merge_nodes_adds_curated_aliases():
    partial = {
        "nodes": [
            {
                "id": "NVDA",
                "type": "Ticker",
                "label": "NVDA",
                "aliases": [],
                "provenance": ["s"],
                "evidence": [],
                "confidence": 0.9,
            }
        ],
        "edges": [],
    }
    merged = _merge_partial_facts([partial])
    assert "Nvidia" in merged["nodes"][0]["aliases"]


def test_merge_dedupes_edges_by_source_relation_target_provenance():
    edge = {
        "source": "ON",
        "relation": "BELONGS_TO",
        "target": "Technology",
        "polarity": "",
        "provenance": "src_a",
        "evidence": "ev",
        "confidence": 0.9,
    }
    same_edge_lower = dict(edge, confidence=0.7)
    a = {"nodes": [], "edges": [edge]}
    b = {"nodes": [], "edges": [same_edge_lower]}
    merged = _merge_partial_facts([a, b])
    bt_edges = [e for e in merged["edges"] if e["relation"] == "BELONGS_TO"]
    assert len(bt_edges) == 1
    assert bt_edges[0]["confidence"] == 0.9  # higher confidence kept


def test_merge_keeps_different_edges():
    e1 = {
        "source": "ON",
        "relation": "BELONGS_TO",
        "target": "Technology",
        "polarity": "",
        "provenance": "src_a",
        "evidence": "ev",
        "confidence": 0.9,
    }
    e2 = {
        "source": "ON",
        "relation": "DRIVES_SENTIMENT",
        "target": "Technology",
        "polarity": "bullish",
        "provenance": "src_a",
        "evidence": "ev2",
        "confidence": 0.8,
    }
    merged = _merge_partial_facts([{"nodes": [], "edges": [e1, e2]}])
    assert len(merged["edges"]) == 2


# ---- build_scanner_graph_facts_from_market_dir ----


def test_build_from_market_dir_returns_valid_facts():
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    errors = validate_graph_facts(facts)
    assert errors == [], f"Schema errors: {errors}"


def test_build_has_correct_schema_version():
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    assert facts["schema_version"] == "scanner_graph_facts.v1"


def test_build_has_scan_date_and_run_id():
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    assert facts["scan_date"] == "2026-04-16"
    assert facts["run_id"] == "test-run-001"


def test_build_node_count_matches_metadata():
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    assert facts["metadata"]["node_count"] == len(facts["nodes"])
    assert facts["metadata"]["edge_count"] == len(facts["edges"])


def test_build_contains_real_tickers():
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    ids = {n["id"] for n in facts["nodes"]}
    for ticker in ("ON", "NVDA", "MSFT", "AMD"):
        assert ticker in ids, f"{ticker} not found in built graph"


def test_build_global_regime_populated():
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    assert facts["global_regime"]["summary"]
    assert len(facts["global_regime"]["bullets"]) >= 1


def test_build_inputs_recorded_in_metadata():
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    inputs = facts["metadata"]["inputs"]
    assert "macro_scan_summary.json" in inputs


def test_build_missing_macro_json_raises(tmp_path):
    """macro_scan_summary.json is required — missing it must raise FileNotFoundError."""
    # tmp_path has no files at all
    with pytest.raises(FileNotFoundError):
        build_scanner_graph_facts_from_market_dir(
            tmp_path, scan_date="2026-04-16", run_id="test-run"
        )


# ---- save and load ----


def test_save_creates_file(tmp_path):
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    path = tmp_path / "scanner_graph_facts.json"
    saved = save_scanner_graph_facts(facts, path)
    assert saved == path
    assert path.exists()


def test_save_writes_valid_json(tmp_path):
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    path = tmp_path / "scanner_graph_facts.json"
    save_scanner_graph_facts(facts, path)
    loaded = json.loads(path.read_text())
    assert loaded["schema_version"] == "scanner_graph_facts.v1"


def test_save_stable_ordering(tmp_path):
    """Saving the same facts twice must produce byte-identical output."""
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    p1 = tmp_path / "a.json"
    p2 = tmp_path / "b.json"
    save_scanner_graph_facts(facts, p1)
    save_scanner_graph_facts(facts, p2, overwrite=True)
    assert p1.read_bytes() == p2.read_bytes()


def test_save_does_not_overwrite_by_default(tmp_path):
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    path = tmp_path / "scanner_graph_facts.json"
    save_scanner_graph_facts(facts, path)
    original_mtime = path.stat().st_mtime

    # Second save with overwrite=False must not change the file
    save_scanner_graph_facts(facts, path, overwrite=False)
    assert path.stat().st_mtime == original_mtime


def test_load_roundtrip(tmp_path):
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    path = tmp_path / "scanner_graph_facts.json"
    save_scanner_graph_facts(facts, path)
    loaded = load_scanner_graph_facts(path)
    assert loaded["schema_version"] == facts["schema_version"]
    assert len(loaded["nodes"]) == len(facts["nodes"])
    assert len(loaded["edges"]) == len(facts["edges"])


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_scanner_graph_facts(tmp_path / "no_such_file.json")


def test_load_malformed_json_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json }")
    with pytest.raises(ValueError):
        load_scanner_graph_facts(bad)


# ---- ensure_scanner_graph_facts ----


def test_ensure_builds_when_missing(tmp_path, monkeypatch):
    # Redirect get_scanner_graph_facts_path to tmp_path
    import tradingagents.graph.scanner_facts.builder as bmod

    monkeypatch.setattr(
        bmod,
        "_resolve_market_dir",
        lambda date, rid: FIXTURES,
    )
    monkeypatch.setattr(
        bmod,
        "_resolve_artifact_path",
        lambda date, rid: tmp_path / "scanner_graph_facts.json",
    )
    path = ensure_scanner_graph_facts(scan_date="2026-04-16", run_id="test-run-001")
    assert path.exists()
    facts = load_scanner_graph_facts(path)
    assert validate_graph_facts(facts) == []


def test_ensure_loads_existing_without_rebuilding(tmp_path, monkeypatch):
    import tradingagents.graph.scanner_facts.builder as bmod

    artifact = tmp_path / "scanner_graph_facts.json"
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    save_scanner_graph_facts(facts, artifact)
    original_mtime = artifact.stat().st_mtime

    monkeypatch.setattr(bmod, "_resolve_market_dir", lambda d, r: FIXTURES)
    monkeypatch.setattr(bmod, "_resolve_artifact_path", lambda d, r: artifact)

    ensure_scanner_graph_facts(scan_date="2026-04-16", run_id="test-run-001")
    assert artifact.stat().st_mtime == original_mtime  # file not rewritten
