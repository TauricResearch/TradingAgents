#!/usr/bin/env python3
"""Audit the quality of a completed run's scanner artifacts.

Usage:
    python scripts/audit_run_quality.py --run-id 01KNYA8AQ71JA85B2HQP1GR9V7 --date 2026-04-10

Reads all scanner reports under ``reports/daily/{date}/{run_id}/market/``
and checks for:
- [QUALITY:] header presence and values
- placeholder/process language in final reports
- [NO_EVIDENCE] propagation in summaries
- data inconsistencies (e.g. VIX divergence)
- ticker count vs max_tickers

Exit code 0 = clean, 1 = quality issues found.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from tradingagents.agents.utils.report_quality import (
    assess_report_quality,
    parse_quality_header,
)

_VIX_RE = re.compile(r"VIX[:\s]+(?:at\s+)?(\d+\.?\d*)", re.IGNORECASE)

SCANNER_REPORTS = [
    "gatekeeper_universe_report",
    "geopolitical_report",
    "market_movers_report",
    "sector_performance_report",
    "factor_alignment_report",
    "drift_opportunities_report",
    "smart_money_report",
    "industry_deep_dive_report",
]

SCANNER_SUMMARIES = [
    "gatekeeper_summary",
    "geopolitical_summary",
    "market_movers_summary",
    "sector_summary",
    "factor_alignment_summary",
    "drift_opportunities_summary",
    "smart_money_summary",
    "industry_deep_dive_summary",
]

# Map report keys to markdown filenames
_REPORT_FILES = {
    "gatekeeper_universe_report": "gatekeeper_universe_report.md",
    "geopolitical_report": "geopolitical_report.md",
    "market_movers_report": "market_movers_report.md",
    "sector_performance_report": "sector_performance_report.md",
    "factor_alignment_report": "factor_alignment_report.md",
    "drift_opportunities_report": "drift_opportunities_report.md",
    "smart_money_report": "smart_money_report.md",
    "industry_deep_dive_report": "industry_deep_dive_report.md",
}

_SUMMARY_FILES = {
    "gatekeeper_summary": "gatekeeper_summary.md",
    "geopolitical_summary": "geopolitical_summary.md",
    "market_movers_summary": "market_movers_summary.md",
    "sector_summary": "sector_summary.md",
    "factor_alignment_summary": "factor_alignment_summary.md",
    "drift_opportunities_summary": "drift_opportunities_summary.md",
    "smart_money_summary": "smart_money_summary.md",
    "industry_deep_dive_summary": "industry_deep_dive_summary.md",
}


def _read_file(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def audit_run(reports_dir: Path) -> dict:
    """Audit all scanner artifacts in a run directory.

    Returns a JSON-serializable summary dict.
    """
    market_dir = reports_dir / "market"
    issues: list[dict] = []
    report_qualities: dict[str, dict] = {}
    summary_qualities: dict[str, str] = {}

    # 1. Audit scanner reports
    for key, filename in _REPORT_FILES.items():
        text = _read_file(market_dir / filename)
        if not text:
            issues.append({"file": filename, "issue": "missing_file"})
            report_qualities[key] = {"quality": "empty", "evidence_count": 0}
            continue

        header = parse_quality_header(text)
        if header:
            report_qualities[key] = header
            if header["quality"] != "ok":
                issues.append(
                    {
                        "file": filename,
                        "issue": "quality_degraded",
                        "detail": header,
                    }
                )
        else:
            # No header — assess directly
            assessment = assess_report_quality(text, node_name=key)
            report_qualities[key] = assessment
            if assessment["quality"] != "ok":
                issues.append(
                    {
                        "file": filename,
                        "issue": "quality_degraded",
                        "detail": assessment,
                    }
                )

    # 2. Audit summaries
    for key, filename in _SUMMARY_FILES.items():
        text = _read_file(market_dir / filename)
        if not text:
            summary_qualities[key] = "missing"
            continue
        if text.strip().startswith("[NO_EVIDENCE]"):
            summary_qualities[key] = "no_evidence"
        elif "pending" in text.lower() or "awaiting" in text.lower():
            summary_qualities[key] = "placeholder_propagated"
            issues.append(
                {
                    "file": filename,
                    "issue": "placeholder_in_summary",
                }
            )
        else:
            summary_qualities[key] = "ok"

    # 3. VIX consistency check
    vix_values: dict[str, float] = {}
    for key, filename in _REPORT_FILES.items():
        text = _read_file(market_dir / filename)
        match = _VIX_RE.search(text)
        if match:
            vix_values[key] = float(match.group(1))

    # Also check ticker reports
    for ticker_dir in reports_dir.iterdir():
        if ticker_dir.is_dir() and ticker_dir.name not in ("market", "portfolio", "report"):
            report_file = ticker_dir / "complete_report.md"
            text = _read_file(report_file)
            for match in _VIX_RE.finditer(text):
                vix_values[f"{ticker_dir.name}/complete_report"] = float(match.group(1))
                break

    if len(set(vix_values.values())) > 1:
        min_vix = min(vix_values.values())
        max_vix = max(vix_values.values())
        if min_vix > 0 and (max_vix - min_vix) / min_vix > 0.20:
            issues.append(
                {
                    "issue": "vix_inconsistency",
                    "values": {k: v for k, v in sorted(vix_values.items())},
                }
            )

    # 4. Ticker count check
    meta_file = reports_dir / "run_meta.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())
        max_tickers = meta.get("params", {}).get("max_tickers")
        if max_tickers:
            market_dir / "report"
            ticker_dirs = [
                d.name
                for d in reports_dir.iterdir()
                if d.is_dir() and d.name not in ("market", "portfolio", "report")
            ]
            if len(ticker_dirs) > max_tickers:
                issues.append(
                    {
                        "issue": "ticker_count_exceeded",
                        "max_tickers": max_tickers,
                        "actual": len(ticker_dirs),
                        "tickers": ticker_dirs,
                    }
                )

    # Summarize
    usable_reports = sum(1 for q in report_qualities.values() if q.get("quality") == "ok")
    total_reports = len(_REPORT_FILES)

    return {
        "run_dir": str(reports_dir),
        "scanner_reports": {
            "usable": usable_reports,
            "total": total_reports,
            "details": report_qualities,
        },
        "summaries": summary_qualities,
        "issues": issues,
        "pass": len(issues) == 0,
    }


def main():
    parser = argparse.ArgumentParser(description="Audit run quality")
    parser.add_argument("--run-id", required=True, help="Run ID (ULID)")
    parser.add_argument("--date", required=True, help="Run date (YYYY-MM-DD)")
    parser.add_argument(
        "--reports-dir",
        default="reports",
        help="Root reports directory (default: reports)",
    )
    args = parser.parse_args()

    run_dir = Path(args.reports_dir) / "daily" / args.date / args.run_id
    if not run_dir.exists():
        print(f"ERROR: Run directory not found: {run_dir}", file=sys.stderr)
        sys.exit(2)

    result = audit_run(run_dir)
    print(json.dumps(result, indent=2))

    if not result["pass"]:
        print(
            f"\nQUALITY ISSUES FOUND: {len(result['issues'])} issue(s). "
            f"Scanner success: {result['scanner_reports']['usable']}/{result['scanner_reports']['total']}.",
            file=sys.stderr,
        )
        sys.exit(1)
    else:
        print(
            f"\nALL CLEAR: {result['scanner_reports']['usable']}/{result['scanner_reports']['total']} scanners OK.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
