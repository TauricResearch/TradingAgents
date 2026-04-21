"""Historical rebuild utility for scanner_graph_facts.json artifacts.

This is the ONLY code path authorised to call
save_scanner_graph_facts(..., overwrite=True).

CLI usage:
    python -m tradingagents.graph.scanner_facts.rebuild \
        --date 2026-04-16 \
        --run-id 01KPBZ79XBDWWYSXVZF0APEYPW \
        [--reports-root /path/to/reports] \
        [--no-overwrite]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from tradingagents.graph.scanner_facts.builder import (
    _merge_partial_facts,
    save_scanner_graph_facts,
    load_scanner_graph_facts,
)
from tradingagents.graph.scanner_facts.from_markdown import facts_from_all_markdown_summaries
from tradingagents.graph.scanner_facts.schema import SCHEMA_VERSION, validate_graph_facts
from tradingagents.report_paths import REPORTS_ROOT, get_scanner_graph_facts_path

_logger = logging.getLogger(__name__)


def _has_usable_markdown(market_dir: Path) -> bool:
    """Return True if at least one non-quality-gated *_summary.md exists."""
    from tradingagents.graph.scanner_facts.from_markdown import is_quality_gated
    for f in market_dir.glob("*_summary.md"):
        text = f.read_text(encoding="utf-8")
        if not is_quality_gated(text):
            return True
    return False


def _build_from_markdown_only(
    market_dir: Path,
    *,
    scan_date: str,
    run_id: str,
) -> dict:
    """Build facts from Markdown summaries only (degraded fallback: macro JSON malformed)."""
    md_partial = facts_from_all_markdown_summaries(market_dir)
    merged = _merge_partial_facts([md_partial])

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    inputs = sorted(f.name for f in market_dir.glob("*_summary.md"))

    facts: dict = {
        "schema_version": SCHEMA_VERSION,
        "scan_date": scan_date,
        "run_id": run_id,
        "source_dir": str(market_dir),
        "global_regime": {
            "summary": "",
            "bullets": [],
            "source": "markdown_summaries_only",
        },
        "nodes": merged["nodes"],
        "edges": merged["edges"],
        "metadata": {
            "node_count": len(merged["nodes"]),
            "edge_count": len(merged["edges"]),
            "generated_at": generated_at,
            "inputs": inputs,
            "degraded_source": "macro_json_malformed",
        },
    }

    errors = validate_graph_facts(facts)
    if errors:
        raise ValueError(
            f"Degraded build failed validation ({len(errors)} errors): "
            + "; ".join(errors[:5])
        )
    return facts


def rebuild_scanner_graph_facts(
    scan_date: str,
    run_id: str,
    reports_root: Path | None = None,
    *,
    overwrite: bool = True,
) -> Path:
    """Rebuild the scanner_graph_facts.json artifact for the given scan_date + run_id.

    Args:
        scan_date:    ISO date string (e.g. "2026-04-16").
        run_id:       Run identifier.
        reports_root: Override the default REPORTS_ROOT (useful for tests).
        overwrite:    Default True — rebuild always overwrites. Set False to skip
                      if the artifact already exists.

    Returns:
        Path to the (re)built artifact.

    Raises:
        FileNotFoundError: market dir or macro_scan_summary.json missing with no MD fallback.
        ValueError: JSON malformed AND no usable markdown summaries.
    """
    root = Path(reports_root) if reports_root else REPORTS_ROOT
    market_dir = root / "daily" / scan_date / run_id / "market"

    if not market_dir.exists():
        raise FileNotFoundError(
            f"Market directory not found: {market_dir}. "
            "Ensure the scanner run completed before rebuilding."
        )

    # Determine artifact path using the same root
    artifact_path = market_dir / "scanner_graph_facts.json"

    if artifact_path.exists() and not overwrite:
        _logger.info("rebuild: artifact already exists at %s — skipping (--no-overwrite)", artifact_path)
        return artifact_path

    # Try primary path: macro JSON + markdown
    macro_path = market_dir / "macro_scan_summary.json"

    try:
        from tradingagents.graph.scanner_facts.from_macro_json import (
            facts_from_macro_scan_summary,
            load_and_parse_macro_scan_summary,
        )
        from tradingagents.graph.scanner_facts.builder import build_scanner_graph_facts_from_market_dir

        facts = build_scanner_graph_facts_from_market_dir(
            market_dir, scan_date=scan_date, run_id=run_id
        )

    except (json.JSONDecodeError, ValueError) as exc:
        # Narrow fallback: macro JSON malformed, try markdown-only
        if "macro_scan_summary" in str(exc) or "not valid JSON" in str(exc):
            _logger.warning(
                "rebuild: macro_scan_summary.json malformed (%s) — "
                "attempting markdown-only fallback", exc
            )
            if not _has_usable_markdown(market_dir):
                raise ValueError(
                    f"macro_scan_summary.json malformed and no usable Markdown "
                    f"summaries found in {market_dir}. Cannot rebuild."
                ) from exc
            facts = _build_from_markdown_only(
                market_dir, scan_date=scan_date, run_id=run_id
            )
        else:
            raise

    return save_scanner_graph_facts(facts, artifact_path, overwrite=overwrite)


# ---------- CLI ----------

def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tradingagents.graph.scanner_facts.rebuild",
        description="Rebuild scanner_graph_facts.json for a historical scan run.",
    )
    parser.add_argument("--date", required=True, help="Scan date (YYYY-MM-DD)")
    parser.add_argument("--run-id", required=True, dest="run_id", help="Run ID")
    parser.add_argument(
        "--reports-root", dest="reports_root", default=None,
        help="Override reports root directory",
    )
    parser.add_argument(
        "--no-overwrite", dest="no_overwrite", action="store_true",
        help="Skip rebuild if artifact already exists",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        path = rebuild_scanner_graph_facts(
            args.date,
            args.run_id,
            reports_root=Path(args.reports_root) if args.reports_root else None,
            overwrite=not args.no_overwrite,
        )
        print(f"Rebuilt: {path}")
        return 0
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(_main())
