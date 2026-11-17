"""The demo account against an in-memory simulated exchange (ADR 0008).

The numbers follow tests/test_intraday_paper.py: with 10,000 USDT of equity, an hourly
ATR of 400 and BTC at 80,000, a full unit is 0.1 BTC (10 contracts of 0.01), the
stop 1,000 away. The exchange charges the taker fee of 0.05% and fills market orders
at its scripted price.
"""

from dataclasses import replace

import pytest
import requests

from tests.test_trader_paper import (
    BAD_RATES,
    BTC,
    DAY0,
    DEFERRED,
    NO_CLOSE,
    T0,
    FakeOKX,
    SpotClose,
    deferred_events,
)
from trader.demo import account as account_module
from trader.demo.account import DemoAccount
from trader.demo.settings import MISMATCH_GRACE_MS, ORDER_POLL_SECONDS, ORDER_POLLS
from trader.intraday.paper import HOUR_MS
from trader.ledger import Fill, Ledger, Position
from trader.okx import DAY_MS, FundingEvent
from trader.okx_private import (
    FUNDING_BILL,
    TRADE_BILL,
    TRANSFER_BILL,
    AccountConfig,
    Balance,
    Bill,
    ExchangeFill,
    ExchangePosition,
    FundingBill,
    OKXPrivateError,
    Order,
    StopOrder,
)
from trader.settings import Coin

ETH = Coin("ETH-USD", "ETH-USDT-SWAP", "ETH-USDT")
CT_VAL = 0.01
FEE = 0.0005
HOUR = T0 - T0 % HOUR_MS  # 2026-01-10 00:00 UTC
HOUR_ID = HOUR // HOUR_MS


