"""Interactive backtest job: paging, request validation, streaming worker,
run store, and the async endpoints."""

import threading
import time
from types import SimpleNamespace

import pytest

from tests.pro_fakes import make_bars
from tradingagents.contracts import Timeframe
from tradingagents.pro.dashboard import backtest_job as btjob
from tradingagents.pro.dashboard.backtest_store import BacktestRunStore
from tradingagents.pro.dashboard.marketdata import MAX_LIMIT
from tradingagents.pro.memory import ProMemory

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from tradingagents.pro.dashboard.app import DashboardState, create_app  # noqa: E402

# --- stubs ------------------------------------------------------------------


class _Bus:
    """Broadcaster stub recording (type, data) publishes."""

    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def publish(self, type_, data):
        self.events.append((type_, dict(data)))

    def types(self):
        return [t for t, _ in self.events]


class _StubMarket:
    def __init__(self, bars, timeframes=(Timeframe.D1,)):
        self._bars = bars
        self._tf = timeframes

    def spec(self, symbol):
        return SimpleNamespace(timeframes=self._tf)

    def get_bars(self, symbol, timeframe, limit=1000, end=None):
        limit = min(limit, MAX_LIMIT)
        pool = [b for b in self._bars if end is None or b.start < end]
        return pool[-limit:]


def _state(bars, tmp_path, timeframes=(Timeframe.D1,)):
    return DashboardState(
        memory=ProMemory(),
        marketdata=_StubMarket(bars, timeframes),
        broadcaster=_Bus(),
        backtest_runs=BacktestRunStore(tmp_path / "runs.json"),
    )


# --- duration → bars --------------------------------------------------------


def test_bars_for_duration_scales_with_timeframe():
    assert btjob.bars_for_duration("7D", Timeframe.D1) == 7 + btjob.MIN_HISTORY
    assert btjob.bars_for_duration("1D", Timeframe.H1) == 24 + btjob.MIN_HISTORY
    # sub-hour long window is large (paged later)
    assert btjob.bars_for_duration("1Y", Timeframe.H1) > 8000


# --- paging -----------------------------------------------------------------


def test_fetch_window_pages_beyond_the_request_cap():
    market = _StubMarket(make_bars(n=1500))
    bars = btjob.fetch_window(market, "XAUUSD", Timeframe.D1, 1300)
    assert len(bars) == 1300
    starts = [b.start for b in bars]
    assert starts == sorted(starts)  # oldest → newest
    assert len(set(starts)) == 1300  # no duplicates across pages


def test_fetch_window_stops_when_history_exhausted():
    market = _StubMarket(make_bars(n=120))
    bars = btjob.fetch_window(market, "XAUUSD", Timeframe.D1, 500)
    assert len(bars) == 120  # can't fabricate more than exists


# --- request validation -----------------------------------------------------


def test_resolve_rejects_unknown_symbol():
    market = _StubMarket(make_bars(n=80))
    with pytest.raises(ValueError, match="unknown symbol"):
        btjob.resolve_request(market, {"symbol": "NOPE", "timeframe": "1d",
                                       "duration": "7D"})


def test_resolve_rejects_unsupported_timeframe():
    market = _StubMarket(make_bars(n=80), timeframes=(Timeframe.D1,))
    with pytest.raises(ValueError, match="does not support"):
        btjob.resolve_request(market, {"symbol": "XAUUSD", "timeframe": "1h",
                                       "duration": "7D"})


def test_resolve_llm_requires_cost_confirmation():
    market = _StubMarket(make_bars(n=80), timeframes=tuple(Timeframe))
    with pytest.raises(btjob._CostConfirmationRequired) as exc:
        btjob.resolve_request(market, {"symbol": "BTC-USD", "timeframe": "1h",
                                       "duration": "1Y", "use_llm": True})
    assert exc.value.estimate["decisions"] == btjob.MAX_LLM_DECISIONS


def test_resolve_llm_caps_decisions_when_confirmed():
    market = _StubMarket(make_bars(n=80), timeframes=tuple(Timeframe))
    resolved = btjob.resolve_request(
        market, {"symbol": "BTC-USD", "timeframe": "1h", "duration": "1Y",
                 "use_llm": True, "confirm_cost": True})
    assert resolved["bars"] == btjob.MIN_HISTORY + btjob.MAX_LLM_DECISIONS


