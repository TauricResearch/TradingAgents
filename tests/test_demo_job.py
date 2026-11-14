"""The hourly demo job (ADR 0008): wait for the intraday decision, follow it on the
simulated exchange, alert, summarize; and the ``demo`` CLI around it."""

import random
import sqlite3
from datetime import UTC, datetime
from functools import partial

import pytest
import requests
from typer.testing import CliRunner

from tests.test_demo_account import BTC, ETH, HOUR, T0, FakeExchange
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
from trader.okx_private import NoBalance, OKXPrivateError
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
    def __init__(self, tmp_path, watchlist=(BTC,)):
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
        self.account = DemoAccount(self.ledger, self.okx, self.exchange, watchlist=watchlist, sleep=lambda s: None)
        self.inbox = Inbox()

    def decide(self, hour, signal, coin=BTC):
        self.intraday.record_signal(hour + 3 * 60_000, coin.research, SignalResult(signal, 1, "", None, 1, 1))
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
    assert text.startswith("【demo】01-10 00:00 UTC\nBTC：Long → ")
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
    assert env.inbox.sent[-1].startswith("【demo】01-10 01:00 UTC\nBTC：Flat → ")


def test_a_reconciliation_problem_blocks_the_hour_and_alerts_once_per_interval(env):
    env.decide(HOUR, "Long")
    env.run(RUN0)
    env.exchange.leverage = 5.0  # set by hand on the exchange
    env.decide(HOUR + HOUR_MS, "Short")
    env.run(RUN0 + HOUR_MS)
    assert len(env.exchange.fill_rows) == 1  # nothing traded at the odd leverage
    assert env.ledger.get("decided_hour") == HOUR
    assert env.inbox.sent[1:] == ["【demo】对账：BTC-USDT-SWAP 在交易所是 cross 5×，不是设计的 cross 3×"]
    env.decide(HOUR + 2 * HOUR_MS, "Short")
    env.run(RUN0 + 2 * HOUR_MS)
    assert len(env.inbox.sent) == 2  # the problem persists but is not repeated yet
    assert env.events().count("problem") == 2
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
    *_, kill, flat = env.inbox.sent
    assert kill.startswith("【demo】熔断：净值") and "已对 BTC-USDT-SWAP 发出市价平仓" in kill
    assert kill.endswith("运行 python -m trader demo resume --kill 解除。")
    assert flat == "【demo】熔断后核实：交易所里已经空仓。"
    assert env.ledger.get("decided_hour") == HOUR  # the second hour was not traded


def test_a_failure_is_raised_and_alerted_once(env):
    def broken(ccy="USDT"):
        raise OKXError("balance failed with code 50001: service unavailable")

    env.exchange.balance = broken
    with pytest.raises(OKXError):
        env.run(RUN0)
    with pytest.raises(OKXError):
        env.run(RUN0 + HOUR_MS)
    assert env.inbox.sent == ["【demo】运行失败：OKXError: balance failed with code 50001: service unavailable"]


def test_the_first_run_of_a_day_sends_yesterdays_summary(env):
    env.ledger.set("summarized_day", "2026-01-09")
    env.decide(HOUR, "Long")
    env.run(RUN0)
    assert env.inbox.sent[-1].startswith("【demo】日报 · 2026-01-09\n权益 9,996.00 USDT，较本金 -0.04%")
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


# -- stops that will not stand, and steps that fail after the orders (#32) ----------------


def wrap(call, before=None, after=None):
    """``call`` with something done first, or once it has returned: for a failure that
    sets in at a given point of the run."""
    def wrapped(*args, **kwargs):
        if before:
            before()
        out = call(*args, **kwargs)
        if after:
            after()
        return out
    return wrapped


