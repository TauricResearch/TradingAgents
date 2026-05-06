"""Lookup helpers for prior-run reports (read-only, filesystem-backed).

These are intentionally tiny and pure: they walk the
``reports/daily/{date}/{run_id}/...`` tree looking for the most recent
artifact that predates ``as_of_date`` and falls within ``lookback_days``.

The functions never raise on missing files — they return ``None`` so callers
can fall back gracefully.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.report_paths import REPORTS_ROOT


def _parse_iso(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _candidate_dates(
    reports_root: Path,
    as_of_date: str,
    lookback_days: int,
) -> list[str]:
    target = _parse_iso(as_of_date)
    if target is None or not reports_root.exists():
        return []
    earliest = target - timedelta(days=lookback_days)
    out: list[date] = []
    for child in reports_root.iterdir():
        if not child.is_dir():
            continue
        d = _parse_iso(child.name)
        if d is None:
            continue
        if earliest <= d < target:
            out.append(d)
    out.sort(reverse=True)
    # Cap to lookback_days entries so inner _load_latest_in_date calls don't grow with calendar time
    return [d.isoformat() for d in out[:lookback_days]]


def _load_latest_in_date(
    date_dir: Path,
    relative_subpath: str,
    filename_tail: str,
) -> dict[str, Any] | None:
    """Return the JSON data from the lexicographically-last file whose name ends with
    ``filename_tail``, scanning all run-id subdirectories under ``date_dir / relative_subpath``.

    Returns ``None`` on any error or if no matching file exists.
    """
    if not date_dir.exists():
        return None
    matches: list[Path] = []
    for run_dir in date_dir.iterdir():
        if not run_dir.is_dir():
            continue
        scan_dir = run_dir / relative_subpath
        if not scan_dir.exists():
            continue
        matches.extend(p for p in scan_dir.iterdir() if p.is_file() and p.name.endswith(filename_tail))
    if not matches:
        return None
    matches.sort(key=lambda p: (p.parent.parent.parent.name, p.name), reverse=True)
    try:
        return json.loads(matches[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def find_latest_prior_analysis(
    ticker: str,
    as_of_date: str,
    reports_root: Path | None = None,
    lookback_days: int | None = None,
) -> dict[str, Any] | None:
    """Return the most recent ``complete_report.json`` strictly before ``as_of_date``.

    Returns ``{"date": "YYYY-MM-DD", "data": {...}}`` or ``None``.
    """
    root = Path(reports_root) if reports_root is not None else Path(REPORTS_ROOT) / "daily"
    lookback = (
        lookback_days
        if lookback_days is not None
        else int(DEFAULT_CONFIG.get("historical_context_lookback_days", 60))
    )
    for d in _candidate_dates(root, as_of_date, lookback):
        data = _load_latest_in_date(
            root / d,
            f"{ticker.upper()}/report",
            "complete_report.json",
        )
        if data is not None:
            return {"date": d, "data": data}
    return None


def find_latest_prior_pm_decision(
    portfolio_id: str,
    as_of_date: str,
    reports_root: Path | None = None,
    lookback_days: int | None = None,
) -> dict[str, Any] | None:
    """Return the most recent ``{portfolio_id}_pm_decision.json`` strictly before ``as_of_date``."""
    root = Path(reports_root) if reports_root is not None else Path(REPORTS_ROOT) / "daily"
    lookback = (
        lookback_days
        if lookback_days is not None
        else int(DEFAULT_CONFIG.get("historical_context_lookback_days", 60))
    )
    for d in _candidate_dates(root, as_of_date, lookback):
        data = _load_latest_in_date(
            root / d,
            "portfolio/report",
            f"{portfolio_id}_pm_decision.json",
        )
        if data is not None:
            return {"date": d, "data": data}
    return None


def _truncate(text: str, limit: int) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def find_latest_execution_failures(
    portfolio_id: str,
    as_of_date: str,
    reports_root: Path | None = None,
    lookback_days: int | None = None,
) -> dict[str, Any] | None:
    """Return the most recent execution result with non-empty failed_trades.

    Scans reports/daily/{date}/{run_id}/portfolio/report/*_execution_result.json
    for the latest file strictly before as_of_date that contains a non-empty
    'failed_trades' list.

    Returns {"date": "YYYY-MM-DD", "failed_trades": [...]} or None.
    """
    root = Path(reports_root) if reports_root is not None else Path(REPORTS_ROOT) / "daily"
    lookback = (
        lookback_days
        if lookback_days is not None
        else int(DEFAULT_CONFIG.get("historical_context_lookback_days", 60))
    )
    for d in _candidate_dates(root, as_of_date, lookback):
        data = _load_latest_in_date(
            root / d,
            "portfolio/report",
            f"{portfolio_id}_execution_result.json",
        )
        if data is not None:
            failed = data.get("failed_trades")
            if isinstance(failed, list) and len(failed) > 0:
                return {"date": d, "failed_trades": failed}
    return None


def format_execution_failure_block(
    failures: dict[str, Any] | None,
    max_chars: int = 600,
) -> str:
    """Format execution failures into a compact prompt block.

    Returns empty string if failures is None or failed_trades is empty.
    Each failure line: "- {action} {ticker} x{shares}: {reason}"
    Header: "## Prior Execution Failures ({date})"
    Instruction: "These trades were REJECTED. Do not repeat them."
    Total output capped at max_chars.
    """
    if not failures:
        return ""
    failed_trades = failures.get("failed_trades")
    if not failed_trades:
        return ""
    date_str = failures.get("date", "?")
    header = f"## Prior Execution Failures ({date_str})"
    instruction = "These trades were REJECTED. Do not repeat them."
    lines: list[str] = [header, instruction]
    for trade in failed_trades:
        action = trade.get("action", "?")
        ticker = trade.get("ticker", "?")
        shares = trade.get("shares", "?")
        reason = trade.get("reason", "unknown")
        lines.append(f"- {action} {ticker} x{shares}: {reason}")
    out = "\n".join(lines)
    return _truncate(out, max_chars)


def format_prior_context_block(
    ticker: str,
    prior_analysis: dict[str, Any] | None,
    prior_pm_decision: dict[str, Any] | None,
    max_chars: int = 1200,
) -> str:
    """Format prior analysis + PM decision as a compact prompt block.

    Returns an empty string if both inputs are ``None``.

    Note: the returned string contains the raw ticker symbol in the section header.
    Callers should anonymize the result before injecting it into LLM prompts.
    """
    if not prior_analysis and not prior_pm_decision:
        return ""
    per_section = max(200, (max_chars - 200) // 2)
    parts: list[str] = [f"## Prior Run Context for {ticker.upper()}"]
    if prior_analysis:
        d = prior_analysis.get("date", "?")
        data = prior_analysis.get("data") or {}
        plan = data.get("trader_investment_plan") or data.get("final_trade_decision") or ""
        parts.append(
            f"\n### Last Trader Plan ({d})\n{_truncate(plan, per_section)}"
        )
    if prior_pm_decision:
        d = prior_pm_decision.get("date", "?")
        data = prior_pm_decision.get("data") or {}
        decision = data.get("decision") or ""
        rationale = data.get("rationale") or ""
        body = decision if not rationale else f"{decision}\n\nRationale: {rationale}"
        parts.append(
            f"\n### Last PM Decision ({d})\n{_truncate(body, per_section)}"
        )
    out = "\n".join(parts)
    return _truncate(out, max_chars)
