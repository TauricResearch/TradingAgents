"""The hourly demo job (ADR 0008): wait for the intraday decision, follow it on the
simulated exchange, alert, summarize; and the ``demo`` CLI around it."""

from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from tests.test_demo_account import BTC, HOUR, T0, FakeExchange
from tests.test_trader_jobs import Inbox
from tests.test_trader_paper import DAY0, FakeOKX
from trader import __main__ as cli
from trader.demo import job
from trader.demo.account import DemoAccount
from trader.demo.settings import INTRADAY_POLL_SECONDS, INTRADAY_WAIT_MS, KILL_SETTLE_SECONDS
from trader.intraday.paper import HOUR_MS
from trader.intraday.types import SignalResult
from trader.ledger import Ledger
from trader.okx import DAY_MS, OKXError
from trader.okx_private import OKXPrivateError
from trader.settings import Settings

RUN0 = HOUR + 10 * 60_000  # the job's slot: ten past the hour


class Clock:
    """A clock the job reads and that its sleeps advance."""

    def __init__(self, now_ms):
        self.now_ms = now_ms
        self.sleeps = []
        self.on_sleep = None

    def now(self):
        return datetime.fromtimestamp(self.now_ms / 1000, UTC)

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now_ms += int(seconds * 1000)
        if self.on_sleep:
            self.on_sleep(len(self.sleeps))


class Env:
    def __init__(self, tmp_path):
        self.settings = Settings(home=tmp_path)
        self.ledger = Ledger(self.settings.demo_ledger_path)
        self.ledger.initialize(10_000.0, T0 - HOUR_MS)
        self.ledger.set("setup_done", True)
        self.ledger.set("summarized_day", "2026-01-10")
        self.intraday = Ledger(self.settings.intraday_ledger_path)
        self.intraday.initialize(10_000.0, T0 - HOUR_MS)
        self.exchange = FakeExchange()
        self.exchange.now = HOUR  # the exchange's clock starts at the top of the hour
        self.okx = FakeOKX()
        self.account = DemoAccount(self.ledger, self.okx, self.exchange, watchlist=(BTC,), sleep=lambda s: None)
        self.inbox = Inbox()

    def decide(self, hour, signal):
        self.intraday.record_signal(hour + 3 * 60_000, BTC.research, SignalResult(signal, 1, "", None, 1, 1))
        self.intraday.set("decided_hour", hour)

    def run(self, now_ms):
        clock = Clock(now_ms)
        self.exchange.now = now_ms
        job.run(self.settings, self.account, self.inbox, self.intraday, now_fn=clock.now, sleep=clock.sleep)
        return clock

    def events(self):
        return [row[0] for row in self.ledger.db.execute("SELECT kind FROM events ORDER BY id")]


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


def test_the_hour_follows_the_intraday_signal_and_reports_the_trade(env):
    env.decide(HOUR, "Long")
    clock = env.run(RUN0)
    assert clock.sleeps == []
    assert env.exchange.book[BTC.swap] == [10.0, 80_000.0]
    assert [s.trigger for s in env.exchange.stops] == [79_000.0]
    assert env.ledger.get("decided_hour") == HOUR
    (text,) = env.inbox.sent
    assert text.startswith("demo · 01-10 00:00 UTC\nBTC：Long → ")
    assert text.endswith("交易所权益 9,996.00 USDT")
    # The same hour again: nothing to do, nothing said.
    env.run(RUN0 + 60_000)
    assert len(env.exchange.fill_rows) == 1 and len(env.inbox.sent) == 1


def test_the_demo_waits_for_the_intraday_decision_then_trades(env):
    clock = Clock(RUN0)
    clock.on_sleep = lambda n: env.decide(HOUR, "Long") if n == 3 else None
    env.exchange.now = RUN0
    job.run(env.settings, env.account, env.inbox, env.intraday, now_fn=clock.now, sleep=clock.sleep)
    assert clock.sleeps == [INTRADAY_POLL_SECONDS] * 3
    assert env.exchange.book[BTC.swap] == [10.0, 80_000.0]


def test_without_a_decision_in_the_window_the_hour_is_skipped(env):
    clock = env.run(RUN0)
    assert len(clock.sleeps) == INTRADAY_WAIT_MS // (INTRADAY_POLL_SECONDS * 1000)
    assert env.exchange.fill_rows == [] and env.inbox.sent == []
    assert env.ledger.get("decided_hour") is None
    assert env.events() == ["skipped"]
    (text,) = [t for (t,) in env.ledger.db.execute("SELECT text FROM events")]
    assert text == "日内账户到 00:25 还没决定 00:00 这个小时，demo 本小时不交易"


