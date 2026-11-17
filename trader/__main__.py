"""Command line: python -m trader init | daily | mark | report | resume | backup, the
intraday account's python -m trader intraday init | run | report | resume, the demo
account's python -m trader demo check | init | run | sync | report | resume (ADR 0008),
the live account's python -m trader live check (ADR 0010), and the offline
evaluation's python -m trader evaluate fetch | replay | signals."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import typer
from dotenv import find_dotenv, load_dotenv

from trader import backup as account_backup, jobs, message, report
from trader.demo import job as demo_job, reconcile, report as demo_report
from trader.demo.account import DEMO, DemoAccount, Sync
from trader.evaluation.cli import evaluate_app
from trader.intraday import job as intraday_job, report as intraday_report
from trader.intraday.paper import IntradayPaper, utc_date
from trader.ledger import Ledger, locked
from trader.live import account as live_account, heartbeat, keys as live_keys
from trader.notify import Labeled, Notifier, labeled
from trader.okx import OKX, REQUEST_ERRORS, OKXError
from trader.okx_private import PROBE_ORDER_MISSING, Balance, NoBalance, OKXPrivate, OKXPrivateError
from trader.paper import Paper
from trader.research import Researcher
from trader.settings import TAKER_FEE, WATCHLIST, Settings

# An uncaught error's traceback must not print the frames' local variables: those of a
# request to OKX hold its headers, with the key, the passphrase and the signature.
app = typer.Typer(add_completion=False, no_args_is_help=True, pretty_exceptions_show_locals=False)
intraday_app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(intraday_app, name="intraday")
demo_app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(demo_app, name="demo")
live_app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(live_app, name="live")
app.add_typer(evaluate_app, name="evaluate")

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
        jobs.daily(
            settings, paper, notifier, lambda: Researcher(settings),
            rerun_factory=lambda: Researcher(settings, fresh_data=True),
        )
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
    notes = (
        "  （没有日内账本，跳过）", "  （没有 demo 账本，跳过）", "  （没有 live 账本，跳过）",
    )
    for rel, note in zip(account_backup.LEDGERS[1:], notes, strict=True):
        if not (settings.home / rel).exists():
            typer.echo(note)


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
        balance = _balance(client)
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
    _print_balance(balance, "模拟账户里还没有 USDT，先在 OKX 模拟盘领取资金")
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
        balance = _balance(client)
    except REQUEST_ERRORS as exc:
        _fail(f"OKX 模拟盘没有应答：{jobs.error_text(exc)}")
    if balance is None or balance.cash <= 0:
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
    _print_sync(result)


@demo_app.command("report")
def demo_report_command() -> None:
    """Print the demo account's performance since its first execution."""
    _, account, _, _ = _open_demo()
    typer.echo(demo_report.full(account))


@demo_app.command("halt")
def demo_halt(yes: bool = typer.Option(False, "--yes", "-y", help="不再确认，直接执行")) -> None:
    """Trip the demo account's kill switch by hand: stop trading and close every position
    at market, with positions open or not. With --yes, one command from a phone over SSH."""
    settings, account, notifier, _ = _open_demo()
    _halt(settings, account, notifier, yes)


@demo_app.command("pause")
def demo_pause(note: str = typer.Option("", "--note", help="为什么暂停，写进暂停原因")) -> None:
    """Pause the demo account by hand: no new orders, its positions and their stops on the
    exchange left as they are, until ``demo resume``. Asks the exchange nothing."""
    settings, account, notifier, _ = _open_demo()
    _pause(settings, account, notifier, note)


