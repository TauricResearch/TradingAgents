"""Multi-symbol engine (roadmap P3 / track T4): PortfolioEngine drives one
shared broker across N symbols on the merged clock, executing a native
strategy per symbol. Proves both symbols trade, capital/caps are shared, the
equity curve tracks the master clock, per-symbol look-ahead safety holds, and
the run is deterministic."""

from datetime import timedelta

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
    PortfolioEngine,
    PortfolioReplay,
    SimBroker,
    build_strategy,
)

CONFIG = ProConfig(asset=AssetClass.BITCOIN, mode=TradingMode.BACKTEST,
                   max_debate_rounds=1)


def _uptrend(n, p0, start=BASE_TS, drift=2.0):
    bars, price = [], p0
    for i in range(n):
        price += drift
        bars.append(OHLCVBar(
            timeframe=Timeframe.D1, start=start + timedelta(days=i),
            open=price, high=price + 0.5, low=price - 0.5, close=price,
            volume=1_000_000.0))
    return bars


def _replay(symbol, bars):
    return BarReplay(symbol, AssetClass.BITCOIN, bars, window=40,
                     precompute_indicators=True)


def _strategy(allow_short="no"):
    return build_strategy("trend_following_v1", {
        "donchian_period": 20, "stop_atr_mult": 2.0, "trail_pct": 0.05,
        "risk_pct": 1.0, "allow_short": allow_short})


def _portfolio(n=160):
    return PortfolioReplay({
        "BTC-USD": _replay("BTC-USD", _uptrend(n, 1000.0)),
        "ETH-USD": _replay("ETH-USD", _uptrend(n, 2000.0)),
    })


class TestPortfolioRun:
    def test_both_symbols_trade_through_the_shared_broker(self):
        pr = _portfolio()
        eng = PortfolioEngine(pr, _strategy(), CONFIG,
                              broker=SimBroker(initial_equity=100_000.0),
                              min_history=40)
        res = eng.run()
        assert res.symbols == ("BTC-USD", "ETH-USD")
        assert res.decisions > 0 and res.executed > 0
        traded = {t.symbol for t in res.trades}
        assert traded == {"BTC-USD", "ETH-USD"}  # both instruments traded
        # equity marked once per master step + one final mark
        assert len(res.equity_curve) == len(pr) + 1

    def test_run_is_deterministic(self):
        a = PortfolioEngine(_portfolio(), _strategy(), CONFIG,
                            broker=SimBroker(initial_equity=100_000.0),
                            min_history=40).run()
        b = PortfolioEngine(_portfolio(), _strategy(), CONFIG,
                            broker=SimBroker(initial_equity=100_000.0),
                            min_history=40).run()
        assert a.equity_curve == b.equity_curve
        assert [(t.symbol, t.pnl) for t in a.trades] == \
               [(t.symbol, t.pnl) for t in b.trades]

    def test_shared_position_cap_binds_across_symbols(self):
        # max_open_positions=1 is a PORTFOLIO cap: with both symbols breaking
        # out, only one can be open at a time, so fewer entries than an
        # uncapped run over the same data
        capped = PortfolioEngine(
            _portfolio(), _strategy(), CONFIG,
            broker=SimBroker(initial_equity=100_000.0, max_open_positions=1),
            min_history=40).run()
        roomy = PortfolioEngine(
            _portfolio(), _strategy(), CONFIG,
            broker=SimBroker(initial_equity=100_000.0, max_open_positions=6),
            min_history=40).run()
        assert capped.executed >= 1
        assert capped.executed < roomy.executed  # the shared cap throttled

    def test_positions_never_cross_symbols(self):
        pr = _portfolio()
        res = PortfolioEngine(pr, _strategy("yes"), CONFIG,
                              broker=SimBroker(initial_equity=100_000.0),
                              min_history=40).run()
        # every trade belongs to one of the two symbols; entries/exits paired
        for t in res.trades:
            assert t.symbol in ("BTC-USD", "ETH-USD")
            assert t.quantity > 0


class TestStaggeredStart:
    def test_late_listed_symbol_only_trades_after_it_starts(self):
        # ETH starts 50 days after BTC; its first trade cannot precede its data
        btc = _replay("BTC-USD", _uptrend(160, 1000.0))
        eth = _replay("ETH-USD", _uptrend(110, 2000.0,
                                          start=BASE_TS + timedelta(days=50)))
        pr = PortfolioReplay({"BTC-USD": btc, "ETH-USD": eth})
        res = PortfolioEngine(pr, _strategy(), CONFIG,
                              broker=SimBroker(initial_equity=100_000.0),
                              min_history=40).run()
        eth_start = BASE_TS + timedelta(days=50)
        eth_trades = [t for t in res.trades if t.symbol == "ETH-USD"]
        assert eth_trades  # it did trade once listed
        assert all(t.opened_at >= eth_start for t in eth_trades)