def test_a_position_whose_stop_will_not_hang_is_closed_and_booked_within_the_run(env):
    env.decide(HOUR, "Long")
    env.exchange.fail(
        "place_stop", OKXPrivateError("/api/v5/trade/order-algo", "50001", "Service temporarily unavailable")
    )
    clock = env.run(RUN0)
    assert clock.sleeps == [KILL_SETTLE_SECONDS]  # the close order fills, then one more sync
    assert env.exchange.book[BTC.swap][0] == 0 and env.exchange.stops == [] and env.exchange.bare() == []
    assert [f.reason for f in env.ledger.fills()] == ["trade", "stop"]
    assert env.ledger.positions() == {} and env.ledger.get("decided_hour") == HOUR
    alert, report = env.inbox.sent
    assert alert.startswith("【demo】止损平仓：BTC-USDT-SWAP +10 张试了 3 次都没挂上止损")
    assert report.startswith("【demo】01-10 00:00 UTC\nBTC：Long → 买入 0.1 @ 80,000.00；无持仓\n")


def test_a_stop_the_price_has_crossed_is_closed_by_the_hourly_run_and_the_hour_goes_on_as_on_paper(env):
    env.decide(HOUR, "Long")
    env.run(RUN0)
    env.exchange.stops = []                       # the stop is not on the exchange
    env.okx.last = env.exchange.price = 78_500.0  # and the price is below it
    env.decide(HOUR + HOUR_MS, "Long")
    clock = env.run(RUN0 + HOUR_MS)
    assert clock.sleeps == [KILL_SETTLE_SECONDS]
    # Closed as a stop at the market, booked, and then the hour's signal is followed:
    # 9,842 of equity buy 9.84 contracts at 78,500, their stop 1,000 below.
    assert [(f.reason, f.price) for f in env.ledger.fills()] == [
        ("trade", 80_000.0), ("stop", 78_500.0), ("trade", 78_500.0),
    ]
    assert env.exchange.book[BTC.swap] == [9.84, 78_500.0]
    assert [(s.contracts, s.trigger) for s in env.exchange.stops] == [(9.84, 77_500.0)]
    alert, report = env.inbox.sent[1:]
    assert alert.startswith("【demo】止损平仓：BTC-USDT-SWAP +10 张的止损价 79,000.00 已被现价 78,500.00 穿越")
    assert report.startswith("【demo】01-10 01:00 UTC\nBTC：Long → 买入 0.0984 @ 78,500.00；持仓 +0.0984，止损 77,500.00")
    # The next hour does not trip over the old stop again.
    env.decide(HOUR + 2 * HOUR_MS, "Long")
    clock = env.run(RUN0 + 2 * HOUR_MS)
    assert clock.sleeps == [] and len(env.inbox.sent) == 3
    assert [c[0] for c in env.exchange.calls].count("close_position") == 1


def test_an_exception_between_the_order_and_its_stop_still_leaves_the_position_with_its_stop(env):
    env.decide(HOUR, "Long")
    failure = OKXError("fills failed with code 50001: service unavailable")
    env.account.execute = wrap(env.account.execute, after=lambda: env.exchange.fail("fills", failure))
    with pytest.raises(OKXError):
        env.run(RUN0)
    assert env.exchange.book[BTC.swap] == [10.0, 80_000.0] and env.exchange.bare() == []
    assert [(s.side, s.contracts, s.trigger) for s in env.exchange.stops] == [("sell", 10.0, 79_000.0)]
    assert env.ledger.get("decided_hour") is None
    assert env.inbox.sent == ["【demo】运行失败：OKXError: fills failed with code 50001: service unavailable"]
    # The next run books the fill behind the position and finds its stop as it should be.
    del env.account.execute
    env.exchange.failures.clear()
    env.decide(HOUR + HOUR_MS, "Long")
    env.run(RUN0 + HOUR_MS)
    assert [f.reason for f in env.ledger.fills()] == ["trade"]
    assert env.ledger.positions()[BTC.swap].stop == 79_000.0
    assert [c[0] for c in env.exchange.calls if c[0].endswith("_stop")] == ["place_stop"]


