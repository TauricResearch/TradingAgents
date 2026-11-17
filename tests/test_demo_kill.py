"""The kill switch of an account on the exchange (#33): tripped before anything is
closed, each position closed on its own and the exchange checked flat, alerted whatever
the run does next; tripped by hand with ``halt``, paused or not; and a balance that
cannot be read fails the run instead of reading as a total loss."""

import pytest

from tests.test_demo_account import BTC, ETH, HOUR, T0, FakeExchange
from tests.test_demo_job import RUN0, Clock, Env
from tests.test_live_pause import LIVE_CAPITAL
from trader.demo import job, report
from trader.demo.account import DEMO, DemoAccount
from trader.demo.settings import KILL_SETTLE_SECONDS
from trader.intraday.paper import HOUR_MS
from trader.ledger import Ledger
from trader.live.account import LIVE
from trader.okx import OKXError
from trader.okx_private import NoBalance, OKXPrivateError

UNAVAILABLE = OKXPrivateError("/api/v5/trade/close-position", "50001", "Service temporarily unavailable")
UNAVAILABLE_TEXT = f"OKXPrivateError: {UNAVAILABLE}"
AFTER = "确认交易所里已经空仓、查明原因后，运行 python -m trader demo resume --kill 解除。"
BOTH = "BTC-USDT-SWAP、ETH-USDT-SWAP"


@pytest.fixture
def env(tmp_path):
    """A demo account long BTC and ETH, ten contracts each at 80,000, with their stops."""
    env = Env(tmp_path, watchlist=(BTC, ETH))
    env.decide(HOUR, "Long")
    env.decide(HOUR, "Long", coin=ETH)
    env.run(RUN0)
    assert env.exchange.book == {BTC.swap: [10.0, 80_000.0], ETH.swap: [10.0, 80_000.0]}
    assert sorted(s.inst for s in env.exchange.stops) == [BTC.swap, ETH.swap]
    env.inbox.sent.clear()
    return env


def fall(env, price=69_000.0):
    """Both down to ``price``; at 69,000, a drawdown past the kill line."""
    for inst in (BTC.swap, ETH.swap):
        env.exchange.mark[inst] = env.exchange.prices[inst] = price


def texts(ledger, kind):
    return [text for _, _, text in ledger.events(kinds=(kind,))]


def halt(env, now_ms=RUN0 + 20 * 60_000):
    clock = Clock(now_ms)
    env.exchange.now = now_ms
    return job.halt(env.settings, env.account, env.inbox, now_fn=clock.now, sleep=clock.sleep), clock


# -- the kill by drawdown ---------------------------------------------------------------


def test_a_close_that_fails_leaves_the_others_closed_its_stop_standing_and_the_next_run_closing_it(env):
    # A failure was alerted a minute ago: the alert of a failed run is throttled, the kill's are not.
    env.ledger.set(DEMO.failures_key, {"OKXError": RUN0 + HOUR_MS - 60_000})
    fall(env)
    env.exchange.fail("close_position", UNAVAILABLE, inst=BTC.swap)
    clock = env.run(RUN0 + HOUR_MS)
    assert env.ledger.get("halted") is True and clock.sleeps == [KILL_SETTLE_SECONDS]
    assert env.exchange.book[ETH.swap][0] == 0 and env.exchange.book[BTC.swap][0] == 10.0
    assert [s.inst for s in env.exchange.stops] == [BTC.swap]  # held, so its stop stands
    failed = f"BTC-USDT-SWAP 平仓失败（{UNAVAILABLE_TEXT}），止损单留着，下一次运行再平"
    kill, still = env.inbox.sent
    assert kill.startswith("【demo】熔断：净值 ")
    assert kill.endswith(f"停止交易；已对 ETH-USDT-SWAP 发出市价平仓；{failed}。{AFTER}")
    assert still == f"【demo】熔断中：BTC-USDT-SWAP 还有仓位；{failed}。"
    daily = report.daily(env.account, "2026-01-10", RUN0 + HOUR_MS).splitlines()
    assert daily[1:3] == ["", f"⚠ 熔断中：交易所里还有 1 个仓位，每次运行都再平，不再下单。{AFTER}"]

    env.exchange.failures.clear()
    env.run(RUN0 + 2 * HOUR_MS)
    assert env.exchange.book[BTC.swap][0] == 0 and env.exchange.stops == [] and env.ledger.positions() == {}
    assert env.inbox.sent[2:] == [
        "【demo】熔断中：BTC-USDT-SWAP 还有仓位；已对 BTC-USDT-SWAP 发出市价平仓。",
        "【demo】熔断后核实：交易所里已经空仓。",
    ]
    assert [f.reason for f in env.ledger.fills()] == ["trade", "trade", "kill", "kill"]


