# Feature 1: Schema, Validation, Alias Registry

**Parent plan:** `docs/superpowers/plans/2026-04-19-json-scanner-graph-facts.md`

**Goal:** Create the `scanner_facts` package skeleton, the canonical schema contract, a `validate_graph_facts` function, and the curated alias registry. No adapters, no build logic yet.

**Files to create:**
- `tradingagents/graph/scanner_facts/__init__.py`
- `tradingagents/graph/scanner_facts/schema.py`
- `tradingagents/graph/scanner_facts/aliases.py`
- `tests/graph/scanner_facts/__init__.py`
- `tests/graph/scanner_facts/test_schema.py`

---

## Step 1: Create package markers

- [ ] Create `tradingagents/graph/scanner_facts/__init__.py` (empty — just `"""Scanner graph facts package."""`).
- [ ] Create `tests/graph/scanner_facts/__init__.py` (empty).

Run:
```bash
conda activate tradingagents
python -c "from tradingagents.graph.scanner_facts import schema"
```
Expected: `ModuleNotFoundError: No module named 'tradingagents.graph.scanner_facts.schema'`

## Step 2: Write the failing tests

- [ ] Create `tests/graph/scanner_facts/test_schema.py` with exactly this content:

```python
import pytest
from tradingagents.graph.scanner_facts.schema import (
    SCHEMA_VERSION,
    NODE_TYPES,
    RELATION_TYPES,
    GraphNode,
    GraphEdge,
    GlobalRegime,
    ScannerGraphFacts,
    validate_graph_facts,
)


# ---- constants ----

def test_schema_version():
    assert SCHEMA_VERSION == "scanner_graph_facts.v1"


def test_node_types_complete():
    assert set(NODE_TYPES) == {
        "Ticker", "Sector", "Theme", "RiskFactor",
        "MarketIndex", "MacroIndicator", "Commodity",
        "CurrencyPair", "CryptoAsset",
    }


def test_relation_types_complete():
    assert set(RELATION_TYPES) == {
        "BELONGS_TO", "DRIVES_SENTIMENT", "EXPOSED_TO",
        "IMPACTS", "RELATED_TO", "HAS_CATALYST",
    }


# ---- validate_graph_facts: valid ----

_VALID_FACTS = {
    "schema_version": "scanner_graph_facts.v1",
    "scan_date": "2026-04-16",
    "run_id": "01KPBZ79XBDWWYSXVZF0APEYPW",
    "source_dir": "reports/daily/2026-04-16/01KPBZ79XBDWWYSXVZF0APEYPW/market",
    "global_regime": {
        "summary": "Risk-On regime.",
        "bullets": ["S&P 500 at new highs."],
        "source": "macro_scan_summary.json",
    },
    "nodes": [
        {
            "id": "ON",
            "type": "Ticker",
            "label": "ON",
            "aliases": ["ON Semiconductor"],
            "provenance": ["smart_money_summary.md#Candidate Rows"],
            "evidence": ["Breakout at $79.93"],
            "confidence": 0.95,
        },
        {
            "id": "Technology",
            "type": "Sector",
            "label": "Technology",
            "aliases": [],
            "provenance": ["smart_money_summary.md#Candidate Rows"],
            "evidence": [],
            "confidence": 0.90,
        },
    ],
    "edges": [
        {
            "source": "ON",
            "relation": "BELONGS_TO",
            "target": "Technology",
            "polarity": "",
            "provenance": "smart_money_summary.md#Candidate Rows",
            "evidence": "ON | Technology | Breakout ...",
            "confidence": 0.95,
        }
    ],
    "metadata": {
        "node_count": 2,
        "edge_count": 1,
        "generated_at": "2026-04-19T00:00:00Z",
        "inputs": ["smart_money_summary.md"],
    },
}


def test_valid_facts_returns_no_errors():
    errors = validate_graph_facts(_VALID_FACTS)
    assert errors == [], errors


# ---- validate_graph_facts: invalid cases ----

def test_missing_required_top_level_key():
    bad = dict(_VALID_FACTS)
    del bad["scan_date"]
    errors = validate_graph_facts(bad)
    assert any("scan_date" in e for e in errors)


def test_invalid_node_type():
    bad = dict(_VALID_FACTS)
    bad["nodes"] = [dict(_VALID_FACTS["nodes"][0], type="UnknownType")]
    errors = validate_graph_facts(bad)
    assert any("UnknownType" in e for e in errors)


def test_invalid_relation_type():
    bad = dict(_VALID_FACTS)
    bad["edges"] = [dict(_VALID_FACTS["edges"][0], relation="INVENTED")]
    errors = validate_graph_facts(bad)
    assert any("INVENTED" in e for e in errors)


def test_edge_missing_source_node():
    bad = dict(_VALID_FACTS)
    bad["edges"] = [dict(_VALID_FACTS["edges"][0], source="MISSING_TICKER")]
    errors = validate_graph_facts(bad)
    assert any("MISSING_TICKER" in e for e in errors)


def test_edge_missing_target_node():
    bad = dict(_VALID_FACTS)
    bad["edges"] = [dict(_VALID_FACTS["edges"][0], target="MISSING_SECTOR")]
    errors = validate_graph_facts(bad)
    assert any("MISSING_SECTOR" in e for e in errors)


def test_edge_missing_provenance():
    bad = dict(_VALID_FACTS)
    bad["edges"] = [dict(_VALID_FACTS["edges"][0], provenance="")]
    errors = validate_graph_facts(bad)
    assert any("provenance" in e for e in errors)


def test_edge_missing_evidence():
    bad = dict(_VALID_FACTS)
    bad["edges"] = [dict(_VALID_FACTS["edges"][0], evidence="")]
    errors = validate_graph_facts(bad)
    assert any("evidence" in e for e in errors)


def test_confidence_out_of_range():
    bad = dict(_VALID_FACTS)
    bad["nodes"] = [dict(_VALID_FACTS["nodes"][0], confidence=1.5)]
    errors = validate_graph_facts(bad)
    assert any("confidence" in e for e in errors)


def test_wrong_schema_version():
    bad = dict(_VALID_FACTS)
    bad["schema_version"] = "scanner_graph_facts.v0"
    errors = validate_graph_facts(bad)
    assert any("schema_version" in e for e in errors)
```

