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
from typing import TYPE_CHECKING

from tradingagents.graph.scanner_facts.normalize import (
    ConfidenceSource,
    canonicalize_sector,
    classify_node_type,
    compute_confidence,
    infer_polarity,
    is_equity_ticker,
)

if TYPE_CHECKING:
    from pathlib import Path

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
    len(cols) >= 3 and not is_full

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

    # Try to canonicalize as sector (using title case)
    titled = clean.title()
    canonical = canonicalize_sector(titled)

    # If it's a canonical sector, use it; otherwise use original clean label
    if canonical in {s for s in {
        "Technology", "Financials", "Consumer Discretionary", "Consumer Staples",
        "Health Care", "Communication Services", "Industrials", "Materials",
        "Real Estate", "Utilities", "Energy"
    }}:
        label = canonical
        node_type = "Sector"
    else:
        # Not a canonical sector; classify by type using clean label
        label = clean
        node_type = classify_node_type(clean)

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

    _emit_macro_relation(
        node_id, node_type, source, evidence_text, implication, nodes, edges, node_ids
    )


def _theme_label_from_row(evidence_text: str, implication: str) -> str:
    """Derive a compact Theme label from a sector/macro row."""
    for candidate in (implication, evidence_text):
        cleaned = " ".join((candidate or "").strip().split())
        if cleaned:
            return cleaned[:80]
    return ""


def _emit_macro_relation(
    node_id: str, node_type: str, source: str,
    evidence_text: str, implication: str,
    nodes: list, edges: list, node_ids: set,
) -> None:
    """Emit the row-level relationship required by the Sector/Macro contract."""
    target = _theme_label_from_row(evidence_text, implication)
    if not target or target == node_id:
        return

    polarity = infer_polarity(node_id, evidence_text, implication)
    hedging = any(w in (evidence_text + " " + implication).lower()
                  for w in ("may", "could", "potential", "if", "uncertain"))
    conf = compute_confidence(
        ConfidenceSource.INFERRED_EDGE,
        hedging=hedging,
        polarity_empty=(polarity == ""),
    )

    if target not in node_ids:
        node_ids.add(target)
        nodes.append(_make_node(
            target, "Theme", target, source,
            [implication or evidence_text], conf,
        ))

    relation = "DRIVES_SENTIMENT" if node_type == "Sector" else "IMPACTS"
    edges.append(_make_edge(
        node_id,
        relation,
        target,
        source,
        " | ".join(p for p in (node_id, evidence_text, implication) if p),
        conf,
        polarity,
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

        # Subject may be a sector, ticker, or other node
        if is_equity_ticker(subject_raw):
            subject = subject_raw
            subject_type = "Ticker"
        else:
            # Try to canonicalize as sector; if unchanged, classify generically
            sector = canonicalize_sector(subject_raw.title())
            if sector == subject_raw.title():
                # Not a known sector alias; classify by type
                subject_type = classify_node_type(subject_raw)
                subject = subject_raw
            else:
                # Known sector alias
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

        if is_equity_ticker(subject_raw):
            subject = subject_raw
            subject_type = "Ticker"
        else:
            # Try to canonicalize as sector; if unchanged, classify generically
            sector = canonicalize_sector(subject_raw.title())
            if sector == subject_raw.title():
                # Not a known sector alias; classify by type
                subject_type = classify_node_type(subject_raw)
                subject = subject_raw
            else:
                # Known sector alias
                subject = sector
                subject_type = "Sector"

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
