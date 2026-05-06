"""``tradingagents kalshi-run`` — slim CLI for the prediction-market pipeline.

Wraps ``tradingagents.execution.runner.run_contract`` with a friendly
typer interface. Live trading requires ``--live`` AND
``paper_mode=False`` in config AND ``TRADINGAGENTS_LIVE_DISABLED`` unset.
Anything less downgrades to paper mode automatically (with a clear log).
"""

from __future__ import annotations

import datetime
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.execution import runner, safety


load_dotenv()
load_dotenv(".env.enterprise", override=False)
console = Console()


def kalshi_run_command(
    contract_id: str = typer.Argument(
        ..., help="Kalshi contract identifier, e.g. KXBTCD-26MAY05-T100000."
    ),
    trade_date: Optional[str] = typer.Option(
        None,
        "--date",
        "-d",
        help="Decision date (YYYY-MM-DD). Defaults to today.",
    ),
    live: bool = typer.Option(
        False,
        "--live",
        help=(
            "Opt-in to live trading. Even with this flag, paper_mode in config "
            "and the TRADINGAGENTS_LIVE_DISABLED env var both need to be off."
        ),
    ),
    bankroll_usd: Optional[float] = typer.Option(
        None,
        "--bankroll",
        help="Override the bankroll used for Kelly sizing (defaults to live balance / $1000 paper).",
    ),
    quick_model: Optional[str] = typer.Option(
        None,
        "--quick-model",
        help="Override quick_think_llm (e.g. gpt-5.4-mini, claude-haiku-4-5).",
    ),
    deep_model: Optional[str] = typer.Option(
        None,
        "--deep-model",
        help="Override deep_think_llm.",
    ),
):
    """Run the full agent committee on a Kalshi contract and (optionally) place the order."""
    trade_date = trade_date or datetime.date.today().isoformat()

    config = DEFAULT_CONFIG.copy()
    if quick_model:
        config["quick_think_llm"] = quick_model
    if deep_model:
        config["deep_think_llm"] = deep_model

    mode = safety.resolve_mode(requested_live=live, config=config)

    console.print(
        Panel(
            f"Contract: [bold]{contract_id}[/bold]\n"
            f"Date: {trade_date}\n"
            f"Mode: [{'red bold' if mode == 'live' else 'green'}]{mode.upper()}[/]",
            title="Kalshi Run",
            border_style="cyan",
        )
    )

    if live and mode != "live":
        console.print(
            "[yellow]--live was passed but the run resolved to paper mode. "
            f"Check kalshi.paper_mode (config={config['kalshi']['paper_mode']}) "
            f"and the {safety.KILL_SWITCH_ENV} env var.[/yellow]"
        )

    result = runner.run_contract(
        contract_id=contract_id,
        trade_date=trade_date,
        requested_live=live,
        config=config,
        bankroll_usd=bankroll_usd,
    )

    console.print()
    console.print(Panel(Markdown(result.final_decision_markdown), title="Portfolio Manager Decision"))

    if result.stake_plan is not None:
        plan = result.stake_plan
        table = Table(title="Stake plan", show_lines=False)
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")
        table.add_row("Side", plan.side.value)
        table.add_row("Contracts", str(plan.contract_count))
        table.add_row("Entry price (¢)", str(plan.price_cents))
        table.add_row("Stake (USD)", f"${plan.stake_usd:,.2f}")
        table.add_row("Full Kelly", f"{plan.full_kelly_fraction:.4f}")
        table.add_row("Discounted fraction", f"{plan.discounted_fraction:.4f}")
        table.add_row("Notes", plan.notes)
        console.print(table)

    summary = Table(title="Run summary")
    summary.add_column("Field", style="cyan")
    summary.add_column("Value", style="white")
    summary.add_row("Decision id", result.decision_id)
    summary.add_row("Mode", result.mode)
    summary.add_row("Venue order id", str(result.venue_order_id) if result.venue_order_id else "—")
    summary.add_row("Notes", result.notes)
    console.print(summary)


def kalshi_settle_command():
    """Walk the order ledger and settle anything Kalshi has finalized."""
    config = DEFAULT_CONFIG.copy()
    summary = runner.settle_pending(config=config)

    table = Table(title="Settlement summary")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Settled this run", str(summary["settled"]))
    console.print(table)

    if not summary["updates"]:
        console.print("[dim]No open contracts had settled outcomes available.[/dim]")
        return

    detail = Table(title="Updates")
    detail.add_column("Decision id", style="cyan")
    detail.add_column("Contract", style="white")
    detail.add_column("Outcome", style="green")
    detail.add_column("Realized P&L (USD)", style="yellow")
    for u in summary["updates"]:
        detail.add_row(
            u["decision_id"][:8],
            u["contract_id"],
            u["outcome"],
            f"${u['realized_pnl_usd']:+,.2f}",
        )
    console.print(detail)


app = typer.Typer(name="kalshi", help="Kalshi prediction-market commands.")
app.command("run")(kalshi_run_command)
app.command("settle")(kalshi_settle_command)


if __name__ == "__main__":
    app()
