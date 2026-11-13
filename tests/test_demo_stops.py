"""The demo account's stops when the exchange does not cooperate (#32, ADR 0010).

What must hold when a run ends, however it ends: every position has a stop for its
whole size on the closing side, or it has been closed, or an alert names its contract.
And at no moment in between has a position lost the stop it had.

None of this has met the real exchange yet (#42), so each thing not known of it is
tested both ways on the fake one: the amendment works or is refused, a second stop may
pend beside the first or may not, a repeated algo client id is refused or accepted, a
trigger the price has passed is refused (under the documented code or another) or is not.

The numbers are tests/test_demo_account.py's: 10,000 USDT, BTC at 80,000, an hourly ATR
of 400, so a unit is 10 contracts and the stop is 1,000 away.
"""

import random

import pytest
import requests

from tests.test_demo_account import BTC, ETH, HOUR, FakeExchange, go_long, quotes
from tests.test_trader_paper import T0, FakeOKX
from trader.demo.account import DemoAccount
from trader.demo.settings import STOP_RETRY_SECONDS, STOP_TRIES
from trader.intraday.paper import HOUR_MS
from trader.ledger import Ledger
from trader.okx_private import OKXPrivateError

UNAVAILABLE = OKXPrivateError("/api/v5/trade/order-algo", "50001", "Service temporarily unavailable")
UNAVAILABLE_TEXT = "/api/v5/trade/order-algo failed with code 50001: Service temporarily unavailable"
NOT_AMENDABLE = OKXPrivateError(
    "/api/v5/trade/amend-algos", "51529",
    "Order modification unsuccessful. Stop order modification only applies to Expiry Futures and Perpetual Futures.",
)
NOT_CLOSED = OKXPrivateError("/api/v5/trade/close-position", "50001", "Service temporarily unavailable")
NOT_CANCELLED = OKXPrivateError("/api/v5/trade/cancel-algos", "50001", "Service temporarily unavailable")
LOST = requests.ConnectionError("connection reset")
STOP_CALLS = ("place_stop", "amend_stop", "cancel_stops", "close_position")


@pytest.fixture
def exchange():
    exchange = FakeExchange()
    yield exchange
    # Whatever a test put the account through, none of its cancellations may have
    # left a held contract without a stop on its closing side.
    assert exchange.gaps == []


@pytest.fixture
def ledger(tmp_path):
    ledger = Ledger(tmp_path / "demo.sqlite")
    ledger.initialize(10_000.0, T0)
    return ledger


@pytest.fixture
def account(ledger, exchange):
    sleeps = []
    acc = DemoAccount(ledger, FakeOKX(), exchange, watchlist=(BTC, ETH), sleep=sleeps.append)
    acc.sleeps = sleeps
    return acc


def traded(account, exchange, signals, hour=HOUR):
    """An hour's orders filled and booked, their stops not yet seen to: the time, the
    quotes and the pending stops ``manage_stops`` is then called with."""
    now = exchange.now
    result = account.sync(now)
    q = quotes(account)
    _, desired = account.execute(hour, signals, now, result.equity, q)
    return now, q, account.sync(now, desired_stops=desired).stops


def hourly(account, exchange, n=1, last=80_000.0):
    """The stops' part of the n-th hourly run after the first: a sync, then
    ``manage_stops`` on quotes whose last price is ``last``."""
    now = exchange.now = T0 + n * HOUR_MS
    result = account.sync(now)
    return account.manage_stops(now, quotes(account, last), result.stops)


def calls(exchange):
    """What was done to stops and positions, in order."""
    return [c[0] for c in exchange.calls if c[0] in STOP_CALLS]


def kinds(ledger):
    return [kind for (kind,) in ledger.db.execute("SELECT kind FROM events ORDER BY id")]


# -- changing a stop without a gap ----------------------------------------------------


def test_a_bigger_position_has_its_stop_amended_to_the_new_size_where_it_stands(account, ledger, exchange):
    go_long(account, exchange)
    (old,) = exchange.stops
    exchange.cash += 10_004.0  # the wallet doubled: the same signal now asks for twice the size
    exchange.now = T0 + HOUR_MS
    now, q, stops = traded(account, exchange, {BTC.research: "Long"}, HOUR + HOUR_MS)
    assert account.manage_stops(now, q, stops) == ([], [])
    (stop,) = exchange.stops
    assert (stop.algo_id, stop.contracts, stop.trigger) == (old.algo_id, 20.0, 79_000.0)
    assert calls(exchange) == ["place_stop", "amend_stop"] and exchange.gaps == []
    assert ledger.db.execute("SELECT text FROM events WHERE kind = 'stop' ORDER BY id DESC").fetchone() == (
        f"BTC-USDT-SWAP 止损改到 79,000.00（20 张，{old.client_id}）",
    )