def test_an_order_that_filled_before_the_execution_raised_still_gets_its_stop(env):
    env.decide(HOUR, "Long")
    env.exchange.fail("order", requests.ConnectionError("connection reset"))  # the fill cannot be read back
    with pytest.raises(requests.ConnectionError):
        env.run(RUN0)
    assert env.exchange.book[BTC.swap] == [10.0, 80_000.0] and env.exchange.bare() == []
    # No fill price was read, so the stop is measured from the quotes.
    assert [(s.side, s.contracts, s.trigger) for s in env.exchange.stops] == [("sell", 10.0, 79_000.0)]
    assert env.inbox.sent == ["【demo】运行失败：ConnectionError: connection reset"]


def test_the_stop_is_measured_from_the_fill_where_it_is_not_at_the_quote(env):
    # The order fills 400 above the quote. The trade sets the stop 1,000 below the
    # fill, and that is what hangs: measured from the quote it would be 400 lower.
    env.decide(HOUR, "Long")
    env.exchange.price = 80_400.0
    env.run(RUN0)
    assert env.exchange.book[BTC.swap] == [10.0, 80_400.0]
    assert [(s.side, s.contracts, s.trigger) for s in env.exchange.stops] == [("sell", 10.0, 79_400.0)]
    assert env.ledger.positions()[BTC.swap].stop == 79_400.0


def test_after_a_failure_the_stop_that_hangs_is_still_the_one_measured_from_the_fill(env):
    env.decide(HOUR, "Long")
    env.exchange.price = 80_400.0
    failure = OKXError("fills failed with code 50001: service unavailable")
    env.account.execute = wrap(env.account.execute, after=lambda: env.exchange.fail("fills", failure))
    with pytest.raises(OKXError):
        env.run(RUN0)
    assert env.exchange.book[BTC.swap] == [10.0, 80_400.0] and env.exchange.bare() == []
    assert [(s.side, s.contracts, s.trigger) for s in env.exchange.stops] == [("sell", 10.0, 79_400.0)]
    assert env.ledger.positions()[BTC.swap].stop == 79_400.0


def test_the_alerts_gathered_before_an_exception_still_go_out_and_the_filled_contract_gets_its_stop(tmp_path):
    env = Env(tmp_path, watchlist=(BTC, ETH))
    env.decide(HOUR, "Long")
    env.decide(HOUR, "Long", coin=ETH)
    env.exchange.fail(
        "place_market", OKXPrivateError("/api/v5/trade/order", "51008", "Insufficient balance"), inst=BTC.swap
    )
    env.exchange.fail("order", requests.ConnectionError("connection reset"), inst=ETH.swap)
    with pytest.raises(requests.ConnectionError):
        env.run(RUN0)
    assert env.inbox.sent == [
        "【demo】下单失败：BTC-USDT-SWAP +10 张：/api/v5/trade/order failed with code 51008: Insufficient balance",
        "【demo】运行失败：ConnectionError: connection reset",
    ]
    assert env.exchange.book[ETH.swap] == [10.0, 80_000.0] and env.exchange.bare() == []
    assert [(s.inst, s.contracts, s.trigger) for s in env.exchange.stops] == [(ETH.swap, 10.0, 79_000.0)]


def test_when_the_stops_cannot_be_seen_to_after_a_failure_the_alert_names_the_contracts(env):
    env.decide(HOUR, "Long")
    down = requests.ConnectionError("connection reset")
    env.account.execute = wrap(env.account.execute, after=lambda: env.exchange.fail("positions", down))
    with pytest.raises(requests.ConnectionError):
        env.run(RUN0)
    assert env.inbox.sent == [
        "【demo】紧急：下单之后出了错，补挂止损这一步也没做成（ConnectionError: connection reset），"
        "BTC-USDT-SWAP 的仓位可能没有止损，请立即人工检查",
        "【demo】运行失败：ConnectionError: connection reset",
    ]
    assert env.exchange.bare() == [BTC.swap]  # nothing could be done for it: the alert is all there is
    assert "stop_failed" in env.events()
    # The next run, the exchange back, hangs the stop.
    del env.account.execute
    env.exchange.failures.clear()
    env.run(RUN0 + HOUR_MS)
    assert [(s.contracts, s.trigger) for s in env.exchange.stops] == [(10.0, 79_000.0)]
    assert env.exchange.bare() == []