def test_a_halted_intraday_account_makes_the_demo_flat(env):
    env.decide(HOUR, "Long")
    env.run(RUN0)
    env.intraday.set("halted", True)
    env.run(RUN0 + HOUR_MS)
    assert env.exchange.book[BTC.swap][0] == 0 and env.exchange.stops == []
    assert "follow_halt" in env.events()
    assert env.inbox.sent[-1].startswith("demo · 01-10 01:00 UTC\nBTC：Flat → ")


def test_a_reconciliation_problem_blocks_the_hour_and_alerts_once_per_interval(env):
    env.exchange.leverage = 5.0
    env.exchange.manual_fill(BTC.swap, 5)
    env.decide(HOUR, "Long")
    env.run(RUN0)
    assert len(env.exchange.fill_rows) == 1  # nothing traded on top of the odd position
    assert env.ledger.get("decided_hour") is None
    assert env.inbox.sent == [
        "demo 对账：交易所里有不是程序下的成交：BTC-USDT-SWAP buy 5 张 @ 80,000.00",
        "demo 对账：BTC-USDT-SWAP 在交易所是 cross 5×，不是设计的 cross 3×",
    ]
    env.decide(HOUR + HOUR_MS, "Long")
    env.run(RUN0 + HOUR_MS)
    assert len(env.inbox.sent) == 2  # the leverage problem persists but is not repeated yet
    assert env.events().count("problem") == 3
    assert len(env.exchange.fill_rows) == 1


def test_a_kill_in_the_sync_settles_its_fills_before_anything_else(env):
    env.decide(HOUR, "Long")
    env.run(RUN0)
    env.exchange.mark[BTC.swap] = env.exchange.prices[BTC.swap] = 59_000.0
    env.decide(HOUR + HOUR_MS, "Long")
    clock = env.run(RUN0 + HOUR_MS)
    assert clock.sleeps == [KILL_SETTLE_SECONDS]
    assert env.ledger.get("halted") is True
    assert [f.reason for f in env.ledger.fills()] == ["trade", "kill"]
    assert env.exchange.book[BTC.swap][0] == 0 and env.exchange.stops == []
    assert env.inbox.sent[-1].startswith("熔断：净值")
    assert env.ledger.get("decided_hour") == HOUR  # the second hour was not traded


def test_a_failure_is_raised_and_alerted_once(env):
    def broken(ccy="USDT"):
        raise OKXError("balance failed with code 50001: service unavailable")

    env.exchange.balance = broken
    with pytest.raises(OKXError):
        env.run(RUN0)
    with pytest.raises(OKXError):
        env.run(RUN0 + HOUR_MS)
    assert env.inbox.sent == ["demo 运行失败：OKXError: balance failed with code 50001: service unavailable"]


def test_the_first_run_of_a_day_sends_yesterdays_summary(env):
    env.ledger.set("summarized_day", "2026-01-09")
    env.decide(HOUR, "Long")
    env.run(RUN0)
    assert env.inbox.sent[-1].startswith("demo 日报 · 2026-01-09\n权益 9,996.00 USDT，较本金 -0.04%")
    assert env.ledger.get("summarized_day") == "2026-01-10"


def test_a_fresh_ledger_is_set_up_on_the_first_run(env):
    env.ledger.set("setup_done", False)
    env.exchange.mode = "long_short_mode"
    env.run(RUN0)
    assert env.exchange.mode == "net_mode" and env.exchange.leverages == {BTC.swap: (3, "cross")}
    assert env.ledger.get("setup_done") is True and env.events()[:2] == ["setup", "setup"]


def test_hour_signals_take_the_newest_row_per_coin_since_the_hour(env):
    env.intraday.record_signal(HOUR - 1, "BTC-USD", SignalResult("Short", 1, "", None, 1, 1))
    env.intraday.record_signal(HOUR + 60_000, "BTC-USD", SignalResult("Long", 1, "", None, 1, 1))
    env.intraday.record_signal(HOUR + 120_000, "BTC-USD", SignalResult(None, None, "", "boom"))
    env.intraday.record_signal(HOUR + 60_000, "ETH-USD", SignalResult("Flat", 1, "", None, 1, 1))
    assert job.hour_signals(env.intraday, HOUR) == {"BTC-USD": None, "ETH-USD": "Flat"}


# -- the CLI ------------------------------------------------------------------------


@pytest.fixture
def demo_cli(tmp_path, monkeypatch):
    """The ``demo`` commands against the fake exchange, with an intraday account present."""
    monkeypatch.setenv("TRADER_HOME", str(tmp_path))
    for name in ("KEY", "SECRET", "PASSPHRASE"):
        monkeypatch.setenv(f"TRADER_OKX_DEMO_{name}", f"demo-{name.lower()}")
    exchange = FakeExchange()
    monkeypatch.setattr(cli, "OKXPrivate", lambda creds: exchange)
    monkeypatch.setattr(cli, "OKX", FakeOKX)
    Ledger(Settings(home=tmp_path).intraday_ledger_path).initialize(10_000.0, T0)
    return CliRunner(), exchange, Settings(home=tmp_path)