@demo_app.command("resume")
def demo_resume(kill: bool = typer.Option(False, "--kill", help="解除熔断；不加时解除暂停")) -> None:
    """Lift the demo account's pause once a sync just now finds nothing that pauses it,
    printing what it found and the reasons lifted (``demo_job.resume``); with --kill, its
    kill switch, once the exchange is flat and you have checked why it tripped."""
    settings, account, notifier, intraday = _open_demo()
    halted = account.ledger.get("halted")
    if kill:
        if not halted:
            _fail("demo 账户没有处于熔断")
        with locked(settings.demo_lock_path):
            if account.sync(_now_ms()).positions:
                _fail("交易所里还有持仓：这次对账已经再发了市价平仓，确认空仓后再解除熔断")
            account.resume(_now_ms())
        notifier.send("熔断已解除" + ("；账户仍在暂停中，不会交易。" if account.paused else "，下一小时恢复交易。"))
        return
    if not account.paused:
        _fail("demo 账户没有处于暂停" + ("；它处于熔断，解除熔断要加 --kill" if halted else ""))
    _resume(settings, account, intraday)
    notifier.send("暂停已解除" + ("；账户仍在熔断中，不会交易。" if halted else "，下一小时恢复交易。"))


@demo_app.command("reconcile")
def demo_reconcile(
    yes: bool = typer.Option(False, "--yes", "-y", help="不再确认，直接写入"),
    note: str = typer.Option("", "--note", help="为什么修复，写进事件"),
) -> None:
    """Repair the demo ledger where it no longer agrees with the exchange, only while the
    account is paused or halted (``trader.demo.reconcile``): book the fills and funding
    fees the syncs missed, read again from the account's opening, and record what still
    differs as an adjustment. Prints what it would write and asks once; with --yes, it
    does not ask."""
    settings, account, _, _ = _open_demo()
    _reconcile(settings, account, yes, note)


@live_app.callback()
def live_main() -> None:
    """The live account: real money on OKX's production environment (ADR 0010)."""


@live_app.command("check")
def live_check(
    base_url: str = typer.Option(
        live_keys.BASE_URL, "--base-url", help="只在这一次运行里改用 OKX 的另一个域名，用来对比两个域名"
    ),
) -> None:
    """Read the production account with the key of the live key file: the account's
    mode, the key's permissions, the USDT balance, the positions and the fee rates the
    account really pays. Places nothing and changes no setting; a read-only key will do."""
    base_url = base_url.rstrip("/")
    if base_url not in live_keys.BASE_URLS:  # the factory holds to the same list
        _fail(f"--base-url 只接受 {' 或 '.join(live_keys.BASE_URLS)}，live 的密钥不发往别处")
    _, client = _live_client(base_url)
    fees, notes = [], []
    try:
        config = client.account_config()
        balance = _balance(client)
        positions = client.positions()
        stops = client.pending_stops()
        for coin in WATCHLIST:
            try:
                fees.append(client.fee_rate(coin.swap))
            except OKXError as exc:  # the shape of this answer is known from OKX's docs alone
                notes.append(f"{coin.swap} 的实际费率没有读到：{jobs.error_text(exc)}")
    except OKXPrivateError as exc:
        _fail(f"OKX 正式环境拒绝了请求：{jobs.error_text(exc)}")
    except REQUEST_ERRORS as exc:
        _fail(f"OKX 正式环境没有应答：{jobs.error_text(exc)}")
    levels = {"1": "现货", "2": "合约模式（单币种保证金）", "3": "跨币种保证金", "4": "组合保证金"}
    permissions = config.permissions.split(",")
    _, trade = _live_trade_verdict(client, permissions)
    sub_account = _sub_account(config)
    kind = {True: "子账户", False: "主账户", None: "不确定是不是子账户"}[sub_account]
    bound = len(config.ip.split(",")) if config.ip else 0
    typer.echo(f"正式环境（真钱），域名 {client.base_url}")
    typer.echo(
        f"账户模式 {levels.get(config.account_level, config.account_level)}，持仓模式 {config.position_mode}，{kind}"
    )
    typer.echo(f"这把 key 的权限 {config.permissions}，{f'绑定了 {bound} 个 IP' if bound else '没有绑定 IP'}")
    _print_balance(balance, "子账户里还没有 USDT，先从主账户划转")
    typer.echo(f"持仓 {len(positions)} 个，挂着的止损单 {len(stops)} 张")
    for p in positions:
        typer.echo(f"  {p.inst} {p.contracts:+g} 张 @ {p.avg_price:,.2f}，{p.margin_mode} {p.leverage:g}×")
    for s in stops:
        typer.echo(f"  止损 {s.inst} {s.side} {s.contracts:g} 张，触发 {s.trigger:,.2f}")
    if fees:
        typer.echo(f"实际费率（等级 {fees[0].level}），模拟盘假设吃单万分之 {TAKER_FEE * 1e4:g}：")
    for fee in fees:
        typer.echo(
            f"  {fee.inst} 吃单万分之 {fee.taker * 1e4:g}（比模拟盘假设 {(fee.taker - TAKER_FEE) * 1e4:+g}），"
            f"挂单万分之 {fee.maker * 1e4:g}"
        )
    typer.echo(trade)
    if "withdraw" in permissions:
        typer.echo("注意：这把 key 带提币权限（withdraw）；ADR 0010 要求只勾交易、不勾提币。")
    if not bound:
        typer.echo("注意：这把 key 没有绑定 IP；ADR 0010 要求绑定 mini 的固定出口 IP。")
    if sub_account is False:
        typer.echo("注意：这把 key 建在主账户下；ADR 0010 要求建在只给这套系统用的子账户下。")
    if sub_account is None:
        typer.echo(UNKNOWN_SUB_ACCOUNT)
    if config.account_level == "1":
        typer.echo("注意：现货模式不能交易合约，请在 OKX 把账户模式改成合约模式（以前叫单币种保证金）或跨币种保证金。")
    for note in notes:
        typer.echo(f"注意：{note}")