class FakeExchange:
    """OKX's simulated trading in memory: a USDT wallet, net positions in contracts,
    market orders filled at ``price`` (per instrument in ``prices``) with the taker
    fee, conditional stops, fills and funding bills with bill ids, and the bills of every
    change of the balance: the trades', the funding fees' and the transfers a person makes
    (``transfer``). ``mark`` prices the positions for equity. ``now`` stamps what happens.

    What is not known of the real exchange's stops is a switch here, so that both
    answers can be tested: whether a second stop may pend beside the first
    (``one_stop``), whether a stop whose trigger the price has passed is refused
    (``refuse_passed``, under ``passed_code`` when not OKX's documented ones), fired
    on the spot (``fire_passed``) or just left pending, whether a repeated algo client
    id is refused (``duplicate_code``), whether an amendment that is accepted takes
    effect (``amend_ignored``), whether a stop whose placement is accepted shows among
    the pending ones (``place_ignored``). ``fail`` scripts the failure of any call.
    ``gaps`` lists the contracts a cancellation left without a closing stop while still
    held; ``at_close`` what was pending for a contract each time its close was asked."""

    simulated = True  # OKXPrivate.simulated: a client of OKX's simulated trading, as the demo's

    def __init__(self, cash=10_000.0, price=80_000.0, leverage=3.0, margin_mode="cross"):
        self.cash = cash
        self.price = price
        self.prices = {}
        self.mark = {}
        self.now = T0
        self.mode = "net_mode"
        self.leverages = {}
        self.leverage, self.margin_mode = leverage, margin_mode
        self.book = {}      # inst -> [contracts, avg price]
        self.orders = {}    # (inst, order id) and, of an order with one, (inst, client id) -> Order
        self.fill_rows = []
        self.stops = []
        self.funding = []     # FundingBill
        self.other_bills = []  # Bill beside the fills' and the funding fees': a transfer, or a test's
        self.calls = []
        self.fill_state = "filled"  # what a placed market order does
        self.place_error = None     # OKXPrivateError to raise from place_market
        self.permission_error = None  # OKXPrivateError to raise from check_trade_permission
        self.failures = []            # scripted by fail()
        self.one_stop = False
        self.refuse_passed = False
        self.passed_code = None
        self.fire_passed = False
        self.duplicate_code = "51065"  # None: a second stop under the same client id is accepted
        self.amend_ignored = False
        self.place_ignored = False
        self.gaps = []
        self.at_close = []            # (inst, its pending stops) at each close_position call
        self.world = {}               # what unsettle() last set
        self._ids = 0

    def fail(self, method, error, times=None, applied=False, inst=None):
        """Script ``method`` to raise ``error`` on its next ``times`` calls (on every
        call when None), for ``inst`` only when given. With ``applied`` the request
        takes effect and raises all the same: its answer was lost, and the error is
        what came back for the resend."""
        self.failures.append(
            {"method": method, "error": error, "times": times, "applied": applied, "inst": inst}
        )

    def unsettle(self, rng, methods):
        """Answer at random each thing not known of the real exchange, move the price or
        not, and script random failures of ``methods``; what was set, for the message
        of an assertion that fails."""
        self.one_stop = rng.random() < 0.3
        self.amend_ignored = rng.random() < 0.2
        self.place_ignored = rng.random() < 0.2
        self.duplicate_code = rng.choice(["51065", "51016", None])
        self.refuse_passed = rng.random() < 0.3
        self.passed_code = rng.choice([None, "59999"])
        self.fire_passed = rng.random() < 0.15
        if rng.random() < 0.3:
            self.price = rng.choice([78_500.0, 80_500.0, 81_500.0, 83_000.0])
        for method in methods:
            if rng.random() < 0.4:
                error = rng.choice([
                    OKXPrivateError(f"/{method}", "50001", "Service temporarily unavailable"),
                    requests.ConnectionError("connection reset"),
                ])
                changes = method not in ("pending_stops", "positions", "fills", "order")
                self.fail(method, error, rng.choice([1, 1, 2, 3, None]), changes and rng.random() < 0.4)
        switches = ("one_stop", "amend_ignored", "place_ignored", "duplicate_code", "refuse_passed",
                    "passed_code", "fire_passed", "price")
        self.world = {name: getattr(self, name) for name in switches} | {"failures": [
            (f["method"], type(f["error"]).__name__, f["times"], f["applied"]) for f in self.failures
        ]}
        return self.world

    def _failing(self, method, inst=None):
        """(error, applied) of the scripted failure this call meets; (None, False) without one."""
        for failure in self.failures:
            if failure["method"] == method and failure["inst"] in (None, inst):
                if failure["times"] is not None:
                    failure["times"] -= 1
                    if not failure["times"]:
                        self.failures.remove(failure)
                return failure["error"], failure["applied"]
        return None, False

    # -- the client's interface ---------------------------------------------

    def account_config(self):
        return AccountConfig(self.mode, "2", "read_only,trade")

    def set_position_mode(self, net=True):
        self.calls.append(("set_position_mode", net))
        self.mode = "net_mode" if net else "long_short_mode"

    def set_leverage(self, inst, leverage, margin_mode="cross"):
        self.calls.append(("set_leverage", inst, leverage, margin_mode))
        self.leverages[inst] = (leverage, margin_mode)

    def balance(self, ccy="USDT"):
        upl = sum(self._upl(inst) for inst in self.book)
        return Balance(ccy, self.cash + upl, self.cash, self.cash + upl, upl)

    def positions(self):
        error, _ = self._failing("positions")
        if error:
            raise error
        return [
            ExchangePosition(inst, c, avg, self._upl(inst), self.leverage, self.margin_mode, None, self.now)
            for inst, (c, avg) in self.book.items() if c
        ]

    def check_trade_permission(self, inst):
        self.calls.append(("check_trade_permission", inst))
        if self.permission_error:
            raise self.permission_error

    def place_market(self, inst, contracts, client_id, reduce_only=False, margin_mode="cross"):
        self.calls.append(("place_market", inst, contracts, client_id, reduce_only, margin_mode))
        error, applied = self._failing("place_market", inst)
        if error and not applied:
            raise error
        if self.place_error:
            raise self.place_error
        if (inst, client_id) in self.orders:
            raise OKXPrivateError("/api/v5/trade/order", "51016", "Client order ID already exists")
        if self.fill_state != "filled":
            order = self._order(inst, contracts, client_id, None, self.fill_state)
            self.orders[(inst, client_id)] = order
        else:
            order = self._fill(inst, contracts, client_id)
        if error:
            raise error
        return order.order_id

    def order(self, inst, client_id=None, order_id=None):
        error, _ = self._failing("order", inst)
        if error:
            raise error
        key = (inst, client_id or order_id)
        if key not in self.orders:
            raise OKXPrivateError("/api/v5/trade/order", "51603", "Order does not exist")
        return self.orders[key]

    def fills(self, begin_ms, end_ms):
        error, _ = self._failing("fills")
        if error:
            raise error
        return [f for f in self.fill_rows if begin_ms <= f.ts < end_ms]

    def close_position(self, inst, margin_mode="cross", client_id=None):
        self.calls.append(("close_position", inst, client_id))
        self.at_close.append((inst, [s for s in self.stops if s.inst == inst]))
        error, applied = self._failing("close_position", inst)
        if error and not applied:
            raise error
        contracts = self.book.get(inst, (0.0, 0.0))[0]
        if contracts:
            self._fill(inst, -contracts, client_id or "")
        self.stops = [s for s in self.stops if s.inst != inst]
        if error:
            raise error

    def place_stop(self, inst, contracts, trigger, client_id, margin_mode="cross"):
        self.calls.append(("place_stop", inst, contracts, trigger, client_id))
        error, applied = self._failing("place_stop", inst)
        if error and not applied:
            raise error
        path, side = "/api/v5/trade/order-algo", "sell" if contracts > 0 else "buy"
        self._refuse_passed(path, inst, side, trigger)
        if self.one_stop and any(s.inst == inst for s in self.stops):
            raise OKXPrivateError(path, "51168", "Failed. You have reduce-only type of open order(s)")
        if self.duplicate_code and any(s.client_id == client_id for s in self.stops):
            raise OKXPrivateError(path, self.duplicate_code, "algoClOrdId already exists.")
        algo_id = f"a{self._next()}"
        if not self.place_ignored:  # else it is answered with an algo id and nowhere to be seen
            self.stops.append(StopOrder(algo_id, client_id, inst, side, abs(contracts), trigger, True, self.now))
            if self.fire_passed and self._passed(inst, side, trigger) and self.book.get(inst, (0.0, 0.0))[0]:
                # Taken, and triggered on the spot: gone from the pending stops, the position with it.
                self.stops.pop()
                self._fire(inst, abs(contracts) if side == "buy" else -abs(contracts), client_id)
        if error:
            raise error
        return algo_id

    def amend_stop(self, stop, contracts, trigger):
        self.calls.append(("amend_stop", stop.algo_id, contracts, trigger))
        error, applied = self._failing("amend_stop", stop.inst)
        if error and not applied:
            raise error
        path = "/api/v5/trade/amend-algos"
        pending = [s for s in self.stops if s.algo_id == stop.algo_id]
        if not pending:
            raise OKXPrivateError(path, "51527", "Order modification unsuccessful. The stop order does not exist.")
        self._refuse_passed(path, stop.inst, stop.side, trigger)
        if not self.amend_ignored:
            self.stops[self.stops.index(pending[0])] = replace(
                pending[0], contracts=abs(contracts), trigger=trigger
            )
        if error:
            raise error

    def pending_stops(self):
        error, _ = self._failing("pending_stops")
        if error:
            raise error
        return list(self.stops)

    def cancel_stops(self, stops):
        self.calls.append(("cancel_stops", [s.algo_id for s in stops]))
        error, applied = self._failing("cancel_stops", stops[0].inst if stops else None)
        if error and not applied:
            raise error
        gone = {s.algo_id for s in stops}
        self.stops = [s for s in self.stops if s.algo_id not in gone]
        for inst in {s.inst for s in stops}:
            held = self.book.get(inst, (0.0, 0.0))[0]
            closing = "sell" if held > 0 else "buy"
            if held and not any(s.inst == inst and s.side == closing for s in self.stops):
                self.gaps.append(inst)
        if error:
            raise error

    def funding_bills(self, begin_ms, end_ms):
        return [b for b in self.funding if begin_ms <= b.ts < end_ms]

    def bills(self, begin_ms, end_ms):
        error, _ = self._failing("bills")
        if error:
            raise error
        rows = [Bill(f.bill_id, TRADE_BILL, "1", f.inst, f.fee, f.ts) for f in self.fill_rows]
        rows += [Bill(b.bill_id, FUNDING_BILL, "173", b.inst, b.amount, b.ts) for b in self.funding]
        rows += self.other_bills
        return sorted((b for b in rows if begin_ms <= b.ts < end_ms), key=lambda b: b.ts)

    # -- what the market does -------------------------------------------------

    def trigger_stop(self, inst, price):
        """The pending stop of ``inst`` fires: the market order the algo places
        (``_fire``) fills at ``price``."""
        (stop,) = [s for s in self.stops if s.inst == inst]
        self.stops.remove(stop)
        contracts = stop.contracts if stop.side == "buy" else -stop.contracts
        self._fire(inst, contracts, stop.client_id, price)

    def settle_funding(self, inst, amount):
        self.cash += amount
        self.funding.append(FundingBill(str(self._next()), inst, amount, self.now))

    def transfer(self, amount):
        """A person moves ``amount`` USDT into the trading account, or out of it when negative."""
        self.cash += amount
        sub_type = "11" if amount > 0 else "12"
        self.other_bills.append(Bill(str(self._next()), TRANSFER_BILL, sub_type, "", amount, self.now))

    def manual_fill(self, inst, contracts, client_id=""):
        """An order that is not the program's fills, under no client id or ``client_id``."""
        self._fill(inst, contracts, client_id)

    def bare(self):
        """The contracts held without a pending reduce-only stop for their whole size
        on the closing side: what a run may only leave behind with an alert."""
        return [
            inst for inst, (held, _) in self.book.items()
            if held and not any(
                s.inst == inst and s.reduce_only and s.contracts == abs(held)
                and s.side == ("sell" if held > 0 else "buy")
                for s in self.stops
            )
        ]

    # -- internals --------------------------------------------------------------

    def _next(self):
        self._ids += 1
        return self._ids

    def _passed(self, inst, side, trigger):
        """Whether the price is already at or past a stop's trigger."""
        price = self.prices.get(inst, self.price)
        return trigger >= price if side == "sell" else trigger <= price

    def _refuse_passed(self, path, inst, side, trigger):
        """With ``refuse_passed``, refuse a stop whose trigger the price has passed, as OKX
        documents it (51280 for a sell stop, 51278 for a buy stop) or under ``passed_code``."""
        if self.refuse_passed and self._passed(inst, side, trigger):
            code = self.passed_code or ("51280" if side == "sell" else "51278")
            way = "higher" if side == "sell" else "lower"
            raise OKXPrivateError(path, code, f"SL trigger price cannot be {way} than the last price.")

    def _upl(self, inst):
        contracts, avg = self.book.get(inst, (0.0, 0.0))
        return contracts * CT_VAL * (self.mark.get(inst, self.price) - avg)

    def _fire(self, inst, contracts, stop_client_id, price=None):
        """The market order a stop places when it fires. OKX gives it a client id of its
        own making, "O" and digits, as seen on simulated trading (#50): its fills carry
        that one, and only the order says which stop it came from, as its algo's client id."""
        return self._fill(inst, contracts, f"O{self._next()}", price=price, algo_client_id=stop_client_id)

    def _order(self, inst, contracts, client_id, price, state, algo_client_id=""):
        order_id = str(self._next())
        fee = -abs(contracts) * CT_VAL * price * FEE if price else 0.0
        return Order(
            order_id, client_id, inst, state, "buy" if contracts > 0 else "sell", abs(contracts),
            abs(contracts) if state == "filled" else 0.0, price, fee, algo_client_id, self.now,
        )

    def _fill(self, inst, contracts, client_id, price=None, algo_client_id=""):
        price = price or self.prices.get(inst, self.price)
        old, avg = self.book.get(inst, (0.0, 0.0))
        new = round(old + contracts, 8)
        realized = 0.0
        if old and (old > 0) != (contracts > 0):
            closed = min(abs(old), abs(contracts)) * (1 if old > 0 else -1)
            realized = closed * CT_VAL * (price - avg)
        if new == 0:
            avg = 0.0
        elif old == 0 or (old > 0) != (new > 0):
            avg = price
        elif abs(new) > abs(old):
            avg = (abs(old) * avg + abs(contracts) * price) / abs(new)
        fee = abs(contracts) * CT_VAL * price * FEE
        self.cash += realized - fee
        self.book[inst] = [new, avg]
        order = self._order(inst, contracts, client_id, price, "filled", algo_client_id)
        self.orders[(inst, order.order_id)] = order
        if client_id:
            self.orders[(inst, client_id)] = order
        self.fill_rows.append(ExchangeFill(
            str(self._next()), f"t{order.order_id}", order.order_id, client_id, inst,
            order.side, abs(contracts), price, -fee, self.now,
        ))
        return order


