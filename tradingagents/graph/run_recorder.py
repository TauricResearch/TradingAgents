"""Run Recorder — graph node + helper.

After Portfolio Manager finishes, this writes:
- one ``runs`` row in SQLite (status, decision, costs link)
- per-analyst markdown files under ``<data_dir>/runs/<run_id>/``
- one or more ``costs`` rows from the RunCostCallback's totals

This is the P7 boundary contract: every graph run produces a persisted
record. The smoke test in tests/smoke/test_f1_exit_gate.py asserts this
fires for every persona run during the exit-gate check.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from tradingagents.persistence import store


_DECISION_RE = re.compile(r"\b(BUY|HOLD|SELL)\b", re.IGNORECASE)


def parse_decision(text: str) -> Optional[str]:
    """Extract BUY/HOLD/SELL from a free-form decision string. Returns None
    when no clear signal is present."""
    if not text:
        return None
    matches = _DECISION_RE.findall(text)
    if not matches:
        return None
    # Prefer the LAST occurrence — typical pattern is reasoning followed by
    # "FINAL TRANSACTION PROPOSAL: **BUY**".
    return matches[-1].upper()


class RunRecorder:
    def __init__(
        self,
        *,
        conn: sqlite3.Connection,
        data_dir: str,
        run_id: str,
        persona_id: Optional[str],
        cost_callback: Any,        # RunCostCallback (duck-typed to ease mocking)
        queue_job_id: Optional[int] = None,
    ) -> None:
        self._conn = conn
        self._data_dir = Path(data_dir)
        self._run_id = run_id
        self._persona_id = persona_id
        self._cost_callback = cost_callback
        self._queue_job_id = queue_job_id
        self._artifact_dir_rel = f"runs/{run_id}"

    def start(self, ticker: str, *, started_ts: str) -> None:
        store.insert_run(
            self._conn,
            run_id=self._run_id,
            ticker=ticker,
            persona_id=self._persona_id,
            started_ts=started_ts,
            artifact_dir=self._artifact_dir_rel,
            queue_job_id=self._queue_job_id,
        )

    def record(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Persist artifacts; return ``state`` unchanged so the graph node
        is a pass-through."""
        ticker = state.get("company_of_interest", "UNKNOWN")
        decision_src = state.get("final_trade_decision") or state.get(
            "trader_investment_plan", ""
        )
        decision = parse_decision(decision_src)

        # Filesystem artifacts
        run_path = self._data_dir / self._artifact_dir_rel
        (run_path / "analysts").mkdir(parents=True, exist_ok=True)
        for key in ("market", "sentiment", "news", "fundamentals", "derivatives"):
            content = state.get(f"{key}_report", "") or ""
            if content:
                (run_path / "analysts" / f"{key}.md").write_text(
                    content, encoding="utf-8"
                )
        (run_path / "trader_plan.md").write_text(
            state.get("trader_investment_plan", "") or "", encoding="utf-8"
        )
        (run_path / "risk_debate.md").write_text(
            json.dumps(state.get("risk_debate_state", {}), indent=2, default=str),
            encoding="utf-8",
        )
        (run_path / "pm_synthesis.md").write_text(
            state.get("final_trade_decision", "") or "", encoding="utf-8"
        )
        # IIC-FORGE F4: write event_context.md when this run was launched
        # in event_alert mode (Secretary.compose_event_alert path).
        event_ctx = state.get("event_context_text", "") or ""
        if event_ctx:
            (run_path / "event_context.md").write_text(event_ctx, encoding="utf-8")
        (run_path / "meta.json").write_text(json.dumps({
            "run_id": self._run_id,
            "persona_id": self._persona_id,
            "ticker": ticker,
            "trade_date": state.get("trade_date"),
            "decision": decision,
        }, indent=2), encoding="utf-8")

        # Costs
        totals = self._cost_callback.totals_by_model()
        for model_name, counts in totals.items():
            store.record_cost(
                self._conn,
                run_id=self._run_id,
                provider="deepseek" if "deepseek" in model_name else "unknown",
                model=model_name,
                in_tokens=counts["in_tokens"],
                out_tokens=counts["out_tokens"],
            )

        # DB finalize
        store.finalize_run(
            self._conn,
            run_id=self._run_id,
            ended_ts=datetime.now(timezone.utc).isoformat(),
            status="complete",
            decision=decision,
            confidence=None,   # F1 doesn't compute confidence; defer to F2
        )

        return state


def make_run_recorder_node(recorder: RunRecorder):
    """LangGraph node factory: returns a callable that records the state."""
    def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        return recorder.record(state)
    return _node
