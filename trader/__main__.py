"""Command line: python -m trader init | daily | mark | report | resume | backup, the
intraday account's python -m trader intraday init | run | report | resume, and the demo
account's python -m trader demo check | init | run | sync | report | resume (ADR 0008)."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import typer
from dotenv import find_dotenv, load_dotenv

from trader import backup as account_backup, jobs, report
from trader.demo import job as demo_job, report as demo_report
from trader.demo.account import DemoAccount
from trader.intraday import job as intraday_job, report as intraday_report
from trader.intraday.paper import IntradayPaper, utc_date
from trader.ledger import Ledger, locked
from trader.notify import Notifier
from trader.okx import OKX, REQUEST_ERRORS
from trader.okx_private import OKXPrivate, OKXPrivateError
from trader.paper import Paper
from trader.research import Researcher
from trader.settings import WATCHLIST, Settings

app = typer.Typer(add_completion=False, no_args_is_help=True)
intraday_app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(intraday_app, name="intraday")
demo_app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(demo_app, name="demo")

DEMO_ENV = "TRADER_OKX_DEMO_KEY / TRADER_OKX_DEMO_SECRET / TRADER_OKX_DEMO_PASSPHRASE"


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


@app.command()
def backup(
    dest: Path,
    with_logs: bool = typer.Option(False, "--with-logs", help="也拷贝 logs/ 下的研究记录"),
) -> None:
    """Copy the account directory (the ledgers, settings, memory) into DEST/<UTC time>/.

    The ledgers are snapshotted through SQLite, which is consistent while a job writes;
    copying ledger.sqlite by hand is not, as the latest commits sit in its -wal file.
    """
    settings = Settings.from_env()
    try:
        target, copied = account_backup.backup(settings.home, dest, with_logs)
    except (FileNotFoundError, FileExistsError) as exc:
        _fail(str(exc))
    typer.echo(f"已备份到 {target}")
    for rel, size in copied:
        typer.echo(f"  {rel}  {size:,} B")
    if not settings.intraday_ledger_path.exists():
        typer.echo("  （没有日内账本，跳过）")


@intraday_app.callback()
def intraday_main() -> None:
    """The intraday account: a second paper account deciding hourly (ADR 0006)."""


@intraday_app.command("init")
def intraday_init() -> None:
    """Open the intraday paper account with TRADER_CAPITAL USDT."""
    settings = Settings.from_env()
    ledger = Ledger(settings.intraday_ledger_path)
    if ledger.initialized:
        _fail(f"{settings.intraday_ledger_path} 里已经有账户了")
    if not settings.capital:
        _fail("先在 .env 里设 TRADER_CAPITAL（模拟本金，单位 USDT）")
    now_ms = _now_ms()
    ledger.initialize(settings.capital, now_ms)
    # The day before the account existed has nothing to summarize: without this the
    # first run would send a summary of zero fills and zero signals.
    ledger.set("summarized_day", utc_date(now_ms))
    typer.echo(
        f"日内模拟账户已建立：{settings.capital:,.2f} USDT，账本在 {settings.intraday_ledger_path}"
    )


@intraday_app.command("run")
def intraday_run() -> None:
    """Replay, decide this hour's signals, trade, and report. Run hourly."""
    # The signal module is developed on its own (ticket T2), so it is imported here,
    # where it is needed, rather than at the top of the command line.
    from trader.intraday.signal import Signaler

    settings, paper, notifier = _open_intraday(require_utc=True)
    intraday_job.run(settings, paper, notifier, Signaler(settings, paper.okx))


@intraday_app.command("report")
def intraday_report_command() -> None:
    """Print the performance of the intraday account's validation period."""
    _, paper, _ = _open_intraday()
    typer.echo(intraday_report.full(paper))


@intraday_app.command("resume")
def intraday_resume() -> None:
    """Lift the intraday account's kill switch, after you have checked why it tripped."""
    settings, paper, notifier = _open_intraday()
    if not paper.ledger.get("halted"):
        _fail("日内账户没有处于熔断")
    with locked(settings.intraday_lock_path):
        paper.resume(_now_ms())
    notifier.send("日内账户熔断已解除，下一小时恢复交易。")


