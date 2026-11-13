"""What the hourly job of an account on the exchange tells the chat besides its trades
(#36): a stop that fired on the exchange, each kind of failure, and what Telegram did
not take the first time."""

import pytest
import requests

from tests.test_demo_account import BTC, HOUR
from tests.test_demo_job import RUN0, Env
from tests.test_trader_jobs import Inbox
from trader.demo.account import DEMO
from trader.intraday.paper import HOUR_MS
from trader.okx import OKXError
from trader.okx_private import NoBalance, OKXPrivateError

UNAVAILABLE = OKXPrivateError("/api/v5/account/balance", "50001", "Service temporarily unavailable")
FAILED = "【demo】运行失败：OKXPrivateError: /api/v5/account/balance failed with code 50001: Service temporarily unavailable"
EXPOSED = "（账户可能有仓位：恢复之前每次失败都报）"


class Down(Inbox):
    """A chat Telegram does not reach while ``down``: what is sent then is refused."""

    def __init__(self):
        super().__init__()
        self.down = False

    def send(self, text):
        return not self.down and super().send(text)


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


def failing(env, error):
    """Every balance read raises ``error`` from now on."""
    def balance(ccy="USDT"):
        raise error
    env.exchange.balance = balance


def fail(env, now_ms, error=UNAVAILABLE):
    failing(env, error)
    with pytest.raises(type(error)):
        env.run(now_ms)


# -- a stop that fired on the exchange ---------------------------------------------


def test_the_run_whose_sync_finds_a_stop_filled_on_the_exchange_says_so_that_hour(env):
    env.decide(HOUR, "Long")
    env.run(RUN0)
    env.exchange.now = RUN0 + 20 * 60_000
    env.exchange.trigger_stop(BTC.swap, 78_950.0)
    env.run(RUN0 + HOUR_MS)  # the next hour undecided: the sync is all the run does
    # 10 contracts long from 80,000 lost 105, and the stop's fill paid 3.95 of fees.
    assert env.inbox.sent[1:] == [
        "【demo】止损成交：BTC-USDT-SWAP 卖出 10 张 @ 78,950.00，盈亏 -108.95 USDT（开仓均价 80,000.00，含手续费 3.95）"
    ]
    assert env.ledger.positions() == {} and [f.reason for f in env.ledger.fills()] == ["trade", "stop"]
    env.run(RUN0 + HOUR_MS + 60_000)  # booked once, told once
    assert len(env.inbox.sent) == 2


# -- failures, by kind ----------------------------------------------------------------


def test_each_kind_of_failure_is_alerted_at_once_and_then_at_most_every_six_hours(env):
    fail(env, RUN0)
    fail(env, RUN0 + HOUR_MS, requests.ConnectionError("connection reset"))
    fail(env, RUN0 + 2 * HOUR_MS)  # the first kind again, an hour after its alert
    limited = OKXPrivateError("/api/v5/account/balance", "50011", "Too Many Requests")
    fail(env, RUN0 + 3 * HOUR_MS, limited)  # OKX's other code: another kind
    fail(env, RUN0 + 6 * HOUR_MS - 1)
    fail(env, RUN0 + 6 * HOUR_MS)
    assert env.inbox.sent == [
        FAILED,
        "【demo】运行失败：ConnectionError: connection reset",
        "【demo】运行失败：OKXPrivateError: /api/v5/account/balance failed with code 50011: Too Many Requests",
        FAILED,
    ]
    assert env.ledger.get(DEMO.failures_key) == {
        "OKXPrivateError 50001": RUN0 + 6 * HOUR_MS,
        "ConnectionError": RUN0 + HOUR_MS,
        "OKXPrivateError 50011": RUN0 + 3 * HOUR_MS,
    }
    fail(env, RUN0 + 9 * HOUR_MS, NoBalance("the account's balance has no USDT row"))
    # The kinds last alerted six hours or more ago are let go.
    assert env.ledger.get(DEMO.failures_key) == {
        "OKXPrivateError 50001": RUN0 + 6 * HOUR_MS, "NoBalance": RUN0 + 9 * HOUR_MS,
    }


