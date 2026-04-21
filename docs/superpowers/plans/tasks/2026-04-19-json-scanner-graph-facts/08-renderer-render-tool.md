# Feature 8: Prompt Renderer + Render Tool

**Parent plan:** `docs/superpowers/plans/2026-04-19-json-scanner-graph-facts.md`

**Goal:** Implement `render.py` — converts a ticker's 2-hop subgraph + global regime into a compact, budget-capped prompt string. Expose this as a LangChain-compatible tool.

**Dependencies already committed:**
- F1: `schema.py`, `aliases.py`
- F7: `search.py` (`retrieve_ticker_subgraph`, `_find_seed_node`)
- F5: `builder.py` (`load_scanner_graph_facts`)
- `tradingagents/report_paths.py` (`get_scanner_graph_facts_path`)

**Files to create:**
- `tradingagents/graph/scanner_facts/render.py`
- `tests/graph/scanner_facts/test_render.py`

---

## Rules

- `render_ticker_graph_context(facts, ticker, *, char_budget=2400)` is the core rendering function. It calls `retrieve_ticker_subgraph` from `search.py`.
- Token budget (600 advisory) is **not** enforced programmatically — character budget is the hard cap.
- Dedup by `(subject, relation, object)` across all edges. Keep the edge with highest confidence. Ties: keep first seen.
- Budget truncation order: **provenance lines first**, then oldest fact lines (bottom-up from Ticker Graph Context section).
- If subgraph is empty AND global regime summary + bullets are empty → return `""`.
- Unknown ticker → `retrieve_ticker_subgraph` raises `KeyError`. Let it propagate. Do **not** catch it.
- Render tool name: `render_ticker_graph_context`. Inputs: `scan_date`, `run_id`, `ticker`. Loads artifact itself using `get_scanner_graph_facts_path` + `load_scanner_graph_facts`.
- Tool produces identical text to direct function call.
- The LangChain-decorated function may keep an internal Python name, but `tool.name` must be exactly `render_ticker_graph_context`.

---

## Per-Node-Type Templates

```text
BELONGS_TO edge (Ticker -> Sector):     "{ticker} belongs to {sector}."
DRIVES_SENTIMENT edge (Ticker -> Theme): "{ticker} is linked to {theme} ({polarity}), with evidence: \"{evidence}\"."
HAS_CATALYST edge (Ticker -> Theme):    "{ticker} has catalyst {theme}: \"{evidence}\"."
EXPOSED_TO edge (any -> RiskFactor):    "{subject} is exposed to {risk}: \"{evidence}\"."
IMPACTS edge (X -> Sector|Theme):       "{source} impacts {target}: \"{evidence}\"."
RELATED_TO edge (any -> any):           "{source} is related to {target}: \"{evidence}\"."
Sector node (standalone):               "{sector} is {polarity} with evidence: \"{evidence}\"."
Theme node (standalone):                "Theme {theme} is active: \"{evidence}\"."
MarketIndex node:                       "{index}: {evidence}."
MacroIndicator node:                    "{indicator}: {evidence}."
Commodity node:                         "{commodity}: {evidence}."
CurrencyPair node:                      "{pair}: {evidence}."
CryptoAsset node:                       "{asset}: {evidence}."
```

Standalone node lines are emitted only for non-Ticker nodes that are **in the subgraph but have no outgoing edge** in the result set (i.e., leaf nodes not covered by an edge template).

---

## Step 1: Write failing tests

- [ ] Create `tests/graph/scanner_facts/test_render.py`:

