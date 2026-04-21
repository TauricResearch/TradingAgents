# Feature 4: Markdown Summary Adapter

**Parent plan:** `docs/superpowers/plans/2026-04-19-json-scanner-graph-facts.md`

**Goal:** Implement `from_markdown.py` — the adapter that parses all `*_summary.md` files in the market dir and returns partial graph facts (nodes + edges). Handles pipe-delimited rows, section splitting, quality gates, and different row shapes per section. Fails loudly on missing required inputs; skips quality-gated files with a logged warning.

**Dependencies already committed:**
- `tradingagents/graph/scanner_facts/schema.py` (F1)
- `tradingagents/graph/scanner_facts/aliases.py` (F1)
- `tradingagents/graph/scanner_facts/normalize.py` (F2)
- All fixtures under `tests/graph/scanner_facts/fixtures/` (F2)

**Files to create:**
- `tradingagents/graph/scanner_facts/from_markdown.py`
- `tests/graph/scanner_facts/test_from_markdown.py`

---

## What real summaries look like (recap)

Real sections use **both** bold-label and heading-label styles:

```text
**Candidate Rows**          ← bold style (smart_money, gatekeeper, geopolitical, industry_deep_dive)
## Candidate Rows           ← heading style (sector_summary)
```

Candidate row formats seen in real fixtures:
```text
* F | Consumer Cyclical | Insider Buying | Insider buying at $12.44 | Signaling auto/consumer cyclical sector revival.
* ON | Technology | Breakout Accumulation | Breakout accumulation at $79.93 | Supports strong technology sector alignment.
*   ON | Technology | Breakout Accumulation | $79.93 price level | Implies institutional accumulation.
- N/A         ← must be skipped (geopolitical/sector use "N/A" or "Not Applicable")
```

Sector/macro rows:
```text
- TECHNOLOGY | Positive acceleration across all timeframes | Sustained growth sector strength.
- EQUITIES (S&P 500, Nasdaq) | Reached new all-time highs | Market resilience.
- SOVEREIGN DEBT (US) | CDS spread 35.03 bps | Reduced perceived risk.
- FX (EUR/USD) | Down -0.13% at 1.18 | Eurozone uncertainties.
- SECTOR/THEME | Positive 1-Day capital inflows | Rotation into growth.
```

Risk/failure rows:
```text
* Consumer Cyclical: Insider buying may not fully offset short-term negative sector rotation.
* Technology | High valuation premiums, concentration risk | Potential for significant reversals.
```

Quality gate headers:
```text
[NO_EVIDENCE]
[QUALITY: empty]
[QUALITY: degraded]
```

---

## Step 1: Write failing tests

- [ ] Create `tests/graph/scanner_facts/test_from_markdown.py`:

