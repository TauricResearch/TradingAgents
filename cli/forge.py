"""IIC-FORGE operational CLI.

Sub-apps:
  - watchlist : manage the curated watchlist (add / list / remove)
  - sense     : sensing-related ops (seed tickers, status, force sweep)

Wired into the main `tradingagents` CLI by ``cli/main.py``.
"""

from __future__ import annotations

import json
import typer
from rich.console import Console
from rich.table import Table

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.persistence.db import connect


app = typer.Typer(name="forge", help="IIC-FORGE operational commands")
console = Console()


# ---------------------------------------------------------------------
# watchlist sub-app
# ---------------------------------------------------------------------

watchlist_app = typer.Typer(name="watchlist", help="Manage the curated watchlist")
app.add_typer(watchlist_app, name="watchlist")


def _conn():
    # Re-read the env var rather than relying solely on DEFAULT_CONFIG —
    # DEFAULT_CONFIG fixes its values at import time, so tests that set
    # TRADINGAGENTS_IIC_DB_PATH after the first import need a live lookup.
    import os
    db_path = os.environ.get("TRADINGAGENTS_IIC_DB_PATH") or DEFAULT_CONFIG["iic_db_path"]
    return connect(db_path)


@watchlist_app.command("add")
def watchlist_add(ticker: str) -> None:
    """Add a ticker to the user-curated watchlist (never expires)."""
    from tradingagents.sensing.watchlist import add_user
    add_user(_conn(), ticker=ticker.upper())
    console.print(f"[green]added[/green] {ticker.upper()} (user-curated, no TTL)")


@watchlist_app.command("list")
def watchlist_list() -> None:
    """Print the current watchlist."""
    conn = _conn()
    rows = list(conn.execute(
        "SELECT ticker, added_ts, last_briefed, ttl_until, tags "
        "FROM watchlist ORDER BY ticker"
    ))
    if not rows:
        console.print("(watchlist is empty)")
        return
    t = Table("ticker", "added", "last_briefed", "ttl_until", "tags")
    for r in rows:
        tags = ", ".join(json.loads(r["tags"]) if r["tags"] else [])
        t.add_row(r["ticker"], r["added_ts"] or "",
                  r["last_briefed"] or "", r["ttl_until"] or "", tags)
    console.print(t)


@watchlist_app.command("remove")
def watchlist_remove(ticker: str) -> None:
    """Remove a ticker from the watchlist (works for user or auto rows)."""
    conn = _conn()
    n = conn.execute("DELETE FROM watchlist WHERE ticker = ?",
                      (ticker.upper(),)).rowcount
    conn.commit()
    if n:
        console.print(f"[yellow]removed[/yellow] {ticker.upper()}")
    else:
        console.print(f"[dim]{ticker.upper()} not on watchlist[/dim]")


# ---------------------------------------------------------------------
# sense sub-app
# ---------------------------------------------------------------------

from tradingagents.sensing.seed_tickers import seed_all, seed_crypto
from tradingagents.sensing.watchlist import sweep_expired


sense_app = typer.Typer(name="sense", help="Sensing operational commands")
app.add_typer(sense_app, name="sense")


@sense_app.command("reseed-tickers")
def sense_reseed_tickers(
    no_polygon: bool = typer.Option(False, "--no-polygon",
                                     help="Skip Polygon equity seed (crypto only)"),
) -> None:
    """Repopulate the `tickers` reference table.

    Without `--no-polygon`, calls Polygon `/v3/reference/tickers` (requires
    POLYGON_API_KEY). With `--no-polygon`, only seeds the crypto static list.
    """
    conn = _conn()
    if no_polygon:
        n = seed_crypto(conn)
        console.print(f"crypto: {n} rows")
    else:
        result = seed_all(conn)
        console.print(f"crypto: {result['crypto']} rows; polygon: {result['polygon']} rows")


@sense_app.command("sweep-watchlist")
def sense_sweep_watchlist() -> None:
    """One-shot prune of expired auto-watchlist entries."""
    conn = _conn()
    n = sweep_expired(conn)
    console.print(f"pruned {n} expired watchlist row(s)")