def test_when_the_amendment_is_refused_the_new_stop_is_pending_before_the_old_one_goes(account, exchange):
    go_long(account, exchange)
    (old,) = exchange.stops
    exchange.fail("amend_stop", NOT_AMENDABLE)  # every time: the endpoint does not take our stops
    assert hourly(account, exchange, last=82_000.0) == ([], [])
    (stop,) = exchange.stops
    assert (stop.contracts, stop.trigger) == (10.0, 81_000.0) and stop.algo_id != old.algo_id
    assert calls(exchange) == ["place_stop", "amend_stop", "place_stop", "cancel_stops"]
    assert exchange.calls[-1] == ("cancel_stops", [old.algo_id])
    assert exchange.gaps == [] and exchange.bare() == []


def test_when_neither_an_amendment_nor_a_second_stop_is_possible_the_old_stop_stays(account, ledger, exchange):
    go_long(account, exchange)
    (old,) = exchange.stops
    exchange.fail("amend_stop", NOT_AMENDABLE)
    exchange.one_stop = True
    alerts, closed = hourly(account, exchange, last=82_000.0)
    assert alerts == [
        "止损没更新：BTC-USDT-SWAP +10 张的止损没能改到 81,000.00（/api/v5/trade/order-algo failed with"
        " code 51168: Failed. You have reduce-only type of open order(s)），"
        "交易所里仍是 79,000.00 的旧止损单，下一次运行再试"
    ]
    assert closed == [] and exchange.stops == [old] and exchange.bare() == []
    # Covered by the stop it had: one try, no close, and the ledger keeps the new stop
    # for the next run to hang.
    assert calls(exchange) == ["place_stop", "amend_stop", "place_stop"] and account.sleeps == []
    assert ledger.positions()[BTC.swap].stop == 81_000.0 and kinds(ledger)[-1] == "stop_failed"
    exchange.failures.clear()
    assert hourly(account, exchange, n=2, last=82_000.0) == ([], [])
    assert [(s.algo_id, s.trigger) for s in exchange.stops] == [(old.algo_id, 81_000.0)]


def test_an_amendment_that_is_accepted_but_changes_nothing_is_not_taken_for_done(account, exchange):
    go_long(account, exchange)
    (old,) = exchange.stops
    exchange.amend_ignored = True
    assert hourly(account, exchange, last=82_000.0) == ([], [])
    (stop,) = exchange.stops
    assert stop.trigger == 81_000.0 and stop.algo_id != old.algo_id
    assert calls(exchange)[1:] == ["amend_stop", "place_stop", "cancel_stops"] and exchange.gaps == []


def test_an_amendment_that_went_through_but_reported_an_error_is_found_by_reading_back(account, exchange):
    go_long(account, exchange)
    (old,) = exchange.stops
    exchange.fail("amend_stop", LOST, times=1, applied=True)
    assert hourly(account, exchange, last=82_000.0) == ([], [])
    assert [(s.algo_id, s.trigger) for s in exchange.stops] == [(old.algo_id, 81_000.0)]
    assert calls(exchange) == ["place_stop", "amend_stop"]  # nothing placed beside it, nothing cancelled


def test_an_amendment_that_cannot_be_read_back_is_alerted_and_left_at_that(account, exchange):
    go_long(account, exchange)
    (old,) = exchange.stops
    result = account.sync(T0 + HOUR_MS)
    q = quotes(account, last=82_000.0)
    exchange.fail("pending_stops", LOST)
    alerts, closed = account.manage_stops(T0 + HOUR_MS, q, result.stops)
    assert alerts == [
        f"止损待确认：BTC-USDT-SWAP +10 张的止损 81,000.00 已改单（{old.client_id}），"
        "但读不回交易所的挂单来确认，别的止损单都没有动，下一次运行再核对"
    ]
    assert closed == [] and [s.trigger for s in exchange.stops] == [81_000.0]
    assert calls(exchange) == ["place_stop", "amend_stop"]


def test_a_new_stop_that_cannot_be_read_back_does_not_cost_the_old_one(account, exchange):
    go_long(account, exchange)
    result = account.sync(T0 + HOUR_MS)
    q = quotes(account, last=82_000.0)
    exchange.fail("amend_stop", NOT_AMENDABLE)
    exchange.fail("pending_stops", LOST)
    alerts, closed = account.manage_stops(T0 + HOUR_MS, q, result.stops)
    new = exchange.stops[-1]
    assert alerts == [
        f"止损待确认：BTC-USDT-SWAP +10 张的止损 81,000.00 已下单（{new.client_id}），"
        "但读不回交易所的挂单来确认，别的止损单都没有动，下一次运行再核对"
    ]
    assert closed == [] and [s.trigger for s in exchange.stops] == [79_000.0, 81_000.0]
    assert "cancel_stops" not in calls(exchange)
    # The next run reads both, keeps the one in place and cancels the other.
    exchange.failures.clear()
    assert hourly(account, exchange, n=2, last=82_000.0) == ([], [])
    assert exchange.stops == [new] and exchange.gaps == []