@demo_app.callback()
def demo_main() -> None:
    """The demo account: real orders on OKX's simulated trading (ADR 0008)."""


@demo_app.command("check")
def demo_check() -> None:
    """Read the simulated account's mode, permissions, USDT balance and positions
    with the key in .env; places nothing."""
    _, client = _demo_client()
    try:
        config = client.account_config()
        balance = client.balance()
        positions = client.positions()
        stops = client.pending_stops()
        trade_error = _trade_permission_error(client)
    except REQUEST_ERRORS as exc:
        _fail(f"OKX 模拟盘没有应答：{jobs.error_text(exc)}")
    levels = {"1": "现货", "2": "合约模式（单币种保证金）", "3": "跨币种保证金", "4": "组合保证金"}
    typer.echo(
        f"模拟账户可用。持仓模式 {config.position_mode}，"
        f"账户模式 {levels.get(config.account_level, config.account_level)}，权限 {config.permissions}"
    )
    typer.echo(
        f"USDT 权益 {balance.equity:,.2f}，钱包 {balance.cash:,.2f}，可用 {balance.available:,.2f}，"
        f"未实现 {balance.unrealized:+,.2f}"
    )
    typer.echo(f"持仓 {len(positions)} 个，挂着的止损单 {len(stops)} 张")
    for p in positions:
        typer.echo(f"  {p.inst} {p.contracts:+g} 张 @ {p.avg_price:,.2f}，{p.margin_mode} {p.leverage:g}×")
    for s in stops:
        typer.echo(f"  止损 {s.inst} {s.side} {s.contracts:g} 张，触发 {s.trigger:,.2f}")
    if config.position_mode != "net_mode":
        typer.echo("注意：demo 账户按单向持仓（net_mode）设计，首次运行会切换；要求当时没有持仓和挂单。")
    if config.account_level == "1":
        typer.echo("注意：现货模式不能交易合约，请在 OKX 模拟盘把账户模式改成合约模式（以前叫单币种保证金）或跨币种保证金。")
    if trade_error:
        typer.echo(f"注意：{trade_error}")
    else:
        typer.echo("交易权限正常（试了一次不存在订单的撤单，没有下单）。")


@demo_app.command("init")
def demo_init() -> None:
    """Open the demo account on the simulated exchange's USDT balance: the account must
    be flat with no pending orders; it is put in net mode at cross LEVERAGE."""
    settings, client = _demo_client()
    ledger = Ledger(settings.demo_ledger_path)
    if ledger.initialized:
        _fail(f"{settings.demo_ledger_path} 里已经有账户了")
    if not settings.intraday_ledger_path.exists():
        _fail("demo 跟随日内账户的信号，先要有日内账户：python -m trader intraday init")
    account = DemoAccount(ledger, OKX(), client)
    try:
        trade_error = _trade_permission_error(client)
        if trade_error:
            _fail(trade_error)
        if client.positions():
            _fail("模拟账户里还有持仓，先在 OKX 平掉再 init")
        if client.pending_stops():
            _fail("模拟账户里还挂着条件单，先在 OKX 撤掉再 init")
        notes = account.setup()
        balance = client.balance()
    except REQUEST_ERRORS as exc:
        _fail(f"OKX 模拟盘没有应答：{jobs.error_text(exc)}")
    if balance.cash <= 0:
        _fail("模拟账户里没有 USDT，先在 OKX 模拟盘领取资金")
    now_ms = _now_ms()
    ledger.initialize(balance.cash, now_ms)
    ledger.set("summarized_day", utc_date(now_ms))
    ledger.set("setup_done", True)
    for note in notes:
        ledger.add_event(now_ms, "setup", note)
        typer.echo(note)
    typer.echo(f"demo 账户已建立：本金 {balance.cash:,.2f} USDT（模拟账户钱包余额），账本在 {settings.demo_ledger_path}")


@demo_app.command("run")
def demo_run() -> None:
    """Sync, keep the stops, follow this hour's intraday signals on the exchange, report.
    Run hourly after the intraday job."""
    settings, account, notifier, intraday = _open_demo(require_utc=True)
    demo_job.run(settings, account, notifier, intraday)


