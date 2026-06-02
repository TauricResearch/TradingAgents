"""`forge alert` — list / approve / dismiss pending event-alert light studies."""

from __future__ import annotations

import json
import typer
from rich.console import Console
from rich.table import Table

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.persistence.db import connect
from tradingagents.persistence import store


alert_app = typer.Typer(name="alert", help="Event-alert light-study approvals")
console = Console()


def _conn():
    import os
    db_path = os.environ.get("TRADINGAGENTS_IIC_DB_PATH") or DEFAULT_CONFIG["iic_db_path"]
    return connect(db_path)


def _utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _transition(conn, brief_id: str, ticker, state: str) -> int:
    rows = conn.execute(
        "SELECT action_id, action_params FROM brief_actions "
        "WHERE brief_id = ? AND action_type = 'run_full_study' AND state = 'pending'",
        (brief_id,),
    ).fetchall()
    n = 0
    for r in rows:
        t = json.loads(r["action_params"]).get("ticker")
        if ticker is None or ticker.upper() == t:
            store.update_action_state(conn, action_id=r["action_id"],
                                      state=state, responded_at=_utc_now_iso())
            n += 1
    return n


@alert_app.command("list")
def alert_list() -> None:
    """Show pending light-study approvals (one row per awaiting ticker)."""
    conn = _conn()
    rows = store.fetch_pending_run_full_study(conn)
    if not rows:
        console.print("(no pending alerts)")
        return
    t = Table("light_brief", "event", "ticker", "expires")
    for r in rows:
        t.add_row(r["brief_id"][:8], (r["trigger_event_id"] or "")[:8],
                  json.loads(r["action_params"])["ticker"], r["expires_at"][:19])
    console.print(t)


@alert_app.command("approve")
def alert_approve(
    brief_id: str,
    ticker: str = typer.Option(None, "--ticker", help="Approve one ticker; omit for all"),
) -> None:
    """Approve a full study for one or all tickers on a light alert."""
    conn = _conn()
    n = _transition(conn, brief_id, ticker, "accepted")
    console.print(f"[green]approved[/green] {n} ticker(s) on {brief_id[:8]}")


@alert_app.command("dismiss")
def alert_dismiss(
    brief_id: str,
    ticker: str = typer.Option(None, "--ticker", help="Dismiss one ticker; omit for all"),
) -> None:
    """Dismiss (decline) one or all tickers on a light alert."""
    conn = _conn()
    n = _transition(conn, brief_id, ticker, "declined")
    console.print(f"[yellow]dismissed[/yellow] {n} ticker(s) on {brief_id[:8]}")
