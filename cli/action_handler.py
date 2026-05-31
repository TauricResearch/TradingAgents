"""`forge action-handler run` — long-running tick loop."""

from __future__ import annotations

import logging
import time

import typer

from tradingagents import default_config as _dc
from tradingagents.persistence.db import connect as iic_connect


action_handler_app = typer.Typer(name="action-handler", help="brief_actions consumer")


def _build_secretary(config: dict):
    from tradingagents.secretary.service import Secretary
    from tradingagents.llm_clients.factory import create_llm_client

    llm = create_llm_client(
        provider=config["llm_provider"],
        model=config["quick_think_llm"],
        base_url=config.get("backend_url"),
    ).get_llm()
    conn = iic_connect(config["iic_db_path"])
    return Secretary(conn=conn, data_dir=config["iic_data_dir"], llm=llm)


def action_handler_run() -> None:
    """Loop calling action_handler.tick() at the configured interval."""
    from tradingagents.orchestrator.action_handler import tick

    config = _dc.DEFAULT_CONFIG
    interval = config["action_handler"]["tick_interval_seconds"]
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    log = logging.getLogger("iic-action-handler")
    log.info("starting tick loop, interval=%ds", interval)

    conn = iic_connect(config["iic_db_path"])
    secretary = _build_secretary(config)

    def _dispatch_backtest(brief_id: str, params: dict) -> int:
        # F2 brief-scoped mode hookup. If F2 hasn't shipped yet, insert a
        # placeholder backtests row so the action-handler seam works end-to-end.
        try:
            from tradingagents.backtest.harness import BacktestHarness  # type: ignore
            harness = BacktestHarness(conn=conn, data_dir=config["iic_data_dir"])
            return harness.run_brief_scoped(brief_id=brief_id)
        except ImportError:
            import json as _j
            cur = conn.execute(
                "INSERT INTO backtests (triggered_by_brief_id, universe, start_date, "
                "end_date, status, created_ts) VALUES (?, ?, ?, ?, 'stub_pending_f2', "
                "datetime('now'))",
                (brief_id, _j.dumps([]), "stub", "stub"),
            )
            conn.commit()
            log.warning("F2 backtest harness not available; inserted stub row id=%s",
                        cur.lastrowid)
            return cur.lastrowid

    try:
        while True:
            tick(conn=conn, secretary=secretary, dispatch_backtest=_dispatch_backtest)
            time.sleep(interval)
    except KeyboardInterrupt:
        log.info("shutdown via KeyboardInterrupt")


@action_handler_app.command("run")
def cmd_run() -> None:
    action_handler_run()
