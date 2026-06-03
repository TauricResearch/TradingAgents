"""Per-ticker runner for compose_morning_digest."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Tuple

from tradingagents.secretary.analysis_runner import (
    run_committee_analysis,
    run_default_analysis,
)
from tradingagents.secretary.synthesis import synthesize_brief


def run_one_ticker(
    *,
    ticker: str,
    trade_date: str,
    config: dict,
    conn: sqlite3.Connection,
    data_dir: Path,
) -> Tuple[List[str], Dict[str, str]]:
    """Run one balanced analysis by default, synthesize, return (run_ids, synthesis)."""
    if config.get("_persona_filter"):
        run_ids = run_committee_analysis(
            persona_ids=config["_persona_filter"],
            ticker=ticker,
            trade_date=trade_date,
            config=config,
            parallel=True,
        )
    elif config.get("committee_mode_enabled"):
        run_ids = run_committee_analysis(
            persona_ids=config.get("committee_persona_ids", []),
            ticker=ticker,
            trade_date=trade_date,
            config=config,
            parallel=True,
        )
    else:
        run_ids = run_default_analysis(
            ticker=ticker,
            trade_date=trade_date,
            config=config,
        )
    persona_runs: List[Dict[str, Any]] = []
    for rid in run_ids:
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (rid,)).fetchone()
        if row is None:
            continue
        artifact_dir = data_dir / row["artifact_dir"]
        pm_md = artifact_dir / "pm_synthesis.md"
        report = pm_md.read_text() if pm_md.exists() else (row["decision"] or "")
        persona_runs.append({"persona_id": row["persona_id"], "final_trade_decision": report})

    from tradingagents.llm_clients.factory import create_llm_client
    llm = create_llm_client(
        provider=config["llm_provider"],
        model=config["deep_think_llm"],
        base_url=config.get("backend_url"),
    ).get_llm()
    synthesis = synthesize_brief(llm=llm, ticker=ticker, persona_runs=persona_runs)
    return run_ids, synthesis