def test_a_new_stop_that_is_accepted_but_does_not_show_as_pending_costs_the_old_one_nothing(account, exchange):
    # The placement is answered with success, and the pending stops, read back, hold
    # only the old one. The answer alone cancels nothing: the old stop covers the
    # position, so it stays as it is and the position with it.
    go_long(account, exchange)
    (old,) = exchange.stops
    exchange.fail("amend_stop", NOT_AMENDABLE)
    exchange.place_ignored = True
    alerts, closed = hourly(account, exchange, last=82_000.0)
    assert alerts == [
        "止损没更新：BTC-USDT-SWAP +10 张的止损没能改到 81,000.00（下单的应答是成功，挂单里却没有），"
        "交易所里仍是 79,000.00 的旧止损单，下一次运行再试"
    ]
    assert closed == [] and exchange.stops == [old] and exchange.book[BTC.swap][0] == 10.0
    # One placement, and nothing after it: no cancellation, no close, no second try.
    assert calls(exchange) == ["place_stop", "amend_stop", "place_stop"] and account.sleeps == []
    assert exchange.bare() == []


def test_a_new_stop_that_never_shows_as_pending_leaves_the_old_one_standing_until_the_close(account, exchange):
    # The position doubled and its stop, for half of it, cannot be amended. Each new
    # stop is answered with success and never shows among the pending ones: after
    # STOP_TRIES of them the position is closed, the old stop still pending as the
    # close goes out. No answer alone cancelled it.
    go_long(account, exchange)
    (old,) = exchange.stops
    exchange.cash += 10_004.0
    exchange.now = T0 + HOUR_MS
    now, q, stops = traded(account, exchange, {BTC.research: "Long"}, HOUR + HOUR_MS)
    exchange.fail("amend_stop", NOT_AMENDABLE)
    exchange.place_ignored = True
    alerts, closed = account.manage_stops(now, q, stops)
    assert closed == [BTC.swap] and len(alerts) == 1
    assert alerts[0].startswith(
        "止损平仓：BTC-USDT-SWAP +20 张试了 3 次都没挂上止损（下单的应答是成功，挂单里却没有），已市价平仓"
    )
    assert calls(exchange) == ["place_stop", "amend_stop"] + ["place_stop"] * STOP_TRIES + ["close_position"]
    assert exchange.at_close == [(BTC.swap, [old])] and exchange.book[BTC.swap][0] == 0


def test_an_old_stop_that_will_not_cancel_stays_beside_the_new_one_until_the_next_run(account, exchange):
    go_long(account, exchange)
    exchange.fail("amend_stop", NOT_AMENDABLE)
    exchange.fail("cancel_stops", NOT_CANCELLED)
    alerts, closed = hourly(account, exchange, last=82_000.0)
    assert alerts == [
        "止损单没撤掉：BTC-USDT-SWAP 止损已到位，1 张多余的止损单没撤掉（/api/v5/trade/cancel-algos failed"
        " with code 50001: Service temporarily unavailable），下一次运行再撤"
    ]
    assert closed == [] and [s.trigger for s in exchange.stops] == [79_000.0, 81_000.0]
    # The next run finds the stop in place: nothing new is placed, the leftover goes.
    exchange.failures.clear()
    placed = calls(exchange).count("place_stop")
    assert hourly(account, exchange, n=2, last=82_000.0) == ([], [])
    assert [s.trigger for s in exchange.stops] == [81_000.0]
    assert calls(exchange).count("place_stop") == placed and exchange.gaps == []


def test_a_cancellation_that_went_through_but_reported_an_error_is_no_alert(account, exchange):
    go_long(account, exchange)
    exchange.fail("amend_stop", NOT_AMENDABLE)
    exchange.fail("cancel_stops", LOST, times=1, applied=True)
    assert hourly(account, exchange, last=82_000.0) == ([], [])
    assert [s.trigger for s in exchange.stops] == [81_000.0]


def test_after_a_flip_the_new_sides_stop_is_pending_before_the_old_sides_goes(account, exchange):
    go_long(account, exchange)
    (old,) = exchange.stops
    exchange.now = T0 + HOUR_MS
    now, q, stops = traded(account, exchange, {BTC.research: "Short"}, HOUR + HOUR_MS)
    assert account.manage_stops(now, q, stops) == ([], [])
    (stop,) = exchange.stops
    assert (stop.side, stop.contracts, stop.trigger) == ("buy", 9.99, 81_000.0)
    # A stop on the other side is not amended into this one: placed, then the old one cancelled.
    assert calls(exchange) == ["place_stop", "place_stop", "cancel_stops"]
    assert exchange.calls[-1] == ("cancel_stops", [old.algo_id])