## Step 3: Run tests to verify they fail

```bash
cd /Users/Ahmet/Repo/TradingAgents/.claude/worktrees/silly-meitner-37bb65
conda activate tradingagents
pytest tests/graph/scanner_facts/test_schema.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError` — schema module does not exist yet.

## Step 4: Implement `schema.py`

- [ ] Create `tradingagents/graph/scanner_facts/schema.py`:

```python
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
    "schema_version", "scan_date", "run_id",
    "source_dir", "global_regime", "nodes", "edges", "metadata",
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
```

## Step 5: Run tests to verify they pass

```bash
pytest tests/graph/scanner_facts/test_schema.py -v
```

Expected: all tests PASS.

## Step 6: Write failing alias test

- [ ] Add `tests/graph/scanner_facts/test_aliases.py`:

```python
from tradingagents.graph.scanner_facts.aliases import (
    TICKER_ALIASES,
    SECTOR_ALIASES,
    INDEX_ALIASES,
    MACRO_ALIASES,
    COMMODITY_ALIASES,
    FX_ALIASES,
    resolve_alias,
)


def test_ticker_aliases_returns_list():
    aliases = TICKER_ALIASES.get("ON", [])
    assert isinstance(aliases, list)
    assert "ON Semiconductor" in aliases or "Onsemi" in aliases


def test_sector_aliases_technology():
    aliases = SECTOR_ALIASES.get("Technology", [])
    assert "Information Technology" in aliases


def test_index_aliases_sp500():
    aliases = INDEX_ALIASES.get("S&P 500", [])
    assert any("SPX" in a or "S&P" in a for a in aliases)


def test_resolve_alias_ticker():
    # "ON Semiconductor" should resolve to canonical id "ON"
    result = resolve_alias("ON Semiconductor", registry=TICKER_ALIASES)
    assert result == "ON"


def test_resolve_alias_not_found_returns_none():
    result = resolve_alias("UNKNOWNXYZ", registry=TICKER_ALIASES)
    assert result is None


def test_all_registry_values_are_lists():
    for registry in (TICKER_ALIASES, SECTOR_ALIASES, INDEX_ALIASES,
                     MACRO_ALIASES, COMMODITY_ALIASES, FX_ALIASES):
        for key, val in registry.items():
            assert isinstance(val, list), f"{key} value must be a list"
```

## Step 7: Run alias tests to verify they fail

```bash
pytest tests/graph/scanner_facts/test_aliases.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError`.

## Step 8: Implement `aliases.py`

- [ ] Create `tradingagents/graph/scanner_facts/aliases.py`:

