"""The offline evaluation (Issue #27): the history store, the historical market, the
replay of the intraday engine over recorded signals, and signal quality."""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from trader.evaluation import signals as sq
from trader.evaluation.history import HOUR_MS, MINUTE_MS, HistoryStore, bar_ms
from trader.evaluation.market import HistoricalOKX
from trader.evaluation.replay import (
    Policy,
    Signal,
    describe,
    efficiency_ratio,
    parse_grid,
    replay,
    signals_from_json,
    signals_from_ledger,
)
from trader.intraday.settings import DEFAULT_PARAMS, Params
from trader.ledger import Ledger
from trader.okx import Bar, ContractSpec, FundingEvent, OKXError
from trader.settings import WATCHLIST, Coin, Settings

BTC = Coin(research="BTC-USD", swap="BTC-USDT-SWAP", spot="BTC-USDT")
SPEC = ContractSpec(contract_value=0.001, lot_size=1.0, min_size=1.0, tick_size=0.1)
DAY0 = 1_767_225_600_000           # 2026-01-01 00:00 UTC
T0 = DAY0 + 24 * HOUR_MS           # the replays start here, a day of history behind them


@pytest.fixture
def store(tmp_path) -> HistoryStore:
    return HistoryStore(tmp_path / "history.sqlite")


def price_path(hours: int, trend: float = 0.0, crash_at: int | None = None) -> Callable[[int], float]:
    """Price per minute since DAY0: 50,000 drifting ``trend`` per hour, dropping 5% at
    minute ``crash_at`` and staying there."""
    def price(minute: int) -> float:
        p = 50_000.0 * (1 + trend * minute / 60)
        return p * 0.95 if crash_at is not None and minute >= crash_at else p
    return price


