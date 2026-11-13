"""IntradayPaper.execute: hourly sizing on the 1h ATR with the intraday constants.

FakeOKX serves hourly candles with an ATR of 400 at a price of 80,000. With 10,000 of
equity a full unit is 0.01 * 10,000 * 80,000 / (2.5 * 400) = 8,000 USDT, i.e. 0.1 BTC, and a
stop sits 2.5 * 400 = 1,000 from the fill.
"""

import pytest

from tests.test_trader_paper import (
    BAD_QUOTES,
    BTC,
    DAY0,
    DEFERRED,
    ETH,
    NO_CLOSE,
    T0,
    FakeOKX,
    SpotClose,
    deferred_events,
    hold,
    hold_eth,
    quoted,
    unusable_events,
)
from trader import rules
from trader.intraday.paper import HOUR_MS, IntradayPaper, utc_date
from trader.intraday.settings import Params
from trader.ledger import Ledger, Position
from trader.okx import DAY_MS
from trader.paper import Paper
from trader.settings import Coin

FEE = 0.0005


@pytest.fixture
def ledger(tmp_path):
    ledger = Ledger(tmp_path / "intraday" / "ledger.sqlite")
    ledger.initialize(10_000.0, T0)
    return ledger


def test_long_opens_a_full_unit_sized_on_the_hourly_atr_and_one_percent_risk(ledger):
    paper = IntradayPaper(ledger, FakeOKX(), (BTC,))
    assert paper.execute({BTC.research: "Long"}, T0) == []
    pos = ledger.positions()[BTC.swap]
    fill_price = 80_000 * 1.0005
    assert pos.qty == pytest.approx(0.1)
    assert pos.entry == pytest.approx(fill_price)
    assert pos.stop == pytest.approx(fill_price - 1_000)
    assert ledger.get("cash") == pytest.approx(10_000 - 0.1 * fill_price * FEE)
    fill = ledger.fills()[0]
    assert (fill.reason, fill.trade_date, fill.ts) == ("trade", "2026-01-10", T0)
    # The validation period starts at this day's midnight, the baseline at the spot close before.
    assert ledger.get("validation_start") == DAY0
    assert ledger.get("baseline_ref") == {BTC.research: 80_000}
    assert ledger.equity_series() == [(DAY0, 10_000.0)]
    assert not ledger.executed("2026-01-10")  # no execution row: the job keeps the hour


def test_short_opens_a_full_unit_short_symmetric_to_long(ledger):
    IntradayPaper(ledger, FakeOKX(), (BTC,)).execute({BTC.research: "Short"}, T0)
    pos = ledger.positions()[BTC.swap]
    fill_price = 80_000 * 0.9995
    assert pos.qty == pytest.approx(-0.1)
    assert pos.entry == pytest.approx(fill_price)
    assert pos.stop == pytest.approx(fill_price + 1_000)


def test_flat_closes_a_position_however_small(ledger):
    hold(ledger, 0.001, 80_000, 75_000)  # 80 USDT: 0.01 unit, far below the threshold
    IntradayPaper(ledger, FakeOKX(), (BTC,)).execute({BTC.research: "Flat"}, T0)
    assert ledger.positions() == {}
    fill = ledger.fills()[0]
    assert fill.qty == pytest.approx(-0.001)
    assert fill.price == pytest.approx(80_000 * 0.9995)
    assert fill.reason == "trade"


def test_flat_without_a_position_trades_nothing(ledger):
    IntradayPaper(ledger, FakeOKX(), (BTC,)).execute({BTC.research: "Flat"}, T0)
    assert ledger.positions() == {}
    assert ledger.fills() == []


def test_a_missing_signal_keeps_the_position(ledger):
    hold(ledger, 0.1, 80_000, 79_000)
    IntradayPaper(ledger, FakeOKX(), (BTC,)).execute({BTC.research: None}, T0)
    assert ledger.positions()[BTC.swap].qty == 0.1
    assert ledger.fills() == []
    IntradayPaper(ledger, FakeOKX(), (BTC,)).execute({}, T0)
    assert ledger.fills() == []


@pytest.mark.parametrize(("held", "trades"), [(0.08, False), (0.07, True)])
def test_a_change_under_a_quarter_unit_is_skipped(ledger, held, trades):
    # Long targets 0.1 BTC (8,000). From 0.08 the change is 1,600 = 0.2 unit: skipped, where
    # the daily threshold of 0.1 would trade. From 0.07 it is 2,400 = 0.3 unit: traded.
    hold(ledger, held, 80_000, 79_000)
    IntradayPaper(ledger, FakeOKX(), (BTC,)).execute({BTC.research: "Long"}, T0)
    assert ledger.positions()[BTC.swap].qty == pytest.approx(0.1 if trades else held)
    assert len(ledger.fills()) == (1 if trades else 0)