# --- streaming worker (deterministic, offline) ------------------------------


def test_run_job_streams_progress_trades_and_persists(tmp_path):
    state = _state(make_bars(n=140), tmp_path)
    job = btjob.new_job({"symbol": "XAUUSD", "timeframe": "1d", "duration": "30D"})
    state.backtest_job = job

    btjob.run_job(state, job, job.params)

    assert job.status == "done", job.error
    types = state.broadcaster.types()
    assert "backtest_progress" in types
    assert types[-1] == "backtest_done"
    # rising synthetic market → the scripted pipeline buys and trades close
    assert job.closed_trades
    assert "backtest_trade" in types
    assert state.backtest is not None
    saved = state.backtest_runs.list()
    assert len(saved) == 1 and saved[0]["symbol"] == "XAUUSD"
    assert job.result["provider"] == "deterministic"


# --- run store --------------------------------------------------------------


def test_run_store_ring_keeps_newest(tmp_path):
    store = BacktestRunStore(tmp_path / "r.json", max_runs=3)
    for i in range(5):
        store.save({"id": f"r{i}", "created_at": str(i),
                    "view": {"symbol": "BTC-USD"}})
    listed = store.list()
    assert [r["id"] for r in listed] == ["r4", "r3", "r2"]  # newest first, cap 3
    assert store.get("r0") is None
    assert store.get("r4")["id"] == "r4"


def test_run_store_survives_corrupt_file(tmp_path):
    path = tmp_path / "r.json"
    path.write_text("{not json", encoding="utf-8")
    store = BacktestRunStore(path)
    assert store.list() == []


# --- endpoints --------------------------------------------------------------


def test_run_endpoint_starts_job_and_records_it(tmp_path):
    state = _state(make_bars(n=140), tmp_path)
    client = TestClient(create_app(state))
    resp = client.post("/api/backtest/run",
                       json={"symbol": "XAUUSD", "timeframe": "1d",
                             "duration": "30D"})
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    for _ in range(100):  # poll up to ~5s for the daemon thread to finish
        status = client.get("/api/backtest/job").json()
        if status.get("status") in ("done", "error"):
            break
        time.sleep(0.05)
    assert status["status"] == "done", status.get("error")
    assert status["job_id"] == job_id
    runs = client.get("/api/backtest/runs").json()["runs"]
    assert len(runs) == 1 and runs[0]["id"] == job_id
    assert client.get(f"/api/backtest/runs/{job_id}").status_code == 200


def test_run_endpoint_validation(tmp_path):
    state = _state(make_bars(n=140), tmp_path)
    client = TestClient(create_app(state))
    assert client.post("/api/backtest/run",
                       json={"symbol": "NOPE", "timeframe": "1d",
                             "duration": "7D"}).status_code == 422
    assert client.post("/api/backtest/run",
                       json={"symbol": "XAUUSD", "timeframe": "1d",
                             "duration": "7D", "bogus": 1}).status_code == 422
    llm = client.post("/api/backtest/run",
                      json={"symbol": "XAUUSD", "timeframe": "1d",
                            "duration": "7D", "use_llm": True})
    assert llm.status_code == 400
    assert llm.json()["detail"]["error"] == "cost_confirmation_required"
    assert client.get("/api/backtest/runs/missing").status_code == 404


def test_run_endpoint_conflicts_when_busy(tmp_path, monkeypatch):
    state = _state(make_bars(n=140), tmp_path)
    client = TestClient(create_app(state))
    gate = threading.Event()

    def _blocking_run(st, job, params):
        gate.wait(timeout=5)
        job.status = "done"

    monkeypatch.setattr(btjob, "run_job", _blocking_run)
    first = client.post("/api/backtest/run",
                        json={"symbol": "XAUUSD", "timeframe": "1d",
                              "duration": "7D"})
    assert first.status_code == 202
    try:
        busy = client.post("/api/backtest/run",
                           json={"symbol": "XAUUSD", "timeframe": "1d",
                                 "duration": "7D"})
        assert busy.status_code == 409
    finally:
        gate.set()