UNKNOWN_SUB_ACCOUNT = (
    "注意：应答里没有 uid 或 mainUid，看不出这把 key 是不是建在子账户下；"
    "ADR 0010 要求建在只给这套系统用的子账户下。"
)


@live_app.command("init")
def live_init() -> None:
    """Open the live account on the sub-account's USDT balance, paused: until ``live
    resume`` its hourly runs are a shadow run (ADR 0010). Only reads, so a read-only key
    will do: the account must be flat with no pending stops, and nothing is set up."""
    settings, client = _live_client()
    ledger = Ledger(settings.live_ledger_path)
    if ledger.initialized:
        _fail(f"{settings.live_ledger_path} 里已经有账户了")
    if not settings.intraday_ledger_path.exists():
        _fail("live 跟随日内账户的信号，先要有日内账户：python -m trader intraday init")
    try:
        config = client.account_config()
        positions = client.positions()
        stops = client.pending_stops()
        balance = _balance(client)
    except OKXPrivateError as exc:
        _fail(f"OKX 正式环境拒绝了请求：{jobs.error_text(exc)}")
    except REQUEST_ERRORS as exc:
        _fail(f"OKX 正式环境没有应答：{jobs.error_text(exc)}")
    sub_account = _sub_account(config)
    if sub_account is False:
        _fail("这把 key 建在主账户下：ADR 0010 要求 live 用只给这套系统用的子账户")
    if positions:
        _fail("子账户里还有持仓，先在 OKX 平掉再 init")
    if stops:
        _fail("子账户里还挂着条件单，先在 OKX 撤掉再 init")
    if balance is None or balance.cash <= 0:
        _fail("子账户里没有 USDT，先划转再 init")
    now_ms = _now_ms()
    ledger.initialize(balance.cash, now_ms)
    ledger.set("summarized_day", utc_date(now_ms))
    account = DemoAccount(ledger, OKX(), client, profile=live_account.LIVE)
    account.pause(now_ms, "建账：影子运行，等解锁（ADR 0010）", "init")
    typer.echo(f"live 账户已建立：本金 {balance.cash:,.2f} USDT（子账户钱包余额），账本在 {settings.live_ledger_path}")
    typer.echo("现在是影子运行：每小时照常对账，记下本该下的单，不下单、不改交易所的设置；解锁见 ADR 0010。")
    if sub_account is None:
        typer.echo(UNKNOWN_SUB_ACCOUNT)


