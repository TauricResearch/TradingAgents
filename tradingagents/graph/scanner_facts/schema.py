"""Canonical schema contract for scanner_graph_facts.v1."""

from __future__ import annotations

from typing import Any, TypedDict

SCHEMA_VERSION = "scanner_graph_facts.v1"

NODE_TYPES: tuple[str, ...] = (
    "Ticker",
    "Sector",
    "Theme",
    "RiskFactor",
    "MarketIndex",
    "MacroIndicator",
    "Commodity",
    "CurrencyPair",
    "CryptoAsset",
)

RELATION_TYPES: tuple[str, ...] = (
    "BELONGS_TO",
    "DRIVES_SENTIMENT",
    "EXPOSED_TO",
    "IMPACTS",
    "RELATED_TO",
    "HAS_CATALYST",
)

_REQUIRED_TOP_LEVEL = (
    "schema_version",
    "scan_date",
    "run_id",
    "source_dir",
    "global_regime",
    "nodes",
    "edges",
    "metadata",
)


class GraphNode(TypedDict):
    id: str
    type: str
    label: str
    aliases: list[str]
    provenance: list[str]
    evidence: list[str]
    confidence: float


class GraphEdge(TypedDict):
    source: str
    relation: str
    target: str
    polarity: str
    provenance: str
    evidence: str
    confidence: float


class GlobalRegime(TypedDict):
    summary: str
    bullets: list[str]
    source: str


class ScannerGraphFacts(TypedDict):
    schema_version: str
    scan_date: str
    run_id: str
    source_dir: str
    global_regime: GlobalRegime
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    metadata: dict[str, Any]


def validate_graph_facts(facts: dict) -> list[str]:
    """Return a list of validation error strings. Empty list = valid."""
    errors: list[str] = []

    # schema_version
    sv = facts.get("schema_version")
    if sv != SCHEMA_VERSION:
        errors.append(f"schema_version must be '{SCHEMA_VERSION}', got {sv!r}")

    # required top-level keys
    for key in _REQUIRED_TOP_LEVEL:
        if key not in facts:
            errors.append(f"missing required top-level key: {key!r}")

    # node validation
    node_ids: set[str] = set()
    for i, node in enumerate(facts.get("nodes", [])):
        nid = node.get("id", "")
        if nid:
            node_ids.add(nid)
        ntype = node.get("type")
        if ntype not in NODE_TYPES:
            errors.append(f"node[{i}] id={nid!r}: invalid type {ntype!r}")
        conf = node.get("confidence")
        if conf is not None and not (0.0 <= float(conf) <= 1.0):
            errors.append(f"node[{i}] id={nid!r}: confidence {conf} out of [0.0, 1.0]")

    # edge validation
    for i, edge in enumerate(facts.get("edges", [])):
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        rel = edge.get("relation")
        prov = edge.get("provenance", "")
        evid = edge.get("evidence", "")

        if rel not in RELATION_TYPES:
            errors.append(f"edge[{i}] {src}->{tgt}: invalid relation {rel!r}")
        if src and src not in node_ids:
            errors.append(f"edge[{i}]: source node {src!r} not in nodes")
        if tgt and tgt not in node_ids:
            errors.append(f"edge[{i}]: target node {tgt!r} not in nodes")
        if not prov:
            errors.append(f"edge[{i}] {src}->{tgt}: provenance must be non-empty")
        if not evid:
            errors.append(f"edge[{i}] {src}->{tgt}: evidence must be non-empty")
        conf = edge.get("confidence")
        if conf is not None and not (0.0 <= float(conf) <= 1.0):
            errors.append(f"edge[{i}] {src}->{tgt}: confidence {conf} out of [0.0, 1.0]")

    return errors
