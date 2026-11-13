"""What pauses an account and what lifts the pause (ADR 0010, #34).

The demo and live accounts pause on what their sync cannot explain: a fill the program
did not make, a change of the balance that no trade, fee or funding explains, a
position the booked fills still do not explain at the next hourly sync. The live account
also pauses when what its orders follow changes (the code of ``trader/`` or the Signal)
and while its equity is over MAX_EQUITY, and refuses an order over MAX_ORDER notional.
Paused, an account sends nothing that changes a position, an order or a setting, its
drawdown alerts and kills nothing, and a person's halt still closes it out; ``resume``
lifts the pause once a sync finds nothing that pauses it."""

from dataclasses import replace

import pytest

from tests.test_demo_account import BTC, HOUR, HOUR_ID, T0, ExchangeFill
from tests.test_demo_job import RUN0, Clock, Env
from tests.test_live_pause import LiveEnv
from trader.demo import job
from trader.demo.account import DEMO, DemoAccount
from trader.intraday.paper import HOUR_MS
from trader.live.account import LIVE, MAX_EQUITY, MAX_ORDER
from trader.okx import DAY_MS
from trader.okx_private import TRADE_BILL, Bill
from trader.settings import KILL_DRAWDOWN

SIGNAL = {"model": "m-1", "prompt": "v1", "watchlist": ["BTC-USD"]}


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


@pytest.fixture
def trading(tmp_path, monkeypatch):
    """The live account unlocked, on code and a Signal of known fingerprints."""
    monkeypatch.setattr(job, "trader_digest", lambda: "code-1")
    live = LiveEnv(tmp_path)
    live.intraday.set("fingerprint", SIGNAL)
    live.account.unpause(T0, "解锁")
    return live


def run(env, hours, signal="Long"):
    """The run of the hour ``hours`` after HOUR, its signal decided as ``signal``."""
    env.decide(HOUR + hours * HOUR_MS, signal)
    return env.run(RUN0 + hours * HOUR_MS)


def resume(env, now_ms):
    env.exchange.now = now_ms
    return job.resume(env.settings, env.account, env.intraday, now_fn=Clock(now_ms).now)


def orders(env):
    return [call for call in env.exchange.calls if call[0] == "place_market"]


def pause_alerts(env):
    return [text for text in env.inbox.sent if text.split("】", 1)[1].startswith("暂停：")]


def events(env, kind):
    return [text for _, _, text in env.ledger.events(kinds=(kind,))]


def test_a_fill_the_program_did_not_make_pauses_the_account_until_a_resume(env):
    run(env, 0)  # Long: 10 contracts and their stop
    stops, calls = list(env.exchange.stops), len(env.exchange.calls)
    env.exchange.manual_fill(BTC.swap, 5)  # a person adds on the exchange
    run(env, 1, "Flat")
    text = "交易所里有不是程序下的成交：BTC-USDT-SWAP buy 5 张 @ 80,000.00"
    assert env.account.paused and pause_alerts(env) == [f"【demo】{DEMO.pause_alert(text)}"]
    assert env.exchange.calls[calls:] == [] and env.exchange.stops == stops
    assert env.exchange.book[BTC.swap][0] == 15 and env.ledger.positions()[BTC.swap].qty == pytest.approx(0.15)
    assert events(env, "shadow_order") == ["BTC-USDT-SWAP 卖出 15 张，平仓，名义 12,000 USDT，信号 Flat"]
    run(env, 2, "Flat")
    assert len(pause_alerts(env)) == 1 and env.exchange.calls[calls:] == []
    env.run(RUN0 + DAY_MS)
    assert f"  暂停原因（01-10 01:10 UTC 起）：{text}" in env.inbox.sent[-1].splitlines()
    reasons, _ = resume(env, RUN0 + DAY_MS + 60_000)
    assert [(r["key"], r["text"]) for r in reasons] == [("fill:" + reasons[0]["key"][5:], text)]
    assert not env.account.paused and env.account.pause_reasons == []
    run(env, 25, "Flat")
    assert orders(env)[-1][1:3] == (BTC.swap, -15)  # trading again


def test_a_position_closed_by_hand_is_not_opened_again_the_next_hour(env):
    run(env, 0)
    env.exchange.manual_fill(BTC.swap, -10)  # a person closes it on the exchange
    calls = len(env.exchange.calls)
    run(env, 1)  # the signal still Long
    assert env.account.paused and env.exchange.book[BTC.swap][0] == 0
    assert env.exchange.calls[calls:] == []


