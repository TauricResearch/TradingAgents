"""CLI commands for portfolio management."""

import typer
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm
from datetime import datetime

from tradingagents.portfolio import PortfolioStore, PositionRecord, Transaction

portfolio_app = typer.Typer(help="Manage your portfolio positions and transactions.")
tx_app = typer.Typer(help="Manage transaction records.")
portfolio_app.add_typer(tx_app, name="tx")

console = Console()


def _get_store() -> PortfolioStore:
    """Get portfolio store instance."""
    return PortfolioStore()


@portfolio_app.command("add")
def portfolio_add():
    """Interactively add a new position to your portfolio."""
    console.print("\n[bold cyan]Add New Position[/bold cyan]\n")

    ticker = Prompt.ask("Stock ticker (e.g., NVDA, 000404.SH)")
    if not ticker.strip():
        console.print("[red]Ticker cannot be empty.[/red]")
        raise typer.Exit(1)

    entry_date = Prompt.ask("Entry date (YYYY-MM-DD)", default=datetime.now().strftime("%Y-%m-%d"))
    entry_price = float(Prompt.ask("Average entry price"))
    quantity = float(Prompt.ask("Quantity (shares)"))
    side = Prompt.ask("Side", choices=["long", "short"], default="long")
    note = Prompt.ask("Note (optional, press Enter to skip)", default="")

    # Confirm
    console.print(f"\n[yellow]Confirm:[/yellow] {ticker.upper()} | {side} | {quantity} shares @ {entry_price} | {entry_date}")
    if not Confirm.ask("Save this position?"):
        console.print("[dim]Cancelled.[/dim]")
        raise typer.Exit()

    store = _get_store()
    position = PositionRecord(
        ticker=ticker.upper().strip(),
        entry_date=entry_date,
        entry_price=entry_price,
        quantity=quantity,
        side=side,
        note=note,
    )
    store.add_position(position)
    console.print("[green]Position added successfully![/green]")


@portfolio_app.command("remove")
def portfolio_remove():
    """Remove a position from your portfolio."""
    store = _get_store()
    positions = store.list_positions()

    if not positions:
        console.print("[yellow]No positions in portfolio.[/yellow]")
        raise typer.Exit()

    # Show current positions
    console.print("\n[bold]Current Positions:[/bold]")
    for i, p in enumerate(positions, 1):
        console.print(f"  {i}. {p.ticker} | {p.quantity} shares @ {p.entry_price} | {p.entry_date}")

    ticker = Prompt.ask("\nTicker to remove")
    if store.remove_position(ticker):
        console.print(f"[green]Removed all positions for {ticker.upper()}.[/green]")
    else:
        console.print(f"[red]No position found for {ticker.upper()}.[/red]")


@portfolio_app.command("list")
def portfolio_list():
    """List all positions in your portfolio."""
    store = _get_store()
    positions = store.list_positions()

    if not positions:
        console.print("[yellow]Portfolio is empty. Use 'portfolio add' to add positions.[/yellow]")
        raise typer.Exit()

    table = Table(title="Portfolio Positions", show_lines=True)
    table.add_column("Ticker", style="cyan", no_wrap=True)
    table.add_column("Side", style="dim")
    table.add_column("Quantity", justify="right")
    table.add_column("Entry Price", justify="right")
    table.add_column("Cost Basis", justify="right", style="yellow")
    table.add_column("Entry Date")
    table.add_column("Note", style="dim")

    total_cost = 0.0
    for p in positions:
        cost = p.entry_price * p.quantity
        total_cost += cost
        table.add_row(
            p.ticker,
            p.side,
            f"{p.quantity:,.2f}",
            f"{p.entry_price:,.4f}",
            f"{cost:,.2f}",
            p.entry_date,
            p.note or "-",
        )

    console.print(table)
    console.print(f"\n[bold]Total Cost Basis:[/bold] {total_cost:,.2f}")
    console.print(f"[bold]Total Positions:[/bold] {len(positions)}")


@portfolio_app.command("clear")
def portfolio_clear():
    """Clear all portfolio data (positions and transactions)."""
    if not Confirm.ask("[red]Are you sure you want to clear ALL portfolio data?[/red]"):
        console.print("[dim]Cancelled.[/dim]")
        raise typer.Exit()

    store = _get_store()
    store.clear()
    console.print("[green]Portfolio data cleared.[/green]")


# ─── Transaction subcommands ──────────────────────────────────


@tx_app.command("add")
def tx_add():
    """Add a transaction record."""
    console.print("\n[bold cyan]Add Transaction[/bold cyan]\n")

    ticker = Prompt.ask("Stock ticker")
    action = Prompt.ask("Action", choices=["buy", "sell"])
    date = Prompt.ask("Date (YYYY-MM-DD)", default=datetime.now().strftime("%Y-%m-%d"))
    price = float(Prompt.ask("Price"))
    quantity = float(Prompt.ask("Quantity"))
    note = Prompt.ask("Note (optional)", default="")

    console.print(f"\n[yellow]Confirm:[/yellow] {action.upper()} {ticker.upper()} | {quantity} shares @ {price} | {date}")
    if not Confirm.ask("Save this transaction?"):
        console.print("[dim]Cancelled.[/dim]")
        raise typer.Exit()

    store = _get_store()
    tx = Transaction(
        ticker=ticker.upper().strip(),
        action=action,
        date=date,
        price=price,
        quantity=quantity,
        note=note,
    )
    store.add_transaction(tx)
    console.print("[green]Transaction recorded![/green]")


@tx_app.command("list")
def tx_list(
    ticker: str = typer.Option(None, "--ticker", "-t", help="Filter by ticker"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max records to show"),
):
    """List transaction records."""
    store = _get_store()
    txs = store.list_transactions(ticker=ticker, limit=limit)

    if not txs:
        msg = "No transactions found"
        if ticker:
            msg += f" for {ticker.upper()}"
        console.print(f"[yellow]{msg}.[/yellow]")
        raise typer.Exit()

    table = Table(title="Transaction History", show_lines=True)
    table.add_column("Date", style="dim")
    table.add_column("Ticker", style="cyan")
    table.add_column("Action", no_wrap=True)
    table.add_column("Quantity", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Total", justify="right", style="yellow")
    table.add_column("Note", style="dim")

    for tx in txs:
        action_style = "[green]BUY[/green]" if tx.action == "buy" else "[red]SELL[/red]"
        table.add_row(
            tx.date,
            tx.ticker,
            action_style,
            f"{tx.quantity:,.2f}",
            f"{tx.price:,.4f}",
            f"{tx.price * tx.quantity:,.2f}",
            tx.note or "-",
        )

    console.print(table)