def test_a_stop_that_is_not_ours_is_replaced_rather_than_amended(account, exchange):
    now, q, _ = traded(account, exchange, {BTC.research: "Long"})
    exchange.place_stop(BTC.swap, 10, 78_000.0, "byhand")  # its fill would not read as a stop of ours
    assert account.manage_stops(now, q, exchange.pending_stops()) == ([], [])
    (stop,) = exchange.stops
    assert stop.trigger == 79_000.0 and stop.client_id.startswith("stp")
    assert calls(exchange) == ["place_stop", "place_stop", "cancel_stops"] and exchange.gaps == []


def test_an_orphan_stop_that_will_not_cancel_is_alerted_and_the_positions_still_get_theirs(account, exchange):
    now, q, _ = traded(account, exchange, {BTC.research: "Long"})
    exchange.place_stop(ETH.swap, -5, 81_000.0, "stpold")  # a stop with no position behind it
    exchange.fail("cancel_stops", NOT_CANCELLED)
    alerts, closed = account.manage_stops(now, q, exchange.pending_stops())
    assert alerts == [
        "止损单没撤掉：ETH-USDT-SWAP 已无持仓，1 张多余的止损单没撤掉（/api/v5/trade/cancel-algos failed"
        " with code 50001: Service temporarily unavailable），下一次运行再撤"
    ]
    assert closed == []
    assert sorted((s.inst, s.trigger) for s in exchange.stops) == [(BTC.swap, 79_000.0), (ETH.swap, 81_000.0)]


def test_a_contract_whose_stop_fails_does_not_keep_the_next_from_its_stop_or_the_ledger_from_its_commit(
    account, ledger, exchange
):
    now, q, stops = traded(account, exchange, {BTC.research: "Long", ETH.research: "Short"})
    exchange.fail("place_stop", UNAVAILABLE, inst=BTC.swap)
    exchange.fail("close_position", NOT_CLOSED, inst=BTC.swap)
    alerts, closed = account.manage_stops(now, q, stops)
    assert len(alerts) == 1 and alerts[0].startswith("紧急：BTC-USDT-SWAP +10 张试了 3 次都没挂上止损")
    assert closed == []
    assert [(s.inst, s.side, s.contracts, s.trigger) for s in exchange.stops] == [(ETH.swap, "buy", 10.0, 81_000.0)]
    assert {inst: pos.stop for inst, pos in ledger.positions().items()} == {BTC.swap: 79_000.0, ETH.swap: 81_000.0}
    assert ledger.get("marks") == {BTC.swap: 80_000.0, ETH.swap: 80_000.0}


def test_while_halted_only_the_ledger_is_updated(account, ledger, exchange):
    go_long(account, exchange)
    exchange.stops = []
    ledger.set("halted", True)
    assert hourly(account, exchange, last=82_000.0) == ([], [])
    assert exchange.stops == [] and calls(exchange) == ["place_stop"]
    assert ledger.positions()[BTC.swap].stop == 81_000.0


# -- a position without a stop that will not hang ---------------------------------------


def test_a_stop_that_will_not_hang_is_tried_three_times_and_then_the_position_is_closed_at_market(
    account, ledger, exchange
):
    now, q, stops = traded(account, exchange, {BTC.research: "Long"})
    exchange.fail("place_stop", UNAVAILABLE)
    alerts, closed = account.manage_stops(now, q, stops)
    assert closed == [BTC.swap]
    assert calls(exchange) == ["place_stop"] * STOP_TRIES + ["close_position"]
    assert account.sleeps == [STOP_RETRY_SECONDS] * (STOP_TRIES - 1)
    _, inst, client_id = exchange.calls[-1]
    assert inst == BTC.swap and client_id.startswith("stp")
    assert alerts == [
        f"止损平仓：BTC-USDT-SWAP +10 张试了 3 次都没挂上止损（{UNAVAILABLE_TEXT}），已市价平仓（{client_id}）"
    ]
    assert exchange.book[BTC.swap][0] == 0 and kinds(ledger)[-1] == "stop_closed"
    # The sync that follows books the close as a stop: flat, and nothing to explain.
    result = account.sync(now + 5_000)
    assert result.problems == [] and ledger.positions() == {}
    assert [f.reason for f in ledger.fills()] == ["trade", "stop"]


def test_a_stop_that_hangs_on_the_second_try_keeps_the_position(account, exchange):
    now, q, stops = traded(account, exchange, {BTC.research: "Long"})
    exchange.fail("place_stop", UNAVAILABLE, times=1)
    assert account.manage_stops(now, q, stops) == ([], [])
    assert [(s.contracts, s.trigger) for s in exchange.stops] == [(10.0, 79_000.0)]
    assert calls(exchange) == ["place_stop", "place_stop"] and account.sleeps == [STOP_RETRY_SECONDS]