```python
"""Tests for from_markdown.py — *_summary.md adapter.

Uses the real 2026-04-16 fixtures. Tests verify correct handling of:
- Section splitting (bold and heading styles)
- Candidate rows: Ticker + Sector nodes + BELONGS_TO + DRIVES_SENTIMENT
- Sector/macro rows: Sector + MarketIndex + MacroIndicator nodes + IMPACTS/DRIVES_SENTIMENT
- Risk rows: RiskFactor nodes + EXPOSED_TO edges
- Not Applicable / N/A rows: skipped
- SECTOR/THEME leader rows: skipped (no Ticker node created)
- Quality-gated files: skipped with warning
- All fixtures together: no crash, expected node types present
"""
from pathlib import Path

import pytest

from tradingagents.graph.scanner_facts.from_markdown import (
    facts_from_markdown_summary,
    facts_from_all_markdown_summaries,
    is_quality_gated,
)
from tradingagents.graph.scanner_facts.schema import validate_graph_facts

FIXTURES = Path(__file__).parent / "fixtures"


# ---- helpers ----

def _node_ids(result: dict) -> set[str]:
    return {n["id"] for n in result["nodes"]}


def _nodes_by_type(result: dict, node_type: str) -> list[dict]:
    return [n for n in result["nodes"] if n["type"] == node_type]


def _edges_by_relation(result: dict, relation: str) -> list[dict]:
    return [e for e in result["edges"] if e["relation"] == relation]


def _edge_exists(result: dict, source: str, relation: str, target: str) -> bool:
    return any(
        e["source"] == source and e["relation"] == relation and e["target"] == target
        for e in result["edges"]
    )


# ---- quality gate ----

def test_quality_gate_no_evidence():
    assert is_quality_gated("[NO_EVIDENCE] nothing found") is True


def test_quality_gate_empty():
    assert is_quality_gated("[QUALITY: empty]") is True


def test_quality_gate_degraded():
    assert is_quality_gated("[QUALITY: degraded] partial content") is True


def test_quality_gate_normal_content():
    assert is_quality_gated("* ON | Technology | Breakout | $79.93 | Strong.") is False


def test_quality_gate_empty_string():
    assert is_quality_gated("") is True


def test_quality_gate_whitespace_only():
    assert is_quality_gated("   \n  ") is True


# ---- smart_money_summary.md: Candidate Rows ----

def test_smart_money_on_ticker_node():
    text = (FIXTURES / "smart_money_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="smart_money_summary.md")
    assert "ON" in _node_ids(result)


def test_smart_money_all_tickers_present():
    text = (FIXTURES / "smart_money_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="smart_money_summary.md")
    ids = _node_ids(result)
    for ticker in ("F", "PBR", "OWL", "ABT", "JBLU", "ON", "QBTS"):
        assert ticker in ids, f"{ticker} not found in nodes: {ids}"


def test_smart_money_belongs_to_edges():
    text = (FIXTURES / "smart_money_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="smart_money_summary.md")
    assert _edge_exists(result, "ON", "BELONGS_TO", "Technology")
    assert _edge_exists(result, "F", "BELONGS_TO", "Consumer Discretionary")
    assert _edge_exists(result, "ABT", "BELONGS_TO", "Health Care")


def test_smart_money_sector_canonicalization():
    """Consumer Cyclical → Consumer Discretionary; Financial → Financials; Healthcare → Health Care."""
    text = (FIXTURES / "smart_money_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="smart_money_summary.md")
    ids = _node_ids(result)
    assert "Consumer Discretionary" in ids, f"Expected Consumer Discretionary, got {ids}"
    assert "Financials" in ids, f"Expected Financials, got {ids}"
    assert "Health Care" in ids, f"Expected Health Care, got {ids}"
    assert "Consumer Cyclical" not in ids
    assert "Financial" not in ids
    assert "Healthcare" not in ids


def test_smart_money_drives_sentiment_bullish_on():
    text = (FIXTURES / "smart_money_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="smart_money_summary.md")
    ds_edges = _edges_by_relation(result, "DRIVES_SENTIMENT")
    on_bullish = [e for e in ds_edges if e["source"] == "ON" and e["polarity"] == "bullish"]
    assert on_bullish, "ON should have a bullish DRIVES_SENTIMENT edge"


def test_smart_money_risk_section_creates_risk_factor_nodes():
    text = (FIXTURES / "smart_money_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="smart_money_summary.md")
    rf_nodes = _nodes_by_type(result, "RiskFactor")
    assert len(rf_nodes) >= 1, "Expected RiskFactor nodes from Risk / Failure Modes"


# ---- gatekeeper_summary.md: Candidate Rows ----

def test_gatekeeper_nvda_aapl_msft_present():
    text = (FIXTURES / "gatekeeper_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="gatekeeper_summary.md")
    ids = _node_ids(result)
    for ticker in ("NVDA", "AAPL", "MSFT", "AMZN", "TSLA", "AMD", "ORCL", "NFLX", "PLTR"):
        assert ticker in ids, f"{ticker} not found"


def test_gatekeeper_telecom_canonicalized():
    """T is listed under 'Telecommunications' — must canonicalize to 'Communication Services'."""
    text = (FIXTURES / "gatekeeper_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="gatekeeper_summary.md")
    ids = _node_ids(result)
    assert "Communication Services" in ids, f"Expected Communication Services, got {ids}"
    assert "Telecommunications" not in ids


def test_gatekeeper_nflx_belongs_to_communication_services():
    text = (FIXTURES / "gatekeeper_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="gatekeeper_summary.md")
    assert _edge_exists(result, "NFLX", "BELONGS_TO", "Communication Services")


# ---- geopolitical_summary.md: Not Applicable rows ----

def test_geopolitical_not_applicable_rows_produce_no_ticker_nodes():
    text = (FIXTURES / "geopolitical_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="geopolitical_summary.md")
    ticker_nodes = _nodes_by_type(result, "Ticker")
    assert ticker_nodes == [], f"Geopolitical adapter should produce no Ticker nodes, got: {ticker_nodes}"


def test_geopolitical_sector_macro_rows_produce_nodes():
    text = (FIXTURES / "geopolitical_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="geopolitical_summary.md")
    ids = _node_ids(result)
    # EQUITIES (S&P 500, Nasdaq), SOVEREIGN DEBT, FX rows should produce some nodes
    assert len(ids) > 0, "Geopolitical summary should produce non-empty nodes"


def test_geopolitical_fx_nodes_classified_correctly():
    text = (FIXTURES / "geopolitical_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="geopolitical_summary.md")
    fx_nodes = _nodes_by_type(result, "CurrencyPair")
    # EUR/USD, JPY/USD, CNY/USD appear in Sector/Macro section
    assert len(fx_nodes) >= 1, f"Expected CurrencyPair nodes, got: {_node_ids(result)}"


# ---- sector_summary.md: heading-style sections, SECTOR/THEME rows ----

def test_sector_summary_no_candidate_ticker_rows():
    """sector_summary.md Candidate Rows section contains only '- N/A'."""
    text = (FIXTURES / "sector_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="sector_summary.md")
    ticker_nodes = _nodes_by_type(result, "Ticker")
    assert ticker_nodes == [], f"Sector summary should produce no Ticker nodes, got: {ticker_nodes}"


def test_sector_summary_sector_nodes_produced():
    text = (FIXTURES / "sector_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="sector_summary.md")
    sector_nodes = _nodes_by_type(result, "Sector")
    assert len(sector_nodes) >= 4, f"Expected Sector nodes from Sector/Macro section, got: {sector_nodes}"


def test_sector_summary_sector_theme_rows_skipped():
    """SECTOR/THEME leader rows in sector_summary.md should not create Ticker nodes."""
    text = (FIXTURES / "sector_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="sector_summary.md")
    assert "SECTOR/THEME" not in _node_ids(result)


def test_sector_summary_technology_canonicalized_from_upper():
    """'TECHNOLOGY' in sector_summary.md should become 'Technology'."""
    text = (FIXTURES / "sector_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="sector_summary.md")
    assert "Technology" in _node_ids(result)


# ---- industry_deep_dive_summary.md ----

def test_industry_deep_dive_tickers_present():
    text = (FIXTURES / "industry_deep_dive_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="industry_deep_dive_summary.md")
    ids = _node_ids(result)
    for ticker in ("ON", "AMD", "INTC", "AVGO", "MSFT", "DLR", "EQIX", "CBRE", "PLD"):
        assert ticker in ids, f"{ticker} not in {ids}"


def test_industry_deep_dive_consumer_defensive_canonicalized():
    """'Consumer Defensive' in industry_deep_dive → 'Consumer Staples'."""
    text = (FIXTURES / "industry_deep_dive_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="industry_deep_dive_summary.md")
    ids = _node_ids(result)
    assert "Consumer Staples" in ids, f"Expected Consumer Staples, got {ids}"


def test_industry_deep_dive_risk_factor_for_technology():
    text = (FIXTURES / "industry_deep_dive_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="industry_deep_dive_summary.md")
    # Risk / Failure Modes: "Technology | High valuation premiums, concentration risk | ..."
    et_edges = _edges_by_relation(result, "EXPOSED_TO")
    assert any("Technology" in e["source"] or "Technology" in e["target"]
               for e in et_edges), f"Expected Technology EXPOSED_TO edge, got: {et_edges}"


# ---- market_movers_summary.md ----

def test_market_movers_no_ticker_nodes():
    text = (FIXTURES / "market_movers_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="market_movers_summary.md")
    ticker_nodes = _nodes_by_type(result, "Ticker")
    assert ticker_nodes == [], f"Market movers should have no Ticker nodes, got: {ticker_nodes}"


def test_market_movers_sp500_classified_as_market_index():
    text = (FIXTURES / "market_movers_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="market_movers_summary.md")
    index_nodes = _nodes_by_type(result, "MarketIndex")
    assert any("S&P 500" in n["id"] or "500" in n["id"] for n in index_nodes), (
        f"S&P 500 not found in MarketIndex nodes: {[n['id'] for n in index_nodes]}"
    )


def test_market_movers_vix_classified_as_macro_indicator():
    text = (FIXTURES / "market_movers_summary.md").read_text()
    result = facts_from_markdown_summary(text, source="market_movers_summary.md")
    macro_nodes = _nodes_by_type(result, "MacroIndicator")
    assert any("VIX" in n["id"] for n in macro_nodes), (
        f"VIX not in MacroIndicator nodes: {[n['id'] for n in macro_nodes]}"
    )


# ---- quality gating ----

def test_quality_gated_text_returns_empty_facts():
    result = facts_from_markdown_summary(
        "[NO_EVIDENCE] nothing qualified", source="test_summary.md"
    )
    assert result["nodes"] == []
    assert result["edges"] == []


def test_quality_degraded_returns_empty_facts():
    result = facts_from_markdown_summary(
        "[QUALITY: degraded] some partial content", source="test_summary.md"
    )
    assert result["nodes"] == []
    assert result["edges"] == []


# ---- facts_from_all_markdown_summaries ----

def test_all_summaries_combined_ticker_count():
    result = facts_from_all_markdown_summaries(FIXTURES)
    ticker_nodes = _nodes_by_type(result, "Ticker")
    # Across all fixtures: F, PBR, OWL, ABT, JBLU, ON, QBTS, NVDA, AAPL, MSFT, AMZN, TSLA...
    assert len(ticker_nodes) >= 10, f"Expected ≥10 tickers, got {len(ticker_nodes)}"


def test_all_summaries_combined_no_crash():
    result = facts_from_all_markdown_summaries(FIXTURES)
    assert "nodes" in result
    assert "edges" in result


def test_all_summaries_schema_valid():
    result = facts_from_all_markdown_summaries(FIXTURES)
    facts = {
        "schema_version": "scanner_graph_facts.v1",
        "scan_date": "2026-04-16",
        "run_id": "test-run",
        "source_dir": "test",
        "global_regime": {"summary": "", "bullets": [], "source": "test"},
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
    assert errors == [], f"Schema errors: {errors}"


def test_all_summaries_on_present_from_multiple_sources():
    """ON appears in smart_money AND industry_deep_dive — should be in merged nodes once."""
    result = facts_from_all_markdown_summaries(FIXTURES)
    on_nodes = [n for n in result["nodes"] if n["id"] == "ON"]
    assert len(on_nodes) == 1, f"ON should appear exactly once, got {len(on_nodes)}"
    # But provenance should contain both sources
    if on_nodes:
        provenance_str = str(on_nodes[0]["provenance"])
        assert "smart_money" in provenance_str or "industry_deep_dive" in provenance_str


def test_all_summaries_confidence_range():
    result = facts_from_all_markdown_summaries(FIXTURES)
    for node in result["nodes"]:
        assert 0.10 <= node["confidence"] <= 0.99, f"Node {node['id']} confidence out of range"
    for edge in result["edges"]:
        assert 0.10 <= edge["confidence"] <= 0.99, f"Edge {edge} confidence out of range"
```