def test_demo_init_opens_the_account_on_the_wallet_balance(demo_cli):
    runner, exchange, settings = demo_cli
    exchange.mode = "long_short_mode"
    result = runner.invoke(cli.app, ["demo", "init"])
    assert result.exit_code == 0, result.output
    assert "持仓模式已切到单向（net_mode）" in result.output
    assert "demo 账户已建立：本金 10,000.00 USDT（模拟账户钱包余额）" in result.output
    ledger = Ledger(settings.demo_ledger_path, readonly=True)
    assert ledger.get("capital") == 10_000.0 and ledger.get("setup_done") is True
    again = runner.invoke(cli.app, ["demo", "init"])
    assert again.exit_code == 1 and "已经有账户了" in again.output


def test_demo_init_refuses_an_account_that_is_not_flat(demo_cli):
    runner, exchange, settings = demo_cli
    exchange.manual_fill(BTC.swap, 5)
    result = runner.invoke(cli.app, ["demo", "init"])
    assert result.exit_code == 1 and "模拟账户里还有持仓" in result.output
    assert not settings.demo_ledger_path.exists() or not Ledger(settings.demo_ledger_path).initialized


def test_demo_init_refuses_a_key_that_cannot_trade(demo_cli):
    runner, exchange, settings = demo_cli
    exchange.mode = "long_short_mode"
    exchange.permission_error = OKXPrivateError(
        "/api/v5/trade/cancel-order", "50123", "This API Key does not have trading permission for the Crypto"
    )
    result = runner.invoke(cli.app, ["demo", "init"])
    assert result.exit_code == 1, result.output
    assert "这把 key 下不了单：50123" in result.output and "勾上加密货币/永续合约" in result.output
    # Refused before anything was changed on the exchange or written to the ledger.
    assert exchange.mode == "long_short_mode" and exchange.leverages == {}
    assert not settings.demo_ledger_path.exists() or not Ledger(settings.demo_ledger_path).initialized


def test_demo_init_needs_the_intraday_account(demo_cli):
    runner, _, settings = demo_cli
    settings.intraday_ledger_path.unlink()
    result = runner.invoke(cli.app, ["demo", "init"])
    assert result.exit_code == 1 and "先要有日内账户" in result.output


def test_demo_sync_report_and_resume(demo_cli):
    runner, exchange, settings = demo_cli
    assert runner.invoke(cli.app, ["demo", "init"]).exit_code == 0
    result = runner.invoke(cli.app, ["demo", "sync"])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("权益 10,000.00 USDT，钱包 10,000.00，持仓 0 个，挂着的止损单 0 张，新记成交 0 笔")
    result = runner.invoke(cli.app, ["demo", "report"])
    assert result.exit_code == 0 and "demo 账户还没开始" in result.output
    result = runner.invoke(cli.app, ["demo", "resume"])
    assert result.exit_code == 1 and "没有处于熔断" in result.output
    ledger = Ledger(settings.demo_ledger_path)
    ledger.set("halted", True)
    ledger.db.close()
    exchange.manual_fill(BTC.swap, 5)
    result = runner.invoke(cli.app, ["demo", "resume"])
    assert result.exit_code == 1 and "交易所里还有持仓" in result.output
    exchange.manual_fill(BTC.swap, -5)
    result = runner.invoke(cli.app, ["demo", "resume"])
    assert result.exit_code == 0, result.output
    assert Ledger(settings.demo_ledger_path, readonly=True).get("halted") is False


def test_demo_run_needs_an_account_and_a_utc_clock(demo_cli, monkeypatch):
    runner, _, _ = demo_cli
    monkeypatch.setattr(cli.time, "localtime", lambda: type("T", (), {"tm_gmtoff": 0})())
    result = runner.invoke(cli.app, ["demo", "run"])
    assert result.exit_code == 1 and "先运行 python -m trader demo init" in result.output
    assert runner.invoke(cli.app, ["demo", "init"]).exit_code == 0
    monkeypatch.setattr(cli.time, "localtime", lambda: type("T", (), {"tm_gmtoff": 3600})())
    result = runner.invoke(cli.app, ["demo", "run"])
    assert result.exit_code == 1 and "TZ=UTC" in result.output


def test_the_demo_ledger_lives_beside_the_others(tmp_path):
    settings = Settings(home=tmp_path)
    assert settings.demo_ledger_path == tmp_path / "demo" / "ledger.sqlite"
    assert settings.demo_lock_path == tmp_path / "demo" / "trader.lock"
    assert DAY0 < T0 < DAY0 + DAY_MS
