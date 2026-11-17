"""The checks before the demo's and the live account's orders (#39, ADR 0010).

An order is judged by the position it leaves, not by its own size: a flip of a position
at the coin cap, which closes the old side and opens the new one in a single order of
about twice the cap, is sent. An order that would leave a position over the coin cap,
which the rules never size, is refused as a miscalculation, and one over the profile's
position cap is refused; an order that only reduces a position never is.

The orders come minutes after the hour's first quotes, so the last prices are read again
just before them, and the orders, their stops and the check whether a stop is already
crossed all go by these. A contract whose price or ATR is not a positive finite number
sits the hour out: no order, its stop left where it is, an alert.

The numbers are tests/test_demo_account.py's: 10,000 USDT, BTC at 80,000, contracts of
0.01 BTC in lots of 0.01, an hourly ATR of 400. An ATR of 300, 0.375% of the price,
makes a full unit larger than the coin cap, so a position is held at the cap: 12.5
contracts.
"""

import math
from dataclasses import replace

import pytest

from tests.test_demo_account import BTC, ETH, HOUR, FakeExchange
from tests.test_demo_job import RUN0, Clock, Env
from tests.test_live_pause import LiveEnv
from tests.test_trader_paper import T0, FakeOKX
from trader import rules
from trader.demo import account as account_module, job
from trader.demo.account import DEMO, DemoAccount
from trader.intraday.paper import HOUR_MS
from trader.ledger import Ledger
from trader.okx import Bar

UNUSABLE = "，都要是大于 0 的有限数；这个币本小时不交易，止损也不按它调整"


class Market(FakeOKX):
    """FakeOKX with a last price (``prices``) and an hourly true range, which is the ATR
    (``ranges``), per contract; one in neither has FakeOKX's 80,000 and 400."""

    def __init__(self):
        super().__init__()
        self.prices, self.ranges = {}, {}

    def last_price(self, inst):
        return self.prices.get(inst, self.last)

    def bars(self, inst, bar, start_ms, end_ms):
        if bar != "1H" or inst not in self.ranges:
            return super().bars(inst, bar, start_ms, end_ms)
        half = self.ranges[inst] / 2
        return [Bar(ts, 80_000, 80_000 + half, 80_000 - half, 80_000) for ts in range(start_ms, end_ms, HOUR_MS)]


@pytest.fixture
def ledger(tmp_path):
    ledger = Ledger(tmp_path / "demo.sqlite")
    ledger.initialize(10_000.0, T0)
    return ledger


@pytest.fixture
def exchange():
    return FakeExchange()


@pytest.fixture
def market():
    return Market()


@pytest.fixture
def account(ledger, market, exchange):
    return DemoAccount(ledger, market, exchange, watchlist=(BTC,), sleep=lambda s: None)


def both(ledger, market, exchange):
    return DemoAccount(ledger, market, exchange, watchlist=(BTC, ETH), sleep=lambda s: None)


def hour(account, exchange, n, signals, price=None):
    """The ``n``-th hour after HOUR as the job runs it, the price moved to ``price``
    first when given: sync, quote, keep the stops, trade the hour's ``signals``, sync,
    hang the new stops. The alerts."""
    now = exchange.now = T0 + n * HOUR_MS
    if price is not None:
        exchange.price = account.okx.last = price
    alerts, desired = [], {}
    result = account.sync(now)
    quotes = account.quotes(HOUR + n * HOUR_MS, result.positions, now, alerts)
    account.manage_stops(now, quotes, result.stops, alerts=alerts)
    account.execute(HOUR + n * HOUR_MS, signals, now, result.equity, quotes, alerts=alerts, desired=desired)
    result = account.sync(now, desired_stops=desired)
    account.manage_stops(now, quotes, result.stops, alerts=alerts)
    return alerts


def orders(exchange):
    return [(call[1], call[2]) for call in exchange.calls if call[0] == "place_market"]


