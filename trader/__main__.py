"""Command line: python -m trader init | daily | mark | report | resume."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

import typer
from dotenv import find_dotenv, load_dotenv

from trader import jobs, report
from trader.ledger import Ledger, locked
from trader.notify import Notifier
from trader.okx import OKX
from trader.paper import Paper
from trader.research import Researcher
from trader.settings import Settings

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def main() -> None:
    """Daily paper trading of the crypto watchlist on TradingAgents ratings."""
    load_dotenv(find_dotenv(usecwd=True))
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )


@app.command()
def init() -> None:
    """Open the paper account with TRADER_CAPITAL USDT."""
    settings = Settings.from_env()
    ledger = Ledger(settings.ledger_path)
    if ledger.initialized:
        _fail(f"{settings.ledger_path} 里已经有账户了")
    if not settings.capital:
        _fail("先在 .env 里设 TRADER_CAPITAL（模拟本金，单位 USDT）")
    ledger.initialize(settings.capital, _now_ms())
    typer.echo(f"模拟账户已建立：{settings.capital:,.2f} USDT，账本在 {settings.ledger_path}")


@app.command()
def daily() -> None:
    """Research the watchlist for the previous UTC day, trade, and send the report."""
    settings, paper, notifier = _open(require_utc=True)
    try:
        jobs.daily(settings, paper, notifier, lambda: Researcher(settings))
    except Exception as exc:
        notifier.send(f"daily 运行失败：{jobs.error_text(exc)}")
        raise


@app.command()
def mark() -> None:
    """Replay the closed minutes for stops, funding and the drawdown limit. Run hourly."""
    settings, paper, notifier = _open(require_utc=True)
    jobs.mark(settings, paper, notifier)


@app.command("report")
def report_command() -> None:
    """Print the performance of the validation period."""
    settings, paper, _ = _open()
    typer.echo(report.full(paper, settings.memory_log_path))


@app.command()
def resume() -> None:
    """Lift the kill switch, after you have checked why it tripped."""
    settings, paper, notifier = _open()
    if not paper.ledger.get("halted"):
        _fail("账户没有处于熔断")
    with locked(settings.lock_path):
        paper.resume(_now_ms())
    notifier.send("熔断已解除，下一次 daily 恢复交易。")


def _open(require_utc: bool = False) -> tuple[Settings, Paper, Notifier]:
    settings = Settings.from_env()
    notifier = Notifier(settings)
    # Dates are taken from the local clock (ADR 0002), so the scheduled jobs
    # refuse to run in any other zone.
    if require_utc and time.localtime().tm_gmtoff != 0:
        notifier.send("trader 不在 UTC 时区运行，已退出。请用 TZ=UTC 启动。")
        _fail("trader must run with TZ=UTC")
    ledger = Ledger(settings.ledger_path)
    if not ledger.initialized:
        _fail("还没有模拟账户，先运行 python -m trader init")
    return settings, Paper(ledger, OKX()), notifier


def _fail(message: str) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(1)


def _now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


if __name__ == "__main__":
    app()