def test_an_error_without_a_code_is_of_its_type_and_an_http_error_of_its_status(env):
    fail(env, RUN0, OKXError("candles failed with code 50001: service unavailable"))
    for status in (502, 503, 502):
        response = requests.Response()
        response.status_code = status
        fail(env, RUN0 + HOUR_MS, requests.HTTPError(f"{status} Server Error", response=response))
    assert [t.split("：")[1] for t in env.inbox.sent] == [
        "OKXError: candles failed with code 50001: service unavailable",
        "HTTPError: 502 Server Error",
        "HTTPError: 503 Server Error",
    ]


def test_while_the_account_holds_a_position_every_failure_is_alerted(env):
    env.decide(HOUR, "Long")
    env.run(RUN0)
    fail(env, RUN0 + HOUR_MS)
    fail(env, RUN0 + 2 * HOUR_MS)
    assert env.inbox.sent[1:] == [FAILED, FAILED + EXPOSED]


def test_an_order_left_unconfirmed_has_each_failure_alerted_until_a_sync_reads_the_exchange(env):
    env.decide(HOUR, "Long")
    env.exchange.fill_state = "live"  # taken, and not seen to fill
    env.run(RUN0)
    assert env.ledger.positions() == {} and "order_pending" in env.events()
    fail(env, RUN0 + HOUR_MS)
    fail(env, RUN0 + 2 * HOUR_MS)
    assert env.inbox.sent[1:] == [FAILED, FAILED + EXPOSED]
    del env.exchange.balance
    env.run(RUN0 + 3 * HOUR_MS)  # its sync finds no position: the order did not fill
    fail(env, RUN0 + 4 * HOUR_MS)
    assert env.inbox.sent[1:] == [FAILED, FAILED + EXPOSED]


# -- what Telegram did not take -------------------------------------------------------


def test_an_alert_telegram_did_not_take_goes_out_first_on_the_next_run_and_not_twice(env):
    env.inbox = Down()
    env.inbox.down = True
    fail(env, RUN0)
    fail(env, RUN0 + HOUR_MS)  # the same kind: its alert is still waiting
    fail(env, RUN0 + 2 * HOUR_MS, requests.ConnectionError("connection reset"))
    assert env.inbox.sent == []
    assert [m["kind"] for m in env.ledger.get(DEMO.unsent_key)["messages"]] == [
        "OKXPrivateError 50001", "ConnectionError",
    ]
    assert env.ledger.get(DEMO.failures_key) is None  # no alert went out: no interval started

    env.inbox.down = False
    fail(env, RUN0 + 3 * HOUR_MS)  # resent first, which starts its interval: nothing new
    assert env.inbox.sent == [
        FAILED + "\n（补发：01-10 00:10 UTC 没发出去）",
        "【demo】运行失败：ConnectionError: connection reset\n（补发：01-10 02:10 UTC 没发出去）",
    ]
    assert env.ledger.get(DEMO.unsent_key) == {"messages": [], "dropped": 0}
    assert env.ledger.get(DEMO.failures_key) == {
        "OKXPrivateError 50001": RUN0 + 3 * HOUR_MS, "ConnectionError": RUN0 + 3 * HOUR_MS,
    }


def test_what_a_run_could_not_send_goes_out_ahead_of_the_next_runs_own(env):
    env.inbox = Down()
    env.inbox.down = True
    env.decide(HOUR, "Long")
    env.run(RUN0)  # its hourly report is refused
    env.inbox.down = False
    env.exchange.now = RUN0 + 20 * 60_000
    env.exchange.trigger_stop(BTC.swap, 78_950.0)
    env.run(RUN0 + HOUR_MS)
    report, stop = env.inbox.sent
    assert report.startswith("【demo】01-10 00:00 UTC\nBTC：Long → ")
    assert report.endswith("\n（补发：01-10 00:10 UTC 没发出去）")
    assert stop.startswith("【demo】止损成交：")
    assert env.ledger.get(DEMO.failures_key) is None  # the report was no failure's alert