def test_a_new_stop_that_was_placed_but_reported_an_error_is_not_placed_twice(account, exchange):
    now, q, stops = traded(account, exchange, {BTC.research: "Long"})
    exchange.fail("place_stop", LOST, times=1, applied=True)
    assert account.manage_stops(now, q, stops) == ([], [])
    assert [(s.contracts, s.trigger) for s in exchange.stops] == [(10.0, 79_000.0)]
    assert calls(exchange) == ["place_stop"] and account.sleeps == []


@pytest.mark.parametrize("duplicate_code", ["51065", "51016", None])
def test_a_retry_carries_the_same_client_id_and_ends_with_one_stop_whether_or_not_the_exchange_refuses_it(
    account, exchange, duplicate_code
):
    # The stop went through, its answer was lost, and the pending stops could not be
    # read either: all there is to do is try again. OKX's table has 51065 for a repeated
    # algo client id and 51016 for an order's; the exchange may also take the repeat.
    exchange.duplicate_code = duplicate_code
    now, q, stops = traded(account, exchange, {BTC.research: "Long"})
    exchange.fail("place_stop", LOST, times=1, applied=True)
    exchange.fail("pending_stops", LOST, times=1)
    assert account.manage_stops(now, q, stops) == ([], [])
    first, second = [c for c in exchange.calls if c[0] == "place_stop"]
    assert first == second
    assert [(s.contracts, s.trigger) for s in exchange.stops] == [(10.0, 79_000.0)]
    assert exchange.gaps == []


def test_placements_that_fail_while_the_pending_stops_cannot_be_read_end_in_a_close(account, exchange):
    now, q, stops = traded(account, exchange, {BTC.research: "Long"})
    exchange.fail("place_stop", UNAVAILABLE)
    exchange.fail("pending_stops", LOST)
    alerts, closed = account.manage_stops(now, q, stops)
    assert closed == [BTC.swap] and alerts[0].startswith("止损平仓：BTC-USDT-SWAP +10 张试了 3 次都没挂上止损")
    assert calls(exchange) == ["place_stop"] * STOP_TRIES + ["close_position"]


def test_a_stop_for_part_of_the_position_does_not_count_as_its_stop(account, exchange):
    # The position doubled and the exchange takes neither an amendment nor a second
    # stop: the old stop covers half of it, which is not a stop for the position.
    go_long(account, exchange)
    (old,) = exchange.stops
    exchange.cash += 10_004.0
    exchange.now = T0 + HOUR_MS
    now, q, stops = traded(account, exchange, {BTC.research: "Long"}, HOUR + HOUR_MS)
    exchange.fail("amend_stop", NOT_AMENDABLE)
    exchange.one_stop = True
    assert exchange.bare() == [BTC.swap]
    alerts, closed = account.manage_stops(now, q, stops)
    assert closed == [BTC.swap] and alerts[0].startswith("止损平仓：BTC-USDT-SWAP +20 张试了 3 次都没挂上止损")
    assert exchange.bare() == []
    assert calls(exchange) == ["place_stop", "amend_stop"] + ["place_stop"] * STOP_TRIES + ["close_position"]
    # The old stop stood until the position itself was closed, and nothing cancelled it.
    assert exchange.at_close == [(BTC.swap, [old])]
    assert old.algo_id not in [algo_id for c in exchange.calls if c[0] == "cancel_stops" for algo_id in c[1]]


def test_when_the_close_fails_as_well_the_alert_names_the_contract_and_the_next_run_takes_it_up(
    account, ledger, exchange
):
    now, q, stops = traded(account, exchange, {BTC.research: "Long"})
    exchange.fail("place_stop", UNAVAILABLE)
    exchange.fail("close_position", NOT_CLOSED)
    alerts, closed = account.manage_stops(now, q, stops)
    assert alerts == [
        f"紧急：BTC-USDT-SWAP +10 张试了 3 次都没挂上止损（{UNAVAILABLE_TEXT}），市价平仓也失败"
        "（/api/v5/trade/close-position failed with code 50001: Service temporarily unavailable），"
        "请立即人工处理；下一次运行会再试"
    ]
    assert closed == []
    assert calls(exchange) == ["place_stop"] * STOP_TRIES + ["close_position"] * STOP_TRIES
    assert exchange.book[BTC.swap][0] == 10.0 and exchange.bare() == [BTC.swap]
    assert ledger.positions()[BTC.swap].stop == 79_000.0 and kinds(ledger)[-1] == "stop_failed"
    exchange.failures.clear()
    assert hourly(account, exchange) == ([], [])
    assert [(s.contracts, s.trigger) for s in exchange.stops] == [(10.0, 79_000.0)] and exchange.bare() == []


