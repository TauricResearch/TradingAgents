import datetime
from decimal import Decimal
from datetime import date as date_type

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from tradingagents.backtesting import SimpleBacktestEngine
from tradingagents.models.backtest import BacktestConfig, BacktestStatus
from tradingagents.models.portfolio import PortfolioConfig

from cli.display import create_question_box
from cli.utils import loading

console = Console()


def sma_buy(ticker: str, trading_date: date_type, ctx: dict) -> bool:
    loader = ctx["data_loader"]
    ohlcv = loader.load_ohlcv(ticker, date_type(2020, 1, 1), trading_date)
    if len(ohlcv.bars) < 20:
        return False
    prices = [float(b.close) for b in ohlcv.bars[-20:]]
    sma = sum(prices) / len(prices)
    current = float(ohlcv.bars[-1].close)
    return current > sma * 1.02


def sma_sell(ticker: str, trading_date: date_type, ctx: dict) -> bool:
    loader = ctx["data_loader"]
    ohlcv = loader.load_ohlcv(ticker, date_type(2020, 1, 1), trading_date)
    if len(ohlcv.bars) < 20:
        return False
    prices = [float(b.close) for b in ohlcv.bars[-20:]]
    sma = sum(prices) / len(prices)
    current = float(ohlcv.bars[-1].close)
    return current < sma * 0.98


def rsi_buy(ticker: str, trading_date: date_type, ctx: dict) -> bool:
    loader = ctx["data_loader"]
    ohlcv = loader.load_ohlcv(ticker, date_type(2020, 1, 1), trading_date)
    if len(ohlcv.bars) < 15:
        return False
    changes = []
    for i in range(1, min(15, len(ohlcv.bars))):
        changes.append(float(ohlcv.bars[-i].close) - float(ohlcv.bars[-i-1].close))
    gains = [c for c in changes if c > 0]
    losses = [-c for c in changes if c < 0]
    avg_gain = sum(gains) / 14 if gains else 0.001
    avg_loss = sum(losses) / 14 if losses else 0.001
    rs = avg_gain / avg_loss if avg_loss else 100
    rsi = 100 - (100 / (1 + rs))
    return rsi < 30


def rsi_sell(ticker: str, trading_date: date_type, ctx: dict) -> bool:
    loader = ctx["data_loader"]
    ohlcv = loader.load_ohlcv(ticker, date_type(2020, 1, 1), trading_date)
    if len(ohlcv.bars) < 15:
        return False
    changes = []
    for i in range(1, min(15, len(ohlcv.bars))):
        changes.append(float(ohlcv.bars[-i].close) - float(ohlcv.bars[-i-1].close))
    gains = [c for c in changes if c > 0]
    losses = [-c for c in changes if c < 0]
    avg_gain = sum(gains) / 14 if gains else 0.001
    avg_loss = sum(losses) / 14 if losses else 0.001
    rs = avg_gain / avg_loss if avg_loss else 100
    rsi = 100 - (100 / (1 + rs))
    return rsi > 70


def hold_buy(ticker: str, trading_date: date_type, ctx: dict) -> bool:
    return ctx.get("day_index", 0) == 5


def hold_sell(ticker: str, trading_date: date_type, ctx: dict) -> bool:
    return False


STRATEGIES = {
    "sma": (sma_buy, sma_sell),
    "rsi": (rsi_buy, rsi_sell),
    "hold": (hold_buy, hold_sell),
}


