"""F2 reflection — write a persona-aware outcome_log row when a forward
test matures. The existing _resolve_pending_entries reflection loop is
untouched; this is the second, persona-aware scoring path."""

from __future__ import annotations

import sqlite3
from typing import Optional

from tradingagents.persistence.memory import OutcomeLog


def write_outcome_log_on_close(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ticker: str,
    persona_id: Optional[str],
    decision: str,
    alpha: float,
    total_return: float,
    backtest_id: int,
    close_date: str,
    benchmark: str,
) -> int:
    """Append one row to outcome_log tagged with persona/backtest context."""
    outcome_md = (
        f"forward-test close {close_date}: "
        f"decision={decision}, total_return={total_return:+.4f}, "
        f"alpha vs {benchmark}={alpha:+.4f}"
    )
    log = OutcomeLog(conn)
    return log.append(
        run_id=run_id,
        ticker=ticker,
        decision=decision,
        outcome_md=outcome_md,
        pnl_proxy=alpha,
        tags={
            "persona_id": persona_id,
            "backtest_id": backtest_id,
            "source": "forward_test",
            "close_date": close_date,
            "benchmark": benchmark,
        },
    )