def test_a_close_that_fails_once_is_tried_again_under_the_same_client_id(account, exchange):
    now, q, stops = traded(account, exchange, {BTC.research: "Long"})
    exchange.fail("place_stop", UNAVAILABLE)
    exchange.fail("close_position", NOT_CLOSED, times=1)
    alerts, closed = account.manage_stops(now, q, stops)
    assert closed == [BTC.swap] and alerts[0].startswith("止损平仓：")
    assert exchange.calls[-2][0] == "close_position" and exchange.calls[-2] == exchange.calls[-1]
    assert exchange.book[BTC.swap][0] == 0


def test_a_close_that_went_through_but_kept_reporting_errors_counts_as_closed(account, exchange):
    now, q, stops = traded(account, exchange, {BTC.research: "Long"})
    exchange.fail("place_stop", UNAVAILABLE)
    exchange.fail("close_position", NOT_CLOSED, applied=True)
    alerts, closed = account.manage_stops(now, q, stops)
    assert closed == [BTC.swap] and len(alerts) == 1 and alerts[0].startswith("止损平仓：")


def test_a_position_with_neither_a_stop_nor_a_quote_is_alerted(account, exchange):
    exchange.manual_fill("SOL-USDT-SWAP", 5)  # it appeared after the quotes were taken
    result = account.sync(T0)
    assert account.manage_stops(T0, {}, result.stops) == ([
        "没有止损：SOL-USDT-SWAP +5 张没有覆盖全部仓位的止损单，这次运行又没有它的报价，算不出止损价，请人工处理"
    ], [])
    exchange.place_stop("SOL-USDT-SWAP", 5, 70_000.0, "byhand")
    assert account.manage_stops(T0, {}, exchange.pending_stops()) == ([], [])


# -- a stop the price has already passed ------------------------------------------------


def test_a_stop_the_last_price_has_crossed_is_not_placed_and_the_position_is_closed_as_on_paper(
    account, ledger, exchange
):
    go_long(account, exchange)
    exchange.stops = []  # not on the exchange: it never hung, or was cancelled by hand
    exchange.price = 78_500.0
    alerts, closed = hourly(account, exchange, last=78_500.0)
    assert closed == [BTC.swap]
    assert calls(exchange) == ["place_stop", "close_position"]  # the one stop is the first hour's
    client_id = exchange.calls[-1][2]
    assert alerts == [
        "止损平仓：BTC-USDT-SWAP +10 张的止损价 79,000.00 已被现价 78,500.00 穿越，交易所里没有这张止损单，"
        f"已市价平仓（{client_id}）"
    ]
    result = account.sync(T0 + HOUR_MS + 5_000)
    assert result.problems == [] and ledger.positions() == {}
    assert [(f.reason, f.price) for f in ledger.fills()] == [("trade", 80_000.0), ("stop", 78_500.0)]
    # The next hour has nothing left to trip over.
    assert hourly(account, exchange, n=2, last=78_400.0) == ([], [])
    assert calls(exchange) == ["place_stop", "close_position"]


def test_a_stop_that_is_pending_as_it_should_is_left_to_fire_on_the_exchange(account, exchange):
    go_long(account, exchange)
    assert hourly(account, exchange, last=78_500.0) == ([], [])
    assert calls(exchange) == ["place_stop"] and [s.trigger for s in exchange.stops] == [79_000.0]


def test_a_stop_the_exchange_refuses_as_already_passed_closes_the_position_at_once(account, exchange):
    # The quotes at hand still say 80,000; the exchange knows better.
    now, q, stops = traded(account, exchange, {BTC.research: "Long"})
    exchange.refuse_passed = True
    exchange.price = 78_900.0
    alerts, closed = account.manage_stops(now, q, stops)
    assert closed == [BTC.swap]
    assert calls(exchange) == ["place_stop", "close_position"] and account.sleeps == []
    assert alerts == [
        "止损平仓：BTC-USDT-SWAP +10 张的止损 79,000.00 被交易所拒绝，触发价已在现价另一侧"
        "（/api/v5/trade/order-algo failed with code 51280: SL trigger price cannot be higher than the"
        f" last price.），已市价平仓（{exchange.calls[-1][2]}）"
    ]


def test_a_shorts_stop_refused_as_already_passed_closes_it_too(account, exchange):
    now, q, stops = traded(account, exchange, {BTC.research: "Short"})
    exchange.refuse_passed = True
    exchange.price = 81_200.0
    alerts, closed = account.manage_stops(now, q, stops)
    assert closed == [BTC.swap] and calls(exchange) == ["place_stop", "close_position"]
    assert alerts[0].startswith("止损平仓：BTC-USDT-SWAP -10 张的止损 81,000.00 被交易所拒绝")
    assert "code 51278: SL trigger price cannot be lower than the last price." in alerts[0]