def load(store: HistoryStore, price: Callable[[int], float], hours: int, inst: str = BTC.swap) -> None:
    """Fill the store with ``hours`` hours of minute and hourly candles from DAY0 built
    on ``price``; every minute's range is 0.1% either side of it."""
    minutes = []
    for i in range(hours * 60):
        p = price(i)
        minutes.append(Bar(DAY0 + i * MINUTE_MS, p, p * 1.001, p * 0.999, p))
    hourly = []
    for h in range(hours):
        chunk = minutes[h * 60:(h + 1) * 60]
        hourly.append(Bar(
            DAY0 + h * HOUR_MS, chunk[0].open, max(b.high for b in chunk),
            min(b.low for b in chunk), chunk[-1].close,
        ))
    end = DAY0 + hours * HOUR_MS
    store.put_bars(inst, "1m", minutes, DAY0, end)
    store.put_bars(inst, "1H", hourly, DAY0, end)
    store.put_funding(inst, [FundingEvent(DAY0 + 8 * HOUR_MS * k, 0.0001) for k in range(1, hours // 8)], DAY0, end)
    store.put_spec(inst, SPEC)


# -- the history store -------------------------------------------------------

class FakeOKX:
    def __init__(self):
        self.calls: list[tuple] = []

    def bars(self, inst, bar, start_ms, end_ms):
        self.calls.append(("bars", inst, bar, start_ms, end_ms))
        step = bar_ms(bar)
        return [Bar(t, 1.0, 2.0, 0.5, 1.5) for t in range(start_ms, end_ms, step)]

    def funding(self, inst, start_ms, end_ms):
        self.calls.append(("funding", inst, start_ms, end_ms))
        return [FundingEvent(t, 0.0001) for t in range(start_ms, end_ms, 8 * HOUR_MS)]

    def contract_spec(self, inst):
        self.calls.append(("spec", inst))
        return SPEC


def test_the_store_fetches_only_the_gaps_of_a_range(store):
    okx = FakeOKX()
    now = DAY0 + 10 * HOUR_MS
    assert store.ensure_bars(okx, BTC.swap, "1H", DAY0, DAY0 + 4 * HOUR_MS, now) == 4
    assert store.ensure_bars(okx, BTC.swap, "1H", DAY0 + 6 * HOUR_MS, DAY0 + 8 * HOUR_MS, now) == 2
    okx.calls.clear()
    # Asking for the whole span only fetches the hole and the tail.
    assert store.ensure_bars(okx, BTC.swap, "1H", DAY0, DAY0 + 9 * HOUR_MS, now) == 3
    assert okx.calls == [
        ("bars", BTC.swap, "1H", DAY0 + 4 * HOUR_MS, DAY0 + 6 * HOUR_MS),
        ("bars", BTC.swap, "1H", DAY0 + 8 * HOUR_MS, DAY0 + 9 * HOUR_MS),
    ]
    assert store.coverage(BTC.swap, "1H") == [(DAY0, DAY0 + 9 * HOUR_MS)]
    assert len(store.bars(BTC.swap, "1H", DAY0, DAY0 + 9 * HOUR_MS)) == 9
    okx.calls.clear()
    assert store.ensure_bars(okx, BTC.swap, "1H", DAY0, DAY0 + 9 * HOUR_MS, now) == 0
    assert okx.calls == []


def test_the_store_never_marks_candles_not_closed_yet_as_fetched(store):
    okx = FakeOKX()
    now = DAY0 + 2 * HOUR_MS + 30 * MINUTE_MS  # the 02:00 candle is still open
    store.ensure_bars(okx, BTC.swap, "1H", DAY0, DAY0 + 5 * HOUR_MS, now)
    assert okx.calls == [("bars", BTC.swap, "1H", DAY0, DAY0 + 2 * HOUR_MS)]
    assert store.coverage(BTC.swap, "1H") == [(DAY0, DAY0 + 2 * HOUR_MS)]
    # Later, the rest is fetched.
    store.ensure_bars(okx, BTC.swap, "1H", DAY0, DAY0 + 5 * HOUR_MS, DAY0 + 6 * HOUR_MS)
    assert store.coverage(BTC.swap, "1H") == [(DAY0, DAY0 + 5 * HOUR_MS)]


def test_funding_and_specs_are_cached_the_same_way(store):
    okx = FakeOKX()
    now = DAY0 + 48 * HOUR_MS
    assert store.ensure_funding(okx, BTC.swap, DAY0, DAY0 + 24 * HOUR_MS, now) == 3
    assert store.ensure_funding(okx, BTC.swap, DAY0, DAY0 + 24 * HOUR_MS, now) == 0
    assert [e.ts for e in store.funding(BTC.swap, DAY0, DAY0 + 9 * HOUR_MS)] == [DAY0, DAY0 + 8 * HOUR_MS]
    assert store.spec(BTC.swap) is None
    assert store.ensure_spec(okx, BTC.swap) == SPEC
    assert store.ensure_spec(okx, BTC.swap) == SPEC
    assert okx.calls.count(("spec", BTC.swap)) == 1


def test_an_unknown_bar_size_is_refused():
    with pytest.raises(ValueError, match="unknown bar size"):
        bar_ms("3m")


# -- the historical market ---------------------------------------------------

def test_the_historical_market_only_knows_what_had_closed_by_then(store):
    load(store, price_path(48), 48)
    market = HistoricalOKX(store, DAY0 + 5 * HOUR_MS + 3 * MINUTE_MS)
    hourly = market.bars(BTC.swap, "1H", DAY0, DAY0 + 48 * HOUR_MS)
    assert [b.ts for b in hourly][-1] == DAY0 + 4 * HOUR_MS  # 05:00 is still open at 05:03
    minutes = market.bars(BTC.swap, "1m", DAY0 + 5 * HOUR_MS, DAY0 + 6 * HOUR_MS)
    assert [b.ts for b in minutes] == [DAY0 + 5 * HOUR_MS + k * MINUTE_MS for k in range(3)]
    # The last price is the close of the 05:02 candle, the last one closed at 05:03.
    assert market.last_price(BTC.swap) == minutes[-1].close
    assert market.contract_spec(BTC.swap) == SPEC
    assert [e.ts for e in market.funding(BTC.swap, DAY0, DAY0 + 48 * HOUR_MS)] == []
    market.at(DAY0 + 8 * HOUR_MS)
    assert [e.ts for e in market.funding(BTC.swap, DAY0, DAY0 + 48 * HOUR_MS)] == [DAY0 + 8 * HOUR_MS]


def test_the_historical_market_refuses_what_the_store_lacks(store):
    market = HistoricalOKX(store, DAY0 + HOUR_MS)
    with pytest.raises(OKXError, match="no 1m candle"):
        market.last_price(BTC.swap)
    with pytest.raises(OKXError, match="no contract spec"):
        market.contract_spec(BTC.swap)


# -- replaying the engine ----------------------------------------------------

def run(store, signals, start_ms, end_ms, **kwargs):
    """A replay of the one-coin watchlist the synthetic history covers."""
    return replay(store, signals, start_ms, end_ms, watchlist=(BTC,), **kwargs)


def test_a_replay_trades_the_signals_hour_by_hour_with_the_real_engine(store):
    load(store, price_path(72, trend=0.002), 72)  # up 0.2% an hour, no dips
    signals = [
        Signal(T0 + 2 * HOUR_MS + 4 * MINUTE_MS, BTC.research, "Long", 2),
        Signal(T0 + 20 * HOUR_MS + 4 * MINUTE_MS, BTC.research, "Flat", 1),
    ]
    result = run(store, signals, T0, T0 + 24 * HOUR_MS, capital=10_000.0)
    assert [(f.reason, f.qty > 0) for f in result.fills] == [("trade", True), ("trade", False)]
    assert result.fills[0].ts == T0 + 2 * HOUR_MS + 5 * MINUTE_MS   # the minute after the signal
    assert result.fills[1].ts == T0 + 20 * HOUR_MS + 5 * MINUTE_MS
    # Long 10,000 USDT (the coin cap) through an 18-hour, 3.6% rise, less fees and slippage.
    m = result.metrics()
    assert 0.03 < m["return"] < 0.037
    assert m["trades"] == 2 and m["stops"] == 0 and m["hours"] == 24 and not m["halted"]
    assert m["fees"] > 0 and m["turnover"] > 19_000
    assert m["max_drawdown"] < 0.002
    assert len(result.daily) == 2  # the validation start and the midnight after it
    assert m["sharpe"] is None   # too few days


def test_an_hour_without_a_signal_keeps_the_position(store):
    load(store, price_path(72, trend=0.002), 72)
    signals = [Signal(T0 + 2 * HOUR_MS + 4 * MINUTE_MS, BTC.research, "Long", 2)]
    result = run(store, signals, T0, T0 + 10 * HOUR_MS)
    assert len(result.fills) == 1
    assert result.equity[-1][1] > result.equity[2][1]
    assert all(0.9 < e < 1.1 for e in result.exposure[2:])


def test_a_stop_out_in_the_replay_is_the_engines(store):
    # The 5% crash at hour 30 (minute 1,800 since DAY0) is a stop fill at 2.5 ATRs.
    load(store, price_path(72, crash_at=30 * 60), 72)
    signals = [Signal(T0 + 2 * HOUR_MS + 4 * MINUTE_MS, BTC.research, "Long", 3)]
    result = run(store, signals, T0, T0 + 12 * HOUR_MS)
    assert [f.reason for f in result.fills] == ["trade", "stop"]
    assert result.fills[1].ts == DAY0 + 30 * HOUR_MS
    assert result.metrics()["return"] < -0.02


def test_the_cooldown_policy_keeps_a_stopped_coin_flat_for_a_while(store):
    load(store, price_path(72, crash_at=30 * 60), 72)
    longs = [Signal(T0 + h * HOUR_MS + 4 * MINUTE_MS, BTC.research, "Long", 3) for h in range(2, 14)]
    plain = run(store, longs, T0, T0 + 14 * HOUR_MS)
    cooled = run(store, longs, T0, T0 + 14 * HOUR_MS, policy=Policy(stop_cooldown_hours=4))
    # Without a cooldown the Long of hour 06 (the crash hour) re-enters at once (and
    # the engine later trims the position as the crash widens the ATR).
    assert [f.reason for f in plain.fills[:3]] == ["trade", "stop", "trade"]
    assert plain.fills[2].ts == T0 + 6 * HOUR_MS + 5 * MINUTE_MS
    # With one, the coin stays flat four hours after the stop at 06:00 and re-enters at 10:05.
    assert [f.reason for f in cooled.fills[:3]] == ["trade", "stop", "trade"]
    assert cooled.fills[2].ts == T0 + 10 * HOUR_MS + 5 * MINUTE_MS
    assert not any(T0 + 6 * HOUR_MS < f.ts < T0 + 10 * HOUR_MS for f in cooled.fills)


def test_the_flip_policy_ignores_a_weak_reversal(store):
    load(store, price_path(72, trend=0.002), 72)
    signals = [
        Signal(T0 + 2 * HOUR_MS + 4 * MINUTE_MS, BTC.research, "Long", 3),
        Signal(T0 + 5 * HOUR_MS + 4 * MINUTE_MS, BTC.research, "Short", 1),
        Signal(T0 + 8 * HOUR_MS + 4 * MINUTE_MS, BTC.research, "Short", 2),
    ]
    plain = run(store, signals, T0, T0 + 10 * HOUR_MS)
    strict = run(store, signals, T0, T0 + 10 * HOUR_MS, policy=Policy(flip_min_conviction=2))
    # Following every signal, the account reverses at 05:05 (and rebalances later as
    # the unit moves); requiring conviction 2 for a reversal, it holds until 08:05.
    assert [f.ts for f in plain.fills[:2]] == [T0 + 2 * HOUR_MS + 5 * MINUTE_MS, T0 + 5 * HOUR_MS + 5 * MINUTE_MS]
    assert [f.ts for f in strict.fills[:2]] == [T0 + 2 * HOUR_MS + 5 * MINUTE_MS, T0 + 8 * HOUR_MS + 5 * MINUTE_MS]
    assert plain.fills[1].qty < 0 and strict.fills[1].qty < 0


def test_conviction_weights_size_the_tiers_differently(store):
    load(store, price_path(72, trend=0.002), 72)
    weak = [Signal(T0 + 2 * HOUR_MS + 4 * MINUTE_MS, BTC.research, "Long", 1)]
    strong = [Signal(T0 + 2 * HOUR_MS + 4 * MINUTE_MS, BTC.research, "Long", 3)]
    policy = Policy(conviction_weights=(0.25, 0.5, 1.0))
    small = run(store, weak, T0, T0 + 4 * HOUR_MS, policy=policy, params=Params(risk=0.002))
    big = run(store, strong, T0, T0 + 4 * HOUR_MS, policy=policy, params=Params(risk=0.002))
    # Four times the size, give or take the whole contracts each rounds down to.
    assert big.fills[0].qty == pytest.approx(4 * small.fills[0].qty, abs=4 * SPEC.contract_value)
    assert policy.labels() == {"Flat": 0.0, "Long1": 0.25, "Short1": -0.25, "Long2": 0.5,
                               "Short2": -0.5, "Long3": 1.0, "Short3": -1.0}


def test_other_params_reach_the_engine(store):
    load(store, price_path(72, trend=0.002), 72)
    signals = [Signal(T0 + 2 * HOUR_MS + 4 * MINUTE_MS, BTC.research, "Long", 2)]
    tiny = run(store, signals, T0, T0 + 4 * HOUR_MS, params=Params(risk=0.001))
    tinier = run(store, signals, T0, T0 + 4 * HOUR_MS, params=Params(risk=0.001, stop_mult=5.0))
    assert tinier.fills[0].qty == pytest.approx(tiny.fills[0].qty / 2, abs=SPEC.contract_value)


def test_a_replay_can_keep_its_ledger(store, tmp_path):
    load(store, price_path(72, trend=0.002), 72)
    signals = [Signal(T0 + 2 * HOUR_MS + 4 * MINUTE_MS, BTC.research, "Long", 2)]
    path = tmp_path / "kept.sqlite"
    run(store, signals, T0, T0 + 4 * HOUR_MS, ledger_path=path)
    assert len(Ledger(path).fills()) == 1


def test_trail_after_atr_holds_the_initial_stop_until_profit_reaches_the_threshold(store, tmp_path):
    # Hourly range is ~100 on 50,000 (0.1% each way), so 2.5 ATRs is ~250.
    # Enter Long at T0+2h (~50,000, initial stop ~49,750).
    # At T0+3h price rises +120 (~1.2 ATRs) -> default tightens stop to ~49,870.
    # At T0+3h30m price dips to 49,820 -> default stops out, trail_after_atr=2.0 holds.
    # At T0+5h price rises to 50,350 (~3.5 ATRs >= 2.0) -> trail_after_atr=2.0 now tightens above entry.
    def path(minute: int) -> float:
        t = DAY0 + minute * MINUTE_MS
        if t < T0 + 3 * HOUR_MS:
            return 50_000.0
        if t < T0 + 3 * HOUR_MS + 20 * MINUTE_MS:
            return 50_120.0
        if t < T0 + 4 * HOUR_MS:
            return 49_860.0
        return 50_350.0

    load(store, path, 48)
    signals = [Signal(T0 + h * HOUR_MS + 4 * MINUTE_MS, BTC.research, "Long", 2) for h in (2, 3, 4, 5)]
    plain = run(store, signals, T0, T0 + 6 * HOUR_MS, params=Params(risk=0.002))
    held_ledger = tmp_path / "held.sqlite"
    gated = run(
        store, signals, T0, T0 + 6 * HOUR_MS,
        params=Params(risk=0.002), policy=Policy(trail_after_atr=2.0), ledger_path=held_ledger,
    )
    assert "stop" in [f.reason for f in plain.fills]
    assert "stop" not in [f.reason for f in gated.fills]
    # By hour 5 (+350 > 2.0 * ATR) the gated stop has tightened above the 50,000 entry.
    pos = Ledger(held_ledger).positions()[BTC.swap]
    assert pos.stop > 50_000.0


def test_er_threshold_scales_or_flattens_positions_in_choppy_hours(store):
    # Alternating +1% / -1% every hour: net move over 24h is 0, path is ~24% -> ER == 0.
    def choppy(minute: int) -> float:
        hour = minute // 60
        return 50_000.0 * (1.01 if hour % 2 else 1.0)

    load(store, choppy, 48)
    market = HistoricalOKX(store, T0 + 2 * HOUR_MS + 4 * MINUTE_MS)
    assert efficiency_ratio(market, BTC.swap, T0 + 2 * HOUR_MS + 4 * MINUTE_MS, bars=24) == pytest.approx(0.0)
    # Insufficient history -> None.
    assert efficiency_ratio(market, BTC.swap, DAY0 + 5 * HOUR_MS, bars=24) is None

    signals = [Signal(T0 + 2 * HOUR_MS + 4 * MINUTE_MS, BTC.research, "Short", 2)]
    full = run(store, signals, T0, T0 + 4 * HOUR_MS, params=Params(risk=0.002))
    half = run(
        store, signals, T0, T0 + 4 * HOUR_MS,
        params=Params(risk=0.002), policy=Policy(er_threshold=0.25, er_scale=0.5),
    )
    none = run(
        store, signals, T0, T0 + 4 * HOUR_MS,
        params=Params(risk=0.002), policy=Policy(er_threshold=0.25, er_scale=0.0),
    )
    assert abs(half.fills[0].qty) == pytest.approx(abs(full.fills[0].qty) / 2, abs=2 * SPEC.contract_value)
    assert none.fills == []

    # On a smooth trend (ER == 1.0 >= 0.25), er_threshold=0.25 takes the full position.
    trend_store = HistoryStore(store.path.with_name("trend.sqlite"))
    load(trend_store, price_path(48, trend=0.003), 48)
    trend_market = HistoricalOKX(trend_store, T0 + 2 * HOUR_MS + 4 * MINUTE_MS)
    assert efficiency_ratio(trend_market, BTC.swap, T0 + 2 * HOUR_MS + 4 * MINUTE_MS, bars=24) == pytest.approx(1.0)
    trend_full = replay(trend_store, signals, T0, T0 + 4 * HOUR_MS, watchlist=(BTC,), params=Params(risk=0.002))
    trend_gated = replay(
        trend_store, signals, T0, T0 + 4 * HOUR_MS, watchlist=(BTC,),
        params=Params(risk=0.002), policy=Policy(er_threshold=0.25, er_scale=0.5),
    )
    assert trend_gated.fills[0].qty == trend_full.fills[0].qty


def test_flat_confirm_requires_consecutive_flats_to_close_a_position(store):
    load(store, price_path(72, trend=0.002), 72)
    # Long at h=2, single Flat at h=4, Long again at h=5, then Flat at h=7, missing at h=8, Flat at h=9.
    signals = [
        Signal(T0 + 2 * HOUR_MS + 4 * MINUTE_MS, BTC.research, "Long", 2),
        Signal(T0 + 4 * HOUR_MS + 4 * MINUTE_MS, BTC.research, "Flat", 1),
        Signal(T0 + 5 * HOUR_MS + 4 * MINUTE_MS, BTC.research, "Long", 2),
        Signal(T0 + 7 * HOUR_MS + 4 * MINUTE_MS, BTC.research, "Flat", 1),
        Signal(T0 + 8 * HOUR_MS + 4 * MINUTE_MS, BTC.research, None, None),
        Signal(T0 + 9 * HOUR_MS + 4 * MINUTE_MS, BTC.research, "Flat", 1),
    ]
    plain = run(store, signals, T0, T0 + 11 * HOUR_MS, params=Params(risk=0.002))
    confirmed = run(
        store, signals, T0, T0 + 11 * HOUR_MS,
        params=Params(risk=0.002), policy=Policy(flat_confirm=2),
    )
    # Default flattens at h=4, re-opens at h=5, flattens at h=7 (4 trades).
    assert len(plain.fills) == 4
    # flat_confirm=2 ignores the lone Flat at h=4 and only flattens on the second consecutive Flat at h=9 (2 trades).
    assert [f.ts for f in confirmed.fills] == [
        T0 + 2 * HOUR_MS + 5 * MINUTE_MS,
        T0 + 9 * HOUR_MS + 5 * MINUTE_MS,
    ]
    assert confirmed.fills[0].qty > 0 and confirmed.fills[1].qty < 0


def sig(hour: int, label: str | None, conviction: int | None = 2) -> Signal:
    """BTC's signal four minutes into that hour of the replay; it trades a minute later."""
    return Signal(T0 + hour * HOUR_MS + 4 * MINUTE_MS, BTC.research, label, conviction)


def traded(result) -> list[tuple[float, str, bool]]:
    """Each fill as (hours since T0, reason, bought)."""
    return [(round((f.ts - T0) / HOUR_MS, 2), f.reason, f.qty > 0) for f in result.fills]


def test_entry_min_conviction_gates_what_opens_a_position_and_nothing_else(store):
    load(store, price_path(72, trend=0.002), 72)
    signals = [sig(2, "Long", 1), sig(3, "Long", 2), sig(4, "Long", 1), sig(6, "Short", 1), sig(8, "Short", 2)]
    plain = run(store, signals, T0, T0 + 10 * HOUR_MS, params=Params(risk=0.002))
    gated = run(
        store, signals, T0, T0 + 10 * HOUR_MS,
        params=Params(risk=0.002), policy=Policy(entry_min_conviction=2),
    )
    # Following every signal, the account opens at 02:05 and reverses in one fill at 06:05.
    assert traded(plain) == [(2.08, "trade", True), (6.08, "trade", False)]
    assert plain.fills[1].qty == pytest.approx(-2 * plain.fills[0].qty, abs=2 * SPEC.contract_value)
    # Gated, the weak Long of 02:04 opens nothing and the one of 03:04 does; the weak
    # Long of 04:04 leaves that position alone; the weak Short of 06:04 still closes it
    # but opens no short, which waits for the Short of 08:04.
    assert traded(gated) == [(3.08, "trade", True), (6.08, "trade", False), (8.08, "trade", False)]
    assert gated.fills[1].qty == -gated.fills[0].qty


def test_entry_confirm_waits_for_consecutive_signals_of_one_direction(store):
    load(store, price_path(72, trend=0.002), 72)
    signals = [
        sig(2, "Long"), sig(3, "Flat"), sig(4, "Long"), sig(5, None, None),
        sig(6, "Long"), sig(7, "Long"), sig(9, "Flat"),
    ]
    plain = run(store, signals, T0, T0 + 11 * HOUR_MS, params=Params(risk=0.002))
    twice = run(store, signals, T0, T0 + 11 * HOUR_MS, params=Params(risk=0.002), policy=Policy(entry_confirm=2))
    thrice = run(store, signals, T0, T0 + 11 * HOUR_MS, params=Params(risk=0.002), policy=Policy(entry_confirm=3))
    assert traded(plain) == [
        (2.08, "trade", True), (3.08, "trade", False), (4.08, "trade", True), (9.08, "trade", False),
    ]
    # The Flat of 03:04 starts the count again; the hour without a signal (05:04) does
    # not, so the Longs of 04:04 and 06:04 are two in a row. Once open, the position
    # follows the signals as they are: the first Flat closes it.
    assert traded(twice) == [(6.08, "trade", True), (9.08, "trade", False)]
    assert traded(thrice) == [(7.08, "trade", True), (9.08, "trade", False)]


def test_entry_er_threshold_refuses_entries_in_choppy_hours_but_keeps_a_position_held(store):
    # Up 0.2% an hour until 03:00 of the replay day, then 0.6% up and down in turn: the
    # 24-hour efficiency ratio falls from 1.0 as the choppy hours replace the trend's.
    def turning(minute: int) -> float:
        hour = minute // 60
        if hour < 27:
            return 50_000.0 * (1 + 0.002 * minute / 60)
        return 52_700.0 * (1.006 if hour % 2 else 1.0)

    load(store, turning, 60)
    market = HistoricalOKX(store, T0 + 14 * HOUR_MS + 4 * MINUTE_MS)
    assert efficiency_ratio(market, BTC.swap, T0 + 2 * HOUR_MS + 4 * MINUTE_MS, bars=24) == pytest.approx(1.0)
    assert efficiency_ratio(market, BTC.swap, T0 + 14 * HOUR_MS + 4 * MINUTE_MS, bars=24) < 0.5

    policy = Policy(entry_er_threshold=0.5)
    early = [sig(h, "Long") for h in range(2, 23)]
    plain = run(store, early, T0, T0 + 24 * HOUR_MS, params=Params(risk=0.002))
    gated = run(store, early, T0, T0 + 24 * HOUR_MS, params=Params(risk=0.002), policy=policy)
    # Opened in the trend, the position is the ungated account's to the last fill,
    # however low the ratio falls afterwards.
    assert plain.fills[0].ts == T0 + 2 * HOUR_MS + 5 * MINUTE_MS
    assert [(f.ts, f.qty) for f in gated.fills] == [(f.ts, f.qty) for f in plain.fills]
    assert sum(f.qty for f in gated.fills) > 0

    # The same Longs starting in the chop open nothing.
    late = [s for s in early if s.ts >= T0 + 14 * HOUR_MS]
    assert traded(run(store, late, T0, T0 + 24 * HOUR_MS, params=Params(risk=0.002))) == [(14.08, "trade", True)]
    assert run(store, late, T0, T0 + 24 * HOUR_MS, params=Params(risk=0.002), policy=policy).fills == []


def test_an_entry_gate_applies_again_after_a_stop_out(store):
    load(store, price_path(72, crash_at=30 * 60), 72)
    signals = [sig(2, "Long", 3)] + [sig(h, "Long", 1) for h in range(3, 14)]
    plain = run(store, signals, T0, T0 + 14 * HOUR_MS)
    gated = run(store, signals, T0, T0 + 14 * HOUR_MS, policy=Policy(entry_min_conviction=2))
    # The weak Longs keep the position until the crash stops it out at 06:00; after it
    # they would open a new one, which the gate refuses.
    assert traded(plain)[:3] == [(2.08, "trade", True), (6.0, "stop", False), (6.08, "trade", True)]
    assert traded(gated) == [(2.08, "trade", True), (6.0, "stop", False)]


# -- signal sources and grids ------------------------------------------------

def test_signals_come_from_a_ledger_or_a_json_file(tmp_path):
    ledger = Ledger(tmp_path / "intraday.sqlite")
    ledger.initialize(10_000.0, T0)
    for k, (label, conviction) in enumerate([("Long", 2), (None, None), ("Flat", 1)]):
        ledger.db.execute(
            "INSERT INTO signals (ts, coin, signal, conviction) VALUES (?, ?, ?, ?)",
            (T0 + k * HOUR_MS, BTC.research, label, conviction),
        )
    assert signals_from_ledger(tmp_path / "intraday.sqlite", T0, T0 + 2 * HOUR_MS) == [
        Signal(T0, BTC.research, "Long", 2), Signal(T0 + HOUR_MS, BTC.research, None, None),
    ]
    path = tmp_path / "signals.json"
    path.write_text(json.dumps([{"ts": T0, "coin": "BTC-USD", "signal": "Short", "conviction": 3},
                                {"ts": T0 + 1, "coin": "ETH-USD"}]))
    assert signals_from_json(path) == [Signal(T0, "BTC-USD", "Short", 3), Signal(T0 + 1, "ETH-USD", None, None)]


def test_a_grid_is_every_combination_of_the_specs():
    grid = parse_grid(["stop_mult=2,3", "atr_bars=10"], ["conviction_weights=off,0.5/1/1", "flip_min_conviction=2"])
    assert len(grid) == 4
    assert grid[0] == (Params(stop_mult=2.0, atr_bars=10), Policy(flip_min_conviction=2))
    assert grid[-1] == (Params(stop_mult=3.0, atr_bars=10),
                        Policy(conviction_weights=(0.5, 1.0, 1.0), flip_min_conviction=2))
    assert parse_grid([], []) == [(DEFAULT_PARAMS, Policy())]
    assert describe(*grid[-1]) == "stop_mult=3 atr_bars=10 conviction_weights=0.5/1/1 flip_min_conviction=2"
    assert describe(DEFAULT_PARAMS, Policy()) == "默认"


@pytest.mark.parametrize("params, policies, message", [
    (["slippage=0.1"], [], "unknown param"),
    ([], ["cooldown=4"], "unknown policy knob"),
    (["risk"], [], "expected name=value"),
    ([], ["conviction_weights=1/2"], "w1/w2/w3"),
    ([], ["trail_after_atr=-0.5"], "trail_after_atr"),
    ([], ["er_threshold=1.2"], "er_threshold"),
    ([], ["er_scale=-0.1"], "er_scale"),
    ([], ["er_bars=0"], "er_bars"),
    ([], ["flat_confirm=0"], "flat_confirm"),
    ([], ["entry_min_conviction=-1"], "entry_min_conviction"),
    ([], ["entry_confirm=0"], "entry_confirm"),
    ([], ["entry_er_threshold=1.5"], "entry_er_threshold"),
])
def test_a_bad_grid_spec_is_refused(params, policies, message):
    with pytest.raises(ValueError, match=message):
        parse_grid(params, policies)


def test_new_policy_knobs_parse_and_describe_defaults_cleanly():
    grid = parse_grid(
        [],
        ["trail_after_atr=0,1.5", "er_threshold=0,0.25", "flat_confirm=1,2"],
    )
    assert len(grid) == 8
    assert grid[0] == (DEFAULT_PARAMS, Policy())
    assert describe(*grid[0]) == "默认"
    assert describe(*grid[-1]) == "trail_after_atr=1.5 er_threshold=0.25 flat_confirm=2"


def test_the_entry_gates_parse_and_are_off_by_default():
    grid = parse_grid([], ["entry_min_conviction=0,2", "entry_confirm=1,2", "entry_er_threshold=0,0.15"])
    assert len(grid) == 8
    assert grid[0] == (DEFAULT_PARAMS, Policy())
    assert grid[-1][1] == Policy(entry_min_conviction=2, entry_confirm=2, entry_er_threshold=0.15)
    assert describe(*grid[-1]) == "entry_min_conviction=2 entry_confirm=2 entry_er_threshold=0.15"
    # They emit no label of their own: the engine's weights stay the default ones.
    assert grid[-1][1].labels() == Policy().labels()


# -- signal quality ------------------------------------------------------------

def test_outcomes_are_the_moves_after_each_signal_in_its_direction(store):
    load(store, price_path(72, trend=0.01), 72)  # +1% an hour
    signals = [
        Signal(T0 + 4 * MINUTE_MS, BTC.research, "Long", 2),
        Signal(T0 + HOUR_MS + 4 * MINUTE_MS, BTC.research, "Short", 1),
        Signal(T0 + 2 * HOUR_MS, BTC.research, "Flat", 1),
        Signal(T0 + 3 * HOUR_MS, BTC.research, None, None),
        Signal(T0 + 3 * HOUR_MS, "DOGE-USD", "Long", 3),
    ]
    out = sq.outcomes(store, signals, {BTC.research: BTC.swap})
    assert [o.direction for o in out] == ["Long", "Short", "Flat"]
    price = price_path(72, trend=0.01)
    # Decided at 00:05: the 00:04 candle's close (minute 1,444 since DAY0) against
    # the 01:04 candle's; the Short's move counts the other way.
    assert out[0].price == price(1444)
    assert out[0].returns[1] == pytest.approx(price(1504) / price(1444) - 1)
    assert out[1].returns[1] == pytest.approx(-(price(1564) / price(1504) - 1))
    assert out[2].returns[24] == pytest.approx(price(3000) / price(1560) - 1)
    rows = sq.summarize(sq.directional(out), sq.by_direction)
    assert [(r.group, r.count) for r in rows] == [("Long", 1), ("Short", 1)]
    assert rows[0].hit_rate[4] == 1.0 and rows[1].hit_rate[4] == 0.0
    assert rows[0].mean_bps[1] > 70 and rows[1].median_bps[1] < -70
    by_coin = sq.summarize(out, sq.by_coin)
    assert [(r.group, r.count) for r in by_coin] == [(BTC.research, 3)]
    assert [r.group for r in sq.summarize(out, sq.by_conviction)] == ["信心 2", "信心 1"]


def test_an_outcome_past_the_end_of_the_history_is_unknown(store):
    load(store, price_path(26), 26)
    out = sq.outcomes(store, [Signal(T0 + HOUR_MS, BTC.research, "Long", 2)], {BTC.research: BTC.swap})
    assert out[0].returns[1] is not None and out[0].returns[24] is None
    row = sq.summarize(out, sq.by_direction)[0]
    assert row.hit_rate[24] is None and row.mean_bps[24] is None


def test_flips_count_the_changes_of_mind():
    series = ["Long", "Long", None, "Short", "Flat", "Long", "Long", "Long"]
    signals = [Signal(T0 + k * HOUR_MS, BTC.research, s, 2) for k, s in enumerate(series)]
    (row,) = sq.flips(signals)
    assert (row.hours, row.long, row.short, row.flat, row.missing) == (8, 5, 1, 1, 1)
    assert row.reversals == 2       # Long -> Short, then Short -> Long (Flat between not counted)
    assert row.changes == 3         # Long|Short|Flat|Long
    assert row.mean_run == pytest.approx(7 / 4)


# -- the command line --------------------------------------------------------

@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADER_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TRADER_CAPITAL", raising=False)
    from trader.evaluation.cli import store_path
    store = HistoryStore(store_path(Settings.from_env()))
    for coin in WATCHLIST:
        load(store, price_path(72, trend=0.002), 72, inst=coin.swap)
    signals = [
        {"ts": T0 + 2 * HOUR_MS + 4 * MINUTE_MS, "coin": c.research, "signal": "Long", "conviction": 2}
        for c in WATCHLIST
    ] + [{"ts": T0 + 10 * HOUR_MS + 4 * MINUTE_MS, "coin": WATCHLIST[0].research, "signal": "Flat", "conviction": 1}]
    (tmp_path / "signals.json").write_text(json.dumps(signals))
    return tmp_path


def test_the_replay_command_runs_a_grid_from_the_cache_and_writes_the_report(home):
    from typer.testing import CliRunner

    from trader.__main__ import app

    out = home / "report.md"
    result = CliRunner().invoke(app, [
        "evaluate", "replay", "2026-01-02", "2026-01-02T12:00", "--no-fetch",
        "--signals-json", str(home / "signals.json"), "--out", str(out),
        "--param", "stop_mult=2.5,3", "--policy", "conviction_weights=off,0.5/1/1",
    ])
    assert result.exit_code == 0, result.output
    text = out.read_text()
    assert text.startswith("# 日内规则层回放")
    assert "4 个配置" in text and "| 默认 |" in text and "stop_mult=3 conviction_weights=0.5/1/1" in text
    assert text.count("\n| ") >= 5  # the header, the rule and four configurations


def test_the_signals_command_reports_the_signal_quality(home):
    from typer.testing import CliRunner

    from trader.__main__ import app

    out = home / "signals.md"
    result = CliRunner().invoke(app, [
        "evaluate", "signals", "2026-01-02", "2026-01-03", "--no-fetch",
        "--signals-json", str(home / "signals.json"), "--out", str(out),
    ])
    assert result.exit_code == 0, result.output
    text = out.read_text()
    assert "## 按方向" in text and "| Long | 3 |" in text and "| Flat | 1 |" in text
    assert "## 换向" in text and f"| {WATCHLIST[0].research} | 2 |" in text


def test_a_period_without_signals_fails_the_replay_command(home):
    from typer.testing import CliRunner

    from trader.__main__ import app

    result = CliRunner().invoke(app, [
        "evaluate", "replay", "2026-01-02T20:00", "2026-01-02T22:00", "--no-fetch",
        "--signals-json", str(home / "signals.json"),
    ])
    assert result.exit_code == 1 and "没有信号" in result.output
    bad = CliRunner().invoke(app, ["evaluate", "replay", "2026-01-02", "2026-01-01", "--no-fetch"])
    assert bad.exit_code != 0 and "结束时间要晚于开始时间" in bad.output
