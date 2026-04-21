# Feature 7: JSON Graph Search

**Parent plan:** `docs/superpowers/plans/2026-04-19-json-scanner-graph-facts.md`

**Goal:** Implement `search.py` — exact + alias lookup and 1/2-hop undirected subgraph retrieval over the in-memory facts dict. Works directly on the schema dict (no file I/O). Raises loudly on unknown ticker (does not silently return empty).

**Dependencies already committed:**
- F1: `schema.py`, `aliases.py`
- F2: `normalize.py`, all fixtures

**Note:** This feature does NOT depend on F5 (builder). It works on any dict that matches the schema shape. The builder produces such a dict; tests here construct minimal dicts inline.

**Files to create:**
- `tradingagents/graph/scanner_facts/search.py`
- `tests/graph/scanner_facts/test_search.py`

---

## Retrieval Rules

- Traversal is **undirected**: follow edges in both directions to discover connected nodes.
- Output edges preserve their **original direction** (source → target as stored).
- `hops` is clamped to `[1, 3]`; default `2`.
- `max_edges` caps the number of edges returned; default `80`. When exceeded, prioritise edges closer to the seed ticker (BFS order).
- Alias lookup: try `id` first, then search `aliases` list on all nodes, then use the curated ticker alias registry from `aliases.py`. The registry fallback is required for artifacts built before aliases were embedded per node.
- Unknown ticker → **raise `KeyError`** with a clear message.
- Empty subgraph (ticker found but no edges) → return the ticker node alone in `nodes`, empty `edges`.

---

## Step 1: Write failing tests

- [ ] Create `tests/graph/scanner_facts/test_search.py`:

```python
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


def test_integration_unknown_ticker_raises_in_real_facts():
    from tradingagents.graph.scanner_facts.builder import (
        build_scanner_graph_facts_from_market_dir,
    )
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-search-unknown"
    )
    with pytest.raises(KeyError):
        retrieve_ticker_subgraph(facts, "ZZZNOTTICKER", hops=2)
```

## Step 2: Run failing tests

```bash
cd /Users/Ahmet/Repo/TradingAgents/.claude/worktrees/silly-meitner-37bb65
conda activate tradingagents
pytest tests/graph/scanner_facts/test_search.py -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError: No module named 'tradingagents.graph.scanner_facts.search'`

## Step 3: Implement `search.py`

- [ ] Create `tradingagents/graph/scanner_facts/search.py`:

