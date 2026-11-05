from datetime import UTC, datetime

import pytest

from trader.ledger import Ledger, Position
from trader.okx import DAY_MS, MINUTE_MS, Bar, ContractSpec, FundingEvent
from trader.paper import Paper, ReplayStalled
from trader.settings import Coin

BTC = Coin("BTC-USD", "BTC-USDT-SWAP", "BTC-USDT")
T0 = int(datetime(2026, 1, 10, 0, 30, tzinfo=UTC).timestamp() * 1000)
DAY0 = T0 - T0 % DAY_MS


class FakeOKX:
    """Twenty daily candles with a true range of 2,000 (ATR 2,000), close 80,000."""

    def __init__(self, minute=(), funding=(), last=80_000.0):
        self.minute = list(minute)
        self.events = list(funding)
        self.last = last
        self.daily = [
            Bar(DAY0 - (20 - i) * DAY_MS, 80_000, 81_000, 79_000, 80_000) for i in range(20)
        ]

    def bars(self, inst, bar, start_ms, end_ms):
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
