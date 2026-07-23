"""Portfolio replay (roadmap P3 / track T4): the k-way timestamp merge that
puts per-symbol BarReplays on one master clock. Verifies the merge, the
active-symbol set, as-of marking, per-symbol look-ahead safety, and that
heterogeneous timeframes / late-listed symbols compose correctly."""

from datetime import timedelta

import pytest

from tests.pro_fakes import BASE_TS
from tradingagents.contracts import AssetClass, OHLCVBar, Timeframe
from tradingagents.pro.backtest import BarReplay, PortfolioReplay


def _bars(n, tf=Timeframe.D1, start=BASE_TS, step=timedelta(days=1), p0=100.0):
    bars, price = [], p0
    for i in range(n):
        price += 0.5
        bars.append(OHLCVBar(
            timeframe=tf, start=start + step * i,
            open=price, high=price + 1.0, low=price - 1.0, close=price,
            volume=1000.0 + i))
    return bars


def _replay(symbol, bars, asset=AssetClass.BITCOIN):
    return BarReplay(symbol, asset, bars, window=10)


class TestMerge:
    def test_timeline_is_sorted_union_without_duplicates(self):
        # BTC daily and ETH daily on the same grid → identical timeline
        pr = PortfolioReplay({
            "BTC": _replay("BTC", _bars(5)),
            "ETH": _replay("ETH", _bars(5)),
        })
        assert pr.symbols == ("BTC", "ETH")
        assert len(pr) == 5  # union of shared timestamps, deduped
        assert pr.timeline == sorted(pr.timeline)

    def test_heterogeneous_timeframes_merge_onto_finer_clock(self):
        # a 4-bar daily series + a 12-bar 4h series over ~2 days
        daily = _replay("BTC", _bars(4, tf=Timeframe.D1, step=timedelta(days=1)))
        h4 = _replay("ETH", _bars(12, tf=Timeframe.H4, step=timedelta(hours=4)))
        pr = PortfolioReplay({"BTC": daily, "ETH": h4})
        # the master clock is the union — at least the 12 4h points
        assert len(pr) >= 12
        assert pr.timeline == sorted(set(pr.timeline))


class TestActiveAndAsOf:
    def test_active_symbols_are_those_closing_on_the_step(self):
        # BTC on even days, ETH on odd days (offset by one) → they alternate
        btc = _replay("BTC", _bars(4, step=timedelta(days=2)))            # d0,2,4,6
        eth = _replay("ETH", _bars(4, start=BASE_TS + timedelta(days=1),
                                   step=timedelta(days=2)))               # d1,3,5,7
        pr = PortfolioReplay({"BTC": btc, "ETH": eth})
        # every step has exactly one active symbol (no shared timestamps)
        for step in range(len(pr)):
            active = pr.active_symbols_at(step)
            assert len(active) == 1

    def test_local_index_is_as_of_never_future(self):
        # ETH starts a day after BTC; before ETH's first bar it is absent
        btc = _replay("BTC", _bars(4))                                    # d0..d3
        eth = _replay("ETH", _bars(3, start=BASE_TS + timedelta(days=1))) # d1..d3
        pr = PortfolioReplay({"BTC": btc, "ETH": eth})
        # step 0 = BASE_TS: ETH has not started
        assert pr.local_index("ETH", 0) is None
        assert pr.bar_at("ETH", 0) is None
        assert pr.snapshot_at("ETH", 0) is None
        # BTC exists from step 0
        assert pr.local_index("BTC", 0) == 0

    def test_slow_symbol_marks_against_its_last_closed_bar(self):
        # BTC daily, ETH every 3 days — between ETH bars, bar_at returns its
        # most recent CLOSED bar (never the upcoming one)
        btc = _replay("BTC", _bars(9))                                    # d0..d8
        eth = _replay("ETH", _bars(3, step=timedelta(days=3)))            # d0,3,6
        pr = PortfolioReplay({"BTC": btc, "ETH": eth})
        # find the step for day 4 (BTC bar), ETH's last close was day 3
        step_d4 = pr.timeline.index(BASE_TS + timedelta(days=4))
        eth_bar = pr.bar_at("ETH", step_d4)
        assert eth_bar is not None
        assert eth_bar.start == BASE_TS + timedelta(days=3)  # not day 6
        assert "ETH" not in pr.active_symbols_at(step_d4)     # no fresh ETH bar

    def test_snapshot_is_per_symbol_lookahead_safe(self):
        btc = _replay("BTC", _bars(6))
        eth = _replay("ETH", _bars(6))
        pr = PortfolioReplay({"BTC": btc, "ETH": eth})
        step = 4
        ts = pr.timestamp_at(step)
        snap = pr.snapshot_at("BTC", step)
        assert snap is not None
        assert snap.symbol == "BTC"
        assert snap.as_of <= ts
        assert all(b.start <= ts for b in snap.bars)  # no future bars leak in


class TestConstruction:
    def test_accepts_a_sequence_and_keys_by_symbol(self):
        pr = PortfolioReplay([_replay("BTC", _bars(4)), _replay("ETH", _bars(4))])
        assert set(pr.symbols) == {"BTC", "ETH"}
        assert pr.replay("BTC").symbol == "BTC"

    def test_empty_and_duplicate_symbols_rejected(self):
        with pytest.raises(ValueError, match="at least one"):
            PortfolioReplay([])
        with pytest.raises(ValueError, match="duplicate"):
            PortfolioReplay([_replay("BTC", _bars(4)), _replay("BTC", _bars(4))])
