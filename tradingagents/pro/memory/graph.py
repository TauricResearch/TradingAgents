"""Lightweight knowledge graph of market relationships.

Typed weighted edges in an adjacency map — enough to inject "what usually
drives this asset" context into debates and to grow from observed
correlations later. Deliberately not a graph database (ADR-0020).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Relation:
    source: str
    relation: str  # e.g. "inverse", "positive", "safe_haven_bid", "drives"
    target: str
    weight: float  # 0..1 strength of the prior
    note: str = ""


class KnowledgeGraph:
    def __init__(self, relations: list[Relation] | None = None):
        self._edges: list[Relation] = list(relations or [])

    def add(self, relation: Relation) -> None:
        self._edges.append(relation)

    def neighbors(self, node: str) -> list[Relation]:
        return [e for e in self._edges if e.source == node or e.target == node]

    def between(self, a: str, b: str) -> list[Relation]:
        return [
            e for e in self._edges
            if {e.source, e.target} == {a, b}
        ]

    def to_prompt_block(self, node: str, limit: int = 8) -> str:
        edges = sorted(self.neighbors(node), key=lambda e: e.weight, reverse=True)[:limit]
        if not edges:
            return ""
        lines = ["Known market relationships (structural priors, not signals):"]
        for e in edges:
            note = f" ({e.note})" if e.note else ""
            lines.append(f"- {e.source} --{e.relation}[{e.weight:.1f}]--> {e.target}{note}")
        return "\n".join(lines)


def default_gold_graph() -> KnowledgeGraph:
    return KnowledgeGraph([
        Relation("DXY", "inverse", "XAUUSD", 0.8, "dollar-priced asset"),
        Relation("US10Y_REAL", "inverse", "XAUUSD", 0.9,
                 "real yields are gold's opportunity cost"),
        Relation("CPI_YOY", "positive", "XAUUSD", 0.6, "inflation-hedge bid"),
        Relation("GEOPOLITICAL_RISK", "safe_haven_bid", "XAUUSD", 0.7),
        Relation("XAUUSD", "positive", "XAGUSD", 0.8, "metals complex co-moves"),
        Relation("FED_FUNDS_RATE", "drives", "US10Y_REAL", 0.7),
        Relation("NFP_CHANGE", "drives", "FED_FUNDS_RATE", 0.5,
                 "labor strength shapes policy path"),
    ])


def default_bitcoin_graph() -> KnowledgeGraph:
    return KnowledgeGraph([
        Relation("DXY", "inverse", "BTC-USD", 0.5, "global liquidity proxy"),
        Relation("FUNDING_RATE", "positive", "BTC-USD", 0.5,
                 "sustained positive funding = leveraged-long crowding"),
        Relation("OPEN_INTEREST", "amplifies", "BTC-USD", 0.5,
                 "high OI amplifies moves both ways"),
        Relation("MVRV", "mean_reverts", "BTC-USD", 0.6,
                 "valuation stretch mean-reverts over cycles"),
        Relation("HASH_RATE", "positive", "BTC-USD", 0.4, "miner commitment"),
        Relation("FEAR_GREED_INDEX", "contrarian_at_extremes", "BTC-USD", 0.5),
        Relation("US10Y_REAL", "inverse", "BTC-USD", 0.5, "risk-asset discounting"),
    ])


def default_graph_for(symbol: str) -> KnowledgeGraph:
    upper = symbol.upper()
    if "BTC" in upper:
        return default_bitcoin_graph()
    return default_gold_graph()