```python
"""Curated alias registry for scanner graph facts.

This is a living file. When a new surface form appears in scanner output
that doesn't resolve to a canonical node id, add it here in the same PR.
Build warnings for heuristic-only classifications are the update backlog.
"""
from __future__ import annotations

TICKER_ALIASES: dict[str, list[str]] = {
    "NVDA": ["Nvidia", "NVIDIA Corporation"],
    "ON": ["ON Semiconductor", "Onsemi"],
    "MSFT": ["Microsoft", "Microsoft Corporation"],
    "AAPL": ["Apple", "Apple Inc"],
    "AMZN": ["Amazon", "Amazon.com"],
    "GOOGL": ["Alphabet", "Google"],
    "META": ["Meta Platforms", "Facebook"],
    "TSLA": ["Tesla", "Tesla Inc"],
    "JPM": ["JPMorgan", "JPMorgan Chase"],
    "BAC": ["Bank of America"],
    "XOM": ["ExxonMobil", "Exxon Mobil"],
    "OXY": ["Occidental Petroleum"],
    "CVX": ["Chevron"],
    "RIG": ["Transocean"],
    "MRVL": ["Marvell", "Marvell Technology"],
    "AMD": ["Advanced Micro Devices"],
    "INTC": ["Intel", "Intel Corporation"],
    "QCOM": ["Qualcomm"],
    "AVGO": ["Broadcom"],
    "TSM": ["TSMC", "Taiwan Semiconductor"],
}

SECTOR_ALIASES: dict[str, list[str]] = {
    "Technology": ["Information Technology", "Tech", "IT Sector"],
    "Financials": ["Financial", "Financial Services", "Finance"],
    "Energy": ["Energy Sector", "Oil & Gas"],
    "Health Care": ["Healthcare", "Health Care Sector", "Pharma", "Biotech"],
    "Consumer Discretionary": ["Consumer Cyclical", "Retail"],
    "Consumer Staples": ["Consumer Defensive", "Staples"],
    "Industrials": ["Industrial", "Industrials Sector"],
    "Materials": ["Basic Materials", "Materials Sector"],
    "Real Estate": ["REITs", "Real Estate Sector"],
    "Utilities": ["Utilities Sector"],
    "Communication Services": ["Communications", "Telecom", "Media"],
}

INDEX_ALIASES: dict[str, list[str]] = {
    "S&P 500": ["SPX", "S&P", "SP500", "S&P500"],
    "NASDAQ": ["Nasdaq", "Nasdaq Composite", "NDX", "QQQ"],
    "Dow Jones": ["DJIA", "Dow", "Dow Jones Industrial Average"],
    "Russell 2000": ["RUT", "Russell", "Small Cap Index"],
}

MACRO_ALIASES: dict[str, list[str]] = {
    "VIX": ["CBOE Volatility Index", "Fear Index", "Volatility Index"],
    "CPI": ["Consumer Price Index", "Inflation"],
    "PCE": ["Personal Consumption Expenditures"],
    "Fed Funds Rate": ["Federal Funds Rate", "Fed Rate", "FOMC Rate"],
    "10Y Yield": ["10-Year Treasury", "US 10Y", "Treasury Yield"],
    "German CDS": ["German Credit Default Swap", "Germany CDS"],
    "DXY": ["US Dollar Index", "Dollar Index"],
}

COMMODITY_ALIASES: dict[str, list[str]] = {
    "Brent Crude": ["Brent", "Brent Oil", "ICE Brent"],
    "WTI Crude": ["WTI", "WTI Oil", "NYMEX Crude"],
    "Gold": ["XAUUSD", "Spot Gold"],
    "Silver": ["XAGUSD", "Spot Silver"],
    "Natural Gas": ["NG", "Nat Gas"],
    "Copper": ["COMEX Copper"],
}

FX_ALIASES: dict[str, list[str]] = {
    "EUR/USD": ["EURUSD", "Euro Dollar"],
    "JPY/USD": ["JPYUSD", "USD/JPY", "USDJPY", "Yen"],
    "CNY/USD": ["CNYUSD", "USD/CNY", "USDCNY", "Yuan", "Renminbi"],
    "GBP/USD": ["GBPUSD", "Cable", "British Pound"],
    "DXY": ["US Dollar Index"],
}


def resolve_alias(
    label: str,
    registry: dict[str, list[str]],
) -> str | None:
    """Return the canonical key for *label*, or None if not found.

    Checks both the canonical keys and their alias lists.
    """
    label_norm = label.strip()
    if label_norm in registry:
        return label_norm
    for canonical, aliases in registry.items():
        if label_norm in aliases:
            return canonical
    return None
```

## Step 9: Run all tests to verify they pass

```bash
pytest tests/graph/scanner_facts/ -v
```

Expected: all tests PASS.

## Step 10: Commit

```bash
cd /Users/Ahmet/Repo/TradingAgents/.claude/worktrees/silly-meitner-37bb65
git add tradingagents/graph/scanner_facts/__init__.py \
        tradingagents/graph/scanner_facts/schema.py \
        tradingagents/graph/scanner_facts/aliases.py \
        tests/graph/scanner_facts/__init__.py \
        tests/graph/scanner_facts/test_schema.py \
        tests/graph/scanner_facts/test_aliases.py
git commit -m "feat(scanner-facts): add schema contract, validate_graph_facts, and alias registry"
```

---

## Done When

- `pytest tests/graph/scanner_facts/ -v` → all green
- `pytest tests/ -v -m "not integration" -x` → no regressions
- `validate_graph_facts` returns `[]` for the valid fixture and at least one error for each of the 8 invalid cases
- `resolve_alias("ON Semiconductor", TICKER_ALIASES)` returns `"ON"`