def test_a_kill_at_the_sync_before_the_orders_still_sends_its_alert(env):
    env.decide(HOUR, "Long")
    env.run(RUN0)
    # The second hour's decision comes late, and while the demo waits for it the
    # market falls through the kill line: the sync that sizes the orders trips it.
    def fall_and_decide(n):
        env.exchange.mark[BTC.swap] = env.exchange.prices[BTC.swap] = 59_000.0
        env.decide(HOUR + HOUR_MS, "Long")

    clock = Clock(RUN0 + HOUR_MS)
    clock.on_sleep = fall_and_decide
    env.exchange.now = RUN0 + HOUR_MS
    job.run(env.settings, env.account, env.inbox, env.intraday, now_fn=clock.now, sleep=clock.sleep)
    assert clock.sleeps == [INTRADAY_POLL_SECONDS, KILL_SETTLE_SECONDS]
    assert env.ledger.get("halted") is True and env.exchange.book[BTC.swap][0] == 0
    assert len(env.inbox.sent) == 3 and env.inbox.sent[1].startswith("【demo】熔断：净值 7,896.00 比峰值 10,000.00")
    # The closes are booked, and the hour is not traded.
    assert env.inbox.sent[2] == "【demo】熔断后核实：交易所里已经空仓。"
    assert [f.reason for f in env.ledger.fills()] == ["trade", "kill"] and env.ledger.get("decided_hour") == HOUR


def test_whatever_fails_once_the_orders_start_no_position_is_left_without_a_stop_and_unnamed(tmp_path):
    # 60 draws from a fixed seed: two coins, an hour that goes well, then an hour whose
    # orders meet an exchange that answers at random what is not known of the real one
    # and fails at random, from the first order on or once the orders are done.
    rng = random.Random(32)
    calls = ("place_market", "order", "fills", "positions", "pending_stops",
             "amend_stop", "place_stop", "cancel_stops", "close_position")
    for n in range(60):
        env = Env(tmp_path / str(n), watchlist=(BTC, ETH))
        for hour in (HOUR, HOUR + HOUR_MS):
            for coin in (BTC, ETH):
                env.decide(hour, rng.choice(["Long", "Short", "Flat"]), coin=coin)
            if hour == HOUR:
                env.run(RUN0)
        sent, when, raised = len(env.inbox.sent), rng.choice(["before", "after"]), None
        env.account.execute = wrap(env.account.execute, **{when: partial(env.exchange.unsettle, rng, calls)})
        try:
            env.run(RUN0 + HOUR_MS)
        except Exception as exc:
            raised = exc
        said = env.inbox.sent[sent:]
        told = f"draw {n}: unsettled {when} the orders, {env.exchange.world}, raised {raised!r}, sent {said}"
        assert env.exchange.gaps == [], told
        assert [inst for inst in env.exchange.bare() if not any(inst in text for text in said)] == [], told
        env.ledger.db.close()
        env.intraday.db.close()


