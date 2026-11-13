"""The shadow run (ADR 0010): each hour a paused account records the orders the hour's
signals size against the exchange's equity and positions, as it would send them, or
why there are none, and sends nothing; its daily summary says it is paused and counts
the orders of the day before."""

import pytest

from tests.test_demo_account import BTC, ETH, HOUR
from tests.test_demo_job import RUN0
from tests.test_live_pause import LiveEnv
from trader.demo import account as account_module
from trader.ledger import Ledger
from trader.okx import DAY_MS

KINDS = ("shadow_order", "shadow_none", "order_refused", "skipped")


@pytest.fixture
def live(tmp_path):
    return LiveEnv(tmp_path)


def shadow(env):
    return [(kind, text) for _, kind, text in env.ledger.events(kinds=KINDS)]


def test_a_paused_hour_records_the_orders_it_would_send_and_sends_none(live):
    live.decide(HOUR, "Long")
    live.run(RUN0)
    assert live.exchange.calls == [] and live.inbox.sent == []
    assert shadow(live) == [("shadow_order", "BTC-USDT-SWAP 买入 0.5 张，名义 400 USDT，信号 Long")]
    assert live.ledger.get("decided_hour") == HOUR
    live.run(RUN0 + 60_000)  # the same hour again records nothing new
    assert len(shadow(live)) == 1 and live.exchange.calls == []


def test_the_shadow_orders_are_those_the_account_sends_once_unpaused(tmp_path):
    paused = LiveEnv(tmp_path / "paused", watchlist=(BTC, ETH))
    trading = LiveEnv(tmp_path / "trading", watchlist=(BTC, ETH))
    trading.account.unpause(HOUR, "对照")
    for env in (paused, trading):
        env.decide(HOUR, "Long")
        env.decide(HOUR, "Short", coin=ETH)
        env.run(RUN0)
    sent = [(call[1], call[2]) for call in trading.exchange.calls if call[0] == "place_market"]
    assert len(sent) == 2 and paused.exchange.calls == []
    assert [text.split("，")[0] for kind, text in shadow(paused)] == [
        f"{inst} {'买入' if contracts > 0 else '卖出'} {abs(contracts):g} 张" for inst, contracts in sent
    ]


def test_an_hour_without_an_order_to_send_says_why(live):
    live.decide(HOUR, "Flat")
    live.run(RUN0)
    assert shadow(live) == [("shadow_none", "本小时不下单：离目标仓位不远，或不到最小下单量")]
    assert live.ledger.get("decided_hour") == HOUR


def test_an_hour_the_sync_finds_problems_in_sizes_nothing_and_says_why(live):
    live.exchange.leverage = 5.0
    live.exchange.manual_fill(BTC.swap, 0.5)  # not the program's, which pauses, and without a stop
    live.decide(HOUR, "Long")
    live.run(RUN0)
    assert shadow(live) == [("shadow_none", "本小时不下单：对账有 2 个问题")]
    live.run(RUN0 + 60_000)
    assert len(shadow(live)) == 1 and live.exchange.calls == []


def test_a_halted_paused_account_sizes_nothing(live):
    live.ledger.set("halted", True)
    live.decide(HOUR, "Long")
    live.run(RUN0)
    assert shadow(live) == [("shadow_none", "本小时不下单：熔断中")]


def test_a_refused_order_is_alerted_and_recorded_as_when_trading(live, monkeypatch):
    monkeypatch.setattr(account_module, "MAX_GROSS_EXPOSURE", 0.5)
    live.decide(HOUR, "Long")
    live.run(RUN0)
    refused = "拒绝下单：BTC-USDT-SWAP 变动 +0.005 名义 400 USDT 超过净值 500 的 0.5 倍，可能是算错了"
    assert live.inbox.sent == [f"【live】{refused}"]
    assert shadow(live) == [("order_refused", refused), ("shadow_none", "本小时不下单：要下的单都被拒绝")]
    assert live.exchange.calls == []


def test_an_hour_the_intraday_account_never_decided_is_skipped_as_when_trading(live):
    live.run(RUN0)
    assert shadow(live) == [("skipped", "日内账户到 00:25 还没决定 00:00 这个小时，live 本小时不交易")]
    assert live.ledger.get("decided_hour") is None


def test_the_daily_summary_of_a_paused_account_counts_the_orders_it_would_have_sent(live):
    live.decide(HOUR, "Long")
    live.run(RUN0)
    live.decide(HOUR + DAY_MS, "Long")
    live.run(RUN0 + DAY_MS)
    (daily,) = live.inbox.sent
    assert daily.splitlines()[:4] == [
        "【live】日报 · 2026-01-10",
        "⏸ 暂停中（影子运行）：不下单，昨日本该下 1 笔，明细见 python -m trader live report",
        "  暂停原因：账本里没有记下",  # born paused, as a ledger paused before #34
        "  查明原因后运行 python -m trader live resume 解除",
    ]
    assert len(shadow(live)) == 2 and live.exchange.calls == []


def test_the_events_are_read_back_by_time_and_kind(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    for ts, kind, text in [(1, "a", "x"), (2, "b", "y"), (3, "a", "z")]:
        ledger.add_event(ts, kind, text)
    assert ledger.events() == [(1, "a", "x"), (2, "b", "y"), (3, "a", "z")]
    assert ledger.events(2) == [(2, "b", "y"), (3, "a", "z")]
    assert ledger.events(kinds=("a",)) == [(1, "a", "x"), (3, "a", "z")]
    assert ledger.events(2, ("a", "b")) == [(2, "b", "y"), (3, "a", "z")]
