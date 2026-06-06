"""IIC-FORGE `deepdive <ticker>` command.

Runs one balanced enriched TradingAgents graph by default. Use
``--committee`` to compare the configured committee personas.
"""

from __future__ import annotations

from datetime import date as _date

import typer

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.persistence.db import connect as iic_connect
from tradingagents.secretary.analysis_runner import (
    run_committee_analysis,
    run_default_analysis,
)
from tradingagents.secretary.service import Secretary


def _build_secretary(config: dict) -> Secretary:
    from tradingagents.llm_clients.factory import create_llm_client
    client = create_llm_client(
        provider=config["llm_provider"],
        model=config["deep_think_llm"],
        base_url=config.get("backend_url"),
    )
    llm = client.get_llm()  # unwrap to the underlying LangChain chat model
    conn = iic_connect(config["iic_db_path"])
    return Secretary(conn=conn, data_dir=config["iic_data_dir"], llm=llm)


def run_deepdive(
    *,
    ticker: str,
    trade_date: str,
    parallel: bool = True,
    committee: bool = False,
    config_overrides: dict | None = None,
) -> str:
    """Programmatic entry point — returns the brief_id.

    ``config_overrides`` is merged on top of DEFAULT_CONFIG. Tests use this
    to route persistence to a tmp directory without relying on env vars
    (which DEFAULT_CONFIG snapshots at import time).
    """
    config = dict(DEFAULT_CONFIG)
    if config_overrides:
        config.update(config_overrides)

    if committee:
        run_ids = run_committee_analysis(
            persona_ids=config.get("committee_persona_ids", []),
            ticker=ticker,
            trade_date=trade_date,
            config=config,
            parallel=parallel,
        )
    else:
        run_ids = run_default_analysis(
            ticker=ticker,
            trade_date=trade_date,
            config=config,
        )

    sec = _build_secretary(config)
    return sec.compose_deep_dive(ticker=ticker, run_ids=run_ids, trade_date=trade_date)


def deepdive(
    ticker: str = typer.Argument(..., help="Ticker symbol, e.g. AAPL"),
    trade_date: str = typer.Option(None, "--date", help="Trade date YYYY-MM-DD (default: today)"),
    parallel: bool = typer.Option(True, "--parallel/--no-parallel"),
    committee: bool = typer.Option(False, "--committee/--single", help="Run explicit value/momentum/macro committee"),
):
    """Run a balanced deep-dive and produce a synthesized brief."""
    # Capture config before run_deepdive so we read env-var overrides once.
    config = dict(DEFAULT_CONFIG)
    td = trade_date or _date.today().isoformat()
    brief_id = run_deepdive(
        ticker=ticker.upper(),
        trade_date=td,
        parallel=parallel,
        committee=committee,
    )
    typer.echo(f"brief_id: {brief_id}")
    typer.echo(f"brief markdown: {config['iic_data_dir']}/briefs/{brief_id}.md")

    # F5: post-delivery prompts (backtest y/N + refinement loop)
    from tradingagents.persistence.db import connect as iic_connect
    conn = iic_connect(config["iic_db_path"])
    post_delivery_prompts(brief_id=brief_id, conn=conn)


def post_delivery_prompts(*, brief_id: str, conn) -> None:
    """Interactive post-delivery prompts: backtest y/N + refinement loop.

    Backtest: writes a run_backtest brief_action with state='accepted' on 'y'.
    Refinement: loop reading non-empty lines, each becomes a refine_brief action.
    Empty input exits the loop.
    """
    import sys
    from datetime import datetime, timedelta, timezone
    from tradingagents import default_config as _dc
    from tradingagents.persistence import store

    expires_hours = _dc.DEFAULT_CONFIG["refinement"]["action_expires_hours"]
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=expires_hours)).isoformat()
    now = datetime.now(timezone.utc).isoformat()

    sys.stdout.write("\nRun a backtest on these strategies? [y/N]: ")
    sys.stdout.flush()
    ans = sys.stdin.readline().strip().lower()
    if ans == "y":
        aid = store.insert_brief_action(
            conn, brief_id=brief_id, action_type="run_backtest",
            action_params={}, expires_at=expires_at,
        )
        store.update_action_state(conn, action_id=aid, state="accepted",
                                  responded_at=now)
        sys.stdout.write(f"  → queued (action_id={aid})\n")

    while True:
        sys.stdout.write("Anything to refine? (free text, or Enter to finish): ")
        sys.stdout.flush()
        line = sys.stdin.readline()
        if not line:
            break
        text = line.strip()
        if not text:
            break
        aid = store.insert_brief_action(
            conn, brief_id=brief_id, action_type="refine_brief",
            action_params={"reply_text": text}, expires_at=expires_at,
        )
        store.update_action_state(conn, action_id=aid, state="accepted",
                                  responded_at=now)
        sys.stdout.write(f"  → queued (action_id={aid})\n")
