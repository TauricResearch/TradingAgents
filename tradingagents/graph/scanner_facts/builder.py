"""Builder: merge adapter outputs → validate → save/load immutable artifact.

Immutability invariant:
  save_scanner_graph_facts(..., overwrite=False) is the only path used in normal
  execution. overwrite=True is reserved for rebuild.py exclusively.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from tradingagents.graph.scanner_facts.from_macro_json import (
    facts_from_macro_scan_summary,
    load_and_parse_macro_scan_summary,
)
from tradingagents.graph.scanner_facts.from_markdown import facts_from_all_markdown_summaries
from tradingagents.graph.scanner_facts.schema import SCHEMA_VERSION, validate_graph_facts
from tradingagents.report_paths import get_market_dir, get_scanner_graph_facts_path

_logger = logging.getLogger(__name__)


# ---------- internal path helpers (monkeypatched in tests) ----------

def _resolve_market_dir(scan_date: str, run_id: str) -> Path:
    return get_market_dir(scan_date, run_id)


def _resolve_artifact_path(scan_date: str, run_id: str) -> Path:
    return get_scanner_graph_facts_path(scan_date, run_id)


# ---------- merge ----------

def _merge_partial_facts(partials: list[dict]) -> dict:
    """Merge a list of partial {nodes, edges} dicts into one."""
    nodes: list[dict] = []
    edges: list[dict] = []
    # node key: (type, id)
    node_index: dict[tuple[str, str], int] = {}
    # edge key: (source, relation, target, provenance)
    edge_index: dict[tuple[str, str, str, str], int] = {}

    for partial in partials:
        for node in partial.get("nodes", []):
            key = (node["type"], node["id"])
            if key in node_index:
                existing = nodes[node_index[key]]
                # merge provenance
                for p in node.get("provenance", []):
                    if p not in existing["provenance"]:
                        existing["provenance"].append(p)
                # merge evidence
                for e in node.get("evidence", []):
                    if e not in existing["evidence"]:
                        existing["evidence"].append(e)
                # keep max confidence
                existing["confidence"] = max(existing["confidence"], node["confidence"])
                # merge aliases
                for a in node.get("aliases", []):
                    if a not in existing["aliases"]:
                        existing["aliases"].append(a)
            else:
                node_index[key] = len(nodes)
                nodes.append(dict(node))

        for edge in partial.get("edges", []):
            key = (edge["source"], edge["relation"], edge["target"], edge["provenance"])
            if key in edge_index:
                existing = edges[edge_index[key]]
                # keep highest confidence
                if edge["confidence"] > existing["confidence"]:
                    edges[edge_index[key]] = dict(edge)
            else:
                edge_index[key] = len(edges)
                edges.append(dict(edge))

    return {"nodes": nodes, "edges": edges}


# ---------- build ----------

def build_scanner_graph_facts_from_market_dir(
    market_dir: Path,
    *,
    scan_date: str,
    run_id: str,
) -> dict:
    """Build a complete ScannerGraphFacts dict from a market report directory.

    Raises:
        FileNotFoundError: if macro_scan_summary.json is missing.
        ValueError: if macro_scan_summary.json is malformed JSON.
        ValueError: if graph validation fails after build.
    """
    # Macro JSON (required — fail loudly)
    macro_path = market_dir / "macro_scan_summary.json"
    payload = load_and_parse_macro_scan_summary(macro_path)
    macro_partial = facts_from_macro_scan_summary(
        payload, scan_date=scan_date, run_id=run_id
    )

    # Markdown summaries (optional files — quality-gated ones are skipped)
    md_partial = facts_from_all_markdown_summaries(market_dir)

    # Merge
    merged = _merge_partial_facts([macro_partial, md_partial])

    # Validate
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    inputs = ["macro_scan_summary.json"]
    for fname in market_dir.iterdir():
        if fname.suffix == ".md" and fname.stem.endswith("_summary"):
            inputs.append(fname.name)
    inputs.sort()

    facts: dict = {
        "schema_version": SCHEMA_VERSION,
        "scan_date": scan_date,
        "run_id": run_id,
        "source_dir": str(market_dir),
        "global_regime": macro_partial.get("global_regime", {
            "summary": "", "bullets": [], "source": "macro_scan_summary.json"
        }),
        "nodes": merged["nodes"],
        "edges": merged["edges"],
        "metadata": {
            "node_count": len(merged["nodes"]),
            "edge_count": len(merged["edges"]),
            "generated_at": generated_at,
            "inputs": inputs,
        },
    }

    errors = validate_graph_facts(facts)
    if errors:
        raise ValueError(
            f"Built scanner graph facts failed validation ({len(errors)} errors): "
            + "; ".join(errors[:5])
        )

    return facts


# ---------- save / load ----------

def save_scanner_graph_facts(
    facts: dict,
    path: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write facts to *path* as indented, stably-ordered JSON.

    If *path* exists and overwrite=False, returns the path without writing.
    overwrite=True is reserved for rebuild.py; callers are logged.
    """
    if path.exists() and not overwrite:
        _logger.info("builder: artifact exists at %s — skipping write (immutability)", path)
        return path

    if overwrite:
        _logger.info("builder: overwrite=True requested by caller")

    path.parent.mkdir(parents=True, exist_ok=True)

    # Stable ordering: sort nodes by (type, id), edges by (source, relation, target)
    ordered = dict(facts)
    ordered["nodes"] = sorted(facts["nodes"], key=lambda n: (n["type"], n["id"]))
    ordered["edges"] = sorted(
        facts["edges"], key=lambda e: (e["source"], e["relation"], e["target"])
    )

    path.write_text(json.dumps(ordered, indent=2, ensure_ascii=False, sort_keys=False))
    _logger.info("builder: saved scanner_graph_facts to %s (%d nodes, %d edges)",
                 path, len(facts["nodes"]), len(facts["edges"]))
    return path


def load_scanner_graph_facts(path: Path) -> dict:
    """Load and return facts from *path*.

    Raises:
        FileNotFoundError: if file does not exist.
        ValueError: if file is not valid JSON.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"scanner_graph_facts.json not found at {path}. "
            "Run rebuild_scanner_graph_facts() to generate it."
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"scanner_graph_facts.json at {path} is not valid JSON: {exc}") from exc


# ---------- ensure ----------

def ensure_scanner_graph_facts(
    *,
    scan_date: str,
    run_id: str,
    overwrite: bool = False,
) -> Path:
    """Return path to the artifact, building it first if missing.

    In normal execution overwrite=False: existing artifact is always returned as-is.
    """
    artifact_path = _resolve_artifact_path(scan_date, run_id)

    if artifact_path.exists() and not overwrite:
        _logger.info("builder: artifact already exists at %s", artifact_path)
        return artifact_path

    market_dir = _resolve_market_dir(scan_date, run_id)
    facts = build_scanner_graph_facts_from_market_dir(
        market_dir, scan_date=scan_date, run_id=run_id
    )
    save_scanner_graph_facts(facts, artifact_path, overwrite=overwrite)
    return artifact_path