def test_long_flips_a_short_to_a_full_long(ledger):
    hold(ledger, -0.1, 80_000, 81_000)
    IntradayPaper(ledger, FakeOKX(), (BTC,)).execute({BTC.research: "Long"}, T0)
    pos = ledger.positions()[BTC.swap]
    fill_price = 80_000 * 1.0005
    assert pos.qty == pytest.approx(0.1)
    assert pos.stop == pytest.approx(fill_price - 1_000)
    assert ledger.fills()[0].qty == pytest.approx(0.2)


def test_the_stop_of_a_new_position_uses_the_intraday_multiple(ledger, tmp_path):
    # The multiple is a knob of the engine's Params; the live account runs the default.
    paper = IntradayPaper(ledger, FakeOKX(), (BTC,), params=Params(stop_mult=3.0))
    paper.execute({BTC.research: "Long"}, T0)
    pos = ledger.positions()[BTC.swap]
    # unit = 0.01 * 10,000 * 80,000 / (3.0 * 400) = 6,666.67 -> 0.0833 BTC; stop 3 * 400 below
    assert pos.qty == pytest.approx(0.0833)
    assert pos.stop == pytest.approx(80_000 * 1.0005 - 1_200)
    # The daily account keeps its own 2.5 * 2,000 (trader.settings.STOP_ATR_MULT).
    daily = Ledger(tmp_path / "daily.sqlite")
    daily.initialize(10_000.0, T0)
    Paper(daily, FakeOKX(), (BTC,)).execute("2026-01-09", {BTC.research: "Buy"}, T0)
    assert daily.positions()[BTC.swap].stop == pytest.approx(80_000 * 1.0005 - 5_000)


def test_stops_tighten_to_the_hourly_atr_and_never_loosen(ledger):
    hold(ledger, 0.1, 80_000, 79_500)
    IntradayPaper(ledger, FakeOKX(last=81_000), (BTC,)).execute({BTC.research: None}, T0)
    assert ledger.positions()[BTC.swap] == Position(0.1, 80_000, 80_000)  # 81,000 - 1,000
    IntradayPaper(ledger, FakeOKX(last=80_500), (BTC,)).execute({BTC.research: None}, T0 + HOUR_MS)
    assert ledger.positions()[BTC.swap].stop == 80_000  # 79,500 would loosen it
    assert ledger.fills() == []


def test_a_position_in_a_coin_dropped_from_the_watchlist_keeps_its_stop_managed(ledger):
    eth = Coin("ETH-USD", "ETH-USDT-SWAP", "ETH-USDT")
    hold(ledger, 0.1, 80_000, 79_500)  # BTC, which the watchlist no longer names
    IntradayPaper(ledger, FakeOKX(last=81_000), (eth,)).execute({eth.research: None}, T0)
    assert ledger.positions()[BTC.swap] == Position(0.1, 80_000, 80_000)  # tightened, not traded
    assert ledger.fills() == []


def test_a_stop_crossed_before_execution_fills_at_the_last_price(ledger):
    hold(ledger, 0.1, 80_000, 80_500)
    alerts = IntradayPaper(ledger, FakeOKX(), (BTC,)).execute({BTC.research: None}, T0)
    assert ledger.positions() == {}
    fill = ledger.fills()[0]
    assert (fill.reason, fill.trade_date) == ("stop", None)
    assert fill.price == pytest.approx(80_000 * 0.9995)
    assert "止损" in alerts[0]


def test_nothing_trades_while_halted(ledger):
    ledger.set("halted", True)
    assert IntradayPaper(ledger, FakeOKX(), (BTC,)).execute({BTC.research: "Long"}, T0) == []
    assert ledger.positions() == {}
    assert ledger.fills() == []


def test_fills_carry_the_utc_date_of_their_hour(ledger):
    paper = IntradayPaper(ledger, FakeOKX(), (BTC,))
    paper.execute({BTC.research: "Long"}, DAY0 + 23 * HOUR_MS + 3 * 60_000)
    paper.execute({BTC.research: "Short"}, DAY0 + DAY_MS + 3 * 60_000)
    assert [f.trade_date for f in ledger.fills()] == ["2026-01-10", "2026-01-11"]
    assert utc_date(DAY0 + DAY_MS - 1) == "2026-01-10"


def test_the_validation_period_starts_once(ledger):
    paper = IntradayPaper(ledger, FakeOKX(), (BTC,))
    paper.execute({BTC.research: "Flat"}, T0)
    assert ledger.get("validation_start") == DAY0
    paper.execute({BTC.research: "Long"}, T0 + DAY_MS)
    assert ledger.get("validation_start") == DAY0
    assert ledger.equity_series() == [(DAY0, 10_000.0)]


# -- quotes that cannot be used (tests.test_trader_paper.BAD_QUOTES) --------------------

THIS_HOUR = "，都要是大于 0 的有限数；这个币本小时不交易，止损也不按它调整"


