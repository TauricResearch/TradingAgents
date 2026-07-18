"""Trader-review G1/G2/G3: per-symbol tickets, open-risk view, regime API."""

import pytest

fastapi = pytest.importorskip("fastapi")

from datetime import datetime, timedelta, timezone  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from tests.test_pro_pipeline_graph import CONFIG, FakePipelineLLM, pipeline_snapshot  # noqa: E402
from tradingagents.contracts import OHLCVBar, Timeframe  # noqa: E402
from tradingagents.pro.dashboard.app import DashboardState, create_app  # noqa: E402
from tradingagents.pro.dashboard.service import open_positions_view  # noqa: E402
from tradingagents.pro.dashboard.ticker import TickCache  # noqa: E402
from tradingagents.pro.memory import ProMemory  # noqa: E402

BASE = datetime(2026, 7, 1, tzinfo=timezone.utc)


class FakeAdapter:
    def __init__(self, entries):
        self._entries = entries

    def positions(self):
        from tradingagents.pro.execution.interface import BrokerPosition

        return [
            BrokerPosition(symbol=s, side="BUY" if q > 0 else "SELL",
                           quantity=abs(q), avg_price=price)
            for s, (q, price) in self._entries.items()
        ]


class FakeRouter:
    def __init__(self, book, entries):
        self.local_book = book
        self.adapter = FakeAdapter(entries)


class FakeMarketData:
    def __init__(self, closes):
        self._closes = closes
        self.registry = {s: object() for s in closes}

    def get_bars(self, symbol, timeframe, limit=300):
        close = self._closes[symbol]
        return [OHLCVBar(timeframe=Timeframe.D1, start=BASE + timedelta(days=i),
                         open=close, high=close, low=close, close=close,
                         volume=100.0)
                for i in range(min(limit, 5))]


class TestOpenPositionsView:
    def test_open_stop_from_opening_trade(self):
        from tradingagents.pro.memory import MemoryKind, MemoryRecord, ProMemory

        memory = ProMemory()
        # an open XAUUSD trade (no OUTCOME) carries the stop; a closed one
        # (has an OUTCOME) must not leak its stop into the open view
        memory._add(MemoryRecord(
            kind=MemoryKind.TRADE, text="open", symbol="XAUUSD",
            payload={"stop_loss": 4190.5}))
        closed = memory._add(MemoryRecord(
            kind=MemoryKind.TRADE, text="closed", symbol="BTC-USD",
            payload={"stop_loss": 61000.0}))
        memory._add(MemoryRecord(
            kind=MemoryKind.OUTCOME, text="o", symbol="BTC-USD",
            ref_id=closed.id, payload={"pnl": 1.0}))
        router = FakeRouter({"XAUUSD": -2.0, "BTC-USD": 0.5},
                            {"XAUUSD": (-2.0, 4000.0), "BTC-USD": (0.5, 62000.0)})
        positions, _ = open_positions_view(router, 100_000.0, memory=memory)
        by = {p["symbol"]: p for p in positions}
        assert by["XAUUSD"]["stop_price"] == pytest.approx(4190.5)
        assert by["BTC-USD"]["stop_price"] is None  # closed trade, no leak

    def test_live_mark_long_and_short(self):
        ticks = TickCache()
        ticks.put("XAUUSD", 3900.0, "t")
        ticks.put("BTC-USD", 63000.0, "t")
        router = FakeRouter({"XAUUSD": -2.0, "BTC-USD": 0.5},
                            {"XAUUSD": (-2.0, 4000.0), "BTC-USD": (0.5, 62000.0)})
        positions, total = open_positions_view(router, 100_000.0, ticks=ticks)
        by = {p["symbol"]: p for p in positions}
        # short 2 @ 4000 marked 3900 -> +200 unrealized
        assert by["XAUUSD"]["unrealized_pnl"] == pytest.approx(200.0)
        assert by["XAUUSD"]["mark_source"] == "live"
        assert by["XAUUSD"]["exposure_pct"] == pytest.approx(7.8)
        # long 0.5 @ 62000 marked 63000 -> +500
        assert by["BTC-USD"]["unrealized_pnl"] == pytest.approx(500.0)
        assert total == pytest.approx(700.0)

    def test_eod_fallback_labeled(self):
        router = FakeRouter({"XAUUSD": 1.0}, {"XAUUSD": (1.0, 4000.0)})
        md = FakeMarketData({"XAUUSD": 4050.0})
        positions, total = open_positions_view(router, 100_000.0, marketdata=md)
        [pos] = positions
        assert pos["mark_source"] == "eod"
        assert pos["unrealized_pnl"] == pytest.approx(50.0)

    def test_no_mark_never_fabricates(self):
        router = FakeRouter({"XAUUSD": 1.0}, {"XAUUSD": (1.0, 4000.0)})
        positions, total = open_positions_view(router, None)
        [pos] = positions
        assert pos["mark_source"] == "entry"
        assert pos["mark_price"] == 4000.0
        assert pos["unrealized_pnl"] is None and total is None
        assert pos["exposure_pct"] is None  # no equity -> no percentage