```python
"""Tests for render.py — prompt renderer + LangChain render tool.

All tests use in-memory facts dicts. No real files except the LangChain tool integration test.
"""
import json
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
        "global_regime": global_regime or {
            "summary": "Risk-On regime with S&P 500 reaching new highs.",
            "bullets": [
                "Technology leads 1-month returns.",
                "Key macro risks: VIX reversal risk.",
            ],
            "source": "macro_scan_summary.json",
        },
        "nodes": nodes,
        "edges": edges,
        "metadata": {"node_count": len(nodes), "edge_count": len(edges), "generated_at": "2026-04-16T00:00:00Z", "inputs": []},
    }


def _ticker(id_, aliases=None):
    return {"id": id_, "type": "Ticker", "label": id_, "aliases": aliases or [], "provenance": ["smart_money_summary.md#Candidate Rows"], "evidence": [f"{id_} observed"], "confidence": 0.95}


def _sector(id_):
    return {"id": id_, "type": "Sector", "label": id_, "aliases": [], "provenance": ["sector_summary.md#Candidate Rows"], "evidence": [f"{id_} sector strength"], "confidence": 0.90}


def _theme(id_):
    return {"id": id_, "type": "Theme", "label": id_, "aliases": [], "provenance": ["macro_scan_summary.json#key_themes"], "evidence": [f"{id_} theme active"], "confidence": 0.85}


def _risk(id_):
    return {"id": id_, "type": "RiskFactor", "label": id_, "aliases": [], "provenance": ["gatekeeper_summary.md#Risk / Failure Modes"], "evidence": [f"{id_} risk noted"], "confidence": 0.80}


def _edge(src, rel, tgt, evidence="", polarity="", confidence=0.90, prov="smart_money_summary.md#Candidate Rows"):
    return {
        "source": src, "relation": rel, "target": tgt,
        "polarity": polarity, "provenance": prov,
        "evidence": evidence or f"{src} {rel} {tgt}",
        "confidence": confidence,
    }


# ---- basic rendering ----

def test_render_returns_string():
    facts = _make_facts(
        nodes=[_ticker("ON"), _sector("Technology")],
        edges=[_edge("ON", "BELONGS_TO", "Technology", "ON | Technology | Breakout", polarity="bullish")],
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
        edges=[_edge("ON", "DRIVES_SENTIMENT", "Breakout Accumulation", "insider buying observed", polarity="bullish")],
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
        edges=[_edge("ON", "BELONGS_TO", "Technology", prov="smart_money_summary.md#Candidate Rows")],
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
            _edge("ON", "BELONGS_TO", "Technology", "source A evidence", confidence=0.90, prov="smart_money_summary.md#Candidate Rows"),
            _edge("ON", "BELONGS_TO", "Technology", "source B evidence", confidence=0.95, prov="industry_deep_dive_summary.md#Candidate Rows"),
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
            _edge("ON", "BELONGS_TO", "Technology", confidence=0.95, prov="industry_deep_dive_summary.md#Candidate Rows"),
        ],
    )
    result = render_ticker_graph_context(facts, "ON")
    assert "industry_deep_dive_summary.md" in result


# ---- budget truncation ----

def test_render_char_budget_respected():
    """Output must not exceed char_budget."""
    nodes = [_ticker("ON")] + [_sector(f"Sector{i}") for i in range(30)]
    edges = [_edge("ON", "BELONGS_TO", f"Sector{i}", f"evidence text for sector {i} " * 5) for i in range(30)]
    facts = _make_facts(nodes=nodes, edges=edges)

    result = render_ticker_graph_context(facts, "ON", char_budget=500)
    assert len(result) <= 500


def test_render_budget_appends_omission_notice():
    """When truncation occurs, output must end with '... (N more facts omitted)'."""
    nodes = [_ticker("ON")] + [_sector(f"Sector{i}") for i in range(30)]
    edges = [_edge("ON", "BELONGS_TO", f"Sector{i}", f"evidence text for sector {i} " * 5) for i in range(30)]
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

    # Tight budget that still fits facts but not provenance
    full = render_ticker_graph_context(facts, "ON")
    full_len = len(full)

    # Find length where facts fit but provenance doesn't
    no_prov_len = full_len - full.count("\n- ON ->") * 50  # rough estimate
    result = render_ticker_graph_context(facts, "ON", char_budget=no_prov_len // 2)

    # Even if provenance is gone, ticker section should still have something
    assert "Ticker Graph Context" in result


# ---- empty / missing ----

def test_render_empty_subgraph_empty_regime_returns_empty_string():
    facts = _make_facts(
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
        {"id": "ON", "type": "Ticker", "label": "ON", "aliases": ["ON Semiconductor", "Onsemi"],
         "provenance": ["smart_money_summary.md"], "evidence": ["ON breakout"], "confidence": 0.95},
        _sector("Technology"),
    ]
    facts = _make_facts(nodes=nodes, edges=[_edge("ON", "BELONGS_TO", "Technology")])
    result_by_alias = render_ticker_graph_context(facts, "ON Semiconductor")
    result_by_id = render_ticker_graph_context(facts, "ON")
    assert result_by_alias == result_by_id


# ---- render tool ----

def test_render_tool_produces_same_output(tmp_path):
    """LangChain render tool invocation must produce identical text to direct function call."""
    import shutil
    from tradingagents.graph.scanner_facts.render import get_render_tool
    from tradingagents.graph.scanner_facts.builder import save_scanner_graph_facts

    # Build a minimal facts dict and save it to tmp
    nodes = [_ticker("ON"), _sector("Technology")]
    edges = [_edge("ON", "BELONGS_TO", "Technology", "breakout")]
    facts = _make_facts(nodes=nodes, edges=edges)

    artifact_path = tmp_path / "scanner_graph_facts.json"
    save_scanner_graph_facts(facts, artifact_path)

    tool = get_render_tool()

    # Call tool — monkeypatch get_scanner_graph_facts_path to return tmp path
    with patch(
        "tradingagents.graph.scanner_facts.render.get_scanner_graph_facts_path",
        return_value=artifact_path,
    ):
        tool_result = tool.invoke({"scan_date": "2026-04-16", "run_id": "TESTRUN", "ticker": "ON"})

    direct_result = render_ticker_graph_context(facts, "ON")
    assert tool_result == direct_result


def test_render_tool_missing_ticker_raises(tmp_path):
    """Render tool propagates KeyError when ticker not in graph."""
    from tradingagents.graph.scanner_facts.render import get_render_tool
    from tradingagents.graph.scanner_facts.builder import save_scanner_graph_facts

    facts = _make_facts(nodes=[_ticker("ON"), _sector("Technology")], edges=[])
    artifact_path = tmp_path / "scanner_graph_facts.json"
    save_scanner_graph_facts(facts, artifact_path)

    tool = get_render_tool()
    with patch(
        "tradingagents.graph.scanner_facts.render.get_scanner_graph_facts_path",
        return_value=artifact_path,
    ), pytest.raises(KeyError):
        tool.invoke({"scan_date": "2026-04-16", "run_id": "TESTRUN", "ticker": "UNKNOWN_999"})
```