def test_money_moved_out_pauses_the_account_without_tripping_its_kill_switch(env):
    run(env, 0)
    peak = env.ledger.get("peak")
    env.exchange.transfer(-3_000.0)  # 30% of the equity: past the kill line
    run(env, 1)
    out = "余额有成交和资金费以外的变动：转出 -3,000.00 USDT"
    assert env.account.paused and pause_alerts(env) == [f"【demo】{DEMO.pause_alert(out)}"]
    assert env.ledger.get("halted") is False and "kill" not in env.events()
    assert env.exchange.book[BTC.swap][0] == 10 and env.ledger.get("peak") == peak
    assert not [text for text in env.inbox.sent if "熔断" in text]
    with pytest.raises(job.Refused, match=f"已到熔断线 {KILL_DRAWDOWN:.0%}.*#40"):
        resume(env, RUN0 + HOUR_MS + 60_000)
    assert env.account.paused
    env.exchange.transfer(3_000.0)
    with pytest.raises(job.Refused, match="对账发现了新的暂停原因"):
        resume(env, RUN0 + HOUR_MS + 120_000)
    reasons, _ = resume(env, RUN0 + HOUR_MS + 180_000)
    assert [r["text"] for r in reasons] == [out, "余额有成交和资金费以外的变动：转入 +3,000.00 USDT"]
    assert not env.account.paused


def test_a_paused_account_down_to_the_kill_line_alerts_and_a_halt_still_closes_it_out(env):
    run(env, 0)
    env.exchange.manual_fill(BTC.swap, 5)
    env.exchange.stops.clear()  # and cancels the stop
    run(env, 1)
    env.exchange.mark[BTC.swap] = env.exchange.prices[BTC.swap] = 66_000.0  # 15 contracts: -21%
    run(env, 2)
    assert env.account.paused and env.ledger.get("halted") is False and "kill" not in env.events()
    assert env.exchange.book[BTC.swap][0] == 15
    assert f"【demo】对账：回撤已到熔断线 {KILL_DRAWDOWN:.0%}：账户暂停中，程序不平仓，请人工处理" in env.inbox.sent
    env.exchange.now = RUN0 + 2 * HOUR_MS + 60_000
    job.halt(env.settings, env.account, env.inbox, now_fn=Clock(env.exchange.now).now, sleep=lambda s: None)
    assert env.ledger.get("halted") is True and env.exchange.book[BTC.swap][0] == 0
    assert [f.reason for f in env.ledger.fills()][-1] == "kill"


def test_a_position_the_next_hourly_sync_still_cannot_explain_pauses_and_holds_the_resume(env):
    run(env, 0)
    env.exchange.book[BTC.swap] = [30.0, 80_000.0]  # moved on the exchange, no fill reported
    run(env, 1)
    text = "账本与交易所持仓不一致：BTC-USDT-SWAP 账本推算 +0.1，交易所 +0.3，已按交易所为准"
    assert not env.account.paused and env.ledger.get("decided_hour") == HOUR  # a problem: the hour waits
    assert env.inbox.sent[-1] == f"【demo】对账：{text}"
    run(env, 2)
    assert env.account.paused and pause_alerts(env) == [f"【demo】{DEMO.pause_alert(text)}"]
    with pytest.raises(job.Refused, match="这些情况还在"):
        resume(env, RUN0 + 2 * HOUR_MS + 60_000)
    env.exchange.book[BTC.swap] = [10.0, 80_000.0]  # put back by hand
    reasons, _ = resume(env, RUN0 + 2 * HOUR_MS + 120_000)
    assert [r["key"] for r in reasons] == ["position:BTC-USDT-SWAP"] and not env.account.paused


def test_a_fill_the_exchange_reports_by_the_next_hourly_sync_pauses_nothing(env):
    run(env, 0)
    env.exchange.book[BTC.swap] = [30.0, 80_000.0]  # filled, and reported late (#26)
    env.exchange.other_bills.append(Bill("9009", TRADE_BILL, "1", BTC.swap, -0.64, RUN0 + HOUR_MS))  # its bill is in
    run(env, 1)
    env.exchange.fill_rows.append(ExchangeFill(
        "late", "tlate", "9009", f"trd{HOUR_ID + 1}btc", BTC.swap, "buy", 20.0, 80_000.0, -0.64, RUN0 + HOUR_MS
    ))
    run(env, 2)
    assert not env.account.paused and pause_alerts(env) == []
    assert env.ledger.get("decided_hour") == HOUR + 2 * HOUR_MS and len(orders(env)) == 2


def test_a_resume_whose_sync_finds_a_new_reason_leaves_the_pause_for_the_next_to_lift(env):
    run(env, 0)
    env.exchange.manual_fill(BTC.swap, 5)
    run(env, 1)
    env.exchange.manual_fill(BTC.swap, -5)  # undone by hand before the resume
    with pytest.raises(job.Refused, match="对账发现了新的暂停原因") as refused:
        resume(env, RUN0 + HOUR_MS + 60_000)
    assert "sell 5 张" in str(refused.value) and env.account.paused
    reasons, _ = resume(env, RUN0 + HOUR_MS + 120_000)
    assert len(reasons) == 2 and not env.account.paused