@live_app.command("run")
def live_run() -> None:
    """The live account's hourly run, after the intraday job: a shadow run while the
    account is paused, otherwise the demo's run on the production account. A run that
    returns beats the heartbeat (ADR 0010), when TRADER_LIVE_HEARTBEAT_URL names one."""
    settings, account, notifier, intraday = _open_live(require_utc=True, hourly=True)
    demo_job.run(settings, account, notifier, intraday)
    heartbeat.beat(settings.live_heartbeat_url)


@live_app.command("sync")
def live_sync() -> None:
    """Read the production account into the live ledger now and print what it found;
    trades nothing."""
    settings, account, _, _ = _open_live()
    with locked(settings.live_lock_path):
        result = account.sync(_now_ms())
    _print_sync(result)


@live_app.command("report")
def live_report_command() -> None:
    """Print the live account's performance since its first execution, and the orders
    its shadow run would have sent, by hour."""
    _, account, _, _ = _open_live()
    typer.echo(demo_report.full(account))
    typer.echo(demo_report.shadow(account))


@live_app.command("halt")
def live_halt(yes: bool = typer.Option(False, "--yes", "-y", help="不再确认，直接执行")) -> None:
    """Trip the live account's kill switch by hand: stop trading and close every position
    at market, with positions open or not, paused or not (ADR 0010). A live kill is never
    lifted: it ends the experiment. With --yes, one command from a phone over SSH."""
    settings, account, notifier, _ = _open_live()
    _halt(settings, account, notifier, yes)


@live_app.command("pause")
def live_pause(note: str = typer.Option("", "--note", help="为什么暂停，写进暂停原因")) -> None:
    """Pause the live account by hand: no new orders, its positions and their stops on the
    exchange left as they are, until ``live resume``; unlike a halt, the experiment goes
    on. Asks the exchange nothing."""
    settings, account, notifier, _ = _open_live()
    _pause(settings, account, notifier, note)


@live_app.command("resume")
def live_resume(kill: bool = typer.Option(False, "--kill", help="解除熔断：live 不接受，见 ADR 0010")) -> None:
    """Unpause the live account: the first time, ADR 0010's unlock, after which its next
    hourly run sets the account up and trades. Refused, before the key file is read or
    the exchange asked anything, with --kill (a live kill is never lifted) or while the
    unlock is closed (``trader.live.account.UNLOCK_OPEN``); and unless the dashboard's
    write endpoint wants a token (TRADER_WEB_TOKEN, a condition of the unlock), the
    account is paused and not halted, its key is established to place orders as live
    check establishes it, and a sync just now finds nothing that pauses it
    (``demo_job.resume``), printed with the reasons lifted."""
    if kill:
        _fail(f"live 的熔断不解除：{live_account.LIVE.after_kill}")
    if not live_account.UNLOCK_OPEN:
        _fail("live 还不能解锁：解锁的开关（trader/live/account.py 的 UNLOCK_OPEN）关着；现在只做影子运行")
    settings, client = _live_client()
    if not settings.web_token:
        _fail("还没有设 TRADER_WEB_TOKEN：看板的写入口要有令牌，ADR 0010 把它定为解锁的条件")
    account, notifier, intraday = _live_account(settings, client)
    if not account.paused:
        _fail("live 账户没有处于暂停")
    if account.ledger.get("halted"):
        _fail(f"live 账户处于熔断，不解锁：{live_account.LIVE.after_kill}")
    try:
        config = client.account_config()
        established, line = _live_trade_verdict(client, config.permissions.split(","))
    except OKXPrivateError as exc:
        _fail(f"OKX 正式环境拒绝了请求：{jobs.error_text(exc)}")
    except REQUEST_ERRORS as exc:
        _fail(f"OKX 正式环境没有应答：{jobs.error_text(exc)}")
    if not established:
        _fail(f"交易权限没有确立，不解锁。{line}")
    unlock = not account.ledger.get("setup_done")
    _resume(settings, account, intraday)
    if unlock:
        notifier.send("已解锁：下一次每小时运行先设好账户，然后自动下单。")
        typer.echo("live 已解锁：下一次每小时运行起自动下单。")
    else:
        notifier.send("暂停已解除：下一次每小时运行起恢复自动下单。")
        typer.echo("live 的暂停已解除：下一次每小时运行起恢复自动下单。")


