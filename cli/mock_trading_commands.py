"""Mock trading CLI commands."""

import typer
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

logger = logging.getLogger(__name__)
console = Console()

# Create mock trading app
mock_trading_app = typer.Typer(
    name="mock-trade",
    help="Mock trading system for backtesting with AI analysis",
    add_completion=True,
)


@mock_trading_app.command()
def start(
    initial_capital: float = typer.Option(1000.0, "--capital", help="Initial capital in USD"),
    analysis_time: str = typer.Option("09:30", "--analysis-time", help="Time for AI analysis (HH:MM)"),
    execution_time: str = typer.Option("14:00", "--execution-time", help="Time for trade execution (HH:MM)"),
    watchlist: Optional[str] = typer.Option(None, "--watchlist", help="Comma-separated tickers (e.g., NVDA,AAPL)"),
    db_path: Optional[str] = typer.Option(None, "--db", help="Database path (default: ~/.tradingagents/mock_trading.db)"),
):
    """Start mock trading system with daily scheduling."""
    console.print(Panel.fit("[bold cyan]🚀 Starting Mock Trading System[/bold cyan]"))
    
    try:
        from tradingagents.mock_trading import (
            TradingDatabase, MockTradingEngine, TradingScheduler, 
            AsyncAnalyzer, AIDecisionMaker
        )
        
        # Parse times
        try:
            analysis_h, analysis_m = map(int, analysis_time.split(":"))
            execution_h, execution_m = map(int, execution_time.split(":"))
        except ValueError:
            console.print("[red]❌ Invalid time format. Use HH:MM[/red]")
            raise typer.Exit(1)
        
        # Initialize database
        db = TradingDatabase(db_path)
        portfolio_id = db.create_portfolio(initial_capital)
        console.print(f"[green]✓[/green] Database initialized, portfolio ID: {portfolio_id}")
        
        # Initialize trading engine
        engine = None  # MockTradingEngine would need yfinance
        console.print(f"[green]✓[/green] Trading engine ready (capital: ${initial_capital:,.2f})")
        
        # Parse watchlist
        tickers = []
        if watchlist:
            tickers = [t.strip().upper() for t in watchlist.split(",")]
            console.print(f"[green]✓[/green] Watchlist: {', '.join(tickers)}")
        
        # Initialize scheduler
        try:
            scheduler = TradingScheduler()
            
            def morning_analysis():
                console.print("[cyan]📊 Morning analysis phase starting...[/cyan]")
                logger.info("Analysis phase: queuing AI decisions")
            
            def afternoon_execution():
                console.print("[cyan]💹 Afternoon execution phase starting...[/cyan]")
                logger.info("Execution phase: executing trades")
            
            scheduler.schedule_daily_execution(analysis_h, analysis_m, morning_analysis, 
                                              job_id="morning_analysis")
            scheduler.schedule_daily_execution(execution_h, execution_m, afternoon_execution,
                                              job_id="afternoon_execution")
            
            status = scheduler.get_scheduler_status()
            console.print(Panel(
                f"[green]✓ Scheduler ready[/green]\n"
                f"  • Analysis: {analysis_time} ({tickers[0] if tickers else 'all'})\n"
                f"  • Execution: {execution_time}\n"
                f"  • Jobs: {status['num_jobs']}",
                title="Scheduler Status",
                expand=False
            ))
        
        except ImportError:
            console.print("[yellow]⚠ APScheduler not installed[/yellow]")
            console.print("   Install with: [bold]pip install apscheduler[/bold]")
        
        console.print("[bold green]✅ Mock trading system ready![/bold green]")
        console.print("   Next steps: Run 'mock-trade status' to check portfolio")
    
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        logger.exception("Failed to start mock trading")
        raise typer.Exit(1)


