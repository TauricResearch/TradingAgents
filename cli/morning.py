"""`forge morning-digest` and `forge digest tail` sub-commands.

morning-digest --now runs compose_morning_digest then delivers via every
enabled channel. --dry-run skips channel.send() calls (used by F5 pre-flight).
digest tail prints the most recent morning_digest brief content.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

import typer

from tradingagents import default_config as _dc
from tradingagents.persistence.db import connect as iic_connect


def _config() -> dict:
    return _dc.DEFAULT_CONFIG


morning_app = typer.Typer(name="morning-digest", help="Morning digest scheduling and tail")
digest_app = typer.Typer(name="digest", help="Digest helpers")


def _build_secretary(config: dict) -> Tuple[object, object]:
    from tradingagents.llm_clients.factory import create_llm_client
    from tradingagents.secretary.service import Secretary

    llm = create_llm_client(
        provider=config["llm_provider"],
        model=config["deep_think_llm"],
        base_url=config.get("backend_url"),
    ).get_llm()
    conn = iic_connect(config["iic_db_path"])
    sec = Secretary(conn=conn, data_dir=config["iic_data_dir"], llm=llm)
    return sec, conn


def _build_channels(conn, config) -> Dict[str, object]:
    enabled = config["delivery"]["enabled_channels"]
    out: Dict[str, object] = {}
    if "cli" in enabled:
        from tradingagents.delivery.cli import CLIOutbound
        out["cli"] = CLIOutbound(conn=conn, config=config)
    if "email" in enabled:
        from tradingagents.delivery.email import EmailOutbound
        out["email"] = EmailOutbound(conn=conn, config=config)
    if "telegram" in enabled:
        from tradingagents.delivery.telegram import TelegramOutbound
        out["telegram"] = TelegramOutbound(conn=conn, config=config)
    return out


def _parse_tickers_from_body(body: str) -> list:
    """Cheap shim: parse the per-ticker sections written by compose_morning_digest."""
    tickers: list = []
    current: dict = {}
    for line in body.splitlines():
        if line.startswith("## "):
            if current:
                tickers.append(current)
            current = {"ticker": line[3:].strip(), "consensus": "",
                       "divergence": "", "recommendation": ""}
        elif line.startswith("**Consensus:** "):
            current["consensus"] = line[len("**Consensus:** "):]
        elif line.startswith("**Divergence:** "):
            current["divergence"] = line[len("**Divergence:** "):]
        elif line.startswith("**Recommendation:** "):
            current["recommendation"] = line[len("**Recommendation:** "):]
    if current:
        tickers.append(current)
    return tickers


@morning_app.command("now")
def morning_digest_now(
    dry_run: bool = typer.Option(False, "--dry-run", help="Compose but skip channel sends"),
) -> None:
    config = _config()
    sec, conn = _build_secretary(config)
    ts = datetime.now(timezone.utc).isoformat()
    brief_id = sec.compose_morning_digest(watchlist=None, ts=ts)
    typer.echo(f"morning_digest brief composed: {brief_id}")

    if dry_run:
        typer.echo("dry-run: skipping channel sends")
        return

    from tradingagents.persistence import store as _st
    brief = _st.load_brief(conn, brief_id)
    body_path = Path(config["iic_data_dir"]) / brief["content_path"]
    body = body_path.read_text() if body_path.exists() else ""

    channels = _build_channels(conn, config)
    from tradingagents.delivery.render import render_for_channel
    for name, channel in channels.items():
        if name == "telegram":
            rendered = render_for_channel(
                channel=name, mode="morning_digest",
                brief={**brief, "tickers": _parse_tickers_from_body(body)},
            )
        elif name == "email":
            rendered = render_for_channel(
                channel="email", mode="morning_digest",
                brief={**brief, "tickers": _parse_tickers_from_body(body)},
            )
        else:
            rendered = body
        delivery_id = channel.send(brief=brief, mode="morning_digest", body=rendered)
        typer.echo(f"  delivered via {name}: delivery_id={delivery_id}")


@digest_app.command("tail")
def digest_tail() -> None:
    """Print the most recent morning_digest brief content to stdout."""
    config = _config()
    conn = iic_connect(config["iic_db_path"])
    row = conn.execute(
        "SELECT content_path FROM briefs WHERE mode = 'morning_digest' "
        "ORDER BY generated_ts DESC LIMIT 1"
    ).fetchone()
    if row is None:
        typer.echo("no morning_digest briefs found", err=True)
        raise typer.Exit(1)
    body_path = Path(config["iic_data_dir"]) / row[0]
    sys.stdout.write(body_path.read_text())