@live_app.command("reconcile")
def live_reconcile(
    yes: bool = typer.Option(False, "--yes", "-y", help="不再确认，直接写入"),
    note: str = typer.Option("", "--note", help="为什么修复，写进事件"),
) -> None:
    """Repair the live ledger where it no longer agrees with the production account, as
    ``demo reconcile`` does: only while paused or halted, asked once unless --yes. It
    reads the exchange and writes only the ledger."""
    settings, account, _, _ = _open_live()
    _reconcile(settings, account, yes, note)


def _open(require_utc: bool = False) -> tuple[Settings, Paper, Labeled]:
    settings = Settings.from_env()
    notifier = labeled(Notifier(settings), message.DAILY)
    # Dates are taken from the local clock (ADR 0002), so the scheduled jobs
    # refuse to run in any other zone.
    if require_utc and time.localtime().tm_gmtoff != 0:
        notifier.send("trader 不在 UTC 时区运行，已退出。请用 TZ=UTC 启动。")
        _fail("trader must run with TZ=UTC")
    ledger = Ledger(settings.ledger_path)
    if not ledger.initialized:
        _fail("还没有模拟账户，先运行 python -m trader init")
    return settings, Paper(ledger, OKX()), notifier


def _open_intraday(require_utc: bool = False) -> tuple[Settings, IntradayPaper, Labeled]:
    settings = Settings.from_env()
    notifier = labeled(Notifier(settings), message.INTRADAY)
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
    notifier = labeled(Notifier(settings), DEMO.name)
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


def _halt(settings: Settings, account: DemoAccount, notifier: Notifier, yes: bool) -> None:
    """``demo halt`` and ``live halt``: asked once unless ``yes``, then ``demo_job.halt``."""
    name = account.profile.name
    if not yes:
        typer.confirm(
            f"停止 {name} 账户的交易，市价平掉交易所里的全部仓位。{account.profile.after_kill}确定吗？", abort=True
        )
    try:
        lines = demo_job.halt(settings, account, notifier)
    except Exception as exc:
        if account.ledger.get("halted"):
            _fail(f"{name} 已熔断，但这次没做完：{jobs.error_text(exc)}")
        _fail(f"{name} 没能熔断：{jobs.error_text(exc)}")
    for line in lines:
        typer.echo(line)


MANUAL_PAUSE = "manual_pause"  # the key of the reason demo pause and live pause enter


def _pause(settings: Settings, account: DemoAccount, notifier: Notifier, note: str) -> None:
    """``demo pause`` and ``live pause``: a reason a person gives, entered under the
    account's lock, so an hourly run under way finishes first. A halted account is
    refused; a second manual pause only says the first stands."""
    profile = account.profile
    if account.ledger.get("halted"):
        _fail(f"{profile.name} 账户处于熔断，不用再暂停")
    reason = f"人工暂停：{note.strip()}" if note.strip() else "人工暂停"
    with locked(profile.lock_path(settings)):
        entered = account.pause(_now_ms(), reason, key=MANUAL_PAUSE)
    if not entered:
        standing = next(r for r in account.pause_reasons if r["key"] == MANUAL_PAUSE)
        when = datetime.fromtimestamp(standing["since"] / 1000, UTC).strftime("%m-%d %H:%M")
        typer.echo(f"{profile.name} 已经在人工暂停中（{when} UTC 起）：{standing['text']}")
        return
    text = (
        f"{reason}。不再下新单，仓位和止损单原样保留，暂停期间不改止损、回撤到线只告警；"
        f"运行 {profile.resume_command} 解除。"
    )
    notifier.send(text)
    typer.echo(text)