def test_what_the_stops_raised_is_sent_even_when_the_run_then_fails(env):
    env.decide(HOUR, "Long")
    env.run(RUN0)
    env.exchange.stops = []
    env.okx.last = env.exchange.price = 78_500.0
    # The position is closed for its crossed stop, and then the sync that would book
    # the close fails: the close must still be heard of.
    failure = OKXError("fills failed with code 50001: service unavailable")
    env.exchange.close_position = wrap(
        env.exchange.close_position, after=lambda: env.exchange.fail("fills", failure)
    )
    with pytest.raises(OKXError):
        env.run(RUN0 + HOUR_MS)
    closed, failed = env.inbox.sent[1:]
    assert closed.startswith("【demo】止损平仓：BTC-USDT-SWAP +10 张的止损价 79,000.00 已被现价 78,500.00 穿越")
    assert failed == "【demo】运行失败：OKXError: fills failed with code 50001: service unavailable"


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
    assert result.exit_code == 1 and "没有处于暂停" in result.output
    result = runner.invoke(cli.app, ["demo", "resume", "--kill"])
    assert result.exit_code == 1 and "没有处于熔断" in result.output
    ledger = Ledger(settings.demo_ledger_path)
    ledger.set("halted", True)
    ledger.db.close()
    result = runner.invoke(cli.app, ["demo", "resume"])
    assert result.exit_code == 1 and "它处于熔断，解除熔断要加 --kill" in result.output
    exchange.manual_fill(BTC.swap, 5)
    result = runner.invoke(cli.app, ["demo", "resume", "--kill"])
    assert result.exit_code == 1 and "交易所里还有持仓" in result.output
    assert exchange.book[BTC.swap][0] == 0  # the halted account's sync closed it
    result = runner.invoke(cli.app, ["demo", "resume", "--kill"])
    assert result.exit_code == 0, result.output
    assert Ledger(settings.demo_ledger_path, readonly=True).get("halted") is False


def test_demo_resume_lifts_a_pause_and_leaves_a_kill_to_its_flag(demo_cli):
    runner, exchange, settings = demo_cli
    assert runner.invoke(cli.app, ["demo", "init"]).exit_code == 0
    ledger = Ledger(settings.demo_ledger_path)
    DemoAccount(ledger, FakeOKX(), exchange).pause(T0, "对不上账")
    ledger.set("halted", True)
    ledger.db.close()
    result = runner.invoke(cli.app, ["demo", "resume"])
    assert result.exit_code == 0, result.output
    ledger = Ledger(settings.demo_ledger_path, readonly=True)
    assert ledger.get("paused") is False and ledger.get("halted") is True


def test_demo_pause_enters_the_reason_given_and_resume_lifts_it(demo_cli, monkeypatch):
    runner, exchange, settings = demo_cli
    inbox = Inbox()
    monkeypatch.setattr(cli, "Notifier", lambda settings: inbox)
    assert runner.invoke(cli.app, ["demo", "init"]).exit_code == 0
    result = runner.invoke(cli.app, ["demo", "pause", "--note", "换模型之前"])
    assert result.exit_code == 0, result.output
    text = (
        "人工暂停：换模型之前。不再下新单，仓位和止损单原样保留，暂停期间不改止损、回撤到线只告警；"
        "运行 python -m trader demo resume 解除。"
    )
    assert result.output.splitlines() == [text] and inbox.sent[-1] == f"【demo】{text}"
    ledger = Ledger(settings.demo_ledger_path, readonly=True)
    assert ledger.get("paused") is True
    assert [(r["key"], r["text"]) for r in ledger.get("pause_reasons")] == [("manual_pause", "人工暂停：换模型之前")]
    result = runner.invoke(cli.app, ["demo", "resume"])
    assert result.exit_code == 0, result.output
    assert any(line.startswith("解除暂停：人工暂停：换模型之前（") for line in result.output.splitlines())
    assert Ledger(settings.demo_ledger_path, readonly=True).get("paused") is False