def run_backtest(
    ticker: str = None,
    start_date: str = None,
    end_date: str = None,
    initial_cash: float = 100000.0,
    strategy: str = "sma",
) -> None:
    if not ticker:
        console.print(create_question_box("Ticker Symbol", "Enter the ticker symbol to backtest", "AAPL"))
        ticker = typer.prompt("", default="AAPL")

    if not start_date:
        default_start = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
        console.print(create_question_box("Start Date", "Enter backtest start date (YYYY-MM-DD)", default_start))
        start_date = typer.prompt("", default=default_start)

    if not end_date:
        default_end = datetime.datetime.now().strftime("%Y-%m-%d")
        console.print(create_question_box("End Date", "Enter backtest end date (YYYY-MM-DD)", default_end))
        end_date = typer.prompt("", default=default_end)

    try:
        start = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        console.print("[red]Invalid date format. Use YYYY-MM-DD[/red]")
        return

    if start >= end:
        console.print("[red]Start date must be before end date[/red]")
        return

    console.print()
    console.print(Panel(
        f"[bold]Backtest Configuration[/bold]\n\n"
        f"Ticker: [cyan]{ticker.upper()}[/cyan]\n"
        f"Period: [cyan]{start_date}[/cyan] to [cyan]{end_date}[/cyan]\n"
        f"Initial Cash: [cyan]${initial_cash:,.2f}[/cyan]\n"
        f"Strategy: [cyan]{strategy}[/cyan]",
        title="Configuration",
        border_style="blue",
    ))
    console.print()

    if strategy not in STRATEGIES:
        console.print(f"[red]Unknown strategy: {strategy}. Use: sma, rsi, or hold[/red]")
        return

    buy_fn, sell_fn = STRATEGIES[strategy]

    config = BacktestConfig(
        name=f"{strategy.upper()} Backtest - {ticker.upper()}",
        tickers=[ticker.upper()],
        start_date=start,
        end_date=end,
        portfolio_config=PortfolioConfig(
            initial_cash=Decimal(str(initial_cash)),
            commission_per_trade=Decimal("1"),
            slippage_percent=Decimal("0.05"),
        ),
        warmup_period=5,
    )

    with loading("Running backtest...", show_elapsed=True):
        engine = SimpleBacktestEngine(config, buy_signal=buy_fn, sell_signal=sell_fn)
        result = engine.run()

    console.print()

    if result.status == BacktestStatus.FAILED:
        console.print(f"[red]Backtest failed: {result.error_message}[/red]")
        return

    metrics = result.metrics
    trade_log = result.trade_log

    performance_table = Table(title="Performance Metrics", box=box.ROUNDED)
    performance_table.add_column("Metric", style="cyan")
    performance_table.add_column("Value", style="green")

    performance_table.add_row("Total Return", f"${float(metrics.total_return):,.2f}")
    performance_table.add_row("Total Return %", f"{float(metrics.total_return_percent):.2f}%")
    performance_table.add_row("Annualized Return", f"{float(metrics.annualized_return):.2f}%")
    performance_table.add_row("Sharpe Ratio", f"{float(metrics.sharpe_ratio):.2f}" if metrics.sharpe_ratio else "N/A")
    performance_table.add_row("Sortino Ratio", f"{float(metrics.sortino_ratio):.2f}" if metrics.sortino_ratio else "N/A")
    performance_table.add_row("Max Drawdown", f"{float(metrics.max_drawdown_percent):.2f}%")
    performance_table.add_row("Volatility (Ann.)", f"{float(metrics.annualized_volatility):.2f}%")

    console.print(performance_table)
    console.print()

    trading_table = Table(title="Trading Statistics", box=box.ROUNDED)
    trading_table.add_column("Metric", style="cyan")
    trading_table.add_column("Value", style="green")

    trading_table.add_row("Total Trades", str(trade_log.total_trades))
    trading_table.add_row("Winning Trades", str(trade_log.winning_trades))
    trading_table.add_row("Losing Trades", str(trade_log.losing_trades))
    trading_table.add_row("Win Rate", f"{float(trade_log.win_rate):.1f}%" if trade_log.win_rate else "N/A")
    trading_table.add_row("Profit Factor", f"{float(trade_log.profit_factor):.2f}" if trade_log.profit_factor else "N/A")
    trading_table.add_row("Avg Win", f"${float(trade_log.avg_win):,.2f}" if trade_log.avg_win else "N/A")
    trading_table.add_row("Avg Loss", f"${float(trade_log.avg_loss):,.2f}" if trade_log.avg_loss else "N/A")

    console.print(trading_table)
    console.print()

    summary_table = Table(title="Portfolio Summary", box=box.ROUNDED)
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")

    summary_table.add_row("Start Equity", f"${float(metrics.start_equity):,.2f}")
    summary_table.add_row("End Equity", f"${float(metrics.end_equity):,.2f}")
    summary_table.add_row("Trading Days", str(metrics.trading_days))
    summary_table.add_row("Duration", f"{result.duration_seconds:.1f} seconds")

    console.print(summary_table)
    console.print()

    console.print(f"[green]Backtest completed successfully![/green]")