def _resume(settings: Settings, account: DemoAccount, intraday: Ledger) -> None:
    """``demo resume`` and ``live resume``: ``demo_job.resume``, what its sync found and
    the reasons it lifted printed; a refusal fails the command with its reason."""
    try:
        reasons, result = demo_job.resume(settings, account, intraday)
    except demo_job.Refused as exc:
        _fail(f"{account.profile.name} 没有解除暂停：{exc}")
    _print_sync(result)
    if not reasons:
        typer.echo("解除暂停：账本里没有记下原因")
    for reason in reasons:
        when = datetime.fromtimestamp(reason["since"] / 1000, UTC).strftime("%m-%d %H:%M")
        typer.echo(f"解除暂停：{reason['text']}（{when} UTC 起）")


def _reconcile(settings: Settings, account: DemoAccount, yes: bool, note: str) -> None:
    """``demo reconcile`` and ``live reconcile``: the plan, made under the account's lock,
    printed; asked once unless ``yes``; then written under the lock again. A refusal, or
    an exchange that does not answer, fails the command with its reason; a no writes
    nothing."""
    profile = account.profile
    lock = profile.lock_path(settings)
    try:
        with locked(lock):
            repair = reconcile.plan(account, _now_ms())
    except reconcile.Refused as exc:
        _fail(f"{profile.name} 没有修复：{exc}")
    except REQUEST_ERRORS as exc:
        _fail(f"{profile.name} 没有修复：读交易所失败（{jobs.error_text(exc)}）")
    for line in reconcile.describe(repair):
        typer.echo(line)
    if repair.empty:
        return
    if not yes:
        typer.confirm("把上面这些写进账本吗？", default=False, abort=True)
    try:
        with locked(lock):
            text = reconcile.apply(account, repair, _now_ms(), note)
    except reconcile.Refused as exc:
        _fail(f"{profile.name} 没有修复：{exc}")
    typer.echo(f"已写入：{text}")
    if account.ledger.get("halted"):
        typer.echo(f"账户仍在熔断中：{profile.after_kill}")
    else:
        typer.echo(f"账户仍在暂停中：运行 {profile.resume_command}，它先对一次账，对得上才解除暂停。")


def _balance(client: OKXPrivate) -> Balance | None:
    """The account's USDT balance; None when it has none (``NoBalance``)."""
    try:
        return client.balance()
    except NoBalance:
        return None


def _print_balance(balance: Balance | None, missing: str) -> None:
    if balance is None:
        typer.echo(f"USDT 没有余额：{missing}")
        return
    typer.echo(
        f"USDT 权益 {balance.equity:,.2f}，钱包 {balance.cash:,.2f}，可用 {balance.available:,.2f}，"
        f"未实现 {balance.unrealized:+,.2f}"
    )


def _print_sync(result: Sync) -> None:
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


def _open_live(
    require_utc: bool = False, hourly: bool = False,
) -> tuple[Settings, DemoAccount, Notifier, Ledger]:
    settings, client = _live_client(hourly=hourly)
    return (settings, *_live_account(settings, client, require_utc))