@pytest.fixture
def ledger(tmp_path):
    ledger = Ledger(tmp_path / "demo.sqlite")
    ledger.initialize(10_000.0, T0)
    return ledger


@pytest.fixture
def exchange():
    return FakeExchange()


@pytest.fixture
def okx():
    return FakeOKX(funding=[FundingEvent(T0 + HOUR_MS, 0.0001)])


@pytest.fixture
def account(ledger, okx, exchange):
    sleeps = []
    acc = DemoAccount(ledger, okx, exchange, watchlist=(BTC,), sleep=sleeps.append)
    acc.sleeps = sleeps
    return acc


def quotes(account, last=80_000.0):
    account.okx.last = last
    return account.quotes(HOUR, account.ledger.positions(), T0, [])


def go_long(account, exchange, now=T0):
    """The first hour: a Long signal opens 0.1 BTC; sync and stops follow."""
    exchange.now = now
    result = account.sync(now)
    q = quotes(account)
    account.manage_stops(now, q, result.stops)
    alerts, desired = account.execute(HOUR, {BTC.research: "Long"}, now, result.equity, q)
    result = account.sync(now, desired_stops=desired)
    alerts += account.manage_stops(now, q, result.stops)[0]
    return alerts, result


# -- setup and sync ---------------------------------------------------------------


