import sys
from pathlib import Path

import typer

from cli.display import console
from cli.run import run_analysis
from tradingagents.backtest import iter_grid, run_backtest, summarize
from tradingagents.dataflows.symbols import safe_ticker_component
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.portfolio import load_portfolio

# prompt_toolkit's win32 output module is importable only on Windows (it asserts
# the platform at import time), so gate on the platform rather than catching the
# failure — that way a genuinely broken prompt_toolkit on Windows still surfaces
# instead of silently disabling the handler below. Off Windows this stays an
# empty tuple, which `except` accepts and never matches (#1138).
if sys.platform == "win32":  # pragma: no cover - platform dependent
    from prompt_toolkit.output.win32 import NoConsoleScreenBufferError

    _NO_CONSOLE_ERRORS: tuple[type[BaseException], ...] = (NoConsoleScreenBufferError,)
else:
    _NO_CONSOLE_ERRORS = ()

app = typer.Typer(
    name="TradingAgents",
    help="TradingAgents CLI: Multi-Agents LLM Financial Trading Framework",
    add_completion=True,  # Enable shell completion
)


@app.callback(invoke_without_command=True)
def analyze(
    ctx: typer.Context,
    checkpoint: bool | None = typer.Option(
        None,
        "--checkpoint/--no-checkpoint",
        help="Enable/disable checkpoint-resume (save state after each node so a "
        "crashed run can resume). Omit to honor TRADINGAGENTS_CHECKPOINT_ENABLED.",
    ),
    clear_checkpoints: bool = typer.Option(
        False,
        "--clear-checkpoints",
        help="Delete all saved checkpoints before running (force fresh start).",
    ),
    portfolio: str = typer.Option(
        None,
        "--portfolio",
        help="JSON file with current holdings and cash, so the trader, risk and "
        "portfolio agents size against your actual position.",
    ),
):
    """Run an analysis. This is what a bare `tradingagents` does."""
    if ctx.invoked_subcommand is not None:
        return
    if clear_checkpoints:
        from tradingagents.graph.checkpointer import clear_all_checkpoints
        n = clear_all_checkpoints(DEFAULT_CONFIG["data_cache_dir"])
        console.print(f"[yellow]Cleared {n} checkpoint(s).[/yellow]")
    portfolio_context = None
    if portfolio:
        try:
            portfolio_context = load_portfolio(portfolio)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from None

    try:
        run_analysis(checkpoint=checkpoint, portfolio=portfolio_context)
    except _NO_CONSOLE_ERRORS:
        # A terminal with no console buffer cannot host the interactive prompts.
        # Emit one actionable line on stderr instead of a prompt_toolkit
        # traceback; plain text, since rich may not render here either (#1138).
        typer.echo(
            "Error: no Windows console available. The interactive CLI needs a real "
            "console buffer — run it from Windows Terminal, PowerShell, or cmd.exe "
            "rather than a piped or embedded terminal.",
            err=True,
        )
        raise typer.Exit(code=1) from None


@app.command()
def backtest(
    tickers: str = typer.Argument(..., help="Comma-separated tickers, e.g. NVDA,AAPL"),
    start: str = typer.Option(..., "--start", help="First analysis date, YYYY-MM-DD"),
    end: str = typer.Option(..., "--end", help="Last analysis date, YYYY-MM-DD"),
    every: int = typer.Option(7, "--every", help="Days between analysis dates"),
    analysts: str = typer.Option(
        None, "--analysts", help="Comma-separated analysts to run; omit for all four"
    ),
    asset_type: str = typer.Option("stock", "--asset-type", help="stock or crypto"),
    portfolio: str = typer.Option(
        None, "--portfolio", help="JSON file with holdings and cash, held constant across the grid"
    ),
    run_id: str = typer.Option(
        None, "--run-id", help="Continue an earlier sweep: its cells are skipped and its log reused"
    ),
):
    """Score past decisions over a grid of tickers and dates."""

    try:
        dates = iter_grid(start, end, every)
        book = load_portfolio(portfolio) if portfolio else None
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    names = [t.strip() for t in tickers.split(",") if t.strip()]
    if not names:
        console.print("[red]No ticker to analyze; pass them comma-separated, e.g. NVDA,AAPL[/red]")
        raise typer.Exit(code=1)

    kwargs = {"asset_type": asset_type, "portfolio": book, "run_id": run_id}
    if analysts:
        kwargs["selected_analysts"] = [a.strip().lower() for a in analysts.split(",") if a.strip()]

    try:
        result = run_backtest(names, dates, DEFAULT_CONFIG, **kwargs)
    except Exception as exc:  # a missing key or an unknown analyst is a setup error
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    console.print(summarize(result).render())
    console.print(f"\nRan {result.cells_run} cells, skipped {result.skipped}. Log: {result.log_path}")
    for ticker, date, reason in result.failures:
        console.print(f"[yellow]failed:[/yellow] {ticker} {date}: {reason}")
    for ticker, reason in result.settlement_failures:
        console.print(f"[yellow]unsettled:[/yellow] {ticker}: {reason}")


@app.command()
def learn(
    run_id: str = typer.Argument(
        ..., help="The backtest to learn from: its folder name under <results>/backtest"
    ),
    holdout: float = typer.Option(
        0.25, "--holdout", help="Share of the latest analysis dates held out for the final score"
    ),
):
    """Test whether Jev judgments of the reports predict a backtest's outcomes."""
    from rich.markup import escape

    try:
        run_dir = Path(DEFAULT_CONFIG["results_dir"]) / "backtest" / safe_ticker_component(run_id)
    except ValueError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]")
        raise typer.Exit(code=1) from None
    if not (run_dir / "trading_memory.md").exists():
        console.print(f"[red]No backtest log in {escape(str(run_dir))}; pass the run id of a "
                      "backtest, the folder its log was written to.[/red]")
        raise typer.Exit(code=1)
    try:
        from tradingagents.report_features import JevUnavailable, learn_from_run
    except ImportError:
        console.print(escape('Learning from reports needs the jev extra: pip install "tradingagents[jev]"'),
                      style="red")
        raise typer.Exit(code=1) from None

    try:
        result = learn_from_run(run_dir, holdout=holdout)
    except (ValueError, JevUnavailable) as exc:  # too few decisions, a bad holdout, no Jev
        console.print(escape(str(exc)), style="red")
        raise typer.Exit(code=1) from None
    console.print(result.evaluation.render(), markup=False)
    console.print(f"\n{result.decisions.describe()}. Jev requests sent: {result.requests}; "
                  f"the other answers came from {result.cache_path}.")
    if len(result.models) > 1:
        console.print(f"[yellow]The answers come from several models ({', '.join(sorted(result.models))}); "
                      "pin jev_model and ask again before comparing questions.[/yellow]")
    console.print(f"Feature table: {result.table_path}", soft_wrap=True)


@app.command()
def ui(
    port: int = typer.Option(8501, "--port", help="Port to serve the UI on"),
    host: str = typer.Option("127.0.0.1", "--host", help="Address to bind; 0.0.0.0 exposes it on your network"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open a browser tab"),
):
    """Open the browser UI: live analysis, saved reports and backtests."""
    from cli.webui.server import serve

    try:
        serve(host, port, open_browser=not no_browser)
    except OSError as exc:  # port taken, or an address this machine does not have
        console.print(f"[red]Could not start the UI on {host}:{port}: {exc}[/red]")
        raise typer.Exit(code=1) from None


if __name__ == "__main__":
    app()
