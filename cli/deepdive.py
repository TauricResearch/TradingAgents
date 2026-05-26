"""IIC-FORGE `deepdive <ticker>` command.

Runs three personas (macro / value / momentum) over the ticker, then calls
the Secretary to produce a synthesis brief. Parallel by default; ``--no-parallel``
runs sequentially (used by tests and for deterministic debugging).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date as _date
from pathlib import Path
from typing import List

import typer

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.personas.loader import Persona, load_all_personas
from tradingagents.persistence.db import connect as iic_connect
from tradingagents.secretary.service import Secretary


def _personas_dir() -> str:
    return str(Path(__file__).resolve().parent.parent / "tradingagents" / "personas")


def _run_one_persona(persona: Persona, ticker: str, trade_date: str, config: dict) -> str:
    """Construct a TradingAgentsGraph with the persona overlay, propagate, return run_id."""
    # Build a per-run config overlay.
    overlay = dict(config)
    overlay["persona_id"] = persona.id
    overlay["deep_think_llm"] = persona.llm.deep_think_llm
    overlay["quick_think_llm"] = persona.llm.quick_think_llm
    if persona.llm.deepseek_reasoning_effort is not None:
        overlay["deepseek_reasoning_effort"] = persona.llm.deepseek_reasoning_effort

    # Compute selected_analysts from the persona's include list.
    selected = list(persona.analysts.include)

    # Import here to avoid heavy imports at module import time.
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = TradingAgentsGraph(
        config=overlay,
        selected_analysts=selected,
    )
    # propagate(company_name, trade_date) is the public entry point confirmed
    # in tradingagents/graph/trading_graph.py line 342.
    graph.propagate(ticker, trade_date)
    return graph.run_id


def _build_secretary(config: dict) -> Secretary:
    from tradingagents.llm_clients.factory import create_llm_client
    llm = create_llm_client(
        provider=config["llm_provider"],
        model=config["deep_think_llm"],
        base_url=config.get("backend_url"),
    )
    conn = iic_connect(config["iic_db_path"])
    return Secretary(conn=conn, data_dir=config["iic_data_dir"], llm=llm)


def run_deepdive(*, ticker: str, trade_date: str, parallel: bool = True) -> str:
    """Programmatic entry point — returns the brief_id."""
    config = dict(DEFAULT_CONFIG)
    personas: List[Persona] = load_all_personas(_personas_dir())
    if not personas:
        raise RuntimeError(f"No personas found in {_personas_dir()}")

    if parallel:
        with ThreadPoolExecutor(max_workers=len(personas)) as ex:
            futures = [ex.submit(_run_one_persona, p, ticker, trade_date, config)
                       for p in personas]
            run_ids = [f.result() for f in futures]
    else:
        run_ids = [_run_one_persona(p, ticker, trade_date, config) for p in personas]

    sec = _build_secretary(config)
    return sec.compose_deep_dive(ticker=ticker, run_ids=run_ids, trade_date=trade_date)


def deepdive(
    ticker: str = typer.Argument(..., help="Ticker symbol, e.g. AAPL"),
    trade_date: str = typer.Option(None, "--date", help="Trade date YYYY-MM-DD (default: today)"),
    parallel: bool = typer.Option(True, "--parallel/--no-parallel"),
):
    """Run a three-persona deep-dive and produce a synthesized brief."""
    # Capture config before run_deepdive so we read env-var overrides once.
    config = dict(DEFAULT_CONFIG)
    td = trade_date or _date.today().isoformat()
    brief_id = run_deepdive(ticker=ticker.upper(), trade_date=td, parallel=parallel)
    typer.echo(f"brief_id: {brief_id}")
    typer.echo(f"brief markdown: {config['iic_data_dir']}/briefs/{brief_id}.md")