def test_setup_switches_to_net_mode_once_and_sets_the_leverage(account, exchange):
    exchange.mode = "long_short_mode"
    assert account.setup() == ["持仓模式已切到单向（net_mode）", "1 个合约杠杆设为 cross 3×"]
    assert exchange.leverages == {BTC.swap: (3, "cross")}
    assert account.setup() == ["1 个合约杠杆设为 cross 3×"]
    assert exchange.calls.count(("set_position_mode", True)) == 1


def test_a_fresh_sync_reads_the_wallet_and_books_nothing(account, ledger, exchange):
    result = account.sync(T0)
    assert (result.equity, result.cash, result.positions, result.fills, result.problems) == (
        10_000.0, 10_000.0, {}, [], []
    )
    assert ledger.get("synced_to") == T0 and ledger.get("equity") == 10_000.0
    assert ledger.equity_series() == []  # no midnight passed since the account opened


def test_a_sync_snapshots_each_midnight_it_passes_at_the_current_equity(account, ledger):
    account.sync(T0 + 2 * DAY_MS + HOUR_MS)
    assert ledger.equity_series() == [(DAY0 + DAY_MS, 10_000.0), (DAY0 + 2 * DAY_MS, 10_000.0)]


# -- the first trade --------------------------------------------------------------


def test_a_long_signal_buys_a_unit_on_the_exchange_and_hangs_its_stop(account, ledger, exchange):
    alerts, result = go_long(account, exchange)
    assert alerts == []
    assert exchange.book[BTC.swap] == [10.0, 80_000.0]
    (place,) = [c for c in exchange.calls if c[0] == "place_market"]
    assert place == ("place_market", BTC.swap, 10.0, f"trd{HOUR_ID}btc", False, "cross")
    # The ledger is the exchange's copy: fee from the exchange, position with our stop.
    (fill,) = ledger.fills()
    assert (fill.inst, fill.qty, fill.price, fill.fee, fill.reason, fill.trade_date) == (
        BTC.swap, 0.1, 80_000.0, pytest.approx(4.0), "trade", "2026-01-10"
    )
    pos = ledger.positions()[BTC.swap]
    assert (pos.qty, pos.entry, pos.stop) == (0.1, 80_000.0, 79_000.0)
    assert ledger.get("cash") == pytest.approx(9_996.0)
    assert result.equity == pytest.approx(9_996.0)
    (stop,) = exchange.stops
    assert (stop.inst, stop.side, stop.contracts, stop.trigger, stop.reduce_only) == (
        BTC.swap, "sell", 10.0, 79_000.0, True
    )
    assert stop.client_id.startswith("stp")
    # The validation period starts with the day of the first execution.
    assert ledger.get("validation_start") == DAY0
    assert ledger.get("baseline_ref") == {BTC.research: 80_000.0}
    assert ledger.equity_series() == [(DAY0, 10_000.0)]


def test_a_rerun_of_the_hour_places_nothing_and_a_stale_ledger_reads_the_order_back(
    account, ledger, exchange
):
    go_long(account, exchange)
    q = quotes(account)
    # Same hour, same signal, ledger in sync: the position is at its target already.
    alerts, desired = account.execute(HOUR, {BTC.research: "Long"}, T0, 9_996.0, q)
    assert (alerts, desired) == ([], {})
    # A ledger that missed the fill (a crash between order and sync) asks again with
    # the same client id: the exchange refuses the duplicate and the order is read back.
    ledger.commit(positions={}, cash=10_000.0)
    alerts, desired = account.execute(HOUR, {BTC.research: "Long"}, T0, 10_000.0, q)
    assert alerts == [] and desired == {BTC.swap: 79_000.0}
    assert exchange.book[BTC.swap] == [10.0, 80_000.0]
    assert len(exchange.fill_rows) == 1


def test_the_hourly_stop_tightens_on_the_exchange_but_never_loosens(account, ledger, exchange):
    go_long(account, exchange)
    (hung,) = exchange.stops
    result = account.sync(T0 + HOUR_MS)
    account.manage_stops(T0 + HOUR_MS, quotes(account, last=82_000.0), result.stops)
    assert ledger.positions()[BTC.swap].stop == 81_000.0
    (stop,) = exchange.stops
    assert stop.trigger == 81_000.0 and stop.contracts == 10.0
    # The stop was amended where it stood: never cancelled, and no second one placed.
    assert stop.algo_id == hung.algo_id
    changes = ("place_stop", "amend_stop", "cancel_stops")
    assert [c[0] for c in exchange.calls if c[0] in changes] == ["place_stop", "amend_stop"]
    result = account.sync(T0 + 2 * HOUR_MS)
    account.manage_stops(T0 + 2 * HOUR_MS, quotes(account, last=79_500.0), result.stops)
    assert ledger.positions()[BTC.swap].stop == 81_000.0
    assert exchange.stops[0].trigger == 81_000.0
    assert [c[0] for c in exchange.calls if c[0] in changes] == ["place_stop", "amend_stop"]