def stops(exchange):
    return [(s.side, s.contracts, s.trigger) for s in exchange.stops]


def events(ledger, kind):
    return [text for _, _, text in ledger.events(kinds=(kind,))]


# -- a flip at the coin cap -----------------------------------------------------------


@pytest.mark.parametrize(("first", "then", "price", "contracts"), [
    ("Short", "Long", 80_400.0, 12.36),   # refused before #39, the issue's case
    ("Short", "Long", 79_600.0, 12.61),
    ("Long", "Short", 80_400.0, -12.49),  # refused before #39
    ("Long", "Short", 79_600.0, -12.49),  # refused before #39
])
def test_a_position_at_the_coin_cap_flips_in_one_order_whichever_way_the_price_went(
    account, market, exchange, first, then, price, contracts,
):
    market.ranges[BTC.swap] = 300.0
    assert hour(account, exchange, 0, {BTC.research: first}) == []
    held = 12.5 if first == "Long" else -12.5
    assert exchange.book[BTC.swap] == [held, 80_000.0]
    # The price moves half a percent: the equity the flip sizes against is 10,000 less the
    # fee of 5 and plus or minus the 50 the position made. The new side is at the cap of
    # that equity, rounded down to a lot; the order is about twice the cap.
    assert hour(account, exchange, 1, {BTC.research: then}, price=price) == []
    assert orders(exchange) == [
        (BTC.swap, held), (BTC.swap, round(contracts - held, 8)),
    ]
    assert exchange.book[BTC.swap] == [contracts, price]
    side, trigger = ("sell", price - 750) if contracts > 0 else ("buy", price + 750)
    assert stops(exchange) == [(side, abs(contracts), trigger)]


# -- what is refused, and what never is -------------------------------------------------


@pytest.mark.parametrize(("first", "text"), [
    (None, "变动 +0.25，成交后名义 20,000 USDT，超过净值 10,000 的 1 倍"),      # opening
    ("Long", "变动 +0.1998，成交后名义 19,984 USDT，超过净值 9,998 的 1 倍"),   # adding
    ("Short", "变动 +0.2998，成交后名义 19,984 USDT，超过净值 9,998 的 1 倍"),  # flipping
])
def test_an_order_sized_wrong_beyond_the_coin_cap_is_still_refused_and_alerted(
    account, ledger, market, exchange, monkeypatch, first, text,
):
    if first:
        market.ranges[BTC.swap] = 800.0
        hour(account, exchange, 0, {BTC.research: first})  # 5 contracts, 4,000 USDT
    sent, book = orders(exchange), dict(exchange.book)
    market.ranges[BTC.swap] = 200.0  # half the ATR: a target at the coin cap, 12.49 contracts
    sized = rules.to_quantity
    monkeypatch.setattr(rules, "to_quantity", lambda *args: 2 * sized(*args))  # a bug: twice the position
    refused = f"拒绝下单：BTC-USDT-SWAP {text}，可能是算错了"
    assert hour(account, exchange, 1, {BTC.research: "Long"}) == [refused]
    assert events(ledger, "order_refused") == [refused]
    assert orders(exchange) == sent and exchange.book == book


@pytest.mark.parametrize("cap", ["coin", "position"])
def test_an_order_that_only_reduces_a_position_is_never_refused(account, market, exchange, monkeypatch, cap):
    hour(account, exchange, 0, {BTC.research: "Long"})  # 10 contracts, 8,000 USDT
    if cap == "coin":
        monkeypatch.setattr(account_module, "MAX_COIN_EXPOSURE", 0.25)
    else:
        account.profile = replace(DEMO, max_position=2_500.0)
    market.ranges[BTC.swap] = 800.0  # a unit half the size: down to 4.99 contracts, 3,992 USDT
    assert hour(account, exchange, 1, {BTC.research: "Long"}) == []
    assert exchange.book[BTC.swap][0] == 4.99
    assert hour(account, exchange, 2, {BTC.research: "Flat"}) == []
    assert exchange.book[BTC.swap][0] == 0 and exchange.stops == []


