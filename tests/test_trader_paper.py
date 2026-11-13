import dataclasses
import math
import sqlite3
from datetime import UTC, datetime

import pytest

from trader import rules
from trader.intraday.paper import HOUR_MS, IntradayPaper
from trader.intraday.types import SignalResult
from trader.ledger import Ledger, Position
from trader.okx import DAY_MS, MINUTE_MS, Bar, ContractSpec, FundingEvent
from trader.paper import Paper, ReplayStalled
from trader.settings import Coin

BTC = Coin("BTC-USD", "BTC-USDT-SWAP", "BTC-USDT")
T0 = int(datetime(2026, 1, 10, 0, 30, tzinfo=UTC).timestamp() * 1000)
DAY0 = T0 - T0 % DAY_MS


class FakeOKX:
    """Twenty daily candles with a true range of 2,000 (ATR 2,000), close 80,000; hourly
    candles ("1H") with a true range of 400 (ATR 400), close 80,000, for any range."""

    def __init__(self, minute=(), funding=(), last=80_000.0):
        self.minute = list(minute)
        self.events = list(funding)
        self.last = last
        self.daily = [
            Bar(DAY0 - (20 - i) * DAY_MS, 80_000, 81_000, 79_000, 80_000) for i in range(20)
        ]

    def bars(self, inst, bar, start_ms, end_ms):
        if bar == "1H":
            hours = range(start_ms, end_ms, HOUR_MS)
            return [Bar(ts, 80_000, 80_200, 79_800, 80_000) for ts in hours]
        series = self.minute if bar == "1m" else self.daily
        return [b for b in series if start_ms <= b.ts < end_ms]

    def funding(self, inst, start_ms, end_ms):
        return [e for e in self.events if start_ms <= e.ts < end_ms]

    def last_price(self, inst):
        return self.last

    def contract_spec(self, inst):
        return ContractSpec(contract_value=0.01, lot_size=0.01, min_size=0.01)


def minutes(start, prices):
    """1-minute candles from ``start``: a number is a flat candle, a tuple is OHLC."""
    out = []
    for i, p in enumerate(prices):
        o, h, lo, c = p if isinstance(p, tuple) else (p, p, p, p)
        out.append(Bar(start + i * MINUTE_MS, o, h, lo, c))
    return out