def test_a_missing_stop_is_hung_again_and_an_orphan_cancelled(account, ledger, exchange):
    go_long(account, exchange)
    exchange.stops = []  # gone on the exchange
    exchange.place_stop(ETH.swap, -5, 3_200.0, "stpold")  # a stop with no position behind it
    result = account.sync(T0 + HOUR_MS)
    account.manage_stops(T0 + HOUR_MS, quotes(account), result.stops)
    assert [(s.inst, s.trigger) for s in exchange.stops] == [(BTC.swap, 79_000.0)]
    kinds = [row[1] for row in ledger.db.execute("SELECT ts, kind FROM events ORDER BY id")]
    assert "stop_cancelled" in kinds


# -- adding, flipping, flattening -------------------------------------------------


def test_more_equity_adds_on_the_same_side_and_keeps_the_tighter_stop(account, ledger, exchange):
    go_long(account, exchange)
    exchange.cash += 10_004.0  # the user topped the demo wallet up
    now = exchange.now = T0 + HOUR_MS
    result = account.sync(now)
    q = quotes(account)
    alerts, desired = account.execute(HOUR + HOUR_MS, {BTC.research: "Long"}, now, result.equity, q)
    assert alerts == []
    assert exchange.book[BTC.swap] == [20.0, 80_000.0]
    assert desired == {BTC.swap: 79_000.0}
    result = account.sync(now, desired_stops=desired)
    account.manage_stops(now, q, result.stops)
    assert ledger.positions()[BTC.swap].qty == pytest.approx(0.2)
    assert exchange.stops[0].contracts == 20.0 and exchange.stops[0].trigger == 79_000.0


def test_a_short_signal_flips_in_one_order_and_the_stop_moves_above(account, ledger, exchange):
    go_long(account, exchange)
    now = exchange.now = T0 + HOUR_MS
    result = account.sync(now)
    q = quotes(account)
    alerts, desired = account.execute(HOUR + HOUR_MS, {BTC.research: "Short"}, now, result.equity, q)
    assert alerts == []
    place = [c for c in exchange.calls if c[0] == "place_market"][-1]
    # Equity 9,996 after the fee: a unit is 0.09996 BTC, rounded down to the lot of
    # 0.01 contracts, so 9.99 contracts short: one order of 19.99 through zero.
    assert place[1:] == (BTC.swap, -19.99, f"trd{HOUR_ID + 1}btc", False, "cross")
    assert exchange.book[BTC.swap] == [-9.99, 80_000.0]
    assert desired == {BTC.swap: 81_000.0}
    result = account.sync(now, desired_stops=desired)
    account.manage_stops(now, q, result.stops)
    pos = ledger.positions()[BTC.swap]
    assert (pos.qty, pos.stop) == (pytest.approx(-0.0999), 81_000.0)
    (stop,) = exchange.stops
    assert (stop.side, stop.contracts, stop.trigger) == ("buy", 9.99, 81_000.0)
    assert result.problems == []


def test_flat_closes_reduce_only_and_the_stop_goes_with_it(account, ledger, exchange):
    go_long(account, exchange)
    now = exchange.now = T0 + HOUR_MS
    result = account.sync(now)
    q = quotes(account)
    alerts, desired = account.execute(HOUR + HOUR_MS, {BTC.research: "Flat"}, now, result.equity, q)
    assert alerts == [] and desired == {BTC.swap: None}
    place = [c for c in exchange.calls if c[0] == "place_market"][-1]
    assert place[1:] == (BTC.swap, -10.0, f"trd{HOUR_ID + 1}btc", True, "cross")
    result = account.sync(now, desired_stops=desired)
    account.manage_stops(now, q, result.stops)
    assert ledger.positions() == {} and exchange.stops == []
    assert [f.reason for f in ledger.fills()] == ["trade", "trade"]


def test_a_missing_signal_keeps_the_position(account, exchange):
    go_long(account, exchange)
    now = exchange.now = T0 + HOUR_MS
    result = account.sync(now)
    alerts, desired = account.execute(HOUR + HOUR_MS, {BTC.research: None}, now, result.equity, quotes(account))
    assert (alerts, desired) == ([], {})
    assert len(exchange.fill_rows) == 1


def test_nothing_is_traded_while_halted(account, ledger, exchange):
    ledger.set("halted", True)
    result = account.sync(T0)
    assert account.execute(HOUR, {BTC.research: "Long"}, T0, result.equity, quotes(account)) == ([], {})
    assert exchange.fill_rows == []


# -- what comes back from the exchange ----------------------------------------------


def test_a_stop_that_fired_on_the_exchange_is_booked_as_a_stop_with_the_exchange_price(
    account, ledger, exchange
):
    go_long(account, exchange)
    exchange.now = T0 + 30 * 60_000
    exchange.trigger_stop(BTC.swap, 78_950.0)
    assert exchange.fill_rows[-1].client_id.startswith("O")  # the exchange's name for it, not the stop's (#50)
    result = account.sync(T0 + HOUR_MS)
    assert result.problems == [] and result.paused == [] and not account.paused
    assert ledger.positions() == {}
    stop_fill = ledger.fills()[-1]
    assert (stop_fill.qty, stop_fill.price, stop_fill.reason) == (-0.1, 78_950.0, "stop")
    assert stop_fill.fee == pytest.approx(0.1 * 78_950 * FEE)
    assert result.alerts == [
        "止损平仓 · BTC\n卖出 0.1 @ 78,950.00（开仓均价 80,000.00）\n盈亏 -108.95 USDT（-1.36%）"
    ]
    # Cash is the wallet: 10,000 less both fees less the 105 lost.
    assert ledger.get("cash") == pytest.approx(10_000 - 4.0 - 0.1 * 78_950 * FEE - 105.0)