def test_a_flip_is_judged_by_the_position_it_opens_even_a_smaller_one(account, market, exchange):
    hour(account, exchange, 0, {BTC.research: "Long"})  # 10 contracts, 8,000 USDT
    account.profile = replace(DEMO, max_position=5_000.0)
    market.ranges[BTC.swap] = 500.0  # a unit of 6,397 USDT: short 7.99 contracts
    refused = "拒绝下单：BTC-USDT-SWAP 变动 -0.1799，成交后名义 6,392 USDT，超过单币上限 5,000 USDT"
    assert hour(account, exchange, 1, {BTC.research: "Short"}) == [refused]
    assert exchange.book[BTC.swap] == [10.0, 80_000.0]


def test_an_order_leaving_a_position_over_the_profiles_cap_is_refused(account, ledger, exchange):
    account.profile = replace(DEMO, max_position=7_999.0)
    refused = "拒绝下单：BTC-USDT-SWAP 变动 +0.1，成交后名义 8,000 USDT，超过单币上限 7,999 USDT"
    assert hour(account, exchange, 0, {BTC.research: "Long"}) == [refused]
    assert orders(exchange) == [] and events(ledger, "order_refused") == [refused]
    account.profile = replace(DEMO, max_position=8_000.0)
    assert hour(account, exchange, 1, {BTC.research: "Long"}) == []
    assert exchange.book[BTC.swap] == [10.0, 80_000.0]


def test_a_position_float_noise_rounds_up_to_the_coin_cap_is_not_refused(account):
    # 9,999.999999996 USDT is 1,249.9999999995 lots of 0.0001 BTC, which to_quantity rounds
    # up to 1,250: 0.125 BTC, 10,000 USDT, 4e-9 over the cap
    planned = account.plan({BTC.research: "Long"}, 10_000 - 4e-9, {BTC.swap: (80_000.0, 300.0)})
    assert [(order.new_qty, order.refused) for order in planned] == [(0.125, None)]


# -- quotes that cannot be used -------------------------------------------------------


@pytest.mark.parametrize(("price", "atr", "shown"), [
    (0.0, 400.0, "现价 0.00，ATR 400.00"),
    (-80_000.0, 400.0, "现价 -80,000.00，ATR 400.00"),
    (math.nan, 400.0, "现价 nan，ATR 400.00"),
    (math.inf, 400.0, "现价 inf，ATR 400.00"),
    (80_000.0, 0.0, "现价 80,000.00，ATR 0.00"),
    (80_000.0, math.nan, "现价 80,000.00，ATR nan"),
    (80_000.0, math.inf, "现价 80,000.00，ATR inf"),
])
def test_a_coin_whose_price_or_atr_is_unusable_sits_the_hour_out_and_is_alerted(
    ledger, market, exchange, price, atr, shown,
):
    account = both(ledger, market, exchange)
    market.prices[ETH.swap], market.ranges[ETH.swap] = price, atr
    unusable = f"报价不能用：ETH-USDT-SWAP {shown}{UNUSABLE}"
    assert hour(account, exchange, 0, {BTC.research: "Long", ETH.research: "Long"}) == [unusable]
    assert orders(exchange) == [(BTC.swap, 10.0)]
    assert events(ledger, "quote_unusable") == [unusable]