## Step 2: Run failing tests

```bash
cd /Users/Ahmet/Repo/TradingAgents/.claude/worktrees/silly-meitner-37bb65
conda activate tradingagents
pytest tests/graph/scanner_facts/test_from_markdown.py -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError: No module named 'tradingagents.graph.scanner_facts.from_markdown'`

## Step 3: Implement `from_markdown.py`

- [ ] Create `tradingagents/graph/scanner_facts/from_markdown.py`:

```python
"""Adapter: *_summary.md files → partial ScannerGraphFacts dict.

Parses structured sections from scanner Markdown summaries:
  - Candidate Rows  → Ticker + Sector nodes + BELONGS_TO + DRIVES_SENTIMENT edges
  - Sector / Macro  → Sector/Index/Macro/FX/Crypto nodes + IMPACTS/DRIVES_SENTIMENT edges
  - Risk / Failure  → RiskFactor nodes + EXPOSED_TO edges
  - Dates and Exact Numbers → evidence enrichment only (no new nodes)

Quality-gated files ([NO_EVIDENCE], [QUALITY: empty], [QUALITY: degraded]) return empty output.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from tradingagents.graph.scanner_facts.normalize import (
    ConfidenceSource,
    canonicalize_sector,
    classify_node_type,
    compute_confidence,
    infer_polarity,
    is_equity_ticker,
)

_logger = logging.getLogger(__name__)

_QUALITY_MARKERS = ("[NO_EVIDENCE]", "[QUALITY: empty]", "[QUALITY: degraded]")

# Section header patterns — support both bold and heading styles
_SECTION_RE = re.compile(
    r"(?:^#{1,3}\s*|^\*\*)(Candidate Rows|Sector\s*/\s*Macro Implication|"
    r"Dates and Exact Numbers|Risk\s*/\s*Failure Modes)\*?\*?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Pipe-row bullet pattern
_PIPE_ROW_RE = re.compile(r"^\s*[*-]\s+(.+\|.+)", re.MULTILINE)

# Known summary filenames — used by facts_from_all_markdown_summaries
_SUMMARY_FILES = (
    "smart_money_summary.md",
    "gatekeeper_summary.md",
    "geopolitical_summary.md",
    "industry_deep_dive_summary.md",
    "sector_summary.md",
    "market_movers_summary.md",
    "factor_alignment_summary.md",
    "drift_opportunities_summary.md",
)


# ---------- quality gate ----------

def is_quality_gated(text: str) -> bool:
    if not text or not text.strip():
        return True
    head = text.strip()[:200]
    return any(marker in head for marker in _QUALITY_MARKERS)


# ---------- section splitting ----------

def _split_sections(text: str) -> dict[str, str]:
    """Return a dict of section_name → section_body."""
    sections: dict[str, str] = {}
    matches = list(_SECTION_RE.finditer(text))
    for i, match in enumerate(matches):
        section_name = match.group(1).strip().lower()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[section_name] = text[start:end].strip()
    return sections


# ---------- pipe row parsing ----------

def _parse_pipe_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for match in _PIPE_ROW_RE.finditer(text):
        cols = [c.strip() for c in match.group(1).split("|")]
        if len(cols) >= 2:
            rows.append(cols)
    return rows


# ---------- node/edge construction ----------

def _make_node(
    node_id: str, node_type: str, label: str,
    provenance: str, evidence: list[str], confidence: float,
) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "label": label,
        "aliases": [],
        "provenance": [provenance],
        "evidence": evidence,
        "confidence": round(confidence, 4),
    }


def _make_edge(
    source: str, relation: str, target: str,
    provenance: str, evidence: str, confidence: float, polarity: str = "",
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


# ---------- Candidate Rows handler ----------

def _process_candidate_rows(
    section_text: str, source: str,
    nodes: list, edges: list, node_ids: set,
) -> None:
    for cols in _parse_pipe_rows(section_text):
        first = cols[0].strip()

        # Skip N/A and Not Applicable rows
        if first.upper() in ("N/A", "NOT APPLICABLE", "SECTOR/THEME"):
            continue

        # Detect equity ticker (1–5 uppercase chars)
        if is_equity_ticker(first):
            _process_ticker_row(first, cols, source, nodes, edges, node_ids)
        else:
            # Non-ticker first column — treat as sector/macro row
            _process_sector_macro_row(cols, source, nodes, edges, node_ids)


def _process_ticker_row(
    ticker: str, cols: list[str], source: str,
    nodes: list, edges: list, node_ids: set,
) -> None:
    sector_raw = cols[1].strip() if len(cols) >= 2 else ""
    signal = cols[2].strip() if len(cols) >= 3 else ""
    evidence_text = cols[3].strip() if len(cols) >= 4 else ""
    implication = cols[4].strip() if len(cols) >= 5 else ""

    is_full = len(cols) >= 5 and evidence_text
    is_partial = len(cols) >= 3 and not is_full

    src = ConfidenceSource.MD_PIPE_FULL if is_full else ConfidenceSource.MD_PIPE_PARTIAL
    hedging = any(w in implication.lower() for w in ("may", "could", "potential", "if", "uncertain"))
    polarity = infer_polarity(signal, evidence_text, implication)
    conf = compute_confidence(src, hedging=hedging, polarity_empty=(polarity == ""))

    raw_evidence = " | ".join(c for c in cols if c)
    sector = canonicalize_sector(sector_raw) if sector_raw else ""

    # Ticker node
    if ticker not in node_ids:
        node_ids.add(ticker)
        nodes.append(_make_node(
            ticker, "Ticker", ticker, source,
            [evidence_text or raw_evidence], conf,
        ))

    # Sector node
    if sector:
        if sector not in node_ids:
            node_ids.add(sector)
            nodes.append(_make_node(
                sector, "Sector", sector, source, [], conf,
            ))
        # BELONGS_TO
        edges.append(_make_edge(
            ticker, "BELONGS_TO", sector, source,
            raw_evidence, conf,
        ))
        # DRIVES_SENTIMENT (when signal/implication has clear polarity)
        if polarity:
            edges.append(_make_edge(
                ticker, "DRIVES_SENTIMENT", sector, source,
                raw_evidence, conf, polarity,
            ))


# ---------- Sector / Macro Implication handler ----------

_STRIP_PARENS_RE = re.compile(r"\s*\([^)]*\)")
_FX_LABEL_RE = re.compile(r"FX\s*\(([^)]+)\)", re.IGNORECASE)
_DEBT_LABEL_RE = re.compile(r"SOVEREIGN DEBT\s*\(([^)]+)\)", re.IGNORECASE)


def _clean_leader(raw: str) -> str:
    """Strip parenthetical notes to get a clean label, e.g. 'EQUITIES (S&P 500)' → 'EQUITIES'."""
    return _STRIP_PARENS_RE.sub("", raw).strip()


def _process_sector_macro_row(
    cols: list[str], source: str,
    nodes: list, edges: list, node_ids: set,
) -> None:
    leader = cols[0].strip()

    if leader.upper() in ("N/A", "NOT APPLICABLE", "SECTOR/THEME"):
        return

    evidence_text = cols[1].strip() if len(cols) >= 2 else ""
    implication = cols[2].strip() if len(cols) >= 3 else ""

    # Handle FX (...) labels → extract pair
    fx_match = _FX_LABEL_RE.match(leader)
    if fx_match:
        pair = fx_match.group(1).strip()
        node_type = classify_node_type(pair)
        if node_type == "CurrencyPair" or "/" in pair:
            _emit_macro_node(pair, "CurrencyPair", pair, source, evidence_text, implication, nodes, edges, node_ids)
        return

    # Handle SOVEREIGN DEBT (...) → MacroIndicator
    debt_match = _DEBT_LABEL_RE.match(leader)
    if debt_match:
        country = debt_match.group(1).strip()
        node_id = f"{country} CDS"
        _emit_macro_node(node_id, "MacroIndicator", node_id, source, evidence_text, implication, nodes, edges, node_ids)
        return

    # Clean leader from parens and classify
    clean = _clean_leader(leader)
    # Try upper-case sector name → canonicalize
    maybe_sector = canonicalize_sector(clean.title())
    if maybe_sector != clean.title() or clean.upper() == clean:
        # It was a known sector alias or an uppercase sector name
        canonical = canonicalize_sector(clean.title())
        node_type = classify_node_type(canonical)
        label = canonical
    else:
        node_type = classify_node_type(clean)
        label = clean

    # Skip SECTOR/THEME placeholders
    if label.upper() in ("SECTOR/THEME", "SECTOR", "THEME"):
        return

    _emit_macro_node(label, node_type, label, source, evidence_text, implication, nodes, edges, node_ids)


def _emit_macro_node(
    node_id: str, node_type: str, label: str, source: str,
    evidence_text: str, implication: str,
    nodes: list, edges: list, node_ids: set,
) -> None:
    polarity = infer_polarity(evidence_text, implication)
    hedging = any(w in implication.lower() for w in ("may", "could", "potential", "if"))
    conf = compute_confidence(
        ConfidenceSource.MD_PIPE_PARTIAL,
        hedging=hedging,
        polarity_empty=(polarity == ""),
    )
    if node_id not in node_ids:
        node_ids.add(node_id)
        nodes.append(_make_node(
            node_id, node_type, label, source,
            [evidence_text] if evidence_text else [], conf,
        ))


# ---------- Risk / Failure Modes handler ----------

_RISK_PIPE_RE = re.compile(r"^\s*[*-]\s+(.+\|.+)", re.MULTILINE)
_RISK_COLON_RE = re.compile(r"^\s*[*-]\s+([^:]+):\s+(.+)", re.MULTILINE)


def _process_risk_section(
    section_text: str, source: str,
    nodes: list, edges: list, node_ids: set,
) -> None:
    # Try pipe rows first
    for cols in _parse_pipe_rows(section_text):
        subject_raw = cols[0].strip()
        risk_desc = cols[1].strip() if len(cols) >= 2 else ""
        implication = cols[2].strip() if len(cols) >= 3 else ""
        if not subject_raw or not risk_desc:
            continue

        # Subject may be a sector or ticker
        sector = canonicalize_sector(subject_raw.title())
        if is_equity_ticker(subject_raw):
            subject = subject_raw
            subject_type = "Ticker"
        else:
            subject = sector
            subject_type = "Sector"

        rf_id = (risk_desc + " " + implication)[:80].strip()
        if not rf_id:
            continue

        conf = compute_confidence(
            ConfidenceSource.MD_PIPE_PARTIAL,
            hedging=any(w in implication.lower() for w in ("may", "could", "potential")),
        )

        if subject not in node_ids:
            node_ids.add(subject)
            nodes.append(_make_node(subject, subject_type, subject, source, [], conf))

        if rf_id not in node_ids:
            node_ids.add(rf_id)
            nodes.append(_make_node(rf_id, "RiskFactor", rf_id, source, [risk_desc], conf))

        edges.append(_make_edge(
            subject, "EXPOSED_TO", rf_id, source,
            " | ".join(cols), conf, "bearish",
        ))

    # Colon-style: "Consumer Cyclical: Insider buying may not fully offset..."
    for match in _RISK_COLON_RE.finditer(section_text):
        subject_raw = match.group(1).strip()
        desc = match.group(2).strip()
        if not subject_raw or not desc:
            continue

        sector = canonicalize_sector(subject_raw.title())
        subject = subject_raw if is_equity_ticker(subject_raw) else sector
        subject_type = "Ticker" if is_equity_ticker(subject_raw) else "Sector"
        rf_id = desc[:80]

        conf = compute_confidence(
            ConfidenceSource.MD_FREE_BULLET,
            hedging=any(w in desc.lower() for w in ("may", "could", "potential")),
        )

        if subject not in node_ids:
            node_ids.add(subject)
            nodes.append(_make_node(subject, subject_type, subject, source, [], conf))

        if rf_id not in node_ids:
            node_ids.add(rf_id)
            nodes.append(_make_node(rf_id, "RiskFactor", rf_id, source, [desc], conf))

        edges.append(_make_edge(
            subject, "EXPOSED_TO", rf_id, source, desc, conf, "bearish",
        ))


# ---------- merge helpers ----------

def _merge_into(
    target_nodes: list, target_edges: list, target_ids: set,
    source_nodes: list, source_edges: list,
) -> None:
    """Merge source nodes/edges into target, deduping by id / (src, rel, tgt, prov)."""
    for node in source_nodes:
        nid = node["id"]
        if nid not in target_ids:
            target_ids.add(nid)
            target_nodes.append(node)
        else:
            # Merge provenance + evidence into existing node
            existing = next(n for n in target_nodes if n["id"] == nid)
            for p in node["provenance"]:
                if p not in existing["provenance"]:
                    existing["provenance"].append(p)
            for e in node["evidence"]:
                if e not in existing["evidence"]:
                    existing["evidence"].append(e)
            existing["confidence"] = max(existing["confidence"], node["confidence"])

    seen_edges = {
        (e["source"], e["relation"], e["target"], e["provenance"])
        for e in target_edges
    }
    for edge in source_edges:
        key = (edge["source"], edge["relation"], edge["target"], edge["provenance"])
        if key not in seen_edges:
            seen_edges.add(key)
            target_edges.append(edge)


# ---------- public API ----------

def facts_from_markdown_summary(text: str, *, source: str) -> dict:
    """Parse a single *_summary.md text and return partial graph facts.

    Returns:
        {"nodes": [...], "edges": [...]}
    """
    if is_quality_gated(text):
        _logger.info("from_markdown: %s is quality-gated — skipping", source)
        return {"nodes": [], "edges": []}

    nodes: list[dict] = []
    edges: list[dict] = []
    node_ids: set[str] = set()

    sections = _split_sections(text)

    # Candidate Rows
    candidate_body = sections.get("candidate rows", "")
    if candidate_body:
        _process_candidate_rows(candidate_body, source, nodes, edges, node_ids)

    # Sector / Macro Implication
    sector_body = sections.get("sector / macro implication", "")
    if sector_body:
        for cols in _parse_pipe_rows(sector_body):
            _process_sector_macro_row(cols, source, nodes, edges, node_ids)

    # Risk / Failure Modes
    risk_body = sections.get("risk / failure modes", "")
    if risk_body:
        _process_risk_section(risk_body, source, nodes, edges, node_ids)

    # Dates and Exact Numbers — do not create nodes; skip
    return {"nodes": nodes, "edges": edges}


def facts_from_all_markdown_summaries(market_dir: Path) -> dict:
    """Parse all *_summary.md files in *market_dir* and merge into one partial facts dict.

    Skips quality-gated files (logs a warning per file). Does not raise on missing files.
    """
    nodes: list[dict] = []
    edges: list[dict] = []
    node_ids: set[str] = set()

    for filename in _SUMMARY_FILES:
        path = market_dir / filename
        if not path.exists():
            _logger.debug("from_markdown: %s not found — skipping", filename)
            continue
        text = path.read_text(encoding="utf-8")
        if is_quality_gated(text):
            _logger.warning("from_markdown: %s is quality-gated — skipping", filename)
            continue
        result = facts_from_markdown_summary(text, source=filename)
        _merge_into(nodes, edges, node_ids, result["nodes"], result["edges"])

    return {"nodes": nodes, "edges": edges}
```