```python
"""JSON graph search: exact/alias ticker lookup + 1–3-hop undirected subgraph retrieval.

Traversal is undirected (edges followed in both directions).
Output edges preserve their original stored direction.
Unknown ticker raises KeyError — never returns empty silently.
"""
from __future__ import annotations

import logging
from collections import deque

_logger = logging.getLogger(__name__)


def _find_seed_node(facts: dict, query: str) -> dict | None:
    """Return the node dict whose id or aliases match *query* (case-insensitive for id)."""
    upper = query.strip().upper()
    # Exact id match (case-insensitive)
    for node in facts.get("nodes", []):
        if node["id"].upper() == upper:
            return node
    # Alias match
    for node in facts.get("nodes", []):
        for alias in node.get("aliases", []):
            if alias.strip().upper() == upper or alias.strip() == query.strip():
                return node
    return None


def retrieve_ticker_subgraph(
    facts: dict,
    ticker: str,
    *,
    hops: int = 2,
    node_types: set[str] | None = None,
    max_edges: int = 80,
) -> dict:
    """Return the *hops*-hop undirected subgraph seeded on *ticker*.

    Args:
        facts:      A ScannerGraphFacts dict (schema_version = scanner_graph_facts.v1).
        ticker:     Ticker symbol or alias to look up.
        hops:       Number of hops to traverse; clamped to [1, 3].
        node_types: Optional set of node types to include (None = all types).
        max_edges:  Maximum edges in the result; BFS-order priority.

    Returns:
        {
            "ticker": canonical_id,
            "nodes": [...],
            "edges": [...],
            "hops": effective_hops,
        }

    Raises:
        KeyError: if ticker (or any alias) is not found in facts.
    """
    hops = max(1, min(int(hops), 3))

    seed = _find_seed_node(facts, ticker)
    if seed is None:
        raise KeyError(
            f"Ticker {ticker!r} not found in scanner graph facts "
            f"(run_id={facts.get('run_id')!r}, scan_date={facts.get('scan_date')!r}). "
            "Check spelling or run rebuild_scanner_graph_facts() to regenerate."
        )
    canonical = seed["id"]

    # Build adjacency: node_id → list of (edge, neighbour_id)
    adjacency: dict[str, list[tuple[dict, str]]] = {}
    for edge in facts.get("edges", []):
        src, tgt = edge["source"], edge["target"]
        adjacency.setdefault(src, []).append((edge, tgt))
        adjacency.setdefault(tgt, []).append((edge, src))

    # BFS
    visited_nodes: dict[str, dict] = {}   # id → node dict
    collected_edges: list[dict] = []
    seen_edge_keys: set[tuple] = set()

    # Index nodes by id for fast lookup
    node_by_id: dict[str, dict] = {n["id"]: n for n in facts.get("nodes", [])}

    queue: deque[tuple[str, int]] = deque([(canonical, 0)])
    visited_nodes[canonical] = seed

    while queue:
        current_id, depth = queue.popleft()
        if depth >= hops:
            continue

        for edge, neighbour_id in adjacency.get(current_id, []):
            # Edge key for dedup
            ekey = (edge["source"], edge["relation"], edge["target"], edge["provenance"])

            if len(collected_edges) >= max_edges:
                break

            if neighbour_id not in visited_nodes:
                neighbour = node_by_id.get(neighbour_id)
                if neighbour is None:
                    continue
                if node_types and neighbour["type"] not in node_types:
                    continue
                visited_nodes[neighbour_id] = neighbour
                queue.append((neighbour_id, depth + 1))

            if ekey not in seen_edge_keys:
                seen_edge_keys.add(ekey)
                collected_edges.append(edge)
                if len(collected_edges) >= max_edges:
                    break

    return {
        "ticker": canonical,
        "nodes": list(visited_nodes.values()),
        "edges": collected_edges,
        "hops": hops,
    }
```

## Step 4: Run all tests — all must pass

```bash
pytest tests/graph/scanner_facts/test_search.py -v
```

Expected: all PASS. Notes:
- `test_integration_*` tests call `build_scanner_graph_facts_from_market_dir` — this requires F5 (`builder.py`) to be committed. If F5 is not yet on the branch, skip the integration tests with `-k "not integration"` and they will be added in the F5 merge.
- `test_ticker_with_no_edges_returns_ticker_node_only`: The seed node must always be in the result even when it has no edges.
- `test_2hop_nvda_shares_technology_node`: From ON → Technology (hop 1) → NVDA (hop 2 via Technology). Confirm BFS picks up NVDA.

## Step 5: Run full suite

```bash
pytest tests/graph/scanner_facts/ -v
pytest tests/ -v -m "not integration" -x
```

## Step 6: Commit

```bash
cd /Users/Ahmet/Repo/TradingAgents/.claude/worktrees/silly-meitner-37bb65
git add \
  tradingagents/graph/scanner_facts/search.py \
  tests/graph/scanner_facts/test_search.py
git commit -m "feat(scanner-facts): JSON graph search with alias lookup and 1-3-hop BFS retrieval"
```

---

## Done When

- `pytest tests/graph/scanner_facts/test_search.py -v` → all green
- `pytest tests/ -v -m "not integration" -x` → no regressions
- Unknown ticker raises `KeyError` (not returns empty)
- Alias `"ON Semiconductor"` resolves to node `"ON"`
- Curated registry alias `"Nvidia"` resolves to node `"NVDA"` in the real fixture graph
- 2-hop from `"ON"` includes `Technology`, `AI Infrastructure`, `Concentration risk`, `NVDA`
- `max_edges=1` returns at most 1 edge, and it is the direct ON→Technology edge
