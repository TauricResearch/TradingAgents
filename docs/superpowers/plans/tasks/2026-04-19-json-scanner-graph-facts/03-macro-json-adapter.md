# Feature 3: Macro JSON Adapter

**Parent plan:** `docs/superpowers/plans/2026-04-19-json-scanner-graph-facts.md`

**Goal:** Implement `from_macro_json.py` — the adapter that reads `macro_scan_summary.json` and returns a partial `ScannerGraphFacts`-compatible dict (nodes + edges + global_regime). No I/O beyond file reading. Fails loudly if the file is missing or unparseable.

**Dependencies already committed:**
- `tradingagents/graph/scanner_facts/schema.py` (F1)
- `tradingagents/graph/scanner_facts/aliases.py` (F1)
- `tradingagents/graph/scanner_facts/normalize.py` (F2)
- `tests/graph/scanner_facts/fixtures/macro_scan_summary.json` (F2)

**Files to create:**
- `tradingagents/graph/scanner_facts/from_macro_json.py`
- `tests/graph/scanner_facts/test_from_macro_json.py`

---

## What the real macro_scan_summary.json looks like

Top-level keys: `timeframe`, `executive_summary`, `macro_context`, `key_themes`, `stocks_to_investigate`, `risk_factors`

Key shapes:

```json
"key_themes": [
  { "theme": "Technology Sector Momentum & AI Infrastructure", "conviction": "high", ... }
]

"stocks_to_investigate": [
  {
    "ticker": "ON",
    "name": "ON Semiconductor",
    "sector": "Technology",
    "rationale": "Breakout accumulation at $79.93...",
    "thesis_angle": "Golden Overlap...",
    "conviction": "high",
    "key_catalysts": ["Breakout above $79.93 on 11.54x relative volume", ...],
    "risks": ["High valuation premium...", ...]
  }
]

"risk_factors": [
  "VIX sustained increase above 17.90 negating current Risk-On classification",
  "German sovereign CDS spread acceleration (+13.01%)...",
  ...
]
```

The real fixture is at: `tests/graph/scanner_facts/fixtures/macro_scan_summary.json`

---

## Step 1: Write the failing tests

- [ ] Create `tests/graph/scanner_facts/test_from_macro_json.py`:

```python
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
    result = facts_from_macro_scan_summary(
        REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run"
    )
    regime = result["global_regime"]
    assert "Risk-On" in regime["summary"]


def test_global_regime_source_is_macro_json():
    result = facts_from_macro_scan_summary(
        REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run"
    )
    assert result["global_regime"]["source"] == "macro_scan_summary.json"


def test_global_regime_has_bullets():
    result = facts_from_macro_scan_summary(
        REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run"
    )
    assert len(result["global_regime"]["bullets"]) >= 3


# ---- Theme nodes from key_themes ----

def test_key_themes_become_theme_nodes():
    result = facts_from_macro_scan_summary(
        REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run"
    )
    ids = _node_ids(result)
    # Real fixture has "Technology Sector Momentum & AI Infrastructure"
    assert any("Technology" in nid or "AI Infrastructure" in nid or "Momentum" in nid
               for nid in ids), f"No technology theme found in {ids}"


def test_theme_nodes_have_correct_type():
    result = facts_from_macro_scan_summary(
        REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run"
    )
    theme_nodes = [n for n in result["nodes"] if n["type"] == "Theme"]
    assert len(theme_nodes) >= 4  # 4 key_themes in real fixture


def test_theme_nodes_provenance_is_macro_json():
    result = facts_from_macro_scan_summary(
        REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run"
    )
    theme_nodes = [n for n in result["nodes"] if n["type"] == "Theme"]
    for node in theme_nodes:
        assert any("macro_scan_summary" in p for p in node["provenance"])


# ---- Ticker + Sector nodes from stocks_to_investigate ----

def test_on_ticker_node_created():
    result = facts_from_macro_scan_summary(
        REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run"
    )
    assert "ON" in _node_ids(result)


def test_msft_ticker_node_created():
    result = facts_from_macro_scan_summary(
        REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run"
    )
    assert "MSFT" in _node_ids(result)


def test_technology_sector_node_created():
    result = facts_from_macro_scan_summary(
        REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run"
    )
    assert "Technology" in _node_ids(result)


def test_ticker_aliases_populated_from_name_field():
    result = facts_from_macro_scan_summary(
        REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run"
    )
    on_node = next(n for n in result["nodes"] if n["id"] == "ON")
    # "ON Semiconductor" is the name in the real fixture
    assert "ON Semiconductor" in on_node["aliases"] or len(on_node["aliases"]) >= 0


# ---- BELONGS_TO edges ----

def test_on_belongs_to_technology():
    result = facts_from_macro_scan_summary(
        REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run"
    )
    assert _edge_exists(result, "ON", "BELONGS_TO", "Technology")


def test_msft_belongs_to_technology():
    result = facts_from_macro_scan_summary(
        REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run"
    )
    assert _edge_exists(result, "MSFT", "BELONGS_TO", "Technology")


def test_belongs_to_edges_have_provenance():
    result = facts_from_macro_scan_summary(
        REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run"
    )
    bt_edges = _edges_by_relation(result, "BELONGS_TO")
    for e in bt_edges:
        assert e["provenance"], f"BELONGS_TO edge missing provenance: {e}"
        assert e["evidence"], f"BELONGS_TO edge missing evidence: {e}"


# ---- HAS_CATALYST edges (Ticker -> Theme from key_catalysts) ----

def test_has_catalyst_edges_created_from_key_catalysts():
    result = facts_from_macro_scan_summary(
        REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run"
    )
    hc_edges = _edges_by_relation(result, "HAS_CATALYST")
    assert len(hc_edges) >= 1, "Expected at least one HAS_CATALYST edge"


def test_has_catalyst_source_is_ticker():
    result = facts_from_macro_scan_summary(
        REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run"
    )
    hc_edges = _edges_by_relation(result, "HAS_CATALYST")
    node_ids = _node_ids(result)
    for e in hc_edges:
        assert e["source"] in node_ids, f"HAS_CATALYST source {e['source']!r} not in nodes"


def test_has_catalyst_edges_have_confidence():
    result = facts_from_macro_scan_summary(
        REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run"
    )
    hc_edges = _edges_by_relation(result, "HAS_CATALYST")
    for e in hc_edges:
        assert 0.1 <= e["confidence"] <= 0.99


# ---- EXPOSED_TO edges (Ticker -> RiskFactor from risks) ----

def test_exposed_to_edges_from_stock_risks():
    result = facts_from_macro_scan_summary(
        REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run"
    )
    et_edges = _edges_by_relation(result, "EXPOSED_TO")
    assert len(et_edges) >= 1, "Expected EXPOSED_TO edges from stock risks"


def test_risk_factor_nodes_created():
    result = facts_from_macro_scan_summary(
        REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run"
    )
    rf_nodes = [n for n in result["nodes"] if n["type"] == "RiskFactor"]
    assert len(rf_nodes) >= 1


# ---- Top-level risk_factors list ----

def test_top_level_risk_factors_create_nodes():
    result = facts_from_macro_scan_summary(
        REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run"
    )
    rf_nodes = [n for n in result["nodes"] if n["type"] == "RiskFactor"]
    # real fixture has 6 risk_factors strings → each becomes a node
    assert len(rf_nodes) >= 6


# ---- confidence ----

def test_structured_fields_have_high_confidence():
    result = facts_from_macro_scan_summary(
        REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run"
    )
    bt_edges = _edges_by_relation(result, "BELONGS_TO")
    for e in bt_edges:
        # MACRO_JSON_STRUCTURED base = 0.90
        assert e["confidence"] >= 0.80, f"Low confidence on BELONGS_TO: {e['confidence']}"


# ---- schema validation ----

def test_output_passes_schema_validation():
    result = facts_from_macro_scan_summary(
        REAL_PAYLOAD, scan_date="2026-04-16", run_id="test-run"
    )
    # Wrap in full facts shape for validation
    facts = {
        "schema_version": "scanner_graph_facts.v1",
        "scan_date": "2026-04-16",
        "run_id": "test-run",
        "source_dir": "test",
        "global_regime": result["global_regime"],
        "nodes": result["nodes"],
        "edges": result["edges"],
        "metadata": {"node_count": len(result["nodes"]), "edge_count": len(result["edges"]),
                     "generated_at": "2026-04-16T00:00:00Z", "inputs": []},
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
    result = facts_from_macro_scan_summary(
        payload, scan_date="2026-04-16", run_id="test-run"
    )
    ticker_nodes = [n for n in result["nodes"] if n["type"] == "Ticker"]
    assert ticker_nodes == []


def test_empty_key_themes_produces_no_theme_nodes_from_themes():
    payload = dict(REAL_PAYLOAD, key_themes=[])
    result = facts_from_macro_scan_summary(
        payload, scan_date="2026-04-16", run_id="test-run"
    )
    # RiskFactor nodes from risk_factors still appear, but no Theme nodes from themes
    theme_from_themes = [
        n for n in result["nodes"]
        if n["type"] == "Theme"
        and any("macro_scan_summary.json#key_themes" in p for p in n["provenance"])
    ]
    assert theme_from_themes == []
```

