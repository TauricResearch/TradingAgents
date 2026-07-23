"""Multi-timeframe aggregation (roadmap P3 / track T4): LTF→HTF bucketing, the
look-ahead-safe "only closed HTF bars" rule, and the engine exposing completed
HTF snapshots to a strategy via StrategyContext.htf."""

from datetime import timedelta

import pytest

from tests.pro_fakes import BASE_TS
from tradingagents.contracts import (
    AssetClass,
    OHLCVBar,
    ProConfig,
    Timeframe,
    TradingMode,
)
from tradingagents.pro.backtest import (
    BarReplay,
    MultiTimeframeReplay,
    aggregate_htf,
    htf_bars_as_of,
)


def _hourly(hours, start=BASE_TS, p0=100.0):
    bars, price = [], p0
    for i in range(hours):
        price += 0.25
        bars.append(OHLCVBar(
            timeframe=Timeframe.H1, start=start + timedelta(hours=i),
            open=price, high=price + 0.5, low=price - 0.5, close=price,
            volume=100.0))
    return bars


class TestAggregate:
    def test_hourly_rolls_up_into_daily_ohlcv(self):
        bars = _hourly(48)  # exactly two calendar days
        daily = aggregate_htf(bars, Timeframe.D1)
        assert len(daily) == 2
        d0 = daily[0]
        assert d0.timeframe == Timeframe.D1
        assert d0.start == BASE_TS.replace(hour=0, minute=0, second=0, microsecond=0)
        assert d0.open == bars[0].open           # first hour's open
        assert d0.close == bars[23].close        # last hour's close
        assert d0.high == max(b.high for b in bars[:24])
        assert d0.low == min(b.low for b in bars[:24])
        assert d0.volume == sum(b.volume for b in bars[:24])

    def test_hourly_into_4h_buckets_on_aligned_boundaries(self):
        bars = _hourly(12)  # 00:00..11:00 → three 4h buckets
        h4 = aggregate_htf(bars, Timeframe.H4)
        starts = [b.start.hour for b in h4]
        assert starts == [0, 4, 8]

    def test_rejects_non_coarser_htf(self):
        with pytest.raises(ValueError, match="coarser"):
            aggregate_htf(_hourly(10), Timeframe.H1)  # same tf
        with pytest.raises(ValueError, match="coarser"):
            aggregate_htf(_hourly(10), Timeframe.M15)  # finer


class TestLookaheadSafety:
    def test_only_fully_closed_htf_bars_are_visible(self):
        bars = _hourly(48)
        daily = aggregate_htf(bars, Timeframe.D1)
        # mid day 0 → NO daily bar has closed yet
        assert htf_bars_as_of(daily, BASE_TS + timedelta(hours=12)) == []
        # mid day 1 → only day 0 has closed (day 1 still forming)
        mid_d1 = htf_bars_as_of(daily, BASE_TS + timedelta(days=1, hours=12))
        assert [b.start.day for b in mid_d1] == [BASE_TS.day]
        # after day 1 fully elapses → both visible
        after = htf_bars_as_of(daily, BASE_TS + timedelta(days=2))
        assert len(after) == 2

    def test_replay_snapshot_never_leaks_a_forming_htf_bar(self):
        base = BarReplay("BTC-USD", AssetClass.BITCOIN, _hourly(72), window=24)
        mtf = MultiTimeframeReplay(base, [Timeframe.D1])
        # at an hour within day 1, the HTF snapshot's last bar must be day 0's
        i = next(k for k, b in enumerate(base.bars)
                 if b.start >= BASE_TS + timedelta(days=1, hours=6))
        snap = mtf.htf_snapshot(i, Timeframe.D1)
        assert snap is not None
        assert all(b.start + timedelta(days=1) <= base.bars[i].start
                   for b in snap.bars)  # every HTF bar fully closed by now


class TestEngineWiring:
    def test_context_htf_is_populated_and_lookahead_safe(self):
        seen = {}

        class Probe:
            id = "probe"
            params: dict = {}

            def on_start(self, ctx): ...

            def on_bar(self, ctx):
                # record the HTF daily snapshot's last-bar time vs now
                d = ctx.htf.get(Timeframe.D1)
                if d is not None:
                    seen[ctx.snapshot.as_of] = d.bars[-1].start
                return []

            def on_fill(self, fill): ...

            def on_stop(self, ctx): ...

        from tradingagents.pro.backtest.engine import BacktestEngine

        base = BarReplay("BTC-USD", AssetClass.BITCOIN, _hourly(96), window=24)
        config = ProConfig(asset=AssetClass.BITCOIN, mode=TradingMode.BACKTEST,
                           max_debate_rounds=1)
        BacktestEngine(None, config, base, strategy=Probe(), min_history=24,
                       htf_timeframes=[Timeframe.D1]).run()
        assert seen  # the strategy saw HTF snapshots
        # every HTF daily bar shown had already closed strictly before "now"
        for now, htf_last in seen.items():
            assert htf_last + timedelta(days=1) <= now