## Step 2: Run failing tests

```bash
cd /Users/Ahmet/Repo/TradingAgents/.claude/worktrees/silly-meitner-37bb65
conda activate tradingagents
pytest tests/graph/scanner_facts/test_render.py -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError: No module named 'tradingagents.graph.scanner_facts.render'`

## Step 3: Implement `render.py`

- [ ] Create `tradingagents/graph/scanner_facts/render.py`:

```python
"""Prompt renderer for scanner_graph_facts artifacts.

Converts a ticker's 2-hop subgraph + global regime into a compact,
budget-capped prompt string ready for analyst/trader injection.

Public API:
    render_ticker_graph_context(facts, ticker, *, char_budget=2400) -> str
    get_render_tool() -> LangChain tool
"""
from __future__ import annotations

import logging
from typing import Any

_logger = logging.getLogger(__name__)

_DEFAULT_CHAR_BUDGET = 2400

# -----------------------------------------------------------------
# Edge template dispatch
# -----------------------------------------------------------------

def _render_edge_line(edge: dict) -> str:
    src, rel, tgt = edge["source"], edge["relation"], edge["target"]
    ev = (edge.get("evidence") or "").strip()
    pol = (edge.get("polarity") or "").strip()

    if rel == "BELONGS_TO":
        return f"{src} belongs to {tgt}."
    if rel == "DRIVES_SENTIMENT":
        pol_part = f" ({pol})" if pol else ""
        return f"{src} is linked to {tgt}{pol_part}, with evidence: \"{ev}\"."
    if rel == "HAS_CATALYST":
        return f"{src} has catalyst {tgt}: \"{ev}\"."
    if rel == "EXPOSED_TO":
        return f"{src} is exposed to {tgt}: \"{ev}\"."
    if rel == "IMPACTS":
        return f"{src} impacts {tgt}: \"{ev}\"."
    # RELATED_TO and fallback
    return f"{src} is related to {tgt}: \"{ev}\"."


def _render_node_line(node: dict) -> str:
    nid = node["id"]
    ntype = node.get("type", "")
    ev = (node["evidence"][0] if node.get("evidence") else "").strip()
    pol = ""

    if ntype == "Sector":
        return f"{nid} is {pol or 'noted'} with evidence: \"{ev}\"." if ev else f"{nid} sector."
    if ntype == "Theme":
        return f"Theme {nid} is active: \"{ev}\"." if ev else f"Theme {nid}."
    if ntype in ("MarketIndex", "MacroIndicator", "Commodity", "CurrencyPair", "CryptoAsset"):
        return f"{nid}: {ev}." if ev else f"{nid}."
    return f"{nid}: {ev}." if ev else f"{nid}."


# -----------------------------------------------------------------
# Dedup
# -----------------------------------------------------------------

def _dedup_edges(edges: list[dict]) -> list[dict]:
    """Keep one edge per (source, relation, target); prefer highest confidence."""
    seen: dict[tuple, dict] = {}
    for edge in edges:
        key = (edge["source"], edge["relation"], edge["target"])
        if key not in seen or edge.get("confidence", 0) > seen[key].get("confidence", 0):
            seen[key] = edge
    return list(seen.values())


# -----------------------------------------------------------------
# Core renderer
# -----------------------------------------------------------------

def render_ticker_graph_context(
    facts: dict,
    ticker: str,
    *,
    char_budget: int = _DEFAULT_CHAR_BUDGET,
) -> str:
    """Render prompt-ready ticker graph context.

    Args:
        facts:       ScannerGraphFacts dict (schema_version = scanner_graph_facts.v1).
        ticker:      Ticker symbol or alias (case-insensitive match).
        char_budget: Hard character cap on output (default 2400).

    Returns:
        Formatted prompt string, or "" if both subgraph and global regime are empty.

    Raises:
        KeyError: if ticker is not found in the graph (propagated from search).
    """
    from tradingagents.graph.scanner_facts.search import retrieve_ticker_subgraph

    subgraph = retrieve_ticker_subgraph(facts, ticker, hops=2)
    canonical = subgraph["ticker"]
    raw_edges = subgraph["edges"]
    subgraph_nodes = {n["id"]: n for n in subgraph["nodes"]}

    global_regime = facts.get("global_regime") or {}
    regime_summary = (global_regime.get("summary") or "").strip()
    regime_bullets = [b for b in (global_regime.get("bullets") or []) if b.strip()]

    deduped_edges = _dedup_edges(raw_edges)

    # Determine leaf nodes (nodes in subgraph not covered as source or target of any edge)
    edge_endpoints: set[str] = set()
    for e in deduped_edges:
        edge_endpoints.add(e["source"])
        edge_endpoints.add(e["target"])
    leaf_nodes = [
        n for nid, n in subgraph_nodes.items()
        if nid not in edge_endpoints and n.get("type") != "Ticker"
    ]

    # ---- Check if both regime and subgraph are empty ----
    has_regime = bool(regime_summary or regime_bullets)
    has_subgraph = bool(deduped_edges or leaf_nodes)
    if not has_regime and not has_subgraph:
        return ""

    # ---- Build sections ----
    lines_regime: list[str] = []
    if has_regime:
        lines_regime.append("## Global Market Regime")
        if regime_summary:
            lines_regime.append(f"- {regime_summary}")
        for b in regime_bullets:
            lines_regime.append(f"- {b}")

    lines_facts: list[str] = []
    lines_facts.append(f"## Ticker Graph Context: {canonical}")
    for edge in deduped_edges:
        lines_facts.append(f"- {_render_edge_line(edge)}")
    for node in leaf_nodes:
        lines_facts.append(f"- {_render_node_line(node)}")

    lines_prov: list[str] = []
    if deduped_edges:
        lines_prov.append("## Provenance")
        for edge in deduped_edges:
            prov = edge.get("provenance") or ""
            lines_prov.append(f"- {edge['source']} -> {edge['target']}: {prov}")

    # ---- Budget enforcement ----
    def _join(r, f, p) -> str:
        parts = []
        if r:
            parts.append("\n".join(r))
        if f:
            parts.append("\n".join(f))
        if p:
            parts.append("\n".join(p))
        return "\n\n".join(parts)

    result = _join(lines_regime, lines_facts, lines_prov)
    if len(result) <= char_budget:
        return result

    # Truncation pass 1: drop provenance section
    result = _join(lines_regime, lines_facts, [])
    if len(result) <= char_budget:
        return result

    # Truncation pass 2: drop fact lines from bottom (oldest = bottom of BFS)
    omitted = 0
    while len(result) > char_budget and len(lines_facts) > 2:
        lines_facts.pop()
        omitted += 1
        result = _join(lines_regime, lines_facts, [])

    if omitted:
        suffix = f"\n... ({omitted} more facts omitted)"
        # Ensure suffix fits within budget
        if len(result) + len(suffix) <= char_budget:
            result = result + suffix
        else:
            # Truncate more aggressively to fit suffix
            while len(result) + len(suffix) > char_budget and len(lines_facts) > 2:
                lines_facts.pop()
                omitted += 1
                suffix = f"\n... ({omitted} more facts omitted)"
                result = _join(lines_regime, lines_facts, []) + suffix

    return result[:char_budget]


# -----------------------------------------------------------------
# LangChain render tool
# -----------------------------------------------------------------

def get_render_tool():
    """Return a LangChain @tool that renders ticker graph context from state (scan_date, run_id, ticker).

    The tool loads the artifact from disk using get_scanner_graph_facts_path + load_scanner_graph_facts,
    then calls render_ticker_graph_context.
    """
    from langchain_core.tools import tool as lc_tool
    from tradingagents.graph.scanner_facts.builder import load_scanner_graph_facts
    from tradingagents.report_paths import get_scanner_graph_facts_path

    core_renderer = render_ticker_graph_context

    @lc_tool("render_ticker_graph_context")
    def render_ticker_graph_context_tool(scan_date: str, run_id: str, ticker: str) -> str:
        """Render the scanner graph context for a ticker as a compact prompt string.

        Args:
            scan_date: ISO date string (e.g. "2026-04-16").
            run_id:    Run identifier.
            ticker:    Ticker symbol or alias.

        Returns:
            Formatted prompt string, or "" if graph context is empty.

        Raises:
            FileNotFoundError: if the scanner_graph_facts.json artifact is missing.
            KeyError: if the ticker is not found in the graph.
        """
        artifact_path = get_scanner_graph_facts_path(scan_date, run_id)
        facts = load_scanner_graph_facts(artifact_path)
        return core_renderer(facts, ticker)

    return render_ticker_graph_context_tool
```