@demo_app.command("sync")
def demo_sync() -> None:
    """Read the exchange into the ledger now and print what it found; trades nothing."""
    settings, account, _, _ = _open_demo()
    with locked(settings.demo_lock_path):
        result = account.sync(_now_ms())
    typer.echo(
        f"权益 {result.equity:,.2f} USDT，钱包 {result.cash:,.2f}，持仓 {len(result.positions)} 个，"
        f"挂着的止损单 {len(result.stops)} 张，新记成交 {len(result.fills)} 笔"
    )
    for inst, pos in result.positions.items():
        stop = f"{pos.stop:,.2f}" if pos.stop is not None else "未知"
        typer.echo(f"  {inst} {pos.qty:+g} @ {pos.entry:,.2f}，止损 {stop}")
    for text in result.problems:
        typer.echo(f"  问题：{text}")
    for text in result.alerts:
        typer.echo(f"  {text}")


@demo_app.command("report")
def demo_report_command() -> None:
    """Print the demo account's performance since its first execution."""
    _, account, _, _ = _open_demo()
    typer.echo(demo_report.full(account))


@demo_app.command("resume")
def demo_resume() -> None:
    """Lift the demo account's kill switch, after you have checked why it tripped."""
    settings, account, notifier, _ = _open_demo()
    if not account.ledger.get("halted"):
        _fail("demo 账户没有处于熔断")
    with locked(settings.demo_lock_path):
        if account.sync(_now_ms()).positions:
            _fail("交易所里还有持仓，平掉再解除熔断")
        account.resume(_now_ms())
    notifier.send("demo 账户熔断已解除，下一小时恢复交易。")


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


def _open_intraday(require_utc: bool = False) -> tuple[Settings, IntradayPaper, Notifier]:
    settings = Settings.from_env()
    notifier = Notifier(settings)
    if require_utc and time.localtime().tm_gmtoff != 0:
        notifier.send("trader 不在 UTC 时区运行，已退出。请用 TZ=UTC 启动。")
        _fail("trader must run with TZ=UTC")
    ledger = Ledger(settings.intraday_ledger_path)
    if not ledger.initialized:
        _fail("还没有日内模拟账户，先运行 python -m trader intraday init")
    return settings, IntradayPaper(ledger, OKX()), notifier


PRECHECK_INST = WATCHLIST[0].swap  # the contract the trade-permission probe names


def _trade_permission_error(client: OKXPrivate) -> str | None:
    """Why the key cannot place orders, or None when it can (OKXPrivate.check_trade_permission)."""
    try:
        client.check_trade_permission(PRECHECK_INST)
    except OKXPrivateError as exc:
        hint = "；请在 OKX 模拟盘的 API 管理里给这把 key 的交易权限勾上加密货币/永续合约" if exc.code == "50123" else ""
        return f"这把 key 下不了单：{exc.code} {exc.message}{hint}"
    return None


def _demo_client() -> tuple[Settings, OKXPrivate]:
    """The settings and the signed client of the demo key in .env."""
    try:
        settings = Settings.from_env()
    except ValueError as exc:  # some of the three variables are set, not all
        _fail(str(exc))
    if settings.okx_demo is None:
        _fail(f"先在 .env 里设 {DEMO_ENV}（OKX 模拟交易的 API，只勾“交易”权限）")
    return settings, OKXPrivate(settings.okx_demo)


def _open_demo(require_utc: bool = False) -> tuple[Settings, DemoAccount, Notifier, Ledger]:
    settings, client = _demo_client()
    notifier = Notifier(settings)
    if require_utc and time.localtime().tm_gmtoff != 0:
        notifier.send("trader 不在 UTC 时区运行，已退出。请用 TZ=UTC 启动。")
        _fail("trader must run with TZ=UTC")
    ledger = Ledger(settings.demo_ledger_path)
    if not ledger.initialized:
        _fail("还没有 demo 账户，先运行 python -m trader demo init")
    if not settings.intraday_ledger_path.exists():
        _fail("没有日内账本可跟随：python -m trader intraday init")
    intraday = Ledger(settings.intraday_ledger_path, readonly=True)
    return settings, DemoAccount(ledger, OKX(), client), notifier, intraday


def _fail(message: str) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(1)


def _now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


if __name__ == "__main__":
    app()