@pytest.mark.parametrize(("price", "atr", "shown"), BAD_QUOTES)
def test_a_held_coin_without_a_usable_quote_sits_the_hour_out_beside_one_that_trades(
    ledger, price, atr, shown,
):
    hold_eth(ledger)
    alerts = IntradayPaper(ledger, quoted(price, atr), (BTC, ETH)).execute(
        {BTC.research: "Long", ETH.research: "Flat"}, T0
    )
    unusable = f"报价不能用：ETH-USDT-SWAP {shown}{THIS_HOUR}"
    assert alerts == [unusable] and unusable_events(ledger) == [unusable]
    # Flat closes a position however small, but not on a quote that cannot be used. The
    # equity marks ETH at its last mark, 10,500, on which a unit of BTC is
    # 0.01 * 10,500 * 80,000 / 1,000 = 8,400 USDT: 0.105 BTC.
    assert ledger.positions()[ETH.swap] == Position(1.0, 2_000.0, 1_800.0)
    assert ledger.positions()[BTC.swap].qty == pytest.approx(0.105)
    assert [f.inst for f in ledger.fills()] == [BTC.swap]
    assert ledger.get("cash") == pytest.approx(10_000 - 0.105 * 80_000 * 1.0005 * FEE)
    assert ledger.get("marks") == {ETH.swap: 2_500.0}
    assert ledger.equity_series() == [(DAY0, 10_500.0)]


@pytest.mark.parametrize(("price", "atr", "shown"), BAD_QUOTES)
def test_a_coin_without_a_usable_quote_is_not_opened(ledger, price, atr, shown):
    alerts = IntradayPaper(ledger, quoted(price, atr), (BTC, ETH)).execute(
        {BTC.research: "Long", ETH.research: "Short"}, T0
    )
    assert alerts == [f"报价不能用：ETH-USDT-SWAP {shown}{THIS_HOUR}"]
    assert list(ledger.positions()) == [BTC.swap]
    assert ledger.positions()[BTC.swap].qty == pytest.approx(0.1)  # a full unit, as alone


def test_a_held_coin_without_a_usable_quote_still_counts_toward_the_gross_cap(ledger, monkeypatch):
    hold_eth(ledger, 3.0)  # 7,500 USDT at its last mark, 1,500 up
    monkeypatch.setattr(rules, "MAX_GROSS_EXPOSURE", 1.0)
    IntradayPaper(ledger, quoted(0.0, 100.0), (BTC, ETH)).execute(
        {BTC.research: "Long", ETH.research: None}, T0
    )
    # A unit of BTC is 0.01 * 11,500 * 80,000 / 1,000 = 9,200 USDT, but beside ETH's 7,500
    # the gross cap of 1 times the equity of 11,500 leaves 4,000: 0.05 BTC.
    assert ledger.positions()[BTC.swap].qty == pytest.approx(0.05)


def test_the_equity_marks_a_position_at_its_quote_where_it_is_usable(ledger):
    hold(ledger, 0.1, 80_000, 79_000)
    ledger.set("marks", {BTC.swap: 81_000.0})
    IntradayPaper(ledger, FakeOKX(last=90_000), (BTC,)).execute({BTC.research: None}, T0)
    assert ledger.equity_series() == [(DAY0, pytest.approx(11_000.0))]  # not 10,100, at the mark


def test_an_atr_below_zero_is_refused_too(ledger, monkeypatch):
    hold_eth(ledger)
    monkeypatch.setattr(rules, "atr", lambda *args, **kwargs: -100.0)  # every contract's
    alerts = IntradayPaper(ledger, quoted(2_100.0, 100.0), (BTC, ETH)).execute(
        {BTC.research: "Long", ETH.research: "Flat"}, T0
    )
    assert alerts == [
        f"报价不能用：BTC-USDT-SWAP 现价 80,000.00，ATR -100.00{THIS_HOUR}",
        f"报价不能用：ETH-USDT-SWAP 现价 2,100.00，ATR -100.00{THIS_HOUR}",
    ]
    assert unusable_events(ledger) == alerts
    assert ledger.positions() == {ETH.swap: Position(1.0, 2_000.0, 1_800.0)}
    assert ledger.fills() == [] and ledger.get("cash") == 10_000.0


@pytest.mark.parametrize(("close", "problem"), NO_CLOSE)
def test_without_a_usable_reference_close_the_validation_period_waits_for_an_hour_with_one(
    ledger, close, problem,
):
    okx = SpotClose(close)
    paper = IntradayPaper(ledger, okx, (BTC,))
    text = DEFERRED.format(problem)
    assert paper.execute({BTC.research: "Long"}, T0) == [text]
    assert ledger.positions()[BTC.swap].qty == pytest.approx(0.1)  # bought as ever
    assert ledger.get("validation_start") is None and ledger.get("baseline_ref") is None
    assert ledger.equity_series() == [] and deferred_events(ledger) == [text]
    okx.close = 80_000.0  # served the next hour
    assert paper.execute({BTC.research: "Long"}, T0 + HOUR_MS) == []
    assert ledger.get("validation_start") == DAY0
    assert ledger.get("baseline_ref") == {BTC.research: 80_000.0}
    assert [ts for ts, _ in ledger.equity_series()] == [DAY0]