## Step 4: Run all tests — fix failures in `from_markdown.py`

```bash
pytest tests/graph/scanner_facts/test_from_markdown.py -v
```

Expected: all tests PASS. Common issues:
- `test_smart_money_belongs_to_edges`: `ABT | Healthcare | ...` → `canonicalize_sector("Healthcare")` must return `"Health Care"`. Verify `normalize.py` has this mapping (it was added in F2).
- `test_geopolitical_fx_nodes_classified_correctly`: Section header must match `_SECTION_RE`. If the geopolitical fixture uses `**Sector / Macro Implication**` bold style, verify the regex captures it. The regex covers both styles — check spacing.
- `test_sector_summary_sector_nodes_produced`: `sector_summary.md` uses `## Candidate Rows` heading style. The regex must match.
- `test_all_summaries_on_present_from_multiple_sources`: ON appears in `smart_money_summary.md` and `industry_deep_dive_summary.md`. Merge should keep one node with combined provenance.

If a test fails due to missing canonicalization, add the mapping to `normalize.py` (not to `from_markdown.py`).

## Step 5: Run full suite

```bash
pytest tests/graph/scanner_facts/ -v
pytest tests/ -v -m "not integration" -x
```

## Step 6: Commit

```bash
cd /Users/Ahmet/Repo/TradingAgents/.claude/worktrees/silly-meitner-37bb65
git add \
  tradingagents/graph/scanner_facts/from_markdown.py \
  tests/graph/scanner_facts/test_from_markdown.py
git commit -m "feat(scanner-facts): markdown adapter with real fixture integration tests"
```

---

## Done When

- `pytest tests/graph/scanner_facts/test_from_markdown.py -v` → all green
- `pytest tests/ -v -m "not integration" -x` → no regressions
- `ON` node appears exactly once across merged summaries with provenance from both source files
- Sector/macro rows produce row-level relationships; macro/index/commodity/FX-style rows must emit `IMPACTS` edges to a derived Theme target instead of remaining standalone nodes
- `validate_graph_facts(wrapped)` returns `[]` on merged output
- Quality-gated text returns empty nodes/edges