@pytest.mark.parametrize(("side", "price", "atr"), [
    ("Long", math.inf, 400.0),   # a stop 'crossed' by an infinite price: closed at market
    ("Long", 80_000.0, 0.0),     # a stop tightened onto the price itself: closed at market
    ("Short", 0.0, 400.0),       # a stop tightened down to 1,000, far under the price
])
def test_a_held_coin_without_a_usable_quote_keeps_its_position_and_its_stop(
    account, ledger, market, exchange, side, price, atr,
):
    hour(account, exchange, 0, {BTC.research: side})
    before = stops(exchange)
    market.prices[BTC.swap], market.ranges[BTC.swap] = price, atr
    alerts = hour(account, exchange, 1, {BTC.research: "Short" if side == "Long" else "Long"})
    assert len(alerts) == 1 and alerts[0].startswith("报价不能用：BTC-USDT-SWAP ")
    assert exchange.book[BTC.swap][0] == (10.0 if side == "Long" else -10.0)
    assert stops(exchange) == before and len(orders(exchange)) == 1
    assert "close_position" not in [call[0] for call in exchange.calls]
    assert ledger.positions()[BTC.swap].stop == before[0][2]


def test_a_held_coin_without_a_quote_still_counts_toward_the_gross_cap(ledger, market, exchange, monkeypatch):
    account = both(ledger, market, exchange)
    market.ranges[ETH.swap] = 300.0
    hour(account, exchange, 0, {ETH.research: "Long"})  # ETH at the coin cap: 12.5 contracts, 10,000 USDT
    monkeypatch.setattr(rules, "MAX_GROSS_EXPOSURE", 1.5)
    market.prices[ETH.swap] = 0.0
    hour(account, exchange, 1, {BTC.research: "Long", ETH.research: "Long"})
    # A unit of BTC is 7,996 USDT, but beside ETH's 10,000 (at its entry price) the gross
    # cap of 1.5 times the equity of 9,995 leaves 4,992.50: 6.24 contracts.
    assert orders(exchange) == [(ETH.swap, 12.5), (BTC.swap, 6.24)]


# -- prices read again before the orders --------------------------------------------------


def run_deciding_late(env, meanwhile, signal="Long"):
    """The hour's run at RUN0, the intraday account deciding ``signal`` only after the
    run's first look, and ``meanwhile`` happening while it waits."""
    clock = Clock(RUN0)

    def decide(n):
        if n == 1:
            meanwhile()
            env.decide(HOUR, signal)

    clock.on_sleep = decide
    env.exchange.now = RUN0
    job.run(env.settings, env.account, env.inbox, env.intraday, now_fn=clock.now, sleep=clock.sleep)


def test_the_orders_and_their_stops_go_by_the_price_read_again_after_the_wait(tmp_path):
    env = Env(tmp_path)

    def rally():  # three ATRs up while the intraday account decides
        env.exchange.price = env.okx.last = 81_200.0

    run_deciding_late(env, rally)
    # The new stop, 1,000 under the fill, is above the price the run first read: by that
    # price it would be crossed, and the position just opened closed at market.
    assert env.exchange.book[BTC.swap] == [10.0, 81_200.0]
    assert stops(env.exchange) == [("sell", 10.0, 80_200.0)]
    (report,) = env.inbox.sent
    assert report.startswith("【demo】成交 · 01-10 08:00 北京（00:00 UTC）\n\nBTC · 信号 Long\n")


def test_a_shadow_hour_sizes_its_orders_at_the_price_read_again_too(tmp_path):
    live = LiveEnv(tmp_path)

    def rally():
        live.exchange.price = live.okx.last = 81_200.0

    run_deciding_late(live, rally)
    assert events(live.ledger, "shadow_order") == ["BTC-USDT-SWAP 买入 0.5 张，名义 406 USDT，信号 Long"]


def test_a_price_unusable_by_the_time_of_the_orders_keeps_the_coin_out_of_the_hour(tmp_path):
    env = Env(tmp_path)

    def broken():
        env.okx.last = 0.0

    run_deciding_late(env, broken)
    unusable = f"报价不能用：BTC-USDT-SWAP 现价 0.00，ATR 400.00{UNUSABLE}"
    assert env.inbox.sent == [f"【demo】{unusable}"]
    assert env.exchange.calls == [] and env.ledger.get("decided_hour") == HOUR
    assert events(env.ledger, "quote_unusable") == [unusable]
