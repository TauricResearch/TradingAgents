"""The ``tradingagents backtest`` command.

Non-interactive by design, unlike ``analyze``: a backtest is long-running and
belongs in a script, a tmux pane or CI, not behind a series of prompts. Every
choice is a flag with a sensible default.

The command is two separable phases, and ``--score-only`` exposes the seam.
Producing decisions is slow and costs money; scoring them is free. Re-scoring a
finished run under a different weight map or cost model never re-runs the
agents.
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from tradingagents.backtest.portfolio import PortfolioConfig
from tradingagents.backtest.prices import benchmark_for, load_prices
from tradingagents.backtest.report import score, write_report
from tradingagents.backtest.runner import (
    BacktestRunner,
    BacktestSpec,
    default_graph_factory,
)
from tradingagents.backtest.store import DecisionStore
from tradingagents.default_config import DEFAULT_CONFIG

console = Console()


def _run_dir(results_dir: str, label: str) -> Path:
    return Path(results_dir) / "backtests" / label


def backtest(
    tickers: str = typer.Option(
        ..., "--tickers", "-t",
        help="Comma-separated tickers to replay, e.g. 'NVDA,AAPL'.",
    ),
    start: str = typer.Option(..., "--start", help="First decision date (yyyy-mm-dd)."),
    end: str = typer.Option(..., "--end", help="Last decision date (yyyy-mm-dd)."),
    every: int = typer.Option(
        5, "--every",
        help="Business days between decisions. 5 is roughly weekly and matches "
             "the holding window the decision log resolves outcomes over.",
    ),
    label: str = typer.Option(
        None, "--label",
        help="Name for this run's directory under results/backtests. "
             "Defaults to '<tickers>_<start>_<end>'. Reuse a label to resume.",
    ),
    analysts: str = typer.Option(
        "market,social,news,fundamentals", "--analysts",
        help="Comma-separated analyst team for each run.",
    ),
    workers: int = typer.Option(
        1, "--workers",
        help="Tickers to replay concurrently. Dates within one ticker always "
             "run in order, because the decision log is causal.",
    ),
    strict_pit: bool = typer.Option(
        False, "--strict-point-in-time",
        help="Abort any decision whose data requests reach past its trade date. "
             "Turns the look-ahead guarantees into an enforced invariant.",
    ),
    hold_policy: str = typer.Option(
        "carry", "--hold-policy",
        help="What a Hold rating does: 'carry' the current position (the "
             "Research Manager's definition) or go 'flat'.",
    ),
    allow_short: bool = typer.Option(
        False, "--allow-short",
        help="Act on Sell/Underweight as short positions instead of going flat.",
    ),
    commission_bps: float = typer.Option(1.0, "--commission-bps"),
    slippage_bps: float = typer.Option(5.0, "--slippage-bps"),
    capital: float = typer.Option(100_000.0, "--capital"),
    baseline_trials: int = typer.Option(
        200, "--baseline-trials",
        help="Random-rating trials for the skill baseline. 0 disables it.",
    ),
    score_only: bool = typer.Option(
        False, "--score-only",
        help="Re-score stored decisions without running any agents. Free.",
    ),
):
    """Replay the agent graph over a date range and score it as a portfolio."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    analyst_list = tuple(a.strip() for a in analysts.split(",") if a.strip())
    run_label = label or f"{'-'.join(ticker_list)}_{start}_{end}"

    config = DEFAULT_CONFIG.copy()
    out_dir = _run_dir(config["results_dir"], run_label)
    store = DecisionStore(out_dir / "decisions.jsonl")

    # Validate everything before the expensive phase. The execution rules are
    # only used when scoring, but building them after the replay would let a
    # typo in --hold-policy discard a backtest that had already been paid for.
    try:
        spec = BacktestSpec(
            tickers=ticker_list, start=start, end=end, every_n_days=every,
            selected_analysts=analyst_list, max_workers=workers,
            strict_point_in_time=strict_pit,
        )
        portfolio_config = PortfolioConfig(
            hold_policy=hold_policy, allow_short=allow_short,
            commission_bps=commission_bps, slippage_bps=slippage_bps,
            initial_cash=capital,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    runner = BacktestRunner(
        spec=spec, store=store, graph_factory=default_graph_factory(analyst_list),
        config=config, memory_dir=out_dir / "memory",
    )

    if not score_only:
        _produce(runner, spec, out_dir)

    _score(runner, store, spec, config, out_dir, portfolio_config, baseline_trials)


def _produce(runner: BacktestRunner, spec: BacktestSpec, out_dir: Path) -> None:
    """Run the agents over the schedule, showing live progress."""
    console.print(
        f"[bold]Replaying[/bold] {', '.join(spec.tickers)} "
        f"from {spec.start} to {spec.end}, every {spec.every_n_days} business day(s)."
    )
    console.print(f"Decisions are appended to [cyan]{runner.store.path}[/cyan].")
    console.print("Interrupting is safe — a later run with the same label resumes.\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        tasks = {
            ticker: progress.add_task(ticker, total=None) for ticker in spec.tickers
        }

        def on_progress(event):
            task = tasks[event.ticker]
            progress.update(
                task, total=event.total, completed=event.index,
                description=(
                    f"{event.ticker} {event.date} "
                    + ("[dim]cached[/dim]" if event.skipped
                       else f"[red]{event.error.split(':')[0]}[/red]" if event.error
                       else f"[green]{event.rating}[/green]")
                ),
            )

        runner.on_progress = on_progress
        summary = runner.run()

    console.print(
        f"\n{summary.produced} decision(s) produced, {summary.skipped} reused, "
        f"{summary.failed} failed, in {summary.wall_seconds / 60:.1f} min."
    )
    if summary.failed:
        console.print(
            "[yellow]Failed decision points are retried automatically on the "
            "next run with the same label.[/yellow]"
        )


def _score(runner, store, spec, config, out_dir, portfolio_config, baseline_trials):
    """Score stored decisions and write the report."""
    records = store.decisions(runner.signature)
    if not records:
        console.print(
            "[yellow]No stored decisions to score for this configuration.[/yellow]"
        )
        raise typer.Exit(code=1)

    benchmark = benchmark_for(spec.tickers, config)
    cache_dir = out_dir / "prices"
    console.print(f"\nLoading prices (cached in [cyan]{cache_dir}[/cyan])…")

    prices = load_prices(spec.tickers, spec.start, spec.end, cache_dir=cache_dir)
    benchmark_frame = load_prices(
        [benchmark], spec.start, spec.end, cache_dir=cache_dir
    ).get(benchmark)

    if not prices:
        console.print(
            "[red]No price history could be loaded, so the decisions cannot be "
            "scored. The stored decisions are safe — fix connectivity and re-run "
            "with --score-only.[/red]"
        )
        raise typer.Exit(code=1)

    payload = score(
        store=store,
        prices_by_ticker=prices,
        signature=runner.signature,
        benchmark=benchmark,
        benchmark_prices=benchmark_frame,
        config=portfolio_config,
        n_baseline_trials=baseline_trials,
    )
    path = write_report(payload, out_dir)

    console.print()
    console.print(Markdown(path.read_text(encoding="utf-8")))
    console.print(f"\nScorecard written to [cyan]{path}[/cyan]")
    console.print(
        "Re-score with different execution rules at no cost using "
        f"[cyan]--score-only --label {out_dir.name}[/cyan]."
    )