@pytest.mark.parametrize("error", [
    requests.ConnectionError("connection reset"),
    OKXPrivateError("/api/v5/trade/order", "50001", "Service temporarily unavailable"),
])
def test_a_fill_whose_order_cannot_be_read_is_booked_by_the_sync_that_reads_it(account, ledger, exchange, error):
    go_long(account, exchange)
    exchange.now = T0 + 30 * 60_000
    exchange.trigger_stop(BTC.swap, 78_950.0)
    exchange.fail("order", error, times=1)
    with pytest.raises(type(error)):
        account.sync(T0 + HOUR_MS)
    # Nothing of that sync is kept: an answer lost does not make the stop's fill another's.
    assert [f.reason for f in ledger.fills()] == ["trade"] and not account.paused
    assert ledger.positions()[BTC.swap].qty == pytest.approx(0.1)
    result = account.sync(T0 + HOUR_MS + 60_000)
    assert [f.reason for f in ledger.fills()] == ["trade", "stop"] and not account.paused
    assert ledger.positions() == {}
    assert result.alerts == [
        "止损平仓 · BTC\n卖出 0.1 @ 78,950.00（开仓均价 80,000.00）\n盈亏 -108.95 USDT（-1.36%）"
    ]


def test_a_fill_under_the_programs_client_id_is_told_without_reading_its_order(account, ledger, exchange):
    result = account.sync(T0)
    account.execute(HOUR, {BTC.research: "Long"}, T0, result.equity, quotes(account))
    exchange.fail("order", requests.ConnectionError("connection reset"))
    account.sync(T0)
    assert [f.reason for f in ledger.fills()] == ["trade"]


def test_a_fill_without_a_client_id_is_told_by_its_orders(account, ledger, exchange):
    result = account.sync(T0)
    account.execute(HOUR, {BTC.research: "Long"}, T0, result.equity, quotes(account))
    exchange.fill_rows[-1] = replace(exchange.fill_rows[-1], client_id="")
    account.sync(T0)
    assert [f.reason for f in ledger.fills()] == ["trade"] and not account.paused


@pytest.mark.parametrize("client_id", ["", "mine1", "O77"])
def test_a_fill_of_an_order_that_is_not_the_programs_is_manual_whatever_its_client_id(
    account, ledger, exchange, client_id
):
    go_long(account, exchange)
    exchange.now = T0 + HOUR_MS
    exchange.manual_fill(BTC.swap, 5, client_id)
    result = account.sync(T0 + HOUR_MS)
    assert [f.reason for f in ledger.fills()] == ["trade", "manual"] and account.paused
    assert result.paused == ["交易所里有不是程序下的成交：BTC-USDT-SWAP buy 5 张 @ 80,000.00"]


def test_a_fill_of_an_order_the_exchange_does_not_know_is_manual(account, ledger, exchange):
    go_long(account, exchange)
    exchange.now = T0 + HOUR_MS
    exchange.manual_fill(BTC.swap, 5, "O77")
    exchange.fail("order", OKXPrivateError("/api/v5/trade/order", "51603", "Order does not exist"))
    result = account.sync(T0 + HOUR_MS)
    assert [f.reason for f in ledger.fills()] == ["trade", "manual"] and account.paused
    assert result.paused == ["交易所里有不是程序下的成交：BTC-USDT-SWAP buy 5 张 @ 80,000.00"]


def test_a_fired_stop_is_told_from_all_its_fills_and_from_the_entry_of_the_position_it_closed():
    # A short's stop, filled in two pieces: 0.1 BTC at 81,300 on average, 1,300 above
    # the entry, lose 130 and 4 of fees, 1.68% of the 8,000 the 0.1 BTC cost.
    legs = [
        (4.0, Fill(T0, BTC.swap, 0.04, 81_000.0, 1.6, "stop")),
        (6.0, Fill(T0 + 1, BTC.swap, 0.06, 81_500.0, 2.4, "stop")),
    ]
    short = Position(-0.1, 80_000.0, 81_000.0)
    assert account_module._fired_text(BTC.swap, legs, short) == (
        "止损平仓 · BTC\n"
        "买入 0.1 @ 均价 81,300.00（2 笔 · 开仓均价 80,000.00）\n"
        "盈亏 -134.00 USDT（-1.68%）"
    )
    # No position it could have closed, in the ledger: no entry to measure from.
    for held in (None, Position(0.1, 80_000.0, 79_000.0)):
        assert account_module._fired_text(BTC.swap, legs, held) == (
            "止损平仓 · BTC\n买入 0.1 @ 均价 81,300.00（2 笔）\n账本里没有它平掉的仓位，算不出盈亏"
        )


def test_funding_is_booked_with_the_public_rate_and_not_twice(account, ledger, exchange):
    go_long(account, exchange)
    exchange.now = T0 + HOUR_MS
    exchange.settle_funding(BTC.swap, -0.8)
    account.sync(T0 + HOUR_MS + 1)
    account.sync(T0 + 2 * HOUR_MS)  # the overlap window sees the bill again
    rows = ledger.db.execute("SELECT ts, inst, rate, amount FROM funding").fetchall()
    assert rows == [(T0 + HOUR_MS, BTC.swap, 0.0001, -0.8)]
    assert ledger.get("cash") == pytest.approx(9_996.0 - 0.8)


