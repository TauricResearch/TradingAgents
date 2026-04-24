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
from typing import TYPE_CHECKING

from tradingagents.graph.scanner_facts.normalize import (
    ConfidenceSource,
    canonicalize_sector,
    compute_confidence,
    infer_polarity,
    is_equity_ticker,
)

if TYPE_CHECKING:
    from pathlib import Path

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
        str(theme_obj.get("conviction") or "")
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
        str(stock.get("conviction") or "")

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