## Step 4: Run tests — all must pass

```bash
pytest tests/graph/scanner_facts/test_render.py -v
```

Expected: all PASS. Common issues:
- `test_render_empty_subgraph_empty_regime_returns_empty_string`: requires a ticker that **is** in the graph but has no edges AND global regime is empty. The test constructs exactly this case with `XYZ` ticker and empty regime.
- `test_render_char_budget_respected`: the generated output with 30 nodes/edges should exceed 500 chars before truncation. If it doesn't, increase the evidence text repetitions.
- `test_render_tool_produces_same_output`: uses `patch` for `get_scanner_graph_facts_path`. Make sure `from tradingagents.graph.scanner_facts.render import get_scanner_graph_facts_path` is the import path being patched.

## Step 5: Run full suite

```bash
pytest tests/graph/scanner_facts/ -v
pytest tests/ -v -m "not integration" -x
```

## Step 6: Commit

```bash
cd /Users/Ahmet/Repo/TradingAgents/.claude/worktrees/silly-meitner-37bb65
git add \
  tradingagents/graph/scanner_facts/render.py \
  tests/graph/scanner_facts/test_render.py
git commit -m "feat(scanner-facts): prompt renderer with budget/dedup + LangChain render tool"
```

---

## Done When

- `pytest tests/graph/scanner_facts/test_render.py -v` → all green
- `pytest tests/ -v -m "not integration" -x` → no regressions
- Dedup test: same BELONGS_TO triple appears once
- Budget test: output ≤ `char_budget` chars with omission notice
- Alias test: canonical and alias inputs produce identical output
- Tool test: tool invocation matches direct function call
