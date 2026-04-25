"""Tests for render.py — prompt renderer + LangChain render tool.

All tests use in-memory facts dicts. No real files except the LangChain tool integration test.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from tradingagents.graph.scanner_facts.render import render_ticker_graph_context
from tradingagents.graph.scanner_facts.schema import SCHEMA_VERSION

FIXTURES = Path(__file__).parent / "fixtures"


def _make_facts(nodes, edges, global_regime=None):
    return {
        "schema_version": SCHEMA_VERSION,
        "scan_date": "2026-04-16",
        "run_id": "TESTRUN",
        "source_dir": "reports/daily/2026-04-16/TESTRUN/market",
        "global_regime": global_regime
        or {
            "summary": "Risk-On regime with S&P 500 reaching new highs.",
            "bullets": [
                "Technology leads 1-month returns.",
                "Key macro risks: VIX reversal risk.",
            ],
            "source": "macro_scan_summary.json",
        },
        "nodes": nodes,
        "edges": edges,
        "metadata": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "generated_at": "2026-04-16T00:00:00Z",
            "inputs": [],
        },
    }


def _ticker(id_, aliases=None):
    return {
        "id": id_,
        "type": "Ticker",
        "label": id_,
        "aliases": aliases or [],
        "provenance": ["smart_money_summary.md#Candidate Rows"],
        "evidence": [f"{id_} observed"],
        "confidence": 0.95,
    }


def _sector(id_):
    return {
        "id": id_,
        "type": "Sector",
        "label": id_,
        "aliases": [],
        "provenance": ["sector_summary.md#Candidate Rows"],
        "evidence": [f"{id_} sector strength"],
        "confidence": 0.90,
    }


def _theme(id_):
    return {
        "id": id_,
        "type": "Theme",
        "label": id_,
        "aliases": [],
        "provenance": ["macro_scan_summary.json#key_themes"],
        "evidence": [f"{id_} theme active"],
        "confidence": 0.85,
    }


def _risk(id_):
    return {
        "id": id_,
        "type": "RiskFactor",
        "label": id_,
        "aliases": [],
        "provenance": ["gatekeeper_summary.md#Risk / Failure Modes"],
        "evidence": [f"{id_} risk noted"],
        "confidence": 0.80,
    }


def _edge(
    src,
    rel,
    tgt,
    evidence="",
    polarity="",
    confidence=0.90,
    prov="smart_money_summary.md#Candidate Rows",
):
    return {
        "source": src,
        "relation": rel,
        "target": tgt,
        "polarity": polarity,
        "provenance": prov,
        "evidence": evidence or f"{src} {rel} {tgt}",
        "confidence": confidence,
    }


# ---- basic rendering ----


def test_render_returns_string():
    facts = _make_facts(
        nodes=[_ticker("ON"), _sector("Technology")],
        edges=[
            _edge(
                "ON", "BELONGS_TO", "Technology", "ON | Technology | Breakout", polarity="bullish"
            )
        ],
    )
    result = render_ticker_graph_context(facts, "ON")
    assert isinstance(result, str)
    assert len(result) > 0


def test_render_contains_global_regime():
    facts = _make_facts(
        nodes=[_ticker("ON"), _sector("Technology")],
        edges=[_edge("ON", "BELONGS_TO", "Technology")],
    )
    result = render_ticker_graph_context(facts, "ON")
    assert "Global Market Regime" in result
    assert "Risk-On regime" in result


def test_render_contains_ticker_section():
    facts = _make_facts(
        nodes=[_ticker("ON"), _sector("Technology")],
        edges=[_edge("ON", "BELONGS_TO", "Technology", "ON sector assignment")],
    )
    result = render_ticker_graph_context(facts, "ON")
    assert "Ticker Graph Context: ON" in result
    assert "belongs to Technology" in result


def test_render_belongs_to_template():
    facts = _make_facts(
        nodes=[_ticker("NVDA"), _sector("Technology")],
        edges=[_edge("NVDA", "BELONGS_TO", "Technology", "NVDA sector evidence")],
    )
    result = render_ticker_graph_context(facts, "NVDA")
    assert "NVDA belongs to Technology." in result


def test_render_drives_sentiment_template():
    facts = _make_facts(
        nodes=[_ticker("ON"), _theme("Breakout Accumulation")],
        edges=[
            _edge(
                "ON",
                "DRIVES_SENTIMENT",
                "Breakout Accumulation",
                "insider buying observed",
                polarity="bullish",
            )
        ],
    )
    result = render_ticker_graph_context(facts, "ON")
    assert "ON is linked to Breakout Accumulation" in result
    assert "insider buying observed" in result


def test_render_has_catalyst_template():
    facts = _make_facts(
        nodes=[_ticker("ON"), _theme("AI Infrastructure")],
        edges=[_edge("ON", "HAS_CATALYST", "AI Infrastructure", "AI data center cycle", "bullish")],
    )
    result = render_ticker_graph_context(facts, "ON")
    assert "ON has catalyst AI Infrastructure" in result
    assert "AI data center cycle" in result


def test_render_exposed_to_template():
    facts = _make_facts(
        nodes=[_ticker("ON"), _sector("Technology"), _risk("concentration risk")],
        edges=[
            _edge("ON", "BELONGS_TO", "Technology"),
            _edge("Technology", "EXPOSED_TO", "concentration risk", "high sector weight"),
        ],
    )
    result = render_ticker_graph_context(facts, "ON")
    assert "exposed to concentration risk" in result


def test_render_contains_provenance_section():
    facts = _make_facts(
        nodes=[_ticker("ON"), _sector("Technology")],
        edges=[
            _edge("ON", "BELONGS_TO", "Technology", prov="smart_money_summary.md#Candidate Rows")
        ],
    )
    result = render_ticker_graph_context(facts, "ON")
    assert "Provenance" in result
    assert "smart_money_summary.md" in result


# ---- dedup ----


def test_render_dedup_same_triple():
    """Same (subject, relation, object) from two sources must appear only once in output."""
    facts = _make_facts(
        nodes=[_ticker("ON"), _sector("Technology")],
        edges=[
            _edge(
                "ON",
                "BELONGS_TO",
                "Technology",
                "source A evidence",
                confidence=0.90,
                prov="smart_money_summary.md#Candidate Rows",
            ),
            _edge(
                "ON",
                "BELONGS_TO",
                "Technology",
                "source B evidence",
                confidence=0.95,
                prov="industry_deep_dive_summary.md#Candidate Rows",
            ),
        ],
    )
    result = render_ticker_graph_context(facts, "ON")
    # Should appear exactly once
    count = result.count("ON belongs to Technology.")
    assert count == 1


def test_render_dedup_keeps_highest_confidence():
    """When deduping, the provenance of the higher-confidence edge must appear."""
    facts = _make_facts(
        nodes=[_ticker("ON"), _sector("Technology")],
        edges=[
            _edge("ON", "BELONGS_TO", "Technology", confidence=0.75, prov="low_conf_source.md"),
            _edge(
                "ON",
                "BELONGS_TO",
                "Technology",
                confidence=0.95,
                prov="industry_deep_dive_summary.md#Candidate Rows",
            ),
        ],
    )
    result = render_ticker_graph_context(facts, "ON")
    assert "industry_deep_dive_summary.md" in result


# ---- budget truncation ----


def test_render_char_budget_respected():
    """Output must not exceed char_budget."""
    nodes = [_ticker("ON")] + [_sector(f"Sector{i}") for i in range(30)]
    edges = [
        _edge("ON", "BELONGS_TO", f"Sector{i}", f"evidence text for sector {i} " * 5)
        for i in range(30)
    ]
    facts = _make_facts(nodes=nodes, edges=edges)

    result = render_ticker_graph_context(facts, "ON", char_budget=500)
    assert len(result) <= 500


def test_render_budget_appends_omission_notice():
    """When truncation occurs, output must end with '... (N more facts omitted)'."""
    nodes = [_ticker("ON")] + [_sector(f"Sector{i}") for i in range(30)]
    edges = [
        _edge("ON", "BELONGS_TO", f"Sector{i}", f"evidence text for sector {i} " * 5)
        for i in range(30)
    ]
    facts = _make_facts(nodes=nodes, edges=edges)

    result = render_ticker_graph_context(facts, "ON", char_budget=300)
    assert "more facts omitted" in result


def test_render_provenance_truncated_first():
    """Provenance section is removed before fact lines when truncating."""
    nodes = [_ticker("ON"), _sector("Technology"), _theme("AI Infrastructure")]
    edges = [
        _edge("ON", "BELONGS_TO", "Technology"),
        _edge("ON", "HAS_CATALYST", "AI Infrastructure", "AI cycle"),
    ]
    facts = _make_facts(nodes=nodes, edges=edges)

    # Get full output and verify provenance is there
    full = render_ticker_graph_context(facts, "ON")
    assert "Provenance" in full

    # Create a budget that removes provenance but keeps facts and regime
    # Set budget to be slightly less than full but enough for regime + facts
    lines = full.split("\n")
    prov_start = next(i for i, line in enumerate(lines) if "Provenance" in line)
    # Join everything up to provenance line and add some buffer
    target = "\n".join(lines[:prov_start]).strip()
    result = render_ticker_graph_context(facts, "ON", char_budget=len(target) + 50)

    # Provenance should be gone
    assert "Provenance" not in result
    # But ticker section should still have content
    assert "Ticker Graph Context" in result


# ---- empty / missing ----


def test_render_empty_subgraph_empty_regime_returns_empty_string():
    _make_facts(
        nodes=[],
        edges=[],
        global_regime={"summary": "", "bullets": [], "source": "macro_scan_summary.json"},
    )
    # No ticker in graph → retrieve_ticker_subgraph raises KeyError
    # So test with a graph that has the ticker but no edges
    ticker_only_facts = _make_facts(
        nodes=[_ticker("XYZ")],
        edges=[],
        global_regime={"summary": "", "bullets": [], "source": "macro_scan_summary.json"},
    )
    result = render_ticker_graph_context(ticker_only_facts, "XYZ")
    # Only global regime check: empty regime + empty subgraph = ""
    assert result == ""


def test_render_unknown_ticker_raises():
    facts = _make_facts(nodes=[_ticker("ON"), _sector("Technology")], edges=[])
    with pytest.raises(KeyError):
        render_ticker_graph_context(facts, "UNKNOWN_XYZ_999")


# ---- alias resolution ----


def test_render_resolves_alias():
    """Rendering via alias should produce same output as canonical id."""
    nodes = [
        {
            "id": "ON",
            "type": "Ticker",
            "label": "ON",
            "aliases": ["ON Semiconductor", "Onsemi"],
            "provenance": ["smart_money_summary.md"],
            "evidence": ["ON breakout"],
            "confidence": 0.95,
        },
        _sector("Technology"),
    ]
    facts = _make_facts(nodes=nodes, edges=[_edge("ON", "BELONGS_TO", "Technology")])
    result_by_alias = render_ticker_graph_context(facts, "ON Semiconductor")
    result_by_id = render_ticker_graph_context(facts, "ON")
    assert result_by_alias == result_by_id


# ---- render tool ----


def test_render_tool_produces_same_output(tmp_path):
    """LangChain render tool invocation must produce identical text to direct function call."""
    from tradingagents.graph.scanner_facts.builder import save_scanner_graph_facts

    # Build a minimal facts dict and save it to tmp
    nodes = [_ticker("ON"), _sector("Technology")]
    edges = [_edge("ON", "BELONGS_TO", "Technology", "breakout")]
    facts = _make_facts(nodes=nodes, edges=edges)

    artifact_path = tmp_path / "scanner_graph_facts.json"
    save_scanner_graph_facts(facts, artifact_path)

    # Patch get_scanner_graph_facts_path before getting the tool
    with patch(
        "tradingagents.report_paths.get_scanner_graph_facts_path",
        return_value=artifact_path,
    ):
        from tradingagents.graph.scanner_facts.render import get_render_tool

        tool = get_render_tool()
        assert tool.name == "render_ticker_graph_context"
        tool_result = tool.invoke({"scan_date": "2026-04-16", "run_id": "TESTRUN", "ticker": "ON"})

    direct_result = render_ticker_graph_context(facts, "ON")
    assert tool_result == direct_result


def test_render_tool_missing_ticker_raises(tmp_path):
    """Render tool propagates KeyError when ticker not in graph."""
    from tradingagents.graph.scanner_facts.builder import save_scanner_graph_facts

    facts = _make_facts(nodes=[_ticker("ON"), _sector("Technology")], edges=[])
    artifact_path = tmp_path / "scanner_graph_facts.json"
    save_scanner_graph_facts(facts, artifact_path)

    with patch(
        "tradingagents.report_paths.get_scanner_graph_facts_path",
        return_value=artifact_path,
    ):
        from tradingagents.graph.scanner_facts.render import get_render_tool

        tool = get_render_tool()
        with pytest.raises(KeyError):
            tool.invoke({"scan_date": "2026-04-16", "run_id": "TESTRUN", "ticker": "UNKNOWN_999"})
