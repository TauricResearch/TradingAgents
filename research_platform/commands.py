"""Command line for the research platform.

    tradingagents-platform run AAPL MSFT 2222.SR --date 2026-11-20
    tradingagents-platform run --file watchlist.txt
    tradingagents-platform signals
    tradingagents-platform scorecard
    tradingagents-platform paper --cash 100000
    tradingagents-platform dashboard
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer

from research_platform.config import ANALYSTS, platform_config, provider_key_status

app = typer.Typer(help="TradingAgents research platform (research only; no broker, no orders).",
                  no_args_is_help=True)


def _store():
    from research_platform.watchlist import default_store

    return default_store(platform_config())


@app.command()
def run(
    tickers: Annotated[list[str] | None, typer.Argument(help="Tickers to analyze")] = None,
    file: Annotated[Path | None, typer.Option("--file", "-f", help="Watchlist file (text or JSON list)")] = None,
    date: Annotated[str | None, typer.Option(help="Analysis date YYYY-MM-DD (default: today)")] = None,
    analysts: Annotated[str, typer.Option(help="Comma-separated analysts")] = "market,news,fundamentals,valuation",
    rerun: Annotated[bool, typer.Option(help="Run again even if the ticker is recorded for the date")] = False,
    name: Annotated[str | None, typer.Option(help="A label stored with each run")] = None,
):
    """Run the full agent graph for each ticker and record the decisions (calls the LLM)."""
    from research_platform.prices import today
    from research_platform.watchlist import load_watchlist, parse_watchlist, run_watchlist

    cfg = platform_config()
    key, present = provider_key_status(cfg)
    if key and not present:
        typer.echo(f"{key} is not set for provider {cfg['llm_provider']}: add it to .env first.", err=True)
        raise typer.Exit(1)
    chosen = tuple(a.strip() for a in analysts.split(",") if a.strip())
    unknown = set(chosen) - set(ANALYSTS)
    if unknown:
        raise typer.BadParameter(f"unknown analysts: {', '.join(sorted(unknown))}")
    symbols = load_watchlist(file) if file else []
    symbols += parse_watchlist(",".join(tickers or []))
    if not symbols:
        raise typer.BadParameter("give tickers or --file")
    date = date or today()
    typer.echo(f"{len(symbols)} tickers on {date} with {cfg['llm_provider']} "
               f"({cfg['quick_think_llm']} / {cfg['deep_think_llm']})")
    result = run_watchlist(list(dict.fromkeys(symbols)), date, cfg, chosen, rerun=rerun, name=name,
                           progress=lambda i, n, t: typer.echo(f"[{i}/{n}] {t} ..."))
    typer.echo(f"ran {len(result.ran)}, skipped {len(result.skipped)} already recorded, "
               f"failed {len(result.failed)}")
    for ticker, error in result.failed:
        typer.echo(f"  {ticker}: {error}")


@app.command()
def signals(ticker: Annotated[str | None, typer.Option(help="Only this ticker")] = None,
            csv: Annotated[Path | None, typer.Option(help="Also write the table to this CSV file")] = None):
    """List recorded signals."""
    import pandas as pd

    rows = _store().all(ticker)
    if not rows:
        typer.echo("No signals recorded yet.")
        return
    frame = pd.DataFrame([{k: getattr(s, k) for k in (
        "date", "ticker", "status", "rating", "price", "size_pct", "stop_long", "error")} for s in rows])
    typer.echo(frame.to_string(index=False))
    if csv:
        frame.to_csv(csv, index=False)
        typer.echo(f"written to {csv}")


@app.command()
def scorecard(csv: Annotated[Path | None, typer.Option(help="Also write every outcome to this CSV file")] = None):
    """Score recorded signals against later prices and the regional benchmark."""
    from research_platform.scorecard import score

    card = score(_store().all(only_ok=True), cfg=platform_config())
    typer.echo(card.render())
    if csv:
        card.frame().to_csv(csv, index=False)
        typer.echo(f"written to {csv}")


@app.command()
def paper(cash: Annotated[float, typer.Option(help="Starting cash")] = 100_000.0,
          benchmark: Annotated[str, typer.Option(help="Buy-and-hold comparison")] = "SPY",
          no_stops: Annotated[bool, typer.Option(help="Ignore the recorded ATR stops")] = False,
          csv: Annotated[Path | None, typer.Option(help="Also write the trades to this CSV file")] = None):
    """Simulate a paper portfolio that follows the recorded signals."""
    from research_platform.paper import simulate

    result = simulate(_store().all(only_ok=True), params={"starting_cash": cash, "use_stops": not no_stops},
                      benchmark=benchmark)
    typer.echo(result.render())
    if csv and result.trades:
        result.trades_frame().to_csv(csv, index=False)
        typer.echo(f"written to {csv}")


@app.command()
def dashboard(port: Annotated[int, typer.Option(help="Local port")] = 8501):
    """Open the local Streamlit dashboard."""
    script = Path(__file__).with_name("dashboard.py")
    raise typer.Exit(subprocess.call([sys.executable, "-m", "streamlit", "run", str(script),
                                      "--server.port", str(port), "--server.address", "127.0.0.1",
                                      "--browser.gatherUsageStats", "false"]))


if __name__ == "__main__":
    app()
