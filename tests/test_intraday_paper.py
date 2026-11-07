"""IntradayPaper.execute: hourly sizing on the 1h ATR with the intraday constants.

FakeOKX serves hourly candles with an ATR of 400 at a price of 80,000. With 10,000 of
equity a full unit is 0.01 * 10,000 * 80,000 / (2.5 * 400) = 8,000 USDT, i.e. 0.1 BTC, and a
stop sits 2.5 * 400 = 1,000 from the fill.
"""

import pytest

from tests.test_trader_paper import BTC, DAY0, T0, FakeOKX, hold
from trader.intraday.paper import HOUR_MS, IntradayPaper, utc_date
from trader.ledger import Ledger, Position
from trader.okx import DAY_MS

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


def test_stops_tighten_to_the_hourly_atr_and_never_loosen(ledger):
    hold(ledger, 0.1, 80_000, 79_500)
    IntradayPaper(ledger, FakeOKX(last=81_000), (BTC,)).execute({BTC.research: None}, T0)
    assert ledger.positions()[BTC.swap] == Position(0.1, 80_000, 80_000)  # 81,000 - 1,000
    IntradayPaper(ledger, FakeOKX(last=80_500), (BTC,)).execute({BTC.research: None}, T0 + HOUR_MS)
    assert ledger.positions()[BTC.swap].stop == 80_000  # 79,500 would loosen it
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