def test_a_fill_the_program_did_not_make_is_booked_and_pauses_the_account_once(account, ledger, exchange):
    go_long(account, exchange)
    exchange.now = T0 + HOUR_MS
    exchange.manual_fill(BTC.swap, 5)
    exchange.manual_fill(BTC.swap, -2)
    result = account.sync(T0 + HOUR_MS)
    text = "交易所里有不是程序下的成交：BTC-USDT-SWAP buy 5 张 @ 80,000.00；BTC-USDT-SWAP sell 2 张 @ 80,000.00"
    assert result.problems == [] and result.paused == [text] and result.holding == []
    assert result.alerts == [
        f"暂停：{text}。不再下新单，仓位和止损单原样保留；查明原因后运行 python -m trader demo resume 解除。"
    ]
    (reason,) = account.pause_reasons
    assert account.paused and reason["text"] == text and reason["since"] == T0 + HOUR_MS
    assert [f.reason for f in ledger.fills()] == ["trade", "manual", "manual"]
    assert ledger.positions()[BTC.swap].qty == pytest.approx(0.13)
    # The next sync reads the fills again in its overlap: booked once, and paused for once.
    again = account.sync(T0 + HOUR_MS + 60_000)
    assert again.paused == [] and again.alerts == [] and len(account.pause_reasons) == 1
    assert len(ledger.fills()) == 3


def test_a_position_the_fills_do_not_explain_is_a_problem_and_the_exchange_wins(account, ledger, exchange):
    go_long(account, exchange)
    exchange.book[BTC.swap] = [30.0, 80_000.0]  # changed behind our back, no fill in sight
    result = account.sync(T0 + HOUR_MS)
    assert result.problems == [
        "账本与交易所持仓不一致：BTC-USDT-SWAP 账本推算 +0.1，交易所 +0.3，已按交易所为准"
    ]
    assert ledger.positions()[BTC.swap].qty == pytest.approx(0.3)
    assert ledger.positions()[BTC.swap].stop == 79_000.0  # same side: the stop is kept


def test_a_fill_reported_late_settles_the_unexplained_position_instead_of_counting_twice(
    account, ledger, exchange
):
    go_long(account, exchange)
    exchange.book[BTC.swap] = [30.0, 80_000.0]  # the exchange shows 0.3 BTC, its fill not yet
    result = account.sync(T0 + HOUR_MS)
    assert len(result.problems) == 1
    exchange.now = T0 + HOUR_MS + 60_000
    exchange.fill_rows.append(ExchangeFill(
        "late", "tlate", "9009", "trd1btc", BTC.swap, "buy", 20.0, 80_000.0, -0.64, exchange.now
    ))
    result = account.sync(T0 + 2 * HOUR_MS)
    assert result.problems == []
    assert ledger.positions()[BTC.swap].qty == pytest.approx(0.3)
    assert ledger.net_fills() == {BTC.swap: pytest.approx(0.3)}
    late = [f for f in ledger.fills(T0 + HOUR_MS) if f.reason == "trade"]
    assert [(f.qty, f.fee) for f in late] == [(pytest.approx(0.2), pytest.approx(0.64))]


def test_a_fill_the_exchange_stamps_after_our_clock_is_still_this_syncs(account, ledger, exchange):
    # The exchange's clock runs 2 s ahead of ours: the fill of an order just awaited
    # carries a time past our now. The sync must still book it (2026-11-10 13:10Z).
    go_long(account, exchange)
    exchange.now = T0 + HOUR_MS + 2_000
    exchange._fill(BTC.swap, 10.0, "trd2btc")
    result = account.sync(T0 + HOUR_MS)
    assert result.problems == []
    assert ledger.positions()[BTC.swap].qty == pytest.approx(0.2)
    assert [f.qty for f in ledger.fills(T0 + HOUR_MS)] == [pytest.approx(0.1)]


def test_a_position_still_unexplained_at_the_next_hourly_sync_pauses_the_account(account, ledger, exchange):
    go_long(account, exchange)
    exchange.book[BTC.swap] = [30.0, 80_000.0]
    text = "账本与交易所持仓不一致：BTC-USDT-SWAP 账本推算 +0.1，交易所 +0.3，已按交易所为准"
    first = account.sync(T0 + HOUR_MS)
    assert first.problems == [text] and first.holding == [text] and not account.paused
    # A sync of the same run, minutes later, still leaves a late fill its time.
    soon = account.sync(T0 + HOUR_MS + MISMATCH_GRACE_MS - 1)
    assert soon.problems == [text] and soon.paused == [] and not account.paused
    later = account.sync(T0 + 2 * HOUR_MS)
    assert later.problems == [] and later.paused == [text] and later.holding == [text]
    assert account.paused and ledger.positions()[BTC.swap].qty == pytest.approx(0.3)
    assert account.sync(T0 + 3 * HOUR_MS).alerts == []  # paused for it once


def test_the_fills_add_up_per_instrument(ledger):
    ledger.commit(positions={}, cash=0.0, fills=[
        Fill(T0, BTC.swap, 0.1, 80_000.0, 0.4, "trade", "2026-01-01"),
        Fill(T0 + 1, BTC.swap, -0.04, 81_000.0, 0.2, "stop", "2026-01-01"),
        Fill(T0 + 2, "ETH-USDT-SWAP", -1.5, 2_000.0, 0.1, "trade", "2026-01-01"),
    ])
    assert ledger.net_fills() == {BTC.swap: pytest.approx(0.06), "ETH-USDT-SWAP": -1.5}


def test_a_position_not_at_the_designed_leverage_is_a_problem(account, exchange):
    exchange.leverage, exchange.margin_mode = 5.0, "isolated"
    go_long(account, exchange)
    result = account.sync(T0 + HOUR_MS)
    assert result.problems == ["BTC-USDT-SWAP 在交易所是 isolated 5×，不是设计的 cross 3×"]


# -- the kill switch ----------------------------------------------------------------


