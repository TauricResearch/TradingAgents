"""A paused account (ADR 0010): it syncs, books what it finds and alerts its problems,
and sends the exchange nothing that would change a position, an order or a setting.
The live account is born paused. The fake exchange records only the calls that change
something, so an empty record is a run that only read."""

import pytest

from tests.test_demo_account import BTC, HOUR, T0, FakeExchange
from tests.test_demo_job import RUN0, Env
from trader.demo.account import DemoAccount, Paused, ReadOnly
from trader.intraday.paper import HOUR_MS
from trader.ledger import Ledger
from trader.live.account import LIVE
from trader.okx_private import StopOrder
from trader.settings import KILL_DRAWDOWN


class LiveEnv(Env):
    """``Env`` with the live account in the demo's place: born paused, on a production
    client, its ledger at the live path and never set up."""

    def __init__(self, tmp_path, watchlist=(BTC,)):
        super().__init__(tmp_path, watchlist)
        self.ledger = Ledger(self.settings.live_ledger_path)
        self.ledger.initialize(10_000.0, T0 - HOUR_MS)
        self.ledger.set("summarized_day", "2026-01-10")
        self.exchange = FakeExchange()
        self.exchange.simulated = False
        self.exchange.now = HOUR
        self.account = DemoAccount(
            self.ledger, self.okx, self.exchange, watchlist=watchlist, sleep=lambda s: None, profile=LIVE
        )


@pytest.fixture
def live(tmp_path):
    return LiveEnv(tmp_path)


def test_the_live_account_is_born_paused_and_each_change_is_recorded_with_its_reason(live):
    assert live.account.paused is True and live.ledger.get("paused") is None
    live.account.unpause(T0, "解除的原因")
    assert live.account.paused is False
    live.account.pause(T0 + 1, "暂停的原因")
    assert live.account.paused is True
    assert live.ledger.db.execute("SELECT ts, kind, text FROM events ORDER BY id").fetchall() == [
        (T0, "unpause", "解除的原因"), (T0 + 1, "pause", "暂停的原因"),
    ]


def test_a_paused_account_can_only_read(live):
    private = live.account.private
    assert isinstance(private, ReadOnly) and private.simulated is False
    assert private.balance().equity == 10_000.0 and private.positions() == [] and private.pending_stops() == []
    for name in ("set_position_mode", "set_leverage", "place_market", "close_position", "place_stop",
                 "amend_stop", "cancel_stops", "check_trade_permission", "probe_trade_permission"):
        with pytest.raises(Paused):
            getattr(private, name)
    with pytest.raises(Paused):
        live.account.setup()
    assert live.exchange.calls == [] and live.exchange.mode == "net_mode"
    live.account.unpause(T0, "x")
    assert live.account.private is live.exchange


def test_a_paused_run_syncs_and_changes_nothing_on_the_exchange(live):
    live.decide(HOUR, "Long")
    live.run(RUN0)
    assert live.exchange.calls == [] and live.exchange.book == {}
    assert live.inbox.sent == []
    assert live.ledger.get("synced_at") == RUN0 and live.ledger.get("equity") == 10_000.0
    assert live.ledger.get("setup_done") is None


def test_a_paused_account_alerts_its_reconciliation_problems_and_fixes_none(live):
    live.exchange.leverage = 5.0
    live.exchange.manual_fill(BTC.swap, 5)
    live.decide(HOUR, "Long")
    live.run(RUN0)
    assert live.exchange.calls == [] and live.exchange.book[BTC.swap][0] == 5
    assert live.inbox.sent == [
        "【live】对账：交易所里有不是程序下的成交：BTC-USDT-SWAP buy 5 张 @ 80,000.00",
        "【live】对账：BTC-USDT-SWAP 在交易所是 cross 5×，不是设计的 cross 3×",
        "【live】对账：BTC-USDT-SWAP 有仓位没有止损单：账户暂停中，程序不补挂，请人工处理",
    ]
    live.run(RUN0 + HOUR_MS)
    assert len(live.inbox.sent) == 3 and live.exchange.calls == []  # the same problems, not yet repeated


def test_a_paused_account_does_not_follow_a_halted_intraday_account(live):
    live.exchange.manual_fill(BTC.swap, 5)
    live.intraday.set("halted", True)
    live.run(RUN0)
    assert live.exchange.calls == [] and live.exchange.book[BTC.swap][0] == 5
    assert "follow_halt" not in live.events()


def test_a_paused_account_leaves_a_stop_that_does_not_fit_its_position(live):
    live.exchange.manual_fill(BTC.swap, 10)
    live.exchange.stops.append(StopOrder("a1", "", BTC.swap, "sell", 4.0, 70_000.0, True, HOUR))
    stops = list(live.exchange.stops)
    live.run(RUN0)
    assert live.exchange.calls == [] and live.exchange.stops == stops


def test_a_paused_account_at_the_kill_line_alerts_and_closes_nothing(live):
    live.exchange.manual_fill(BTC.swap, 10)
    live.exchange.stops.append(StopOrder("a1", "", BTC.swap, "sell", 10.0, 50_000.0, True, HOUR))
    live.run(RUN0)
    live.exchange.mark[BTC.swap] = live.exchange.prices[BTC.swap] = 59_000.0
    live.run(RUN0 + HOUR_MS)
    live.run(RUN0 + 2 * HOUR_MS)
    assert live.exchange.calls == [] and live.exchange.book[BTC.swap][0] == 10
    assert live.ledger.get("halted") is False and "kill" not in live.events()
    assert [text for text in live.inbox.sent if "熔断" in text] == [
        f"【live】对账：回撤已到熔断线 {KILL_DRAWDOWN:.0%}：账户暂停中，程序不平仓，请人工处理",
    ]


def test_a_demo_account_paused_in_its_ledger_sets_nothing_up_and_trades_nothing(tmp_path):
    env = Env(tmp_path)
    env.ledger.set("paused", True)
    env.ledger.set("setup_done", False)
    env.exchange.mode = "long_short_mode"
    env.decide(HOUR, "Long")
    env.run(RUN0)
    assert env.exchange.calls == [] and env.exchange.book == {} and env.exchange.mode == "long_short_mode"
    assert env.inbox.sent == [] and env.ledger.get("synced_at") == RUN0