def test_an_amendment_refused_as_already_passed_closes_the_position_though_the_old_stop_stands(account, exchange):
    go_long(account, exchange)
    exchange.refuse_passed = True
    result = account.sync(T0 + HOUR_MS)
    q = quotes(account, last=82_000.0)  # on these quotes the stop tightens to 81,000
    exchange.price = 80_500.0           # by the time it is sent, the price is below that
    alerts, closed = account.manage_stops(T0 + HOUR_MS, q, result.stops)
    assert closed == [BTC.swap] and calls(exchange) == ["place_stop", "amend_stop", "close_position"]
    assert alerts[0].startswith("止损平仓：BTC-USDT-SWAP +10 张的止损 81,000.00 被交易所拒绝")
    assert exchange.book[BTC.swap][0] == 0 and exchange.gaps == []


def test_a_passed_trigger_the_exchange_takes_is_left_pending_for_it_to_fire(account, exchange):
    # Whether OKX refuses such a stop is not known. This exchange takes it and keeps it.
    now, q, stops = traded(account, exchange, {BTC.research: "Long"})
    exchange.price = 78_900.0
    assert account.manage_stops(now, q, stops) == ([], [])
    assert [(s.contracts, s.trigger) for s in exchange.stops] == [(10.0, 79_000.0)]
    assert calls(exchange) == ["place_stop"]


def test_a_passed_trigger_the_exchange_fires_on_the_spot_ends_flat_and_booked_as_a_stop(
    account, ledger, exchange
):
    # Or it takes the stop and triggers it at once: the stop never shows as pending.
    now, q, stops = traded(account, exchange, {BTC.research: "Long"})
    exchange.fire_passed = True
    exchange.price = 78_900.0
    assert account.manage_stops(now, q, stops) == ([], [])
    assert exchange.book[BTC.swap][0] == 0 and "close_position" not in calls(exchange)
    result = account.sync(now + 5_000)
    assert result.problems == [] and ledger.positions() == {}
    assert [(f.reason, f.price) for f in ledger.fills()] == [("trade", 80_000.0), ("stop", 78_900.0)]
    # The second try left a stop behind a position that was gone: the next run cancels it.
    assert len(exchange.stops) == 1
    assert hourly(account, exchange) == ([], []) and exchange.stops == []


def test_a_refusal_under_a_code_we_do_not_know_still_ends_with_the_position_closed(account, exchange):
    now, q, stops = traded(account, exchange, {BTC.research: "Long"})
    exchange.refuse_passed, exchange.passed_code = True, "59999"
    exchange.price = 78_900.0
    alerts, closed = account.manage_stops(now, q, stops)
    assert closed == [BTC.swap] and alerts[0].startswith("止损平仓：BTC-USDT-SWAP +10 张试了 3 次都没挂上止损")
    assert calls(exchange) == ["place_stop"] * STOP_TRIES + ["close_position"]


def test_an_unknown_refusal_with_the_old_stop_standing_alerts_and_the_next_hours_quotes_close_it(
    account, exchange
):
    go_long(account, exchange)
    exchange.refuse_passed, exchange.passed_code = True, "59999"
    result = account.sync(T0 + HOUR_MS)
    q = quotes(account, last=82_000.0)
    exchange.price = 80_500.0
    alerts, closed = account.manage_stops(T0 + HOUR_MS, q, result.stops)
    assert closed == [] and [s.trigger for s in exchange.stops] == [79_000.0]
    assert len(alerts) == 1 and alerts[0].startswith("止损没更新：BTC-USDT-SWAP +10 张的止损没能改到 81,000.00")
    # An hour on the quotes themselves show the price under the ledger's stop: the
    # position is closed there, not sent to the exchange to be refused again.
    alerts, closed = hourly(account, exchange, n=2, last=80_500.0)
    assert closed == [BTC.swap]
    assert alerts[0].startswith("止损平仓：BTC-USDT-SWAP +10 张的止损价 81,000.00 已被现价 80,500.00 穿越")
    assert calls(exchange)[-1] == "close_position" and calls(exchange).count("amend_stop") == 1


# -- whatever the exchange does ------------------------------------------------------------

STATES = ("new", "tighten", "resize", "flip", "extra", "foreign")
STOP_METHODS = ("amend_stop", "place_stop", "cancel_stops", "close_position", "pending_stops", "positions")