def test_demo_resume_kill_on_an_account_still_paused_says_it_will_not_trade(demo_cli, monkeypatch):
    runner, exchange, settings = demo_cli
    inbox = Inbox()
    monkeypatch.setattr(cli, "Notifier", lambda settings: inbox)
    assert runner.invoke(cli.app, ["demo", "init"]).exit_code == 0
    ledger = Ledger(settings.demo_ledger_path)
    DemoAccount(ledger, FakeOKX(), exchange).pause(T0, "对不上账")
    ledger.set("halted", True)
    ledger.db.close()
    result = runner.invoke(cli.app, ["demo", "resume", "--kill"])
    assert result.exit_code == 0, result.output
    assert inbox.sent == ["【demo】熔断已解除；账户仍在暂停中，不会交易。"]
    ledger = Ledger(settings.demo_ledger_path, readonly=True)
    assert ledger.get("halted") is False and ledger.get("paused") is True


def test_demo_halt_asks_first_unless_told_yes(demo_cli):
    runner, _, settings = demo_cli
    assert runner.invoke(cli.app, ["demo", "init"]).exit_code == 0
    result = runner.invoke(cli.app, ["demo", "halt"], input="n\n")
    assert result.exit_code == 1 and "停止 demo 账户的交易，市价平掉交易所里的全部仓位。" in result.output
    assert not Ledger(settings.demo_ledger_path, readonly=True).get("halted")
    result = runner.invoke(cli.app, ["demo", "halt", "--yes"])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("人工熔断：停止交易，平掉 0 个仓位，还剩 0 个。")
    assert Ledger(settings.demo_ledger_path, readonly=True).get("halted") is True


def test_demo_halt_that_cannot_record_the_kill_says_it_did_not_halt(demo_cli, monkeypatch):
    runner, _, settings = demo_cli
    assert runner.invoke(cli.app, ["demo", "init"]).exit_code == 0

    def locked_db(self, now_ms, reason):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(DemoAccount, "halt", locked_db)
    result = runner.invoke(cli.app, ["demo", "halt", "--yes"])
    assert result.exit_code == 1 and "demo 没能熔断：OperationalError: database is locked" in result.output
    assert not Ledger(settings.demo_ledger_path, readonly=True).get("halted")


def test_demo_halt_whose_sync_fails_says_the_kill_stands(demo_cli):
    runner, exchange, settings = demo_cli
    assert runner.invoke(cli.app, ["demo", "init"]).exit_code == 0
    exchange.fail("positions", requests.ConnectionError("down"))
    result = runner.invoke(cli.app, ["demo", "halt", "--yes"])
    assert result.exit_code == 1 and "demo 已熔断，但这次没做完：ConnectionError: down" in result.output
    assert Ledger(settings.demo_ledger_path, readonly=True).get("halted") is True


def late_fill(runner, exchange, now):
    """A demo account opened at T0 whose exchange filled 5 contracts at 00:35 and reported
    the fill only after the sync of 01:00 had read past it; the account holds them."""
    assert runner.invoke(cli.app, ["demo", "init"]).exit_code == 0
    exchange.now = T0 + 5 * 60_000
    exchange.manual_fill(BTC.swap, 5)
    row = exchange.fill_rows.pop()
    now[0] = T0 + 30 * 60_000
    assert runner.invoke(cli.app, ["demo", "sync"]).exit_code == 0
    exchange.fill_rows.append(row)


