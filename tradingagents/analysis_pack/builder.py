from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _collect_reports_from_artifacts(artifact_dir: Path) -> dict[str, str]:
    reports: dict[str, str] = {}
    state = _read_json(artifact_dir / "state.json")
    for key in [
        "market_report",
        "sentiment_report",
        "news_report",
        "fundamentals_report",
        "derivatives_report",
    ]:
        if state.get(key):
            reports[key] = state[key]

    analyst_dir = artifact_dir / "analysts"
    for key in ["market", "sentiment", "news", "fundamentals", "derivatives"]:
        path = analyst_dir / f"{key}.md"
        if path.exists():
            reports[f"{key}_report"] = _read_text(path)
    return reports


def _collect_debates_from_artifacts(artifact_dir: Path) -> dict[str, Any]:
    state = _read_json(artifact_dir / "state.json")
    debates: dict[str, Any] = {}
    for key in ["investment_debate_state", "risk_debate_state"]:
        if state.get(key):
            debates[key] = state[key]

    risk_debate = _read_json(artifact_dir / "risk_debate.md")
    if risk_debate:
        debates["risk_debate_state"] = risk_debate
    trader_plan = _read_text(artifact_dir / "trader_plan.md")
    if trader_plan:
        debates["trader_investment_plan"] = trader_plan
    return debates


def build_pack_content_from_runs(
    *,
    conn: sqlite3.Connection,
    data_dir: Path,
    event_id: str | None,
    ticker: str,
    trade_date: str,
    event_context: str,
    run_ids: list[str],
) -> dict[str, Any]:
    reports: dict[str, str] = {}
    debates: dict[str, Any] = {}
    finals: list[dict[str, str]] = []

    for run_id in run_ids:
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            continue
        artifact_dir = data_dir / row["artifact_dir"]
        reports.update(_collect_reports_from_artifacts(artifact_dir))
        debates.update(_collect_debates_from_artifacts(artifact_dir))
        finals.append(
            {
                "run_id": run_id,
                "persona_id": row["persona_id"] or "default",
                "decision": row["decision"] or "",
                "body": _read_text(artifact_dir / "pm_synthesis.md"),
            }
        )

    return {
        "version": 1,
        "ticker": ticker,
        "trade_date": trade_date,
        "event_id": event_id,
        "event_context": event_context,
        "reports": reports,
        "debates": debates,
        "final_trade_decisions": finals,
    }
