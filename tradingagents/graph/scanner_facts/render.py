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
        return f'{src} is linked to {tgt}{pol_part}, with evidence: "{ev}".'
    if rel == "HAS_CATALYST":
        return f'{src} has catalyst {tgt}: "{ev}".'
    if rel == "EXPOSED_TO":
        return f'{src} is exposed to {tgt}: "{ev}".'
    if rel == "IMPACTS":
        return f'{src} impacts {tgt}: "{ev}".'
    # RELATED_TO and fallback
    return f'{src} is related to {tgt}: "{ev}".'


def _render_node_line(node: dict) -> str:
    nid = node["id"]
    ntype = node.get("type", "")
    ev = (node["evidence"][0] if node.get("evidence") else "").strip()
    pol = ""

    if ntype == "Sector":
        return f'{nid} is {pol or "noted"} with evidence: "{ev}".' if ev else f"{nid} sector."
    if ntype == "Theme":
        return f'Theme {nid} is active: "{ev}".' if ev else f"Theme {nid}."
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
        n
        for nid, n in subgraph_nodes.items()
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
    def _join(r: list[str], f: list[str], p: list[str]) -> str:
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


def get_render_tool() -> Any:
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