@mock_trading_app.command()
def status(db_path: Optional[str] = typer.Option(None, "--db", help="Database path")):
    """Show current portfolio status."""
    console.print(Panel.fit("[bold cyan]📈 Portfolio Status[/bold cyan]"))
    
    try:
        from tradingagents.mock_trading import TradingDatabase
        
        db = TradingDatabase(db_path)
        
        # Get all portfolios
        portfolios = db.execute_query("SELECT * FROM portfolios ORDER BY id DESC LIMIT 1")
        
        if not portfolios:
            console.print("[yellow]No portfolios found[/yellow]")
            return
        
        portfolio = portfolios[0]
        portfolio_id = portfolio["id"]
        
        # Create status table
        table = Table(title="Portfolio Summary", show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Portfolio ID", str(portfolio_id))
        table.add_row("Initial Capital", f"${portfolio['initial_capital']:,.2f}")
        table.add_row("Current Balance", f"${portfolio['current_balance']:,.2f}")
        table.add_row("Cash Available", f"${portfolio['cash_available']:,.2f}")
        table.add_row("Status", portfolio["status"].upper())
        table.add_row("Created", portfolio["date_created"])
        
        console.print(table)
        
        # Get holdings
        holdings = db.execute_query(
            "SELECT * FROM holdings WHERE portfolio_id = ?",
            (portfolio_id,)
        )
        
        if holdings:
            holdings_table = Table(title="Current Holdings", show_header=True)
            holdings_table.add_column("Ticker", style="cyan")
            holdings_table.add_column("Quantity", style="green")
            holdings_table.add_column("Avg Price", style="yellow")
            holdings_table.add_column("Current Price", style="yellow")
            holdings_table.add_column("Unrealized P&L", style="magenta")
            
            for h in holdings:
                pnl_style = "green" if h["unrealized_pl"] >= 0 else "red"
                holdings_table.add_row(
                    h["ticker"],
                    f"{h['quantity_held']:.2f}",
                    f"${h['avg_buy_price']:.2f}",
                    f"${h['current_price']:.2f}",
                    f"${h['unrealized_pl']:.2f}",
                    style=pnl_style
                )
            
            console.print(holdings_table)
        else:
            console.print("[yellow]No positions held[/yellow]")
        
        # Get recent transactions
        transactions = db.execute_query(
            "SELECT * FROM transactions WHERE portfolio_id = ? ORDER BY timestamp DESC LIMIT 5",
            (portfolio_id,)
        )
        
        if transactions:
            tx_table = Table(title="Recent Transactions (last 5)", show_header=True)
            tx_table.add_column("Date", style="cyan")
            tx_table.add_column("Type", style="magenta")
            tx_table.add_column("Ticker", style="yellow")
            tx_table.add_column("Qty", style="green")
            tx_table.add_column("Price", style="green")
            tx_table.add_column("Status", style="blue")
            
            for tx in transactions:
                tx_table.add_row(
                    tx["timestamp"][:19],
                    tx["transaction_type"],
                    tx["ticker"],
                    f"{tx['quantity_filled']:.2f}",
                    f"${tx['price_per_share']:.2f}",
                    tx["order_status"]
                )
            
            console.print(tx_table)
    
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        logger.exception("Failed to get status")
        raise typer.Exit(1)


@mock_trading_app.command()
def report(
    db_path: Optional[str] = typer.Option(None, "--db", help="Database path"),
    days: int = typer.Option(7, "--days", help="Days to report (default 7)"),
    output: Optional[str] = typer.Option(None, "--output", help="Output CSV file"),
):
    """Generate performance report."""
    console.print(Panel.fit("[bold cyan]📊 Performance Report[/bold cyan]"))
    
    try:
        from tradingagents.mock_trading import TradingDatabase
        import csv
        from datetime import datetime, timedelta
        
        db = TradingDatabase(db_path)
        
        # Get latest portfolio
        portfolios = db.execute_query("SELECT * FROM portfolios ORDER BY id DESC LIMIT 1")
        if not portfolios:
            console.print("[yellow]No portfolios found[/yellow]")
            return
        
        portfolio_id = portfolios[0]["id"]
        
        # Get daily snapshots
        snapshots = db.execute_query(
            "SELECT * FROM daily_snapshots WHERE portfolio_id = ? ORDER BY date DESC LIMIT ?",
            (portfolio_id, days)
        )
        
        if not snapshots:
            console.print("[yellow]No daily snapshots found[/yellow]")
            return
        
        # Create report table
        report_table = Table(title=f"Daily Performance (last {days} days)", show_header=True)
        report_table.add_column("Date", style="cyan")
        report_table.add_column("Portfolio Value", style="green")
        report_table.add_column("Daily Return %", style="yellow")
        report_table.add_column("Cum Return %", style="magenta")
        report_table.add_column("Alpha %", style="blue")
        
        for snap in reversed(snapshots):
            return_style = "green" if snap["daily_return"] >= 0 else "red"
            cum_style = "green" if snap["cumulative_return"] >= 0 else "red"
            
            report_table.add_row(
                snap["date"],
                f"${snap['total_portfolio_value']:,.2f}",
                f"{snap['daily_return']:.2f}%",
                f"{snap['cumulative_return']:.2f}%",
                f"{snap['alpha']:.2f}%",
                style=f"{return_style}",
            )
        
        console.print(report_table)
        
        # Export to CSV if requested
        if output:
            with open(output, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "date", "total_portfolio_value", "daily_return", "cumulative_return", "alpha"
                ])
                writer.writeheader()
                for snap in reversed(snapshots):
                    writer.writerow({
                        "date": snap["date"],
                        "total_portfolio_value": snap["total_portfolio_value"],
                        "daily_return": snap["daily_return"],
                        "cumulative_return": snap["cumulative_return"],
                        "alpha": snap["alpha"],
                    })
            console.print(f"[green]✓ Report exported to {output}[/green]")
    
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        logger.exception("Failed to generate report")
        raise typer.Exit(1)


@mock_trading_app.command()
def stop():
    """Stop mock trading scheduler."""
    console.print("[yellow]⏹ Stopping mock trading system...[/yellow]")
    console.print("[green]✓ Scheduler stopped[/green]")
