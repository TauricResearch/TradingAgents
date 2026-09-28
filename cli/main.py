import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import typer

from cli.display import console
from cli.headless import (
    AssetMode,
    ResearchEffort,
    build_headless_config,
    run_headless_analysis,
)
from cli.run import run_analysis
from tradingagents.backtest import iter_grid, run_backtest, summarize
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
        if ctx.invoked_subcommand == "analyze" and (
            checkpoint is not None or clear_checkpoints or portfolio is not None
        ):
            raise typer.BadParameter(
                "Put --checkpoint/--no-checkpoint and --portfolio after 'analyze'. "
                "--clear-checkpoints is only available in interactive mode."
            )
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


@app.command("analyze")
def analyze_headless(
    symbol: str = typer.Argument(..., help="Required ticker, e.g. NVDA, 0700.HK, BTC-USD."),
    date: str | None = typer.Option(None, "--date", help="Analysis date (YYYY-MM-DD); default: today, local time."),
    analysts: str = typer.Option("all", "--analysts", help="all, or comma-separated market,social,news,fundamentals."),
    effort: ResearchEffort | None = typer.Option(
        None, "--effort", "--depth", case_sensitive=False,
        help="Research depth: shallow=1, medium=3, deep=5 debate/risk rounds. Default: medium unless env rounds are set.",
    ),
    debate_rounds: int | None = typer.Option(None, "--debate-rounds", min=1, help="Override research debate rounds."),
    risk_rounds: int | None = typer.Option(None, "--risk-rounds", min=1, help="Override risk discussion rounds."),
    asset_type: AssetMode = typer.Option(AssetMode.AUTO, "--asset-type", case_sensitive=False),
    provider: str | None = typer.Option(None, "--provider", help="LLM provider; default: .env / DEFAULT_CONFIG."),
    quick_model: str | None = typer.Option(None, "--quick-model", help="Quick-thinking model ID."),
    deep_model: str | None = typer.Option(None, "--deep-model", help="Deep-thinking model ID."),
    backend_url: str | None = typer.Option(None, "--backend-url", help="LLM API base URL."),
    header: list[str] | None = typer.Option(None, "--header", help="Extra HTTP header 'Name: value'; repeatable. Keep secrets in .env."),
    language: str | None = typer.Option(None, "--language", help="Report language; default: .env / English."),
    temperature: float | None = typer.Option(None, "--temperature", min=0),
    max_tokens: int | None = typer.Option(None, "--max-tokens", min=1),
    max_retries: int | None = typer.Option(None, "--max-retries", min=0),
    checkpoint: bool | None = typer.Option(None, "--checkpoint/--no-checkpoint", help="Override checkpoint/resume setting."),
    portfolio: Path | None = typer.Option(None, "--portfolio", exists=True, dir_okay=False, readable=True, help="JSON holdings and cash."),
    output_dir: Path | None = typer.Option(None, "--output-dir", file_okay=False, help="New/empty directory for this run; otherwise create a unique directory under results_dir/runs."),
    results_dir: Path | None = typer.Option(None, "--results-dir", file_okay=False, help="Override the results root when --output-dir is omitted."),
    json_output: bool = typer.Option(False, "--json", help="Print one machine-readable JSON summary to stdout; diagnostics go to stderr."),
):
    """Analyze SYMBOL without prompts and save reports automatically.

    Defaults: today, all applicable analysts, medium research depth. Uses the
    existing provider/model/key environment settings. Put options after analyze.
    """
    try:
        # Third-party tools can print diagnostics. Keep stdout parseable for
        # --json and keep a redirected terminal from ever entering a Live UI.
        with redirect_stdout(sys.stderr):
            config = build_headless_config(
                DEFAULT_CONFIG,
                effort=effort.value if effort is not None else None,
                debate_rounds=debate_rounds, risk_rounds=risk_rounds, headers=header,
                llm_provider=provider, quick_think_llm=quick_model, deep_think_llm=deep_model,
                backend_url=backend_url, output_language=language, temperature=temperature,
                max_tokens=max_tokens, llm_max_retries=max_retries,
                checkpoint_enabled=checkpoint,
                results_dir=str(results_dir) if results_dir is not None else None,
            )
            result = run_headless_analysis(
                symbol, config=config, analysis_date=date, analysts=analysts,
                asset_type=asset_type.value, portfolio_path=portfolio, output_dir=output_dir,
            )
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    if json_output:
        typer.echo(json.dumps(result, ensure_ascii=False))
    else:
        typer.echo(f"Analysis complete: {result['symbol']} on {result['date']}")
        typer.echo(f"Decision: {result['decision']}")
        if result["needs_review"]:
            typer.echo("No rating could be parsed; review the saved report.", err=True)
        typer.echo(f"Report: {result['report']}")
        typer.echo(f"Run directory: {result['output_dir']}")


if __name__ == "__main__":
    app()