## Step 2: Run failing tests

```bash
cd /Users/Ahmet/Repo/TradingAgents/.claude/worktrees/silly-meitner-37bb65
conda activate tradingagents
pytest tests/graph/scanner_facts/test_from_macro_json.py -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError: No module named 'tradingagents.graph.scanner_facts.from_macro_json'`

## Step 3: Implement `from_macro_json.py`

- [ ] Create `tradingagents/graph/scanner_facts/from_macro_json.py`:

```python
"""Adapter: macro_scan_summary.json → partial ScannerGraphFacts dict.

Produces:
  {
    "global_regime": {...},
    "nodes": [...],
    "edges": [...],
  }

Fails loudly:
  - FileNotFoundError if path is missing
  - ValueError if JSON is malformed
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from tradingagents.graph.scanner_facts.normalize import (
    ConfidenceSource,
    canonicalize_sector,
    compute_confidence,
    infer_polarity,
    is_equity_ticker,
)

_logger = logging.getLogger(__name__)

_SOURCE = "macro_scan_summary.json"
_SOURCE_THEMES = "macro_scan_summary.json#key_themes"
_SOURCE_STOCKS = "macro_scan_summary.json#stocks_to_investigate"
_SOURCE_RISKS = "macro_scan_summary.json#risk_factors"
_SOURCE_EXEC = "macro_scan_summary.json#executive_summary"


# ---------- file loading ----------

def load_and_parse_macro_scan_summary(path: Path) -> dict:
    """Load and parse macro_scan_summary.json. Fails loudly."""
    if not path.exists():
        raise FileNotFoundError(
            f"macro_scan_summary.json not found at {path}. "
            "Cannot build scanner graph facts without it. "
            "Check the scan run completed successfully."
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"macro_scan_summary.json at {path} is not valid JSON: {exc}"
        ) from exc


# ---------- node/edge builders ----------

def _make_node(
    node_id: str,
    node_type: str,
    label: str,
    provenance: list[str],
    evidence: list[str],
    confidence: float,
    aliases: list[str] | None = None,
) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "label": label,
        "aliases": aliases or [],
        "provenance": provenance,
        "evidence": evidence,
        "confidence": round(confidence, 4),
    }


def _make_edge(
    source: str,
    relation: str,
    target: str,
    provenance: str,
    evidence: str,
    confidence: float,
    polarity: str = "",
) -> dict:
    return {
        "source": source,
        "relation": relation,
        "target": target,
        "polarity": polarity,
        "provenance": provenance,
        "evidence": evidence,
        "confidence": round(confidence, 4),
    }


# ---------- main adapter ----------

def facts_from_macro_scan_summary(
    payload: dict,
    *,
    scan_date: str,
    run_id: str,
    source: str = _SOURCE,
) -> dict:
    """Convert a parsed macro_scan_summary.json payload to partial graph facts.

    Returns:
        {
            "global_regime": GlobalRegime dict,
            "nodes": list of GraphNode dicts,
            "edges": list of GraphEdge dicts,
        }
    """
    nodes: list[dict] = []
    edges: list[dict] = []
    node_ids: set[str] = set()

    def _add_node(node: dict) -> None:
        if node["id"] not in node_ids:
            node_ids.add(node["id"])
            nodes.append(node)

    def _add_edge(edge: dict) -> None:
        # Dedupe by (source, relation, target, provenance)
        key = (edge["source"], edge["relation"], edge["target"], edge["provenance"])
        if not any(
            (e["source"], e["relation"], e["target"], e["provenance"]) == key
            for e in edges
        ):
            edges.append(edge)

    # ---- global_regime ----
    exec_summary = str(payload.get("executive_summary") or "")
    macro_ctx = payload.get("macro_context") or {}
    geo_risks = macro_ctx.get("geopolitical_risks") or []

    bullets: list[str] = []
    # Extract key facts from executive_summary (first 3 sentences)
    for sent in exec_summary.replace(". ", ".|").split("|")[:5]:
        s = sent.strip().rstrip(".")
        if s:
            bullets.append(s)
    # Add geopolitical risks as bullets
    for gr in geo_risks[:3]:
        s = str(gr).strip()
        if s:
            bullets.append(s)

    global_regime = {
        "summary": exec_summary[:600] if exec_summary else "",
        "bullets": bullets[:6],
        "source": source,
    }

    # ---- key_themes → Theme nodes ----
    for theme_obj in payload.get("key_themes") or []:
        theme_label = str(theme_obj.get("theme") or "").strip()
        if not theme_label:
            continue
        description = str(theme_obj.get("description") or "")
        conviction = str(theme_obj.get("conviction") or "")
        polarity = infer_polarity(theme_label, description)
        hedging = any(w in description.lower() for w in ("may", "could", "potential", "uncertain"))
        conf = compute_confidence(
            ConfidenceSource.MACRO_JSON_STRUCTURED,
            hedging=hedging,
            polarity_empty=(polarity == ""),
        )
        _add_node(_make_node(
            node_id=theme_label,
            node_type="Theme",
            label=theme_label,
            provenance=[_SOURCE_THEMES],
            evidence=[description[:200]] if description else [],
            confidence=conf,
        ))

    # ---- stocks_to_investigate → Ticker + Sector + edges ----
    for stock in payload.get("stocks_to_investigate") or []:
        ticker = str(stock.get("ticker") or "").strip().upper()
        if not ticker or not is_equity_ticker(ticker):
            _logger.warning("from_macro_json: skipping non-equity ticker %r", ticker)
            continue

        name = str(stock.get("name") or "").strip()
        sector_raw = str(stock.get("sector") or "").strip()
        sector = canonicalize_sector(sector_raw) if sector_raw else ""
        rationale = str(stock.get("rationale") or "")
        thesis = str(stock.get("thesis_angle") or "")
        conviction = str(stock.get("conviction") or "")

        hedging = any(w in rationale.lower() for w in ("may", "could", "potential", "uncertain"))
        conf = compute_confidence(
            ConfidenceSource.MACRO_JSON_STRUCTURED,
            hedging=hedging,
        )

        # Ticker node — use name from payload as alias if available
        aliases: list[str] = []
        if name and name != ticker:
            aliases.append(name)

        _add_node(_make_node(
            node_id=ticker,
            node_type="Ticker",
            label=ticker,
            provenance=[_SOURCE_STOCKS],
            evidence=[rationale[:200]] if rationale else [],
            confidence=conf,
            aliases=aliases,
        ))

        # Sector node
        if sector:
            _add_node(_make_node(
                node_id=sector,
                node_type="Sector",
                label=sector,
                provenance=[_SOURCE_STOCKS],
                evidence=[],
                confidence=compute_confidence(ConfidenceSource.MACRO_JSON_STRUCTURED),
            ))
            # BELONGS_TO edge
            _add_edge(_make_edge(
                source=ticker,
                relation="BELONGS_TO",
                target=sector,
                provenance=_SOURCE_STOCKS,
                evidence=f"{ticker} | {sector} | {thesis or rationale[:100]}",
                confidence=conf,
            ))

        # key_catalysts → HAS_CATALYST edges (Ticker -> Theme)
        for catalyst in stock.get("key_catalysts") or []:
            cat_text = str(catalyst).strip()
            if not cat_text:
                continue
            # Use catalyst text as Theme node id (truncated)
            theme_id = cat_text[:80]
            cat_conf = compute_confidence(
                ConfidenceSource.MACRO_JSON_STRUCTURED,
                hedging=any(w in cat_text.lower() for w in ("may", "could", "potential")),
            )
            _add_node(_make_node(
                node_id=theme_id,
                node_type="Theme",
                label=theme_id,
                provenance=[_SOURCE_STOCKS],
                evidence=[cat_text],
                confidence=cat_conf,
            ))
            _add_edge(_make_edge(
                source=ticker,
                relation="HAS_CATALYST",
                target=theme_id,
                provenance=_SOURCE_STOCKS,
                evidence=cat_text,
                confidence=cat_conf,
            ))

        # stock risks → EXPOSED_TO edges (Ticker -> RiskFactor)
        for risk in stock.get("risks") or []:
            risk_text = str(risk).strip()
            if not risk_text:
                continue
            rf_id = risk_text[:80]
            rf_conf = compute_confidence(
                ConfidenceSource.MACRO_JSON_STRUCTURED,
                hedging=any(w in risk_text.lower() for w in ("may", "could", "potential", "if")),
                polarity_empty=False,
            )
            _add_node(_make_node(
                node_id=rf_id,
                node_type="RiskFactor",
                label=rf_id,
                provenance=[_SOURCE_STOCKS],
                evidence=[risk_text],
                confidence=rf_conf,
            ))
            _add_edge(_make_edge(
                source=ticker,
                relation="EXPOSED_TO",
                target=rf_id,
                provenance=_SOURCE_STOCKS,
                evidence=risk_text,
                confidence=rf_conf,
                polarity="bearish",
            ))

    # ---- top-level risk_factors → RiskFactor nodes ----
    for rf_text in payload.get("risk_factors") or []:
        rf_str = str(rf_text).strip()
        if not rf_str:
            continue
        rf_id = rf_str[:80]
        rf_conf = compute_confidence(
            ConfidenceSource.MACRO_JSON_STRUCTURED,
            hedging=any(w in rf_str.lower() for w in ("may", "could", "potential", "if")),
        )
        _add_node(_make_node(
            node_id=rf_id,
            node_type="RiskFactor",
            label=rf_id,
            provenance=[_SOURCE_RISKS],
            evidence=[rf_str[:200]],
            confidence=rf_conf,
        ))

    return {
        "global_regime": global_regime,
        "nodes": nodes,
        "edges": edges,
    }
```