def before_the_stops(state, account, exchange, last):
    """One of the states ``manage_stops`` finds a position in, by name, and what it is
    then called with (the hourly states on quotes whose last price is ``last``)."""
    if state == "new":  # just opened: no stop yet
        return traded(account, exchange, {BTC.research: "Long"})
    go_long(account, exchange)
    now = exchange.now = T0 + HOUR_MS
    if state == "resize":  # the position doubled: its stop is for half of it
        exchange.cash += 10_004.0
        return traded(account, exchange, {BTC.research: "Long"}, HOUR + HOUR_MS)
    if state == "flip":  # the position went short: its stop is on the wrong side
        return traded(account, exchange, {BTC.research: "Short"}, HOUR + HOUR_MS)
    if state == "extra":  # a second stop of ours beside the first
        exchange.place_stop(BTC.swap, 10, 78_000.0, "stpextra")
    if state == "foreign":  # its only stop is not ours
        exchange.stops = []
        exchange.place_stop(BTC.swap, 10, 78_000.0, "byhand")
    return now, quotes(account, last), account.sync(now).stops  # "tighten": an hour on, new quotes


def test_whatever_the_exchange_does_a_position_ends_with_its_stop_or_closed_or_named_in_an_alert(tmp_path):
    # 150 draws, from a fixed seed, of a state, of an answer to each thing not known of
    # the real exchange, and of failures of the calls manage_stops makes.
    rng = random.Random(32)
    for n in range(150):
        exchange = FakeExchange()
        ledger = Ledger(tmp_path / f"{n}.sqlite")
        ledger.initialize(10_000.0, T0)
        account = DemoAccount(ledger, FakeOKX(), exchange, watchlist=(BTC, ETH), sleep=lambda seconds: None)
        state, last = rng.choice(STATES), rng.choice([78_500.0, 80_000.0, 82_000.0])
        args = before_the_stops(state, account, exchange, last)
        world = exchange.unsettle(rng, STOP_METHODS)
        alerts, closed = account.manage_stops(*args)
        told = f"draw {n}: {state} at {last:,.0f}, {world}, alerts {alerts}"
        assert exchange.gaps == [], told
        assert [inst for inst in exchange.bare() if not any(inst in text for text in alerts)] == [], told
        assert [inst for inst in closed if exchange.book[inst][0]] == [], told
        ledger.db.close()


# -- the last line after a failed step -----------------------------------------------------


def test_protect_reads_the_positions_off_the_exchange_and_gives_each_the_stop_its_trade_set(
    account, ledger, exchange
):
    # The order filled; the sync that would have booked it never ran.
    now = exchange.now
    result = account.sync(now)
    q = quotes(account)
    _, desired = account.execute(HOUR, {BTC.research: "Long"}, now, result.equity, q)
    assert ledger.positions() == {} and desired == {BTC.swap: 79_000.0}
    alerts = []
    account.protect(now, quotes(account, last=79_600.0), desired, alerts)
    assert alerts == []
    assert [(s.inst, s.side, s.contracts, s.trigger) for s in exchange.stops] == [(BTC.swap, "sell", 10.0, 79_000.0)]
    pos = ledger.positions()[BTC.swap]
    assert (pos.qty, pos.entry, pos.stop) == (0.1, 80_000.0, 79_000.0)
    # The next sync books the fill behind the position and keeps its stop.
    result = account.sync(now + 5_000)
    assert result.problems == [] and [f.reason for f in ledger.fills()] == ["trade"]
    assert hourly(account, exchange, last=79_600.0) == ([], [])
    assert [s.trigger for s in exchange.stops] == [79_000.0]


def test_protect_gives_a_position_whose_stop_was_never_worked_out_one_from_the_quotes(account, ledger, exchange):
    exchange.manual_fill(BTC.swap, 10)  # an order that filled before its stop was known
    alerts = []
    account.protect(T0, quotes(account, last=80_400.0), {}, alerts)
    assert alerts == [] and [(s.contracts, s.trigger) for s in exchange.stops] == [(10.0, 79_400.0)]
    assert ledger.positions()[BTC.swap].stop == 79_400.0


def test_protect_closes_what_it_cannot_give_a_stop(account, exchange):
    exchange.manual_fill(BTC.swap, 10)
    exchange.fail("place_stop", UNAVAILABLE)
    alerts = []
    account.protect(T0, quotes(account), {}, alerts)
    assert len(alerts) == 1 and alerts[0].startswith("止损平仓：BTC-USDT-SWAP +10 张试了 3 次都没挂上止损")
    assert exchange.book[BTC.swap][0] == 0


def test_protect_never_raises_and_names_the_contracts_it_could_not_see_to(account, exchange):
    exchange.manual_fill(BTC.swap, 10)
    exchange.fail("positions", LOST)
    alerts = []
    account.protect(T0, quotes(account), {}, alerts)
    assert alerts == [
        "紧急：下单之后出了错，补挂止损这一步也没做成（ConnectionError: connection reset），"
        "BTC-USDT-SWAP、ETH-USDT-SWAP 的仓位可能没有止损，请立即人工检查"
    ]
    assert exchange.stops == []
