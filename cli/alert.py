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


def _resolve_brief_id(conn, brief_id: str) -> str:
    """Resolve a (possibly abbreviated) brief_id to the full id.

    `alert list` prints the 8-char prefix, so operators naturally paste that
    back. Accept any unambiguous prefix (and the full id). Returns the input
    unchanged if it already matches a full id exactly; raises typer.BadParameter
    on no-match or an ambiguous prefix so the caller fails loudly."""
    exact = conn.execute(
        "SELECT 1 FROM brief_actions WHERE brief_id = ? "
        "AND action_type = 'run_full_study' LIMIT 1",
        (brief_id,),
    ).fetchone()
    if exact:
        return brief_id
    matches = [
        r[0] for r in conn.execute(
            "SELECT DISTINCT brief_id FROM brief_actions "
            "WHERE action_type = 'run_full_study' AND brief_id LIKE ?",
            (brief_id + "%",),
        ).fetchall()
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise typer.BadParameter(f"no light alert matches brief id {brief_id!r}")
    raise typer.BadParameter(
        f"ambiguous brief id {brief_id!r} matches {len(matches)} alerts; "
        f"use more characters")


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
    """Approve a full study for one or all tickers on a light alert.

    BRIEF_ID may be the 8-char prefix shown by `forge alert list` or the full id."""
    conn = _conn()
    full_id = _resolve_brief_id(conn, brief_id)
    n = _transition(conn, full_id, ticker, "accepted")
    if n == 0:
        console.print(f"[yellow]no pending tickers matched[/yellow] on {full_id[:8]}")
    else:
        console.print(f"[green]approved[/green] {n} ticker(s) on {full_id[:8]}")


@alert_app.command("dismiss")
def alert_dismiss(
    brief_id: str,
    ticker: str = typer.Option(None, "--ticker", help="Dismiss one ticker; omit for all"),
) -> None:
    """Dismiss (decline) one or all tickers on a light alert.

    BRIEF_ID may be the 8-char prefix shown by `forge alert list` or the full id."""
    conn = _conn()
    full_id = _resolve_brief_id(conn, brief_id)
    n = _transition(conn, full_id, ticker, "declined")
    if n == 0:
        console.print(f"[yellow]no pending tickers matched[/yellow] on {full_id[:8]}")
    else:
        console.print(f"[green]dismissed[/green] {n} ticker(s) on {full_id[:8]}")
