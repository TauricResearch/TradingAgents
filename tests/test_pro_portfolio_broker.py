"""Symbol-aware broker marking + management (roadmap P3 / track T4): the
additive SimBroker methods the multi-symbol engine needs — equity_marks /
gross_notional_marks (each position marked at its own symbol's price) and the
symbol filter on process_bar / close_all. The single-symbol path (symbol=None)
stays byte-identical, covered by the existing order-book suite."""

from datetime import timedelta

from tests.pro_fakes import BASE_TS
from tradingagents.contracts import OHLCVBar, Timeframe
from tradingagents.pro.backtest import PendingOrder, SimBroker
from tradingagents.pro.backtest.costs import CommissionModel, LiquidityModel, SlippageModel


def _bar(open_, high, low, close, day=0) -> OHLCVBar:
    return OHLCVBar(timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=day),
                    open=open_, high=high, low=low, close=close, volume=1_000_000.0)


def _broker() -> SimBroker:
    return SimBroker(slippage=SlippageModel(bps=0), commission=CommissionModel(rate_bps=0),
                     liquidity=LiquidityModel(max_participation=1.0),
                     initial_equity=1_000_000.0)


def _open(broker, oid, symbol, side, qty, entry_day, entry_price, stop):
    """Fill a market order for `symbol` at `entry_price` (bar open). The engine
    is stop-based, so every entry carries a protective stop."""
    broker.submit(PendingOrder(id=oid, kind="market", side=side, quantity=qty,
                               stop_loss=stop, symbol=symbol))
    broker.match_pending(_bar(entry_price, entry_price + 1, entry_price - 1,
                              entry_price, day=entry_day), entry_day)


class TestPortfolioMarking:
    def test_equity_marks_prices_each_position_by_its_symbol(self):
        b = _broker()
        _open(b, "btc", "BTC-USD", "BUY", 10, 1, 100.0, stop=1.0)   # far stops:
        _open(b, "eth", "ETH-USD", "BUY", 5, 2, 200.0, stop=1.0)    # never hit
        assert b.open_count == 2
        # BTC +10/unit (×10 = +100), ETH -10/unit (×5 = -50) → net +50
        eq = b.equity_marks({"BTC-USD": 110.0, "ETH-USD": 190.0})
        assert eq == 1_000_000.0 + 100.0 - 50.0

    def test_symbol_absent_from_marks_is_held_at_entry(self):
        b = _broker()
        _open(b, "btc", "BTC-USD", "BUY", 10, 1, 100.0, stop=1.0)
        _open(b, "eth", "ETH-USD", "BUY", 5, 2, 200.0, stop=1.0)
        # only BTC priced → ETH contributes zero unrealized
        assert b.equity_marks({"BTC-USD": 110.0}) == 1_000_000.0 + 100.0

    def test_gross_notional_marks_sums_across_symbols(self):
        b = _broker()
        _open(b, "btc", "BTC-USD", "BUY", 10, 1, 100.0, stop=1.0)
        _open(b, "eth", "ETH-USD", "BUY", 5, 2, 200.0, stop=1.0)
        assert b.gross_notional_marks({"BTC-USD": 110.0, "ETH-USD": 190.0}) \
            == 110.0 * 10 + 190.0 * 5


class TestSymbolScopedManagement:
    def test_process_bar_only_manages_the_named_symbol(self):
        b = _broker()
        _open(b, "btc", "BTC-USD", "BUY", 10, 1, 100.0, stop=95.0)
        _open(b, "eth", "ETH-USD", "BUY", 5, 2, 200.0, stop=190.0)
        # each symbol is managed against ITS OWN bar. A benign ETH bar first:
        eth_bar = _bar(200, 202, 195, 200, day=3)   # low 195 > ETH stop 190
        closed = b.process_bar(eth_bar, symbol="ETH-USD")
        assert closed == []               # ETH survives
        assert b.open_count == 2          # BTC not in scope, untouched
        # BTC's own bar breaks its stop
        btc_bar = _bar(100, 101, 90, 100, day=3)    # low 90 <= BTC stop 95
        closed = b.process_bar(btc_bar, symbol="BTC-USD")
        assert len(closed) == 1 and closed[0].symbol == "BTC-USD"
        assert b.open_count == 1

    def test_close_all_can_target_a_single_symbol(self):
        b = _broker()
        _open(b, "btc", "BTC-USD", "BUY", 10, 1, 100.0, stop=1.0)
        _open(b, "eth", "ETH-USD", "BUY", 5, 2, 200.0, stop=1.0)
        closed = b.close_all(_bar(210, 211, 209, 210, day=4), symbol="ETH-USD")
        assert len(closed) == 1 and closed[0].symbol == "ETH-USD"
        assert b.open_count == 1 and "btc" in b.positions

    def test_process_bar_default_still_manages_all(self):
        # symbol=None keeps the single-symbol contract: both same-symbol
        # positions managed together
        b = _broker()
        _open(b, "a", "BTC-USD", "BUY", 10, 1, 100.0, stop=95.0)
        _open(b, "c", "BTC-USD", "BUY", 8, 2, 100.0, stop=95.0)
        closed = b.process_bar(_bar(100, 101, 90, 100, day=3))
        assert len(closed) == 2  # both stopped, no symbol filter