def test_demo_reconcile_shows_the_repair_and_writes_it_only_once_told_yes(demo_cli, monkeypatch):
    runner, exchange, settings = demo_cli
    now = [T0]
    monkeypatch.setattr(cli, "_now_ms", lambda: now[0])
    late_fill(runner, exchange, now)
    result = runner.invoke(cli.app, ["demo", "reconcile"])
    assert result.exit_code == 1
    assert "demo 没有修复：demo 账户没有暂停也没有熔断：只有暂停或熔断时才能修复账本" in result.output
    now[0] = T0 + 60 * 60_000
    assert "暂停：账本与交易所持仓不一致" in runner.invoke(cli.app, ["demo", "sync"]).output
    now[0] = T0 + 70 * 60_000
    plan = [
        "重读了 2026-01-10 00:30 到 2026-01-10 01:31 UTC 的成交和资金费",
        "补记漏掉的成交 1 笔：",
        "  2026-01-10 00:35 BTC-USDT-SWAP +0.05 @ 80,000.00，手续费 2.00，非程序",
    ]
    for answer in ("n\n", "\n"):  # Enter alone is a no
        result = runner.invoke(cli.app, ["demo", "reconcile"], input=answer)
        assert result.exit_code == 1 and result.output.splitlines()[:3] == plan
        assert "把上面这些写进账本吗？" in result.output
    ledger = Ledger(settings.demo_ledger_path, readonly=True)
    assert ledger.fills() == [] and ledger.events(kinds=("reconcile",)) == []

    def synced_meanwhile(*args, **kwargs):  # the hourly run synced while the person read the plan
        Ledger(settings.demo_ledger_path).set("synced_to", now[0])
        return True

    with monkeypatch.context() as m:
        m.setattr(cli.typer, "confirm", synced_meanwhile)
        result = runner.invoke(cli.app, ["demo", "reconcile"])
    assert result.exit_code == 1
    assert "demo 没有修复：账本在确认期间变了（多半是每小时的运行刚对过账），这份修复已经不对了：请重新运行" in result.output
    assert ledger.fills() == []
    plan[0] = "重读了 2026-01-10 00:30 到 2026-01-10 01:41 UTC 的成交和资金费"
    result = runner.invoke(cli.app, ["demo", "reconcile"], input="y\n")
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[:3] == plan
    assert result.output.splitlines()[-2:] == [
        "已写入：修复账本（python -m trader demo reconcile）：补记漏掉的成交 1 笔",
        "账户仍在暂停中：运行 python -m trader demo resume，它先对一次账，对得上才解除暂停。",
    ]
    assert [f.reason for f in ledger.fills()] == ["manual"]
    result = runner.invoke(cli.app, ["demo", "reconcile"])
    assert result.exit_code == 0
    assert result.output.splitlines()[-1] == "账本和交易所对得上：没有漏记的成交和资金费，持仓也一致，不用修复。"
    result = runner.invoke(cli.app, ["demo", "resume"])
    assert result.exit_code == 0, result.output


def test_demo_reconcile_of_a_halted_account_leaves_the_kill_standing(demo_cli, monkeypatch):
    runner, exchange, settings = demo_cli
    now = [T0]
    monkeypatch.setattr(cli, "_now_ms", lambda: now[0])
    late_fill(runner, exchange, now)
    ledger = Ledger(settings.demo_ledger_path)
    ledger.set("halted", True)
    ledger.db.close()
    exchange.fail("fills", requests.ConnectionError("down"), times=1)
    result = runner.invoke(cli.app, ["demo", "reconcile", "--yes"])
    assert result.exit_code == 1 and "demo 没有修复：读交易所失败（ConnectionError: down）" in result.output
    result = runner.invoke(cli.app, ["demo", "reconcile", "--yes"])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[-1] == (
        "账户仍在熔断中：确认交易所里已经空仓、查明原因后，运行 python -m trader demo resume --kill 解除。"
    )
    assert exchange.book[BTC.swap][0] == 5.0  # a repair closes nothing


def test_demo_check_shows_an_account_without_usdt_and_init_refuses_it(demo_cli):
    runner, exchange, settings = demo_cli

    def none(ccy="USDT"):
        raise NoBalance("the account's balance has no USDT row")

    exchange.balance = none
    result = runner.invoke(cli.app, ["demo", "check"])
    assert result.exit_code == 0, result.output
    assert "USDT 没有余额：模拟账户里还没有 USDT，先在 OKX 模拟盘领取资金" in result.output
    result = runner.invoke(cli.app, ["demo", "init"])
    assert result.exit_code == 1 and "模拟账户里没有 USDT" in result.output
    assert not settings.demo_ledger_path.exists() or not Ledger(settings.demo_ledger_path).initialized


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