def test_a_change_of_the_live_code_pauses_the_account_until_a_resume_records_it(trading, monkeypatch):
    run(trading, 0)
    assert orders(trading) and trading.ledger.get("fingerprint") == {"code": "code-1", "signal": SIGNAL}
    monkeypatch.setattr(job, "trader_digest", lambda: "code-2")
    calls = len(trading.exchange.calls)
    run(trading, 1, "Short")
    text = "指纹变了：trader/ 的代码（code-1 → code-2）"
    assert trading.account.paused and pause_alerts(trading) == [f"【live】{LIVE.pause_alert(text)}"]
    assert trading.exchange.calls[calls:] == [] and events(trading, "shadow_order")
    run(trading, 2, "Short")
    assert len(pause_alerts(trading)) == 1
    reasons, _ = resume(trading, RUN0 + 2 * HOUR_MS + 60_000)
    assert [r["text"] for r in reasons] == [text]
    assert trading.ledger.get("fingerprint") == {"code": "code-2", "signal": SIGNAL}
    run(trading, 3, "Short")
    assert not trading.account.paused and orders(trading)[-1][2] < 0


def test_a_change_the_resume_finds_is_a_new_reason_it_records_for_the_next_to_lift(trading, monkeypatch):
    run(trading, 0)
    trading.intraday.set("fingerprint", {**SIGNAL, "model": "m-2"})
    run(trading, 1)
    monkeypatch.setattr(job, "trader_digest", lambda: "code-2")  # deployed before the resume
    with pytest.raises(job.Refused, match="指纹变了：trader/ 的代码（code-1 → code-2）"):
        resume(trading, RUN0 + HOUR_MS + 60_000)
    assert trading.account.paused and trading.ledger.get("fingerprint") == {"code": "code-2", "signal": {**SIGNAL, "model": "m-2"}}
    reasons, _ = resume(trading, RUN0 + HOUR_MS + 120_000)
    assert [r["text"] for r in reasons] == [
        "指纹变了：Signal 的指纹（model m-1 → m-2）", "指纹变了：trader/ 的代码（code-1 → code-2）",
    ]
    run(trading, 2)
    assert not trading.account.paused


def test_a_change_of_the_signal_pauses_the_live_account(trading):
    run(trading, 0)
    trading.intraday.set("fingerprint", {**SIGNAL, "model": "m-2"})
    run(trading, 1, "Short")
    text = "指纹变了：Signal 的指纹（model m-1 → m-2）"
    assert trading.account.paused and pause_alerts(trading) == [f"【live】{LIVE.pause_alert(text)}"]
    assert len(orders(trading)) == 1


def test_a_signal_changed_while_the_run_waits_for_the_hours_decision_makes_it_a_shadow_hour(trading):
    run(trading, 0)

    def intraday_decides(n):
        if n == 1:  # the intraday run records its Signal's fingerprint, then decides
            trading.intraday.set("fingerprint", {**SIGNAL, "model": "m-2"})
            trading.decide(HOUR + HOUR_MS, "Short")

    clock = Clock(RUN0 + HOUR_MS)
    clock.on_sleep = intraday_decides
    trading.exchange.now = clock.now_ms
    job.run(trading.settings, trading.account, trading.inbox, trading.intraday, now_fn=clock.now, sleep=clock.sleep)
    assert trading.account.paused and len(orders(trading)) == 1
    assert events(trading, "shadow_order") and trading.ledger.get("decided_hour") == HOUR + HOUR_MS


def test_the_demo_account_trades_on_through_a_change_of_its_code_or_signal(env, monkeypatch):
    monkeypatch.setattr(job, "trader_digest", lambda: "code-1")
    run(env, 0)
    monkeypatch.setattr(job, "trader_digest", lambda: "code-2")
    env.intraday.set("fingerprint", SIGNAL)
    run(env, 1, "Short")
    assert not env.account.paused and env.ledger.get("fingerprint") is None
    assert len(orders(env)) == 2


def test_live_equity_over_its_cap_pauses_the_account_and_holds_the_resume(trading):
    trading.exchange.cash = 2_500.0  # transferred in by mistake
    run(trading, 0)
    text = "净值 2,500.00 USDT 超过上限 2,000 USDT"
    assert trading.account.paused and pause_alerts(trading) == [f"【live】{LIVE.pause_alert(text)}"]
    assert orders(trading) == []
    with pytest.raises(job.Refused) as refused:
        resume(trading, RUN0 + 60_000)
    assert str(refused.value) == f"这些情况还在，解除了也会再暂停：\n  {text}"
    run(trading, 1)
    assert len(pause_alerts(trading)) == 1


def test_a_live_order_over_its_cap_is_refused_and_alerted(trading):
    capped = replace(LIVE, max_order=300.0)
    trading.account = DemoAccount(
        trading.ledger, trading.okx, trading.exchange, watchlist=(BTC,), sleep=lambda s: None, profile=capped
    )
    run(trading, 0)
    refused = "拒绝下单：BTC-USDT-SWAP 变动 +0.005 名义 400 USDT 超过单笔上限 300 USDT"
    assert trading.inbox.sent == [f"【live】{refused}"] and orders(trading) == []
    assert events(trading, "order_refused") == [refused]


def test_the_live_caps_are_adr_0010s_and_the_demo_has_none():
    assert (LIVE.max_equity, LIVE.max_order) == (MAX_EQUITY, MAX_ORDER) == (2_000.0, 4_000.0)
    assert (DEMO.max_equity, DEMO.max_order, DEMO.fingerprinted) == (None, None, False)
    assert LIVE.fingerprinted