def test_a_drawdown_of_a_fifth_trips_the_kill_switch_and_closes_everything(account, ledger, exchange):
    go_long(account, exchange)
    exchange.mark[BTC.swap] = 59_000.0  # unrealized -2,100 on 9,996: a 21% drawdown
    exchange.prices[BTC.swap] = 59_000.0
    exchange.now = T0 + HOUR_MS
    before = len(exchange.calls)
    result = account.sync(T0 + HOUR_MS)
    assert result.killed and ledger.get("halted") is True
    assert result.alerts == [
        "熔断：净值 7,896.00 比峰值 10,000.00 回撤 21.0%，停止交易；已对 BTC-USDT-SWAP 发出市价平仓。"
        "确认交易所里已经空仓、查明原因后，运行 python -m trader demo resume --kill 解除。"
    ]
    (close,) = exchange.calls[before:]
    assert close[:2] == ("close_position", BTC.swap) and close[2].startswith("kil")
    # Only sent: the contract was held when this sync read it, so its stop is kept.
    assert [s.inst for s in result.stops] == [BTC.swap]
    assert exchange.stops == [] and exchange.book[BTC.swap][0] == 0
    # The next sync books the closing fill as a kill and finds the exchange flat;
    # nothing trades until resume.
    result = account.sync(T0 + HOUR_MS + 5_000)
    assert [f.reason for f in ledger.fills()] == ["trade", "kill"] and result.problems == []
    assert ledger.positions() == {} and result.stops == [] and not result.killed
    assert result.alerts == ["熔断后核实：交易所里已经空仓。"]
    assert account.sync(T0 + HOUR_MS + 6_000).alerts == []
    assert account.execute(HOUR + HOUR_MS, {BTC.research: "Long"}, T0 + HOUR_MS, result.equity, quotes(account)) == ([], {})
    account.resume(T0 + 2 * HOUR_MS)
    assert ledger.get("halted") is False and ledger.get("peak") == ledger.get("cash")


# -- orders that go wrong -----------------------------------------------------------


def test_an_order_the_exchange_rejects_alerts_and_moves_on(account, ledger, exchange):
    exchange.place_error = OKXPrivateError("/api/v5/trade/order", "51008", "Insufficient balance")
    result = account.sync(T0)
    alerts, desired = account.execute(HOUR, {BTC.research: "Long"}, T0, result.equity, quotes(account))
    assert alerts == ["下单失败：BTC-USDT-SWAP +10 张：/api/v5/trade/order failed with code 51008: Insufficient balance"]
    assert desired == {} and exchange.fill_rows == []


def test_an_order_that_does_not_fill_in_time_is_left_to_the_next_sync(account, exchange):
    exchange.fill_state = "live"
    result = account.sync(T0)
    alerts, desired = account.execute(HOUR, {BTC.research: "Long"}, T0, result.equity, quotes(account))
    assert alerts == [
        f"订单未成交：BTC-USDT-SWAP trd{HOUR_ID}btc 在 {ORDER_POLLS * ORDER_POLL_SECONDS:g} 秒内没有成交，以下次对账为准"
    ]
    assert desired == {} and account.sleeps == [ORDER_POLL_SECONDS] * (ORDER_POLLS - 1)


def test_an_order_leaving_more_than_a_coins_cap_is_refused_as_a_bug(account, exchange, monkeypatch):
    monkeypatch.setattr(account_module, "MAX_COIN_EXPOSURE", 0.5)
    result = account.sync(T0)
    alerts, _ = account.execute(HOUR, {BTC.research: "Long"}, T0, result.equity, quotes(account))
    assert alerts == ["拒绝下单：BTC-USDT-SWAP 变动 +0.1，成交后名义 8,000 USDT，超过净值 10,000 的 0.5 倍，可能是算错了"]
    assert exchange.fill_rows == []


def test_stops_are_rounded_to_the_tick_size(account, okx, exchange, monkeypatch):
    from trader.okx import ContractSpec

    monkeypatch.setattr(okx, "contract_spec", lambda inst: ContractSpec(0.01, 0.01, 0.01, tick_size=0.5))
    go_long(account, exchange)
    result = account.sync(T0 + HOUR_MS)
    account.manage_stops(T0 + HOUR_MS, quotes(account, last=80_000.3), result.stops)
    assert exchange.stops[0].trigger == 79_000.5


# -- reference closes and funding rates that cannot be used ------------------------


@pytest.mark.parametrize(("close", "problem"), NO_CLOSE)
def test_without_a_usable_reference_close_the_validation_period_waits_for_an_hour_with_one(
    ledger, exchange, close, problem,
):
    okx = SpotClose(close)
    account = DemoAccount(ledger, okx, exchange, watchlist=(BTC,), sleep=lambda seconds: None)
    alerts, _ = go_long(account, exchange)
    text = DEFERRED.format(problem)
    assert alerts == [text]
    assert exchange.book[BTC.swap] == [10.0, 80_000.0]  # bought as ever
    assert ledger.get("validation_start") is None and ledger.get("baseline_ref") is None
    assert deferred_events(ledger) == [text]
    okx.close = 80_000.0  # served the next hour
    exchange.now = T0 + HOUR_MS
    result = account.sync(T0 + HOUR_MS)
    alerts, _ = account.execute(
        HOUR + HOUR_MS, {BTC.research: "Long"}, T0 + HOUR_MS, result.equity, quotes(account)
    )
    assert alerts == []
    assert ledger.get("validation_start") == DAY0
    assert ledger.get("baseline_ref") == {BTC.research: 80_000.0}


@pytest.mark.parametrize("rate", BAD_RATES)
def test_funding_whose_public_rate_is_not_a_finite_number_is_booked_at_a_rate_of_0(
    ledger, exchange, rate,
):
    okx = FakeOKX(funding=[FundingEvent(T0 + HOUR_MS, rate)])
    account = DemoAccount(ledger, okx, exchange, watchlist=(BTC,), sleep=lambda seconds: None)
    go_long(account, exchange)
    exchange.now = T0 + HOUR_MS
    exchange.settle_funding(BTC.swap, -0.8)
    account.sync(T0 + HOUR_MS + 1)
    rows = ledger.db.execute("SELECT ts, inst, rate, amount FROM funding").fetchall()
    assert rows == [(T0 + HOUR_MS, BTC.swap, 0.0, -0.8)]  # the amount is the bill's
    assert ledger.get("cash") == pytest.approx(9_996.0 - 0.8)