@pytest.fixture()
def two_symbol_state():
    state = DashboardState(memory=ProMemory())
    state.recorder.record_run(
        FakePipelineLLM(), CONFIG, pipeline_snapshot(), memory=state.memory
    )
    state.recorder.record_run(
        FakePipelineLLM(), CONFIG, pipeline_snapshot(symbol="BTC-USD"),
        memory=state.memory,
    )
    return state


class TestPerSymbolTickets:
    def test_latest_for_symbol_survives_other_symbol_run(self, two_symbol_state):
        client = TestClient(create_app(two_symbol_state))
        # overall latest is the BTC run…
        latest = client.get("/api/recommendation/latest").json()
        assert latest["symbol"] == "BTC-USD"
        # …but the gold ticket is still one query away (G1)
        gold = client.get("/api/recommendation/latest",
                          params={"symbol": "XAUUSD"}).json()
        assert gold["symbol"] == "XAUUSD"
        assert gold["run_id"] == two_symbol_state.runs[0].run_id
        assert gold["entry_price"] is not None

    def test_unknown_symbol_is_honest(self, two_symbol_state):
        client = TestClient(create_app(two_symbol_state))
        view = client.get("/api/recommendation/latest",
                          params={"symbol": "ETH-USD"}).json()
        assert view == {"status": "no recommendation"}

    def test_run_ticket_endpoint(self, two_symbol_state):
        client = TestClient(create_app(two_symbol_state))
        run_id = two_symbol_state.runs[0].run_id
        ticket = client.get(f"/api/runs/{run_id}/recommendation").json()
        assert ticket["run_id"] == run_id
        assert ticket["symbol"] == "XAUUSD"
        assert ticket["take_profits"], "full ladder served for historical runs"
        assert client.get("/api/runs/nope/recommendation").status_code == 404


class TestRegimeEndpoint:
    def test_per_symbol_regime(self):
        state = DashboardState(memory=ProMemory())
        state.marketdata = FakeMarketData({"XAUUSD": 4000.0, "BTC-USD": 62000.0})
        client = TestClient(create_app(state))
        payload = client.get("/api/regime").json()
        assert set(payload["symbols"]) == {"XAUUSD", "BTC-USD"}
        for sym in payload["symbols"].values():
            assert sym["regime"] is not None
        assert payload["session"]

    def test_degraded_vendor_is_null_not_guess(self):
        state = DashboardState(memory=ProMemory())

        class Broken(FakeMarketData):
            def get_bars(self, *a, **k):
                raise RuntimeError("vendor down")

        state.marketdata = Broken({"XAUUSD": 0.0})
        client = TestClient(create_app(state))
        payload = client.get("/api/regime").json()
        assert payload["symbols"]["XAUUSD"]["regime"] is None