@pytest.fixture
def ledger(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    ledger.initialize(10_000.0, T0)
    return ledger


def hold(ledger, qty, entry, stop, cash=10_000.0):
    ledger.commit(positions={BTC.swap: Position(qty, entry, stop)}, cash=cash)


def test_a_readonly_ledger_reads_but_cannot_write(ledger):
    hold(ledger, 0.04, 80_000, 75_000)
    reader = Ledger(ledger.path, readonly=True)
    assert reader.get("cash") == 10_000.0
    assert reader.positions()[BTC.swap].qty == 0.04
    with pytest.raises(sqlite3.OperationalError):
        reader.set("cash", 0.0)
    with pytest.raises(sqlite3.OperationalError):
        reader.add_event(T0, "x", "y")
    assert ledger.get("cash") == 10_000.0
    with pytest.raises(sqlite3.OperationalError):
        Ledger(ledger.path.with_name("missing.sqlite"), readonly=True)


def test_a_readonly_ledger_can_be_read_from_another_thread(ledger):
    # The web API opens, reads and closes a request's ledger on different worker threads.
    import threading

    reader, seen = Ledger(ledger.path, readonly=True), []
    worker = threading.Thread(target=lambda: seen.append(reader.get("cash")))
    worker.start()
    worker.join()
    assert seen == [10_000.0]
    reader.db.close()


def test_signals_are_recorded_newest_first_and_costed(ledger):
    hour = 3_600_000
    assert ledger.signals() == []  # the daily account's ledger has the table, empty
    ledger.record_signal(T0, BTC.research, SignalResult("Long", 2, "up", None, 100, 20, 0.01))
    ledger.record_signal(T0, "ETH-USD", SignalResult(None, None, "", "RuntimeError: boom"))
    ledger.record_signal(T0 + hour, BTC.research, SignalResult("Flat", 1, "", None, 90, 10, 0.02))
    assert ledger.signals() == [
        (T0 + hour, "BTC-USD", "Flat", 1, "", None, 90, 10, 0.02),
        (T0, "ETH-USD", None, None, "", "RuntimeError: boom", 0, 0, None),
        (T0, "BTC-USD", "Long", 2, "up", None, 100, 20, 0.01),
    ]
    assert ledger.signals(since_ms=T0 + 1) == ledger.signals()[:1]
    assert [row[1] for row in ledger.signals(limit=2)] == ["BTC-USD", "ETH-USD"]
    assert ledger.latest_signals() == {"BTC-USD": (T0 + hour, "Flat"), "ETH-USD": (T0, None)}
    assert ledger.signal_cost_since(0) == (pytest.approx(0.03), True)
    assert ledger.signal_cost_since(T0 + 1) == (pytest.approx(0.02), False)
    assert ledger.signal_costs(0) == [(T0, 0.01), (T0, None), (T0 + hour, 0.02)]
    assert ledger.signal_costs(T0 + 1) == [(T0 + hour, 0.02)]
    # A reader sees them too.
    assert len(Ledger(ledger.path, readonly=True).signals()) == 3


def test_buy_opens_a_full_unit_long(ledger):
    paper = Paper(ledger, FakeOKX(), (BTC,))
    assert paper.execute("2026-01-09", {BTC.research: "Buy"}, T0) == []
    # unit = 0.02 * 10,000 * 80,000 / (2.5 * 2,000) = 3,200 USDT -> 0.04 BTC
    pos = ledger.positions()[BTC.swap]
    fill_price = 80_000 * 1.0005
    assert pos.qty == pytest.approx(0.04)
    assert pos.entry == pytest.approx(fill_price)
    assert pos.stop == pytest.approx(fill_price - 5_000)
    assert ledger.get("cash") == pytest.approx(10_000 - 0.04 * fill_price * 0.0005)
    assert ledger.get("validation_start") == DAY0
    assert ledger.get("baseline_ref") == {BTC.research: 80_000}
    assert ledger.equity_series() == [(DAY0, 10_000.0)]
    # A trade date executes once.
    paper.execute("2026-01-09", {BTC.research: "Sell"}, T0)
    assert ledger.positions()[BTC.swap].qty == pytest.approx(0.04)


def test_hold_keeps_the_position_and_only_tightens_the_stop(ledger):
    hold(ledger, 0.04, 80_000, 75_000)
    Paper(ledger, FakeOKX(last=90_000), (BTC,)).execute("2026-01-09", {BTC.research: "Hold"}, T0)
    assert ledger.positions()[BTC.swap] == Position(0.04, 80_000, 85_000)
    assert ledger.fills() == []
    Paper(ledger, FakeOKX(last=88_000), (BTC,)).execute(
        "2026-01-10", {BTC.research: "Hold"}, T0 + DAY_MS
    )
    assert ledger.positions()[BTC.swap].stop == 85_000  # 83,000 would loosen it


def test_a_position_in_a_coin_dropped_from_the_watchlist_keeps_its_stop_managed(ledger):
    eth = Coin("ETH-USD", "ETH-USDT-SWAP", "ETH-USDT")
    hold(ledger, 0.04, 80_000, 74_000)  # BTC, which the watchlist no longer names
    Paper(ledger, FakeOKX(last=90_000), (eth,)).execute("2026-01-09", {eth.research: None}, T0)
    assert ledger.positions()[BTC.swap] == Position(0.04, 80_000, 85_000)  # tightened, not traded
    assert ledger.fills() == []
    assert ledger.get("marks") == {BTC.swap: 90_000, eth.swap: 90_000}
    alerts = Paper(ledger, FakeOKX(last=84_000), (eth,)).execute(
        "2026-01-10", {eth.research: None}, T0 + DAY_MS
    )
    assert ledger.positions() == {} and ledger.fills()[0].reason == "stop"
    assert len(alerts) == 1 and "BTC-USDT-SWAP" in alerts[0]


def test_failed_research_keeps_the_position(ledger):
    hold(ledger, 0.04, 80_000, 75_000)
    Paper(ledger, FakeOKX(), (BTC,)).execute("2026-01-09", {BTC.research: None}, T0)
    assert ledger.positions()[BTC.swap].qty == 0.04
    assert ledger.fills() == []


def test_sell_flips_a_long_to_a_half_unit_short(ledger):
    hold(ledger, 0.04, 80_000, 75_000)
    Paper(ledger, FakeOKX(), (BTC,)).execute("2026-01-09", {BTC.research: "Sell"}, T0)
    fill_price = 80_000 * 0.9995
    pos = ledger.positions()[BTC.swap]
    assert pos.qty == pytest.approx(-0.02)
    assert pos.entry == pytest.approx(fill_price)
    assert pos.stop == pytest.approx(fill_price + 5_000)
    realized = 0.04 * (fill_price - 80_000)
    assert ledger.get("cash") == pytest.approx(10_000 + realized - 0.06 * fill_price * 0.0005)


def test_a_stop_crossed_before_execution_fills_at_the_last_price(ledger):
    hold(ledger, -0.02, 80_000, 79_000)
    alerts = Paper(ledger, FakeOKX(), (BTC,)).execute("2026-01-09", {BTC.research: "Hold"}, T0)
    assert ledger.positions() == {}
    assert [f.reason for f in ledger.fills()] == ["stop"]
    assert ledger.fills()[0].price == pytest.approx(80_000 * 1.0005)
    assert "止损" in alerts[0]


def test_replay_fills_a_touched_stop_at_the_stop(ledger):
    hold(ledger, 0.04, 80_000, 75_000)
    okx = FakeOKX(minute=minutes(T0 - MINUTE_MS, [80_000, 79_000, (78_000, 78_000, 75_000, 76_000)]))
    alerts = Paper(ledger, okx, (BTC,)).replay(T0 + 3 * MINUTE_MS)
    fill_price = 75_000 * 0.9995
    assert ledger.positions() == {}
    assert ledger.fills()[0].price == pytest.approx(fill_price)
    assert ledger.fills()[0].ts == T0 + MINUTE_MS
    assert ledger.get("cash") == pytest.approx(
        10_000 + 0.04 * (fill_price - 80_000) - 0.04 * fill_price * 0.0005
    )
    assert ledger.get("processed_to") == T0 + 2 * MINUTE_MS
    assert "止损" in alerts[0]


def test_replay_fills_a_gap_through_the_stop_at_the_open(ledger):
    hold(ledger, 0.04, 80_000, 75_000)
    okx = FakeOKX(minute=minutes(T0 - MINUTE_MS, [80_000, (74_000, 74_500, 73_000, 74_000)]))
    Paper(ledger, okx, (BTC,)).replay(T0 + 2 * MINUTE_MS)
    assert ledger.fills()[0].price == pytest.approx(74_000 * 0.9995)


def test_replay_fills_a_short_stop_on_the_high(ledger):
    hold(ledger, -0.02, 80_000, 85_000)
    okx = FakeOKX(minute=minutes(T0 - MINUTE_MS, [80_000, (80_000, 86_000, 80_000, 84_000)]))
    Paper(ledger, okx, (BTC,)).replay(T0 + 2 * MINUTE_MS)
    fill = ledger.fills()[0]
    assert fill.qty == pytest.approx(0.02)
    assert fill.price == pytest.approx(85_000 * 1.0005)


def test_replay_books_funding_at_the_close_before_settlement(ledger):
    hold(ledger, 0.04, 80_000, 70_000)
    okx = FakeOKX(
        minute=minutes(T0 - MINUTE_MS, [80_000, 80_100, 80_200, 80_300]),
        funding=[FundingEvent(T0 + 2 * MINUTE_MS, 0.0001)],
    )
    Paper(ledger, okx, (BTC,)).replay(T0 + 3 * MINUTE_MS)
    # Settled at the start of minute T0+2, priced at the close of minute T0+1.
    assert ledger.funding_total() == pytest.approx(-0.04 * 80_200 * 0.0001)
    assert ledger.get("cash") == pytest.approx(10_000 - 0.04 * 80_200 * 0.0001)


def test_replay_kills_at_the_drawdown_limit(ledger):
    hold(ledger, 1.0, 80_000, 1.0)
    okx = FakeOKX(minute=minutes(T0 - MINUTE_MS, [80_000, 79_000, 77_900, 70_000]))
    alerts = Paper(ledger, okx, (BTC,)).replay(T0 + 3 * MINUTE_MS)
    # Equity 7,900 is 21% below the 10,000 peak: flatten at that close and halt.
    fill_price = 77_900 * 0.9995
    assert ledger.positions() == {}
    assert ledger.get("halted") is True
    assert [f.reason for f in ledger.fills()] == ["kill"]
    assert ledger.get("cash") == pytest.approx(
        10_000 + (fill_price - 80_000) - fill_price * 0.0005
    )
    assert "熔断" in alerts[0]
    assert alerts[0].endswith("确认后运行 python -m trader resume 恢复。")
    paper = Paper(ledger, FakeOKX(), (BTC,))
    assert paper.execute("2026-01-09", {BTC.research: "Buy"}, T0 + 4 * MINUTE_MS) == []
    assert ledger.positions() == {}
    paper.resume(T0 + 5 * MINUTE_MS)
    assert ledger.get("halted") is False
    assert ledger.get("peak") == ledger.get("cash")


def test_replay_is_idempotent(ledger):
    hold(ledger, 0.04, 80_000, 70_000)
    okx = FakeOKX(
        minute=minutes(T0 - MINUTE_MS, [80_000, 80_100, 80_200]),
        funding=[FundingEvent(T0 + MINUTE_MS, 0.0001)],
    )
    paper = Paper(ledger, okx, (BTC,))
    paper.replay(T0 + 2 * MINUTE_MS)
    cash = ledger.get("cash")
    paper.replay(T0 + 2 * MINUTE_MS)
    assert ledger.get("cash") == cash
    assert ledger.funding_total() == pytest.approx(-0.04 * 80_100 * 0.0001)


def test_flat_replay_snapshots_each_midnight(ledger):
    Paper(ledger, FakeOKX(), (BTC,)).replay(T0 + 2 * DAY_MS)
    assert ledger.equity_series() == [(DAY0 + DAY_MS, 10_000.0), (DAY0 + 2 * DAY_MS, 10_000.0)]
    assert ledger.get("processed_to") == T0 + 2 * DAY_MS


def test_replay_snapshots_midnight_with_a_position(ledger):
    start = DAY0 + DAY_MS - 2 * MINUTE_MS
    ledger.commit(positions={BTC.swap: Position(0.04, 80_000, 70_000)}, cash=10_000.0,
                  meta={"processed_to": start})
    okx = FakeOKX(minute=minutes(start - MINUTE_MS, [80_000, 80_000, 81_000, 81_000]))
    Paper(ledger, okx, (BTC,)).replay(DAY0 + DAY_MS + 2 * MINUTE_MS)
    assert ledger.equity_series() == [(DAY0 + DAY_MS, pytest.approx(10_000 + 0.04 * 1_000))]


def test_a_stalled_candle_feed_raises(ledger):
    hold(ledger, 0.04, 80_000, 70_000)
    okx = FakeOKX(minute=minutes(T0 - MINUTE_MS, [80_000, 80_000]))
    with pytest.raises(ReplayStalled):
        Paper(ledger, okx, (BTC,)).replay(T0 + 30 * MINUTE_MS)
    assert ledger.get("processed_to") == T0


def test_a_failed_replay_changes_nothing(ledger):
    hold(ledger, 0.04, 80_000, 70_000)

    class Broken(FakeOKX):
        def funding(self, inst, start_ms, end_ms):
            raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        Paper(ledger, Broken(minute=minutes(T0 - MINUTE_MS, [80_000, 80_000])), (BTC,)).replay(
            T0 + 2 * MINUTE_MS
        )
    assert ledger.get("processed_to") == T0
    assert ledger.positions()[BTC.swap].qty == 0.04


def test_execute_and_replay_record_the_marks_for_a_report_without_okx(ledger):
    paper = Paper(ledger, FakeOKX(last=80_000.0), (BTC,))
    paper.execute("2026-01-09", {BTC.research: "Buy"}, T0)
    assert ledger.get("marks") == {BTC.swap: 80_000.0}  # the quote the execution traded at

    okx = FakeOKX(minute=minutes(T0 - MINUTE_MS, [80_000, 80_500, 81_000]))
    Paper(ledger, okx, (BTC,)).replay(T0 + 3 * MINUTE_MS)
    assert ledger.get("marks") == {BTC.swap: 81_000.0}  # the last close replayed

    equity, unavailable = Paper(ledger, FakeOKX(last=82_000.0), (BTC,)).equity_now()
    entry = ledger.positions()[BTC.swap].entry
    assert (equity, unavailable) == (pytest.approx(ledger.get("cash") + 0.04 * (82_000 - entry)), False)


# -- quotes that cannot be used ---------------------------------------------------------

ETH = Coin("ETH-USD", "ETH-USDT-SWAP", "ETH-USDT")


class Market(FakeOKX):
    """FakeOKX with the last price (``prices``) and the true range of every daily and
    hourly candle, so the ATR (``ranges``), settable by contract."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.prices, self.ranges = {}, {}

    def bars(self, inst, bar, start_ms, end_ms):
        out = super().bars(inst, bar, start_ms, end_ms)
        r = self.ranges.get(inst)
        if r is None or bar == "1m":
            return out
        return [Bar(b.ts, b.close, b.close + r / 2, b.close - r / 2, b.close) for b in out]

    def last_price(self, inst):
        return self.prices.get(inst, self.last)


# A price or an ATR of 0, below 0, NaN or infinite, and how the alert shows it. No candles
# give an ATR below 0 (no true range is): the tests of that patch rules.atr.
BAD_QUOTES = [
    (0.0, 100.0, "现价 0.00，ATR 100.00"),
    (-2_000.0, 100.0, "现价 -2,000.00，ATR 100.00"),
    (math.nan, 100.0, "现价 nan，ATR 100.00"),
    (math.inf, 100.0, "现价 inf，ATR 100.00"),
    (2_100.0, 0.0, "现价 2,100.00，ATR 0.00"),
    (2_100.0, math.nan, "现价 2,100.00，ATR nan"),
    (2_100.0, math.inf, "现价 2,100.00，ATR inf"),
]
TODAY = "，都要是大于 0 的有限数；这个币今天不交易，止损也不按它调整"


def hold_eth(ledger, qty=1.0):
    """``qty`` ETH long from 2,000, its stop at 1,800, last marked at 2,500."""
    ledger.commit(
        positions={ETH.swap: Position(qty, 2_000.0, 1_800.0)}, cash=10_000.0,
        meta={"marks": {ETH.swap: 2_500.0}},
    )


def quoted(price, atr):
    market = Market()
    market.prices[ETH.swap], market.ranges[ETH.swap] = price, atr
    return market


def unusable_events(ledger):
    return [text for _, _, text in ledger.events(kinds=("quote_unusable",))]


@pytest.mark.parametrize(("price", "atr", "shown"), BAD_QUOTES)
def test_a_held_coin_without_a_usable_quote_sits_the_day_out_beside_one_that_trades(
    ledger, price, atr, shown,
):
    hold_eth(ledger)
    alerts = Paper(ledger, quoted(price, atr), (BTC, ETH)).execute(
        "2026-01-09", {BTC.research: "Buy", ETH.research: "Sell"}, T0
    )
    unusable = f"报价不能用：ETH-USDT-SWAP {shown}{TODAY}"
    assert alerts == [unusable] and unusable_events(ledger) == [unusable]
    # ETH keeps its position and its stop; the equity marks it at its last mark, 10,500,
    # on which a unit of BTC is 0.02 * 10,500 * 80,000 / 5,000 = 3,360 USDT: 0.042 BTC.
    assert ledger.positions()[ETH.swap] == Position(1.0, 2_000.0, 1_800.0)
    assert ledger.positions()[BTC.swap].qty == pytest.approx(0.042)
    assert [f.inst for f in ledger.fills()] == [BTC.swap]
    assert ledger.get("cash") == pytest.approx(10_000 - 0.042 * 80_000 * 1.0005 * 0.0005)
    assert ledger.get("marks") == {ETH.swap: 2_500.0, BTC.swap: 80_000.0}
    assert ledger.equity_series() == [(DAY0, 10_500.0)]
    assert ledger.executed("2026-01-09")


@pytest.mark.parametrize(("price", "atr", "shown"), BAD_QUOTES)
def test_a_coin_without_a_usable_quote_is_not_bought(ledger, price, atr, shown):
    alerts = Paper(ledger, quoted(price, atr), (BTC, ETH)).execute(
        "2026-01-09", {BTC.research: "Buy", ETH.research: "Buy"}, T0
    )
    assert alerts == [f"报价不能用：ETH-USDT-SWAP {shown}{TODAY}"]
    assert list(ledger.positions()) == [BTC.swap]
    assert ledger.positions()[BTC.swap].qty == pytest.approx(0.04)  # a full unit, as alone
    assert ledger.get("marks") == {BTC.swap: 80_000.0}


def test_a_held_coin_without_a_usable_quote_still_counts_toward_the_gross_cap(ledger, monkeypatch):
    hold_eth(ledger, 4.0)  # 10,000 USDT at its last mark, 2,000 up
    monkeypatch.setattr(rules, "MAX_GROSS_EXPOSURE", 1.0)
    Paper(ledger, quoted(0.0, 100.0), (BTC, ETH)).execute(
        "2026-01-09", {BTC.research: "Buy", ETH.research: "Sell"}, T0
    )
    # A unit of BTC is 0.02 * 12,000 * 80,000 / 5,000 = 3,840 USDT, but beside ETH's 10,000
    # the gross cap of 1 times the equity of 12,000 leaves 2,000: 0.025 BTC.
    assert ledger.positions()[BTC.swap].qty == pytest.approx(0.025)


def test_the_equity_marks_a_position_at_its_quote_where_it_is_usable(ledger):
    hold(ledger, 0.04, 80_000, 75_000)
    ledger.set("marks", {BTC.swap: 81_000.0})
    Paper(ledger, FakeOKX(last=90_000), (BTC,)).execute("2026-01-09", {BTC.research: "Hold"}, T0)
    assert ledger.equity_series() == [(DAY0, pytest.approx(10_400.0))]  # not 10,040, at the mark


def test_an_atr_below_zero_is_refused_too(ledger, monkeypatch):
    hold_eth(ledger)
    monkeypatch.setattr(rules, "atr", lambda *args, **kwargs: -100.0)  # every contract's
    alerts = Paper(ledger, quoted(2_100.0, 100.0), (BTC, ETH)).execute(
        "2026-01-09", {BTC.research: "Buy", ETH.research: "Sell"}, T0
    )
    assert alerts == [
        f"报价不能用：BTC-USDT-SWAP 现价 80,000.00，ATR -100.00{TODAY}",
        f"报价不能用：ETH-USDT-SWAP 现价 2,100.00，ATR -100.00{TODAY}",
    ]
    assert unusable_events(ledger) == alerts
    assert ledger.positions() == {ETH.swap: Position(1.0, 2_000.0, 1_800.0)}
    assert ledger.fills() == [] and ledger.get("cash") == 10_000.0


# -- candles and last prices that cannot be used ------------------------------------------

MIDNIGHT = DAY0 + DAY_MS
FIELDS = {"open": "开", "high": "高", "low": "低", "close": "收"}  # as the alert names them
BAD_PRICES = [(0.0, "0.00"), (-1.0, "-1.00"), (math.nan, "nan"), (math.inf, "inf")]
AS_MISSING = "；开高低收都要是大于 0 的有限数，这几分钟不判断止损，净值按之前的收盘价算"


def refused_alert(head, field, shown):
    """The alert ``head`` begins, of candles the first of which is at 81,000 but for
    ``field``, shown as ``shown``."""
    prices = "，".join(
        f"{name} {shown if key == field else '81,000.00'}" for key, name in FIELDS.items()
    )
    return f"K 线不能用：{head} {prices}{AS_MISSING}"


def bar_events(ledger):
    return [text for _, _, text in ledger.events(kinds=("bar_unusable",))]


class Minutes(FakeOKX):
    """FakeOKX with each contract's own 1-minute candles."""

    def __init__(self, series, **kwargs):
        super().__init__(**kwargs)
        self.series = series

    def bars(self, inst, bar, start_ms, end_ms):
        if bar != "1m":
            return super().bars(inst, bar, start_ms, end_ms)
        return [b for b in self.series[inst] if start_ms <= b.ts < end_ms]


@pytest.mark.parametrize("account", [Paper, IntradayPaper])
@pytest.mark.parametrize(("qty", "stop"), [(0.04, 75_000.0), (-0.04, 85_000.0)])
@pytest.mark.parametrize("field", list(FIELDS))
@pytest.mark.parametrize(("value", "shown"), BAD_PRICES)
def test_a_candle_with_a_price_that_cannot_be_used_counts_as_missing(
    ledger, account, qty, stop, field, value, shown,
):
    # The minute before midnight is refused. Read, a long's stop would fill at an open or
    # a low of 0 or below, a short's at an infinite open or high, and its close would
    # mark the midnight snapshot and price the funding settled at midnight.
    start = MIDNIGHT - 2 * MINUTE_MS
    ledger.commit(
        positions={BTC.swap: Position(qty, 80_000.0, stop)}, cash=10_000.0,
        meta={"processed_to": start},
    )
    refused = dataclasses.replace(
        Bar(MIDNIGHT - MINUTE_MS, 81_000.0, 81_000.0, 81_000.0, 81_000.0), **{field: value}
    )
    okx = FakeOKX(
        minute=[
            *minutes(start - MINUTE_MS, [80_000, 80_000]), refused,
            *minutes(MIDNIGHT, [82_000, 82_000]),
        ],
        funding=[FundingEvent(MIDNIGHT, 0.0001)],
    )
    alerts = account(ledger, okx, (BTC,)).replay(MIDNIGHT + 2 * MINUTE_MS)
    head = "BTC-USDT-SWAP 有 1 根 1 分钟 K 线按缺失处理，最早一根 01-10 23:59 UTC"
    assert alerts == [refused_alert(head, field, shown)] and bar_events(ledger) == alerts
    # No stop fills at it; midnight and its funding are priced at the close before it,
    # 80,000; the candles after it are replayed as usual.
    assert ledger.positions() == {BTC.swap: Position(qty, 80_000.0, stop)}
    assert ledger.fills() == []
    assert ledger.equity_series() == [(MIDNIGHT, 10_000.0)]
    cash = 10_000 - qty * 80_000 * 0.0001
    assert ledger.get("cash") == pytest.approx(cash)
    assert ledger.get("marks") == {BTC.swap: 82_000.0}
    assert ledger.get("peak") == pytest.approx(max(10_000, cash + qty * 2_000))
    assert ledger.get("processed_to") == MIDNIGHT + 2 * MINUTE_MS


def test_the_candles_after_a_refused_one_and_other_contracts_replay_as_usual(ledger):
    ledger.commit(
        positions={
            BTC.swap: Position(0.04, 80_000.0, 75_000.0), ETH.swap: Position(1.0, 2_000.0, 1_900.0),
        },
        cash=10_000.0,
    )
    okx = Minutes({
        # BTC opens at 0 at T0, a gap through its stop were it read; it reaches it at T0 + 1.
        BTC.swap: minutes(
            T0 - MINUTE_MS, [80_000, (0, 80_000, 80_000, 80_000), (76_000, 76_000, 74_000, 74_500)]
        ),
        ETH.swap: minutes(T0 - MINUTE_MS, [2_000, (1_950, 1_950, 1_850, 1_880), 1_880]),
    })
    alerts = Paper(ledger, okx, (BTC, ETH)).replay(T0 + 2 * MINUTE_MS)
    assert alerts[0] == bar_events(ledger)[0]
    assert alerts[0].startswith(
        "K 线不能用：BTC-USDT-SWAP 有 1 根 1 分钟 K 线按缺失处理，最早一根 01-10 00:30 UTC 开 0.00，"
    )
    assert [a.split(" ")[0] for a in alerts[1:]] == ["止损：ETH-USDT-SWAP", "止损：BTC-USDT-SWAP"]
    assert [(f.inst, f.ts, f.reason) for f in ledger.fills()] == [
        (ETH.swap, T0, "stop"), (BTC.swap, T0 + MINUTE_MS, "stop"),
    ]
    assert [f.price for f in ledger.fills()] == [
        pytest.approx(1_900 * 0.9995), pytest.approx(75_000 * 0.9995),
    ]
    assert ledger.positions() == {}


def test_refused_candles_at_the_end_wait_for_the_next_replay_and_alert_once(ledger):
    hold(ledger, 0.04, 80_000, 70_000)
    zero_close = (80_000, 80_000, 80_000, 0.0)
    okx = FakeOKX(minute=minutes(T0 - MINUTE_MS, [80_000, 80_000, zero_close, zero_close]))
    paper = Paper(ledger, okx, (BTC,))
    assert paper.replay(T0 + 3 * MINUTE_MS) == []  # nothing usable after T0 yet: wait
    assert ledger.get("processed_to") == T0 + MINUTE_MS
    assert bar_events(ledger) == []
    okx.minute += minutes(T0 + 3 * MINUTE_MS, [80_500])
    alerts = paper.replay(T0 + 4 * MINUTE_MS)
    head = "BTC-USDT-SWAP 有 2 根 1 分钟 K 线按缺失处理，最早一根 01-10 00:31 UTC"
    assert alerts == [refused_alert(head, "close", "0.00").replace("81,000", "80,000")]
    assert bar_events(ledger) == alerts
    assert ledger.get("processed_to") == T0 + 4 * MINUTE_MS
    assert ledger.get("marks") == {BTC.swap: 80_500.0}
    assert ledger.fills() == [] and ledger.get("halted") is False


def test_refused_candles_stall_the_replay_as_missing_ones_do(ledger):
    hold(ledger, 0.04, 80_000, 70_000)
    nan_close = (80_000, 80_000, 80_000, math.nan)
    okx = FakeOKX(minute=minutes(T0 - MINUTE_MS, [80_000, 80_000] + [nan_close] * 29))
    with pytest.raises(ReplayStalled, match="no usable closed 1m candles"):
        Paper(ledger, okx, (BTC,)).replay(T0 + 30 * MINUTE_MS)
    assert ledger.get("processed_to") == T0
    assert bar_events(ledger) == []


@pytest.mark.parametrize("seed", [None, (80_000, 80_000, 80_000, math.nan)])
def test_without_a_usable_candle_before_it_a_replay_starts_at_the_last_mark(ledger, seed):
    # Long 0.04 BTC from 60,000, last marked at 80,000; funding settles at the first minute.
    ledger.commit(
        positions={BTC.swap: Position(0.04, 60_000.0, 50_000.0)}, cash=10_000.0,
        meta={"marks": {BTC.swap: 80_000.0}},
    )
    candles = minutes(T0 - MINUTE_MS, [seed, 80_100]) if seed else minutes(T0, [80_100])
    okx = FakeOKX(minute=candles, funding=[FundingEvent(T0, 0.0001)])
    # The candle before T0 belongs to the replay before: no alert for it here.
    assert Paper(ledger, okx, (BTC,)).replay(T0 + MINUTE_MS) == []
    assert ledger.funding_total() == pytest.approx(-0.04 * 80_000 * 0.0001)  # not at 60,000


@pytest.mark.parametrize("account", [Paper, IntradayPaper])
@pytest.mark.parametrize("price", [price for price, _ in BAD_PRICES])
def test_a_last_price_that_cannot_be_used_is_reported_at_the_last_mark(ledger, account, price):
    hold(ledger, 0.04, 80_000, 75_000)
    ledger.set("marks", {BTC.swap: 81_000.0})
    equity, unavailable = account(ledger, FakeOKX(last=price), (BTC,)).equity_now()
    assert (equity, unavailable) == (pytest.approx(10_040.0), True)