def test_the_kill_is_recorded_before_anything_is_closed(env):
    fall(env)
    env.exchange.fail("close_position", RuntimeError("a bug"), times=1)
    with pytest.raises(RuntimeError):
        env.account.sync(RUN0 + HOUR_MS)
    assert env.ledger.get("halted") is True
    (reason,) = texts(env.ledger, "kill")
    assert reason.startswith("回撤 ") and "到了熔断线：净值 " in reason
    # Whatever sync comes next closes what is held.
    result = env.account.sync(RUN0 + HOUR_MS + 1_000)
    assert result.killed and result.alerts == [f"熔断中：{BOTH} 还有仓位；已对 {BOTH} 发出市价平仓。"]
    assert env.exchange.book[BTC.swap][0] == 0 and env.exchange.book[ETH.swap][0] == 0


def test_the_kill_alert_goes_out_though_the_run_then_fails_and_failure_alerts_are_throttled(env):
    env.ledger.set(DEMO.failures_key, {"OKXError": RUN0 + HOUR_MS - 60_000})
    fall(env)

    def down(hour, positions, now_ms, alerts):
        raise OKXError("candles failed with code 50001: service unavailable")

    env.account.quotes = down
    with pytest.raises(OKXError):
        env.run(RUN0 + HOUR_MS)
    kill, flat = env.inbox.sent
    assert kill.startswith("【demo】熔断：净值 ") and kill.endswith(f"已对 {BOTH} 发出市价平仓。{AFTER}")
    assert flat == "【demo】熔断后核实：交易所里已经空仓。"


def test_a_balance_that_cannot_be_read_fails_the_run_alerts_and_closes_nothing(env):
    # Read as zero it was a total loss, and the positions open would have been killed.
    def unreadable(ccy="USDT"):
        raise NoBalance("the account's balance has no USDT row")

    env.exchange.balance = unreadable
    before = list(env.exchange.calls)
    with pytest.raises(NoBalance):
        env.run(RUN0 + HOUR_MS)
    assert env.inbox.sent == ["【demo】运行失败：NoBalance: the account's balance has no USDT row"]
    assert env.exchange.calls == before and not env.ledger.get("halted")
    assert env.exchange.book == {BTC.swap: [10.0, 80_000.0], ETH.swap: [10.0, 80_000.0]}


# -- the kill by hand -----------------------------------------------------------------------


def test_halt_closes_every_position_and_no_run_trades_after(env):
    lines, clock = halt(env)
    summary = f"人工熔断：停止交易，平掉 2 个仓位，还剩 0 个。{AFTER}"
    assert lines == [
        f"熔断中：{BOTH} 还有仓位；已对 {BOTH} 发出市价平仓。",
        "熔断后核实：交易所里已经空仓。",
        summary,
    ]
    assert env.inbox.sent == [f"【demo】{summary}"] and clock.sleeps == [KILL_SETTLE_SECONDS]
    assert env.ledger.get("halted") is True and env.exchange.stops == []
    assert env.exchange.book[BTC.swap][0] == 0 and env.exchange.book[ETH.swap][0] == 0
    assert texts(env.ledger, "kill")[0] == "人工熔断：python -m trader demo halt"
    env.decide(HOUR + HOUR_MS, "Long")
    env.decide(HOUR + HOUR_MS, "Long", coin=ETH)
    env.run(RUN0 + HOUR_MS)
    assert env.exchange.book[BTC.swap][0] == 0 and env.exchange.book[ETH.swap][0] == 0
    assert [f.reason for f in env.ledger.fills()] == ["trade", "trade", "kill", "kill"]


def test_halt_without_positions_still_trips_the_kill_switch(tmp_path):
    env = Env(tmp_path)
    lines, clock = halt(env, RUN0)
    summary = f"人工熔断：停止交易，平掉 0 个仓位，还剩 0 个。{AFTER}"
    assert lines == [summary] and env.inbox.sent == [f"【demo】{summary}"]
    assert env.ledger.get("halted") is True and clock.sleeps == [] and env.exchange.calls == []
    env.decide(HOUR, "Long")
    env.run(RUN0 + 60_000)
    assert env.exchange.book == {} and env.exchange.calls == []


def test_halt_says_what_is_left_and_the_next_run_goes_on_closing_it(env):
    env.exchange.fail("close_position", UNAVAILABLE, inst=BTC.swap)
    lines, _ = halt(env)
    summary = f"人工熔断：停止交易，平掉 1 个仓位，还剩 1 个（BTC-USDT-SWAP），下一次运行接着平。{AFTER}"
    assert lines[-1] == summary and env.inbox.sent == [f"【demo】{summary}"]
    assert [s.inst for s in env.exchange.stops] == [BTC.swap]
    env.exchange.failures.clear()
    env.run(RUN0 + HOUR_MS)
    assert env.exchange.book[BTC.swap][0] == 0 and env.exchange.stops == []


def test_halt_waits_through_a_close_that_the_next_sync_sends_again(env):
    env.exchange.fail("close_position", UNAVAILABLE, times=1, inst=BTC.swap)
    lines, clock = halt(env)
    assert lines[-1] == f"人工熔断：停止交易，平掉 2 个仓位，还剩 0 个。{AFTER}"
    assert clock.sleeps == [KILL_SETTLE_SECONDS] * 2 and env.exchange.stops == []


