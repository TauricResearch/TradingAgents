"""The live commands (ADR 0010): init opens the account paused on a read-only key and
changes nothing on the exchange, run is the hourly job of the live account, sync and
report read, and resume, the unlock, is refused while the switch is closed and,
once it is open, unless the key is established to trade and the account is not halted."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from tests.test_demo_account import BTC, T0, FakeExchange
from tests.test_demo_job import RUN0, Clock
from tests.test_live_pause import LIVE_CAPITAL
from tests.test_trader_jobs import Inbox
from tests.test_trader_paper import FakeOKX
from trader import __main__ as cli
from trader.demo import job
from trader.demo.account import DemoAccount
from trader.demo.settings import ALERT_INTERVAL_MS
from trader.intraday.paper import HOUR_MS
from trader.intraday.types import SignalResult
from trader.ledger import Ledger
from trader.live import account as live_account, keys
from trader.okx_private import PROBE_ORDER_MISSING, NoBalance, OKXPrivateError, StopOrder
from trader.settings import Settings

NO_SUCH_ORDER = OKXPrivateError(
    "/api/v5/trade/cancel-order", PROBE_ORDER_MISSING, "Order cancellation failed as the order does not exist.",
)
READ_ONLY = OKXPrivateError(
    "/api/v5/trade/cancel-order", "50120", "This API key doesn't have permission to use this function",
)


class LiveExchange(FakeExchange):
    """The fake exchange as the live key sees it: the production environment, a
    sub-account, a read-only key until ``permissions`` say otherwise, and the probe of
    the trade permission answering ``probe``."""

    simulated = False
    base_url = "https://openapi.okx.com"

    def __init__(self):
        super().__init__(cash=LIVE_CAPITAL)
        self.permissions = "read_only"
        self.uids = {"uid": "698827017768230914", "main_uid": "44705892343619584"}
        self.probe = NO_SUCH_ORDER

    def account_config(self):
        return replace(super().account_config(), permissions=self.permissions, **self.uids)

    def probe_trade_permission(self, inst):
        self.calls.append(("probe_trade_permission", inst))
        return self.probe


@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("TRADER_HOME", str(tmp_path))
    monkeypatch.delenv("TRADER_LIVE_HEARTBEAT_URL", raising=False)
    monkeypatch.delenv("TRADER_WEB_TOKEN", raising=False)
    exchange, inbox, now = LiveExchange(), Inbox(), [T0]
    monkeypatch.setattr(keys, "client", lambda base_url=keys.BASE_URL: exchange)
    monkeypatch.setattr(cli, "OKX", FakeOKX)
    monkeypatch.setattr(cli, "Notifier", lambda settings: inbox)
    monkeypatch.setattr(cli, "_now_ms", lambda: now[0])
    settings = Settings(home=tmp_path)
    intraday = Ledger(settings.intraday_ledger_path)
    intraday.initialize(10_000.0, T0 - HOUR_MS)
    return SimpleNamespace(exchange=exchange, inbox=inbox, now=now, settings=settings, intraday=intraday)


def invoke(*args):
    return CliRunner().invoke(cli.app, ["live", *args])


def ledger(live):
    return Ledger(live.settings.live_ledger_path)


def test_init_opens_the_account_paused_on_the_wallet_and_changes_nothing_on_the_exchange(live):
    result = invoke("init")
    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        f"live 账户已建立：本金 500.00 USDT（子账户钱包余额），账本在 {live.settings.live_ledger_path}",
        "现在是影子运行：每小时照常对账，记下本该下的单，不下单、不改交易所的设置；解锁见 ADR 0010。",
    ]
    book = ledger(live)
    assert book.get("capital") == LIVE_CAPITAL and book.get("paused") is True
    assert book.get("setup_done") is None and book.get("summarized_day") == "2026-01-10"
    assert [(kind, text) for _, kind, text in book.events()] == [("pause", "建账：影子运行，等解锁（ADR 0010）")]
    assert book.get("pause_reasons") == [{"key": "init", "text": "建账：影子运行，等解锁（ADR 0010）", "since": T0}]
    assert live.exchange.calls == [] and live.inbox.sent == []
    again = invoke("init")
    assert again.exit_code == 1 and "里已经有账户了" in again.output


@pytest.mark.parametrize("arrange, refusal", [
    (lambda ex: ex.uids.update(uid="44705892343619584"), "这把 key 建在主账户下"),
    (lambda ex: ex.manual_fill(BTC.swap, 5), "子账户里还有持仓"),
    (lambda ex: ex.stops.append(StopOrder("a1", "", BTC.swap, "sell", 5.0, 70_000.0, True, T0)), "子账户里还挂着条件单"),
    (lambda ex: setattr(ex, "cash", 0.0), "子账户里没有 USDT"),
])
def test_init_refuses_a_main_account_a_position_a_pending_stop_and_an_empty_wallet(live, arrange, refusal):
    arrange(live.exchange)
    result = invoke("init")
    assert result.exit_code == 1 and refusal in result.output
    assert not ledger(live).initialized


def test_init_goes_on_when_the_answer_cannot_tell_a_sub_account_and_says_so(live):
    live.exchange.uids = {"uid": "", "main_uid": ""}
    result = invoke("init")
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[-1] == cli.UNKNOWN_SUB_ACCOUNT


def test_init_needs_the_intraday_account_it_follows(live):
    live.settings.intraday_ledger_path.unlink()
    result = invoke("init")
    assert result.exit_code == 1 and "先要有日内账户" in result.output
    assert not ledger(live).initialized


def test_run_runs_the_hour_of_the_live_account_in_utc_only(live, monkeypatch):
    monkeypatch.setattr(cli.time, "localtime", lambda: SimpleNamespace(tm_gmtoff=0))
    runs = []
    monkeypatch.setattr(cli.demo_job, "run", lambda settings, account, notifier, intraday: runs.append((account, notifier)))
    result = invoke("run")
    assert result.exit_code == 1 and "先运行 python -m trader live init" in result.output
    assert invoke("init").exit_code == 0
    assert invoke("run").exit_code == 0
    ((account, notifier),) = runs
    assert account.profile is live_account.LIVE and account.paused
    assert account.ledger.path == live.settings.live_ledger_path
    notifier.send("x")
    assert live.inbox.sent == ["【live】x"]
    monkeypatch.setattr(cli.time, "localtime", lambda: SimpleNamespace(tm_gmtoff=3600))
    result = invoke("run")
    assert result.exit_code == 1 and len(runs) == 1
    assert live.inbox.sent[-1] == "【live】trader 不在 UTC 时区运行，已退出。请用 TZ=UTC 启动。"


def test_a_run_that_returns_beats_the_heartbeat_and_one_that_fails_or_cannot_start_does_not(live, monkeypatch):
    monkeypatch.setattr(cli.time, "localtime", lambda: SimpleNamespace(tm_gmtoff=0))
    beats, failure = [], []
    monkeypatch.setattr(cli.heartbeat, "beat", beats.append)

    def hour(settings, account, notifier, intraday):
        if failure:
            raise failure[0]

    monkeypatch.setattr(cli.demo_job, "run", hour)
    assert invoke("run").exit_code == 1 and beats == []
    assert invoke("init").exit_code == 0
    assert invoke("run").exit_code == 0 and beats == [None]
    monkeypatch.setenv("TRADER_LIVE_HEARTBEAT_URL", "https://hc-ping.example/9b1f0c52")
    assert invoke("run").exit_code == 0 and beats == [None, "https://hc-ping.example/9b1f0c52"]
    failure.append(RuntimeError("the hour failed"))
    assert invoke("run").exit_code == 1 and len(beats) == 2


def test_the_hourly_run_alerts_a_bad_key_file_once_per_interval_and_the_other_commands_each_time(live, monkeypatch):
    def bad_key_file(base_url=keys.BASE_URL):
        raise keys.LiveKeyError("密钥文件不存在")

    assert invoke("init").exit_code == 0
    monkeypatch.setattr(keys, "client", bad_key_file)
    alert = "【live】密钥文件有问题，这次没有运行：密钥文件不存在"
    for minutes, command in [(0, "run"), (60, "run"), (60, "sync"), (60 + ALERT_INTERVAL_MS // 60_000, "run")]:
        live.now[0] = T0 + minutes * 60_000
        result = invoke(command)
        assert result.exit_code == 1 and "live 的密钥文件有问题：密钥文件不存在" in result.output
    assert live.inbox.sent == [alert] * 3


def test_sync_reads_the_account_into_the_ledger_and_changes_nothing(live):
    assert invoke("init").exit_code == 0
    live.exchange.manual_fill(BTC.swap, 5)
    calls = list(live.exchange.calls)
    result = invoke("sync")
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[0].startswith("权益 ")
    assert "持仓 1 个" in result.output and "BTC-USDT-SWAP" in result.output
    assert "问题：BTC-USDT-SWAP 有仓位没有止损单：账户暂停中，程序不补挂，请人工处理" in result.output
    assert live.exchange.calls == calls and live.inbox.sent == []


def test_report_prints_the_performance_and_the_shadow_orders_by_hour(live):
    assert invoke("init").exit_code == 0
    empty = invoke("report")
    assert empty.exit_code == 0 and empty.output.splitlines()[-1] == "影子运行还没有记录。"
    book = ledger(live)
    book.add_event(RUN0, "shadow_order", "BTC-USDT-SWAP 买入 0.5 张，名义 400 USDT，信号 Long")
    book.add_event(RUN0 + HOUR_MS, "shadow_none", "本小时不下单：离目标仓位不远，或不到最小下单量")
    result = invoke("report")
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[-2:] == [
        "影子运行：本该下的单 1 笔，另有 1 个小时没有要下的单",
        "  01-10 00:00 UTC  BTC-USDT-SWAP 买入 0.5 张，名义 400 USDT，信号 Long",
    ]
    assert "live 账户还没开始" in result.output


def test_resume_is_refused_while_the_unlock_is_closed_before_the_key_file_or_the_exchange(live, monkeypatch):
    monkeypatch.setattr(live_account, "UNLOCK_OPEN", False)
    assert invoke("init").exit_code == 0
    live.exchange.permissions = "read_only,trade"
    monkeypatch.setattr(keys, "client", lambda base_url=keys.BASE_URL: pytest.fail("the key file was read"))
    result = invoke("resume")
    assert result.exit_code == 1
    assert result.output.strip() == "live 还不能解锁：解锁的开关（trader/live/account.py 的 UNLOCK_OPEN）关着；现在只做影子运行"
    assert ledger(live).get("paused") is True
    assert live.exchange.calls == [] and live.inbox.sent == []


def test_live_halt_kills_the_paused_account_and_resume_never_lifts_the_kill(live):
    assert invoke("init").exit_code == 0
    final = "按 ADR 0010，live 熔断一次就不再解除，实验到此结束。"
    result = invoke("halt", "--yes")
    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [f"人工熔断：停止交易，平掉 0 个仓位，还剩 0 个。{final}"]
    assert live.inbox.sent == [f"【live】人工熔断：停止交易，平掉 0 个仓位，还剩 0 个。{final}"]
    book = ledger(live)
    assert book.get("halted") is True and book.get("paused") is True
    result = invoke("resume", "--kill")
    assert result.exit_code == 1 and f"live 的熔断不解除：{final}" in result.output
    assert ledger(live).get("halted") is True and len(live.inbox.sent) == 1


def test_live_resume_kill_is_refused_before_the_key_is_read(live, monkeypatch):
    monkeypatch.setattr(keys, "client", lambda base_url=keys.BASE_URL: pytest.fail("the key was read"))
    result = invoke("resume", "--kill")
    assert result.exit_code == 1 and "live 的熔断不解除" in result.output


def test_live_init_refuses_a_sub_account_without_usdt(live):
    def none(ccy="USDT"):
        raise NoBalance("the account's balance has no USDT row")

    live.exchange.balance = none
    result = invoke("init")
    assert result.exit_code == 1 and "子账户里没有 USDT，先划转再 init" in result.output
    assert not ledger(live).initialized


@pytest.fixture
def unlocked(live, monkeypatch):
    monkeypatch.setenv("TRADER_WEB_TOKEN", "web-token-of-the-tests")
    assert invoke("init").exit_code == 0
    live.exchange.permissions = "read_only,trade"
    return live


@pytest.mark.parametrize("arrange, refusal", [
    (lambda live: setattr(live.exchange, "permissions", "read_only"), "权限里没有 trade"),
    (lambda live: setattr(live.exchange, "probe", READ_ONLY), "50120"),
    (lambda live: setattr(live.exchange, "probe", None), "这个应答没见过"),
    (lambda live: ledger(live).set("halted", True), "不解锁：按 ADR 0010，live 熔断一次就不再解除"),
])
def test_an_open_unlock_still_refuses_a_key_not_established_to_trade_and_a_halted_account(unlocked, arrange, refusal):
    arrange(unlocked)
    result = invoke("resume")
    assert result.exit_code == 1 and refusal in result.output
    assert ledger(unlocked).get("paused") is True and unlocked.inbox.sent == []


def test_an_open_unlock_is_refused_without_the_dashboards_token_before_the_exchange_is_asked(unlocked, monkeypatch):
    monkeypatch.delenv("TRADER_WEB_TOKEN")
    result = invoke("resume")
    assert result.exit_code == 1 and "还没有设 TRADER_WEB_TOKEN" in result.output
    assert ledger(unlocked).get("paused") is True
    assert unlocked.exchange.calls == [] and unlocked.inbox.sent == []


def test_an_open_unlock_unpauses_the_account_and_its_next_hour_sets_it_up_and_trades(unlocked):
    live = unlocked
    account = DemoAccount(
        ledger(live), FakeOKX(), live.exchange, watchlist=(BTC,), sleep=lambda s: None, profile=live_account.LIVE,
    )

    def run(now_ms):
        hour = now_ms - now_ms % HOUR_MS
        live.intraday.record_signal(hour + 3 * 60_000, BTC.research, SignalResult("Long", 1, "", None, 1, 1))
        live.intraday.set("decided_hour", hour)
        live.exchange.now = now_ms
        clock = Clock(now_ms)
        job.run(live.settings, account, live.inbox, live.intraday, now_fn=clock.now, sleep=clock.sleep)

    run(RUN0)
    assert live.exchange.calls == [] and live.exchange.book == {}
    result = invoke("resume")
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[-2:] == [
        "解除暂停：建账：影子运行，等解锁（ADR 0010）（01-10 00:30 UTC 起）",
        "live 已解锁：下一次每小时运行起自动下单。",
    ]
    assert live.inbox.sent == ["【live】已解锁：下一次每小时运行先设好账户，然后自动下单。"]
    assert not account.paused and account.pause_reasons == []
    assert [(kind, text) for _, kind, text in account.ledger.events(kinds=("pause", "unpause"))] == [
        ("pause", "建账：影子运行，等解锁（ADR 0010）"),
        ("unpause", "python -m trader live resume：解除暂停（建账：影子运行，等解锁（ADR 0010））"),
    ]
    assert live.exchange.calls == [("probe_trade_permission", "BTC-USDT-SWAP")]
    run(RUN0 + HOUR_MS)
    calls = [call[0] for call in live.exchange.calls]
    assert calls[1] == "set_leverage" and calls.index("set_leverage") < calls.index("place_market")
    assert live.exchange.book[BTC.swap][0] > 0 and account.ledger.get("setup_done") is True
    again = invoke("resume")
    assert again.exit_code == 1 and "没有处于暂停" in again.output
    # Paused again, by a fill the program did not make: the resume lifts a pause, not the unlock.
    live.exchange.manual_fill(BTC.swap, -0.1)
    run(RUN0 + 2 * HOUR_MS)
    assert account.paused
    result = invoke("resume")
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[-1] == "live 的暂停已解除：下一次每小时运行起恢复自动下单。"
    assert live.inbox.sent[-1] == "【live】暂停已解除：下一次每小时运行起恢复自动下单。"
    assert not account.paused
