"""Per-ticker fan-out for compose_morning_digest.

Each ticker calls run_personas_parallel (existing) + synthesize_brief
(existing) to produce per-ticker {consensus, divergence, recommendation}.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Tuple

from tradingagents.personas.loader import load_all_personas
from tradingagents.secretary.persona_runner import run_personas_parallel
from tradingagents.secretary.synthesis import synthesize_brief


def _personas_dir() -> Path:
    """Locate persona YAMLs relative to this module — same convention as
    Secretary.compose_event_alert (tradingagents/secretary/service.py)."""
    return Path(__file__).resolve().parent.parent / "personas"


def run_one_ticker(
    *,
    ticker: str,
    trade_date: str,
    config: dict,
    conn: sqlite3.Connection,
    data_dir: Path,
) -> Tuple[List[str], Dict[str, str]]:
    """Run all enabled personas for one ticker, synthesize, return (run_ids, synthesis)."""
    personas = load_all_personas(str(_personas_dir()))
    if config.get("_persona_filter"):
        personas = [p for p in personas if p.id in config["_persona_filter"]]
    run_ids = run_personas_parallel(
        personas=personas,
        ticker=ticker,
        trade_date=trade_date,
        config=config,
        parallel=True,
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