def test_a_halt_whose_sync_fails_stays_halted_and_says_so(env):
    env.exchange.fail("positions", OKXError("positions failed with code 50001: service unavailable"))
    with pytest.raises(OKXError):
        halt(env)
    assert env.ledger.get("halted") is True and env.exchange.book[BTC.swap][0] == 10.0
    assert env.inbox.sent == [
        "【demo】人工熔断：已停止交易，但这次没能平仓（OKXError: positions failed with code 50001: "
        "service unavailable）；每小时的运行会接着平。"
    ]


def test_halt_closes_out_a_paused_account_too(tmp_path):
    # ADR 0010: a paused account's drawdown kills nothing, but a person can kill it.
    env = Env(tmp_path)
    ledger = Ledger(env.settings.live_ledger_path)
    ledger.initialize(LIVE_CAPITAL, T0 - HOUR_MS)
    ledger.set("summarized_day", "2026-01-10")
    exchange = FakeExchange(cash=LIVE_CAPITAL)
    exchange.simulated = False
    account = DemoAccount(ledger, env.okx, exchange, watchlist=(BTC,), sleep=lambda s: None, profile=LIVE)
    exchange.now = RUN0
    exchange.manual_fill(BTC.swap, 5)  # opened by hand on the exchange
    assert account.paused
    lines = job.halt(env.settings, account, env.inbox, now_fn=Clock(RUN0).now, sleep=lambda s: None)
    summary = "人工熔断：停止交易，平掉 1 个仓位，还剩 0 个。按 ADR 0010，live 熔断一次就不再解除，实验到此结束。"
    assert lines[-1] == summary and env.inbox.sent == [f"【live】{summary}"]
    assert ledger.get("halted") is True and account.paused and exchange.book[BTC.swap][0] == 0
    # Its next hour, still paused, is a shadow run that says why it would send nothing.
    env.decide(HOUR, "Long")
    clock = Clock(RUN0 + 60_000)
    exchange.now = clock.now_ms
    job.run(env.settings, account, env.inbox, env.intraday, now_fn=clock.now, sleep=clock.sleep)
    assert exchange.book[BTC.swap][0] == 0
    assert texts(ledger, "shadow_none") == ["本小时不下单：熔断中"]


def test_a_halt_while_the_run_waits_for_the_hours_decision_leaves_the_hour_untraded(env):
    # The run waits for the decision outside its lock, so a person's halt can come in between.
    def halt_then_decide(n):
        if n == 1:
            env.exchange.now = clock.now_ms
            job.halt(env.settings, env.account, env.inbox, now_fn=clock.now, sleep=lambda s: None)
            env.decide(HOUR + HOUR_MS, "Long")
            env.decide(HOUR + HOUR_MS, "Long", coin=ETH)

    clock = Clock(RUN0 + HOUR_MS)
    clock.on_sleep = halt_then_decide
    env.exchange.now = clock.now_ms
    job.run(env.settings, env.account, env.inbox, env.intraday, now_fn=clock.now, sleep=clock.sleep)
    assert env.ledger.get("halted") is True
    assert [env.exchange.book[inst][0] for inst in (BTC.swap, ETH.swap)] == [0, 0]
    assert env.inbox.sent == [f"【demo】人工熔断：停止交易，平掉 2 个仓位，还剩 0 个。{AFTER}"]
    assert [f.reason for f in env.ledger.fills()] == ["trade", "trade", "kill", "kill"]
    assert env.ledger.get("decided_hour") == HOUR


def test_a_halt_while_a_paused_account_waits_for_the_hours_decision_leaves_a_shadow_of_nothing(tmp_path):
    env = Env(tmp_path)
    ledger = Ledger(env.settings.live_ledger_path)
    ledger.initialize(LIVE_CAPITAL, T0 - HOUR_MS)
    ledger.set("summarized_day", "2026-01-10")
    exchange = FakeExchange(cash=LIVE_CAPITAL)
    exchange.simulated = False
    account = DemoAccount(ledger, env.okx, exchange, watchlist=(BTC,), sleep=lambda s: None, profile=LIVE)

    def halt_then_decide(n):
        if n == 1:
            exchange.now = clock.now_ms
            job.halt(env.settings, account, env.inbox, now_fn=clock.now, sleep=lambda s: None)
            env.decide(HOUR, "Long")

    clock = Clock(RUN0)
    clock.on_sleep = halt_then_decide
    exchange.now = RUN0
    job.run(env.settings, account, env.inbox, env.intraday, now_fn=clock.now, sleep=clock.sleep)
    assert ledger.get("halted") is True and account.paused
    assert texts(ledger, "shadow_none") == ["本小时不下单：熔断中"] and texts(ledger, "shadow_order") == []
    assert ledger.fills() == []