def _live_account(
    settings: Settings, client: OKXPrivate, require_utc: bool = False,
) -> tuple[DemoAccount, Notifier, Ledger]:
    """The live account on ``client``, its labeled notifier and the intraday ledger it
    follows, opened read-only."""
    notifier = labeled(Notifier(settings), live_account.LIVE.name)
    if require_utc and time.localtime().tm_gmtoff != 0:
        notifier.send("trader 不在 UTC 时区运行，已退出。请用 TZ=UTC 启动。")
        _fail("trader must run with TZ=UTC")
    ledger = Ledger(settings.live_ledger_path)
    if not ledger.initialized:
        _fail("还没有 live 账户，先运行 python -m trader live init")
    if not settings.intraday_ledger_path.exists():
        _fail("没有日内账本可跟随：python -m trader intraday init")
    intraday = Ledger(settings.intraday_ledger_path, readonly=True)
    return DemoAccount(ledger, OKX(), client, profile=live_account.LIVE), notifier, intraday


def _live_client(base_url: str = live_keys.BASE_URL, hourly: bool = False) -> tuple[Settings, OKXPrivate]:
    """The settings and the production client on the key of the live key file (ADR
    0010). A file that is missing, unreadable, open to other users, incomplete or of
    values no header carries fails the calling command with an alert, and that command
    alone: no other command reads the file. The ``hourly`` run alerts it as it does its
    own failures, through the account's outbox (``demo_job.alert_failure``)."""
    try:
        settings = Settings.from_env()
    except ValueError as exc:  # the demo key's variables are set in part, as in _demo_client
        _fail(str(exc))
    try:
        return settings, live_keys.client(base_url)
    except live_keys.LiveKeyError as exc:
        text = f"密钥文件有问题，这次没有运行：{exc}"
        if hourly and settings.live_ledger_path.exists():
            ledger = Ledger(settings.live_ledger_path)
            box = demo_job.outbox(Notifier(settings), ledger, live_account.LIVE, _now_ms)
            demo_job.alert_failure(ledger, box, live_account.LIVE, exc, text, _now_ms())
        else:
            labeled(Notifier(settings), live_account.LIVE.name).send(text)
        _fail(f"live 的密钥文件有问题：{exc}")


def _sub_account(config) -> bool | None:
    """Whether the key's account is a sub-account, whose uid differs from its main
    account's; None when the answer lacks either, and there is no telling."""
    return config.uid != config.main_uid if config.uid and config.main_uid else None


def _live_trade_verdict(client: OKXPrivate, permissions: list[str]) -> tuple[bool, str]:
    """Whether the live key is established to place orders, and what live check says of
    it: that it may, or a note of why that is not established. The probe is the check's last request and its only
    one that is not a GET; getting no answer to it is noted here rather than raised, so
    that what was read before it is still printed. Only the answer seen from a key that
    may trade counts as that, and a key without the trade permission cannot trade
    whatever the probe is answered: what a read-only key gets has not been seen yet."""
    try:
        answer = client.probe_trade_permission(PRECHECK_INST)
        code = answer.code if answer else "0"
        got = f"探针得到 {answer.code} {answer.message}" if answer else "探针的撤单被接受了"
    except REQUEST_ERRORS as exc:
        code, got = "", f"探针没有得到应答：{jobs.error_text(exc)}"
    shadow = "影子运行可以，解锁前要换成只勾“交易”的 key，交易权限要覆盖加密货币/永续合约。"
    if code.startswith("50"):
        return False, f"注意：这把 key 下不了单（{answer.code} {answer.message}）：{shadow}"
    if "trade" not in permissions:
        return False, f"注意：这把 key 下不了单（权限里没有 trade；{got}）：{shadow}"
    if code == PROBE_ORDER_MISSING:
        return True, "交易权限正常（试了一次不存在订单的撤单，没有下单）。"
    if not code:
        return False, f"注意：交易权限{got}；不能确认这把 key 能下单。"
    return False, f"注意：交易权限{got}，不是“订单不存在”（{PROBE_ORDER_MISSING}）：这个应答没见过，不能确认这把 key 能下单。"


def _fail(message: str) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(1)


def _now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


if __name__ == "__main__":
    app()