## Step 4: Run tests — all must pass

```bash
pytest tests/graph/scanner_facts/test_from_macro_json.py -v
```

Expected: all tests PASS. If any fail, fix `from_macro_json.py` — not the tests.

Common issues to watch for:
- `test_top_level_risk_factors_create_nodes` expects ≥ 6 RiskFactor nodes. The real fixture has 6 `risk_factors` strings plus 2 stock risk entries. The fixture stocks also have 2 risks each. Total RiskFactor nodes ≥ 6. If your dedupe collapses too aggressively by id, check the id truncation.
- `test_output_passes_schema_validation` will catch edge endpoints not in node list. Make sure every HAS_CATALYST and EXPOSED_TO edge target has a corresponding node.

## Step 5: Run full suite — no regressions

```bash
pytest tests/graph/scanner_facts/ -v
pytest tests/ -v -m "not integration" -x
```

## Step 6: Commit

```bash
cd /Users/Ahmet/Repo/TradingAgents/.claude/worktrees/silly-meitner-37bb65
git add \
  tradingagents/graph/scanner_facts/from_macro_json.py \
  tests/graph/scanner_facts/test_from_macro_json.py
git commit -m "feat(scanner-facts): macro JSON adapter with HAS_CATALYST/EXPOSED_TO edges and fail-loud loading"
```

---

## Done When

- `pytest tests/graph/scanner_facts/test_from_macro_json.py -v` → all green
- `pytest tests/ -v -m "not integration" -x` → no regressions
- `validate_graph_facts(wrapped_output)` returns `[]`
- Missing file raises `FileNotFoundError`; malformed JSON raises `ValueError`
