"""Interactive backtest job: paging + retry, request validation, streaming
worker, cancel/interrupted lifecycle, zero-loss artifacts, run store, and the
async endpoints."""

import json
import threading
import time
from datetime import timedelta
from types import SimpleNamespace

import pytest

from tests.pro_fakes import BASE_TS, make_bars
from tradingagents.contracts import OHLCVBar, Timeframe
from tradingagents.pro.dashboard import backtest_job as btjob
from tradingagents.pro.dashboard.backtest_artifacts import RunArtifacts
from tradingagents.pro.dashboard.backtest_store import BacktestRunStore
from tradingagents.pro.dashboard.marketdata import MAX_LIMIT
from tradingagents.pro.memory import ProMemory

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from tradingagents.pro.dashboard.app import DashboardState, create_app  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Artifacts + caches land in a per-test dir, never the operator's."""
    monkeypatch.setenv("TRADINGAGENTS_PRO_DATA", str(tmp_path / "data"))
    return tmp_path


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
    def __init__(self, bars, timeframes=(Timeframe.D1,), fail_first=0):
        self._bars = bars
        self._tf = timeframes
        self._fail_remaining = fail_first  # raise on the first N calls

    def spec(self, symbol):
        return SimpleNamespace(timeframes=self._tf)

    def get_bars(self, symbol, timeframe, limit=1000, end=None):
        if self._fail_remaining > 0:
            self._fail_remaining -= 1
            raise TimeoutError("vendor rate limited")
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
    assert btjob.bars_for_duration("1Y", Timeframe.H1) > 8000


def test_gold_daily_durations_use_trading_days():
    from tradingagents.contracts import AssetClass

    # 1Y of daily gold ≈ 252 trading days, not 365 calendar days
    bars = btjob.bars_for_duration("1Y", Timeframe.D1, AssetClass.GOLD)
    assert bars == 261 + btjob.MIN_HISTORY  # ceil(365 * 5/7)
    assert btjob.periods_per_year(Timeframe.D1, AssetClass.GOLD) == 252
    # crypto trades 24/7: calendar == market
    assert btjob.periods_per_year(Timeframe.D1, AssetClass.BITCOIN) == 365
    assert btjob.bars_for_duration("1Y", Timeframe.D1, AssetClass.BITCOIN) \
        == 365 + btjob.MIN_HISTORY


# --- paging + retry ---------------------------------------------------------


def test_fetch_window_pages_beyond_the_request_cap():
    market = _StubMarket(make_bars(n=1500))
    bars, truncated = btjob.fetch_window(market, "XAUUSD", Timeframe.D1, 1300)
    assert not truncated
    assert len(bars) == 1300
    starts = [b.start for b in bars]
    assert starts == sorted(starts)  # oldest → newest
    assert len(set(starts)) == 1300  # no duplicates across pages


def test_fetch_window_stops_when_history_exhausted():
    market = _StubMarket(make_bars(n=120))
    bars, truncated = btjob.fetch_window(market, "XAUUSD", Timeframe.D1, 500)
    assert not truncated
    assert len(bars) == 120  # can't fabricate more than exists


def test_fetch_window_retries_transient_vendor_errors():
    market = _StubMarket(make_bars(n=200), fail_first=2)  # 2 failures then ok
    bars, truncated = btjob.fetch_window(market, "XAUUSD", Timeframe.D1, 150,
                                         backoff=0.0)
    assert not truncated and len(bars) == 150


def test_fetch_window_reports_progress():
    market = _StubMarket(make_bars(n=1500))
    seen = []
    btjob.fetch_window(market, "XAUUSD", Timeframe.D1, 1300,
                       on_page=lambda have, need: seen.append((have, need)))
    assert seen and seen[-1] == (1300, 1300)
    assert all(n == 1300 for _, n in seen)


def test_fetch_window_persistent_failure_with_no_bars_raises():
    market = _StubMarket(make_bars(n=200), fail_first=99)
    with pytest.raises(ValueError, match="bar fetch failed"):
        btjob.fetch_window(market, "XAUUSD", Timeframe.D1, 150, backoff=0.0)


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


def test_resolve_large_deterministic_run_requires_confirmation():
    market = _StubMarket(make_bars(n=80), timeframes=tuple(Timeframe))
    params = {"symbol": "BTC-USD", "timeframe": "5m", "duration": "1Y"}
    with pytest.raises(btjob._CostConfirmationRequired) as exc:
        btjob.resolve_request(market, params)
    assert exc.value.estimate["decisions"] > btjob.LARGE_RUN_DECISIONS
    assert exc.value.estimate["est_cost_usd"] == 0.0
    # confirmed → full density, NO window trim, NO subsampling
    resolved = btjob.resolve_request(market, {**params, "confirm_cost": True})
    assert resolved["bars"] == btjob.bars_for_duration("1Y", Timeframe.M5)


def test_resolve_carries_sizing_defaults_and_overrides():
    market = _StubMarket(make_bars(n=80))
    params = {"symbol": "XAUUSD", "timeframe": "1d", "duration": "7D"}
    resolved = btjob.resolve_request(market, params)
    # spot-max defaults: 1% risk target, 33% notional cap per position
    assert resolved["risk_per_trade_pct"] == 1.0
    assert resolved["max_position_pct"] == 33.0
    resolved = btjob.resolve_request(
        market, {**params, "risk_per_trade_pct": 0.5, "max_position_pct": 50.0})
    assert resolved["risk_per_trade_pct"] == 0.5
    assert resolved["max_position_pct"] == 50.0


def test_run_request_sizing_bounds():
    base = {"symbol": "BTC-USD", "timeframe": "5m"}
    req = btjob.BacktestRunRequest(**base)
    assert req.risk_per_trade_pct == 1.0 and req.max_position_pct == 33.0
    with pytest.raises(ValueError):
        btjob.BacktestRunRequest(**base, risk_per_trade_pct=0)
    with pytest.raises(ValueError):
        btjob.BacktestRunRequest(**base, risk_per_trade_pct=5.1)
    with pytest.raises(ValueError):
        btjob.BacktestRunRequest(**base, max_position_pct=101)


def test_resolve_strategy_defaults_and_back_compat():
    market = _StubMarket(make_bars(n=80), timeframes=tuple(Timeframe))
    base = {"symbol": "BTC-USD", "timeframe": "1d", "duration": "7D"}
    # no strategy_id, no use_llm -> rules_v1 (deterministic)
    r = btjob.resolve_request(market, base)
    assert r["strategy_id"] == "rules_v1" and r["use_llm"] is False
    assert r["strategy_params"] == {"tp_ladder": "0.5/3.5",
                                    "min_risk_reward": 1.8,
                                    "stop_cooldown_bars": 10}
    # use_llm=True (legacy toggle) -> pipeline_llm (needs cost confirm)
    with pytest.raises(btjob._CostConfirmationRequired):
        btjob.resolve_request(market, {**base, "use_llm": True})
    r = btjob.resolve_request(market, {**base, "use_llm": True,
                                       "confirm_cost": True})
    assert r["strategy_id"] == "pipeline_llm" and r["use_llm"] is True
    # explicit strategy_id wins over use_llm
    r = btjob.resolve_request(market, {**base, "strategy_id": "rules_v1",
                                       "use_llm": True})
    assert r["strategy_id"] == "rules_v1" and r["use_llm"] is False


def test_resolve_rejects_unknown_strategy_and_bad_params():
    market = _StubMarket(make_bars(n=80), timeframes=tuple(Timeframe))
    base = {"symbol": "BTC-USD", "timeframe": "1d", "duration": "7D"}
    with pytest.raises(ValueError, match="unknown strategy"):
        btjob.resolve_request(market, {**base, "strategy_id": "nope_v9"})
    with pytest.raises(ValueError, match="outside declared domain"):
        btjob.resolve_request(
            market, {**base, "strategy_params": {"stop_cooldown_bars": 99}})
    with pytest.raises(ValueError, match="unknown parameter"):
        btjob.resolve_request(
            market, {**base, "strategy_params": {"typo": 1}})


# --- streaming worker (deterministic, offline) ------------------------------


def test_run_job_streams_persists_and_writes_full_artifacts(tmp_path):
    state = _state(make_bars(n=140), tmp_path)
    job = btjob.new_job({"symbol": "XAUUSD", "timeframe": "1d", "duration": "30D"})
    state.backtest_job = job

    btjob.run_job(state, job, job.params)

    assert job.status == "done", job.error
    types = state.broadcaster.types()
    assert "backtest_progress" in types
    assert types[-1] == "backtest_done"
    assert job.closed_trades
    assert "backtest_trade" in types
    assert state.backtest is not None

    # slim transport: the terminal event carries a summary, never bulk arrays
    done = next(d for t, d in state.broadcaster.events if t == "backtest_done")
    assert "view" not in done and done["summary"]["n_trades"] >= 1
    assert "equity_curve" not in (job.result or {})

    saved = state.backtest_runs.list()
    assert len(saved) == 1 and saved[0]["symbol"] == "XAUUSD"
    assert saved[0]["status"] == "done"
    assert saved[0]["indicator_mode"] == "full_history"
    assert job.result["provider"] == "rules"
    # strategy provenance (track T1): a no-strategy_id request defaults to
    # rules_v1 and records the resolved params + schema version
    assert job.result["strategy_id"] == "rules_v1"
    assert job.result["strategy_params"]["tp_ladder"] == "0.5/3.5"
    assert saved[0]["strategy_id"] == "rules_v1"

    # zero-loss artifacts: one equity row + one decision row PER DECISION,
    # and every closed trade
    artifacts = RunArtifacts(job.id)
    equity = artifacts.read("equity")
    decisions = artifacts.read("decisions")
    trades = artifacts.read("trades")
    assert len(decisions) == job.result["decisions"]
    assert len(equity) == len(decisions)
    assert len(trades) == job.result["n_trades"]
    # checkpoint cleared on completion
    assert state.backtest_runs.read_checkpoint() is None

    # sizing provenance: view + summary record exactly what sized the run
    assert job.result["risk_per_trade_pct"] == 1.0
    assert job.result["max_position_pct"] == 33.0
    assert saved[0]["risk_per_trade_pct"] == 1.0
    assert saved[0]["max_position_pct"] == 33.0


def test_run_job_runs_native_trend_following_strategy(tmp_path):
    # a steady uptrend so the Donchian breakout fires; the job must build and
    # run the native (order-book) strategy end to end and record its identity
    bars = make_bars(n=140)
    state = _state(bars, tmp_path)
    job = btjob.new_job({"symbol": "XAUUSD", "timeframe": "1d",
                         "duration": "30D", "strategy_id": "trend_following_v1",
                         "strategy_params": {"donchian_period": 15}})
    state.backtest_job = job
    btjob.run_job(state, job, job.params)
    assert job.status == "done", job.error
    assert job.result["strategy_id"] == "trend_following_v1"
    assert job.result["strategy_params"]["donchian_period"] == 15
    assert job.result["provider"] == "rules"  # deterministic, no LLM
    # orders artifact: listed iff the order book actually produced orders
    orders = RunArtifacts(job.id).read("orders")
    assert ("orders" in job.result["artifacts"]) == bool(orders)


def test_run_job_honors_sizing_overrides(tmp_path):
    state = _state(make_bars(n=140), tmp_path)
    job = btjob.new_job({"symbol": "XAUUSD", "timeframe": "1d",
                         "duration": "30D", "risk_per_trade_pct": 2.0,
                         "max_position_pct": 20.0})
    state.backtest_job = job
    btjob.run_job(state, job, job.params)
    assert job.status == "done", job.error
    assert job.result["risk_per_trade_pct"] == 2.0
    assert job.result["max_position_pct"] == 20.0
    saved = state.backtest_runs.list()
    assert saved[0]["max_position_pct"] == 20.0
    # the cap is enforced per trade: no fill's notional exceeds 20% of the
    # equity in force when it was sized (initial equity + closed P&L bound)
    trades = RunArtifacts(job.id).read("trades")
    if trades:
        equity_bound = 100_000.0 + sum(abs(t["pnl"]) for t in trades)
        for t in trades:
            assert t["quantity"] * t["entry_price"] <= 0.2 * equity_bound


def test_cancel_mid_run_saves_labeled_partial(tmp_path):
    state = _state(make_bars(n=200), tmp_path)
    job = btjob.new_job({"symbol": "XAUUSD", "timeframe": "1d", "duration": "30D"})
    state.backtest_job = job

    # set the cancel flag once the 10th decision completes; the engine
    # notices at the start of the 11th and raises BacktestCancelled
    fired = {"n": 0}
    original = btjob._StreamingEngine._apply_decision

    def cancel_after_10(self, s, i):
        out = original(self, s, i)
        fired["n"] += 1
        if fired["n"] == 10:
            job.cancel.set()
        return out

    try:
        btjob._StreamingEngine._apply_decision = cancel_after_10
        btjob.run_job(state, job, job.params)
    finally:
        btjob._StreamingEngine._apply_decision = original

    assert job.status == "cancelled"
    saved = state.backtest_runs.list()
    assert len(saved) == 1 and saved[0]["status"] == "cancelled"
    assert job.result["status"] == "cancelled"
    # the partial kept its decisions + equity up to the cancel point
    artifacts = RunArtifacts(job.id)
    assert len(artifacts.read("decisions")) == 10
    assert len(artifacts.read("equity")) == 10
    assert state.backtest_runs.read_checkpoint() is None


def test_interrupted_checkpoint_recovers_to_saved_partial(tmp_path):
    store = BacktestRunStore(tmp_path / "runs.json")
    run_id = "deadbeef1234"
    RunArtifacts(run_id).write(
        equity=[["2026-01-01T00:00:00+00:00", 100_000.0],
                ["2026-01-02T00:00:00+00:00", 100_500.0]],
        trades=[{"id": "t1", "pnl": 500.0}],
        decisions=[{"index": 60, "outcome": "executed"},
                   {"index": 61, "outcome": "hold"}],
    )
    store.write_checkpoint({
        "job_id": run_id, "status": "running",
        "params": {"symbol": "BTC-USD", "timeframe": "1h", "duration": "7D",
                   "initial_equity": 100_000.0},
        "started_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-02T00:00:00+00:00",
    })

    record = btjob.recover_interrupted(store)

    assert record is not None and record["status"] == "interrupted"
    listed = store.list()
    assert listed[0]["status"] == "interrupted"
    assert listed[0]["n_trades"] == 1
    assert listed[0]["final_equity"] == 100_500.0
    assert store.read_checkpoint() is None
    # idempotent: nothing left to recover
    assert btjob.recover_interrupted(store) is None


def test_snapshot_caps_closed_trades_but_reports_total():
    job = btjob.new_job({"symbol": "BTC-USD"})
    job.closed_trades = [{"id": str(i)} for i in range(250)]
    snap = job.snapshot()
    assert len(snap["closed_trades"]) == btjob.SNAPSHOT_TRADES
    assert snap["closed_total"] == 250
    assert snap["closed_trades"][-1]["id"] == "249"  # the most recent tail


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


def test_run_store_delete(tmp_path):
    store = BacktestRunStore(tmp_path / "r.json")
    store.save({"id": "a", "created_at": "1", "view": {}})
    store.save({"id": "b", "created_at": "2", "view": {}})
    assert store.delete("a") is True
    assert store.delete("a") is False
    assert [r["id"] for r in store.list()] == ["b"]
    # deletion persists across reload
    assert [r["id"] for r in BacktestRunStore(tmp_path / "r.json").list()] == ["b"]


def test_run_store_survives_corrupt_file(tmp_path):
    path = tmp_path / "r.json"
    path.write_text("{not json", encoding="utf-8")
    store = BacktestRunStore(path)
    assert store.list() == []


def test_run_store_checkpoint_roundtrip(tmp_path):
    store = BacktestRunStore(tmp_path / "r.json")
    assert store.read_checkpoint() is None
    store.write_checkpoint({"job_id": "x", "status": "running"})
    assert store.read_checkpoint()["job_id"] == "x"
    store.clear_checkpoint()
    assert store.read_checkpoint() is None
    store.clear_checkpoint()  # idempotent


# --- artifacts ---------------------------------------------------------------


def test_artifacts_roundtrip_and_delete(tmp_path):
    artifacts = RunArtifacts("run1", tmp_path / "arts")
    artifacts.write(equity=[["t0", 1.0]], trades=[{"id": "a"}],
                    decisions=[{"index": 1}])
    assert artifacts.read("equity") == [["t0", 1.0]]
    assert json.loads(artifacts.path("trades").read_text()) == [{"id": "a"}]
    artifacts.delete()
    assert artifacts.read("equity") == []
    with pytest.raises(KeyError):
        artifacts.path("nope")


# --- endpoints --------------------------------------------------------------


def test_run_endpoint_starts_job_and_records_it(tmp_path):
    state = _state(make_bars(n=140), tmp_path)
    client = TestClient(create_app(state))
    resp = client.post("/api/backtest/run",
                       json={"symbol": "XAUUSD", "timeframe": "1d",
                             "duration": "30D"})
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    for _ in range(200):  # poll up to ~10s for the daemon thread to finish
        status = client.get("/api/backtest/job").json()
        if status.get("status") in ("done", "error"):
            break
        time.sleep(0.05)
    assert status["status"] == "done", status.get("error")
    assert status["job_id"] == job_id
    runs = client.get("/api/backtest/runs").json()["runs"]
    assert len(runs) == 1 and runs[0]["id"] == job_id
    assert client.get(f"/api/backtest/runs/{job_id}").status_code == 200

    # artifacts are served in full
    equity = client.get(f"/api/backtest/runs/{job_id}/artifacts/equity")
    assert equity.status_code == 200
    assert len(equity.json()) == status["result"]["decisions"]
    assert client.get(
        f"/api/backtest/runs/{job_id}/artifacts/bogus").status_code == 404

    # delete removes record + artifacts
    assert client.delete(f"/api/backtest/runs/{job_id}").status_code == 200
    assert client.get(f"/api/backtest/runs/{job_id}").status_code == 404
    assert client.get(
        f"/api/backtest/runs/{job_id}/artifacts/equity").status_code == 404


def test_cancel_endpoint(tmp_path, monkeypatch):
    state = _state(make_bars(n=140), tmp_path)
    client = TestClient(create_app(state))
    # idle → 409
    assert client.post("/api/backtest/cancel").status_code == 409

    gate = threading.Event()

    def _blocking_run(st, job, params):
        gate.wait(timeout=5)
        job.status = "cancelled" if job.cancel.is_set() else "done"

    monkeypatch.setattr(btjob, "run_job", _blocking_run)
    assert client.post("/api/backtest/run",
                       json={"symbol": "XAUUSD", "timeframe": "1d",
                             "duration": "7D"}).status_code == 202
    resp = client.post("/api/backtest/cancel")
    assert resp.status_code == 200 and resp.json()["status"] == "cancelling"
    gate.set()
    for _ in range(100):
        if client.get("/api/backtest/job").json().get("status") == "cancelled":
            break
        time.sleep(0.05)
    assert client.get("/api/backtest/job").json()["status"] == "cancelled"


def test_strategies_endpoint_lists_rules_and_pipeline_llm(tmp_path):
    state = _state(make_bars(n=140), tmp_path)
    client = TestClient(create_app(state))
    resp = client.get("/api/backtest/strategies")
    assert resp.status_code == 200
    strategies = {s["id"]: s for s in resp.json()["strategies"]}
    assert {"rules_v1", "pipeline_llm", "trend_following_v1"} <= set(strategies)
    # the native strategy advertises its own (different) schema
    tf_params = [p["name"] for p in strategies["trend_following_v1"]["params"]]
    assert "donchian_period" in tf_params
    # both advertise the declared param schema for the UI
    names = [p["name"] for p in strategies["rules_v1"]["params"]]
    assert names == ["tp_ladder", "min_risk_reward", "stop_cooldown_bars"]
    ladder = next(p for p in strategies["rules_v1"]["params"]
                  if p["name"] == "tp_ladder")
    assert ladder["default"] == "0.5/3.5" and "1.5/3.0" in ladder["choices"]


def test_run_endpoint_rejects_unknown_strategy(tmp_path):
    state = _state(make_bars(n=140), tmp_path)
    client = TestClient(create_app(state))
    resp = client.post("/api/backtest/run",
                       json={"symbol": "XAUUSD", "timeframe": "1d",
                             "duration": "7D", "strategy_id": "nope_v9"})
    assert resp.status_code == 422


def test_run_endpoint_validation(tmp_path):
    state = _state(make_bars(n=140), tmp_path)
    client = TestClient(create_app(state))
    assert client.post("/api/backtest/run",
                       json={"symbol": "NOPE", "timeframe": "1d",
                             "duration": "7D"}).status_code == 422
    assert client.post("/api/backtest/run",
                       json={"symbol": "XAUUSD", "timeframe": "1d",
                             "duration": "7D", "bogus": 1}).status_code == 422
    assert client.post("/api/backtest/run",
                       json={"symbol": "XAUUSD", "timeframe": "1d",
                             "duration": "7D",
                             "risk_per_trade_pct": 0}).status_code == 422
    assert client.post("/api/backtest/run",
                       json={"symbol": "XAUUSD", "timeframe": "1d",
                             "duration": "7D",
                             "max_position_pct": 150}).status_code == 422
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


# --- optimization endpoints -------------------------------------------------


def _trend_bars(n=200):
    """Steady uptrend with tight wicks — makes trend_following_v1 break out
    and trade (a flat series would leave every trial at return 0)."""
    bars, price = [], 1000.0
    for i in range(n):
        price += 2.0
        bars.append(OHLCVBar(
            timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
            open=price, high=price + 0.5, low=price - 0.5, close=price,
            volume=1_000_000.0))
    return bars


def test_optimize_endpoint_runs_grid_and_records_guards(tmp_path):
    state = _state(_trend_bars(200), tmp_path)
    client = TestClient(create_app(state))
    resp = client.post("/api/backtest/optimize",
                       json={"symbol": "XAUUSD", "timeframe": "1d",
                             "duration": "30D", "objective": "total_return",
                             "param_grid": {"donchian_period": [15, 25],
                                            "trail_pct": [0.03, 0.05]}})
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]

    for _ in range(400):  # grid of 4 child backtests — poll up to ~20s
        status = client.get("/api/backtest/optimize/job").json()
        if status.get("status") in ("done", "error", "cancelled"):
            break
        time.sleep(0.05)
    assert status["status"] == "done", status.get("error")

    listed = client.get("/api/backtest/optimizations").json()["optimizations"]
    assert len(listed) == 1 and listed[0]["id"] == job_id
    assert listed[0]["type"] == "optimization" and listed[0]["n_trials"] == 4

    record = client.get(f"/api/backtest/optimizations/{job_id}").json()
    view = record["view"]
    assert view["best_params"]["donchian_period"] in (15, 25)
    assert view["best_params"]["trail_pct"] in (0.03, 0.05)
    assert len(view["trials"]) == 4
    assert view["deflated_sharpe"] is not None and view["pbo"] is not None
    assert isinstance(view["verdict"], str) and view["verdict"]
    assert client.get("/api/backtest/optimizations/missing").status_code == 404


def test_optimize_endpoint_validation(tmp_path):
    state = _state(_trend_bars(200), tmp_path)
    client = TestClient(create_app(state))
    # unknown symbol
    assert client.post("/api/backtest/optimize",
                       json={"symbol": "NOPE", "timeframe": "1d",
                             "duration": "30D",
                             "param_grid": {"donchian_period": [15]}}
                       ).status_code == 422
    # empty grid — nothing to sweep
    assert client.post("/api/backtest/optimize",
                       json={"symbol": "XAUUSD", "timeframe": "1d",
                             "duration": "30D", "param_grid": {}}
                       ).status_code == 422
    # a grid value outside the strategy's declared domain
    assert client.post("/api/backtest/optimize",
                       json={"symbol": "XAUUSD", "timeframe": "1d",
                             "duration": "30D",
                             "param_grid": {"donchian_period": [999]}}
                       ).status_code == 422
    # unknown objective
    assert client.post("/api/backtest/optimize",
                       json={"symbol": "XAUUSD", "timeframe": "1d",
                             "duration": "30D", "objective": "magic",
                             "param_grid": {"donchian_period": [15]}}
                       ).status_code == 422
    # unknown field rejected by the model
    assert client.post("/api/backtest/optimize",
                       json={"symbol": "XAUUSD", "timeframe": "1d",
                             "duration": "30D", "bogus": 1,
                             "param_grid": {"donchian_period": [15]}}
                       ).status_code == 422


def test_optimize_endpoint_large_grid_needs_cost_confirm(tmp_path):
    state = _state(_trend_bars(200), tmp_path)
    client = TestClient(create_app(state))
    big = {"donchian_period": list(range(10, 60))}  # 50 trials >= confirm gate
    resp = client.post("/api/backtest/optimize",
                       json={"symbol": "XAUUSD", "timeframe": "1d",
                             "duration": "30D", "param_grid": big})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["error"] == "cost_confirmation_required"
    assert detail["estimate"]["trials"] == 50


def test_optimize_endpoint_conflicts_with_running_backtest(tmp_path, monkeypatch):
    state = _state(_trend_bars(200), tmp_path)
    client = TestClient(create_app(state))
    gate = threading.Event()

    def _blocking_run(st, job, params):
        gate.wait(timeout=5)
        job.status = "done"

    monkeypatch.setattr(btjob, "run_job", _blocking_run)
    assert client.post("/api/backtest/run",
                       json={"symbol": "XAUUSD", "timeframe": "1d",
                             "duration": "7D"}).status_code == 202
    try:
        busy = client.post("/api/backtest/optimize",
                           json={"symbol": "XAUUSD", "timeframe": "1d",
                                 "duration": "30D",
                                 "param_grid": {"donchian_period": [15, 25]}})
        assert busy.status_code == 409
    finally:
        gate.set()


# --- portfolio (multi-symbol) endpoint --------------------------------------


def test_portfolio_endpoint_runs_and_records_a_multi_symbol_run(tmp_path):
    state = _state(_trend_bars(200), tmp_path, timeframes=(Timeframe.D1,))
    client = TestClient(create_app(state))
    resp = client.post("/api/backtest/portfolio",
                       json={"symbols": ["XAUUSD", "BTC-USD"], "timeframe": "1d",
                             "duration": "30D", "strategy_id": "trend_following_v1"})
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]

    for _ in range(400):
        status = client.get("/api/backtest/job").json()
        if status.get("status") in ("done", "error"):
            break
        time.sleep(0.05)
    assert status["status"] == "done", status.get("error")

    record = client.get(f"/api/backtest/runs/{job_id}").json()
    view = record["view"]
    assert view["is_portfolio"] is True
    assert view["symbols"] == ["XAUUSD", "BTC-USD"]
    assert view["strategy_id"] == "trend_following_v1"
    # the run is a normal record: it lists + serves its equity/trades artifacts
    runs = client.get("/api/backtest/runs").json()["runs"]
    assert any(r["id"] == job_id for r in runs)
    assert client.get(
        f"/api/backtest/runs/{job_id}/artifacts/equity").status_code == 200


def test_portfolio_endpoint_validation(tmp_path):
    state = _state(_trend_bars(200), tmp_path, timeframes=(Timeframe.D1,))
    client = TestClient(create_app(state))
    # fewer than two symbols → model rejects
    assert client.post("/api/backtest/portfolio",
                       json={"symbols": ["BTC-USD"], "timeframe": "1d",
                             "duration": "30D"}).status_code == 422
    # unknown symbol in the basket
    assert client.post("/api/backtest/portfolio",
                       json={"symbols": ["BTC-USD", "NOPE"], "timeframe": "1d",
                             "duration": "30D"}).status_code == 422
    # a pipeline strategy is not allowed for portfolio runs
    assert client.post("/api/backtest/portfolio",
                       json={"symbols": ["BTC-USD", "XAUUSD"], "timeframe": "1d",
                             "duration": "30D",
                             "strategy_id": "rules_v1"}).status_code == 422


# --- strategy bake-off endpoint ---------------------------------------------


def test_bakeoff_endpoint_ranks_strategies(tmp_path):
    state = _state(_trend_bars(200), tmp_path, timeframes=(Timeframe.D1,))
    client = TestClient(create_app(state))
    resp = client.post("/api/backtest/bakeoff",
                       json={"symbol": "BTC-USD", "timeframe": "1d",
                             "duration": "30D", "objective": "total_return",
                             "strategy_ids": ["trend_following_v1", "momentum_v1"]})
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]

    for _ in range(400):
        status = client.get("/api/backtest/bakeoff/job").json()
        if status.get("status") in ("done", "error"):
            break
        time.sleep(0.05)
    assert status["status"] == "done", status.get("error")

    listed = client.get("/api/backtest/bakeoffs").json()["bakeoffs"]
    assert len(listed) == 1 and listed[0]["id"] == job_id
    assert listed[0]["type"] == "bakeoff" and listed[0]["winner"] in (
        "trend_following_v1", "momentum_v1")

    view = client.get(f"/api/backtest/bakeoffs/{job_id}").json()["view"]
    rows = view["results"]
    assert {r["strategy_id"] for r in rows} == {"trend_following_v1", "momentum_v1"}
    # ranked best-first by the chosen objective
    objs = [r["objective_value"] for r in rows]
    assert objs == sorted(objs, reverse=True)
    assert all("sharpe" in r and "n_trades" in r for r in rows)
    assert client.get("/api/backtest/bakeoffs/missing").status_code == 404


def test_bakeoff_endpoint_validation(tmp_path):
    state = _state(_trend_bars(200), tmp_path, timeframes=(Timeframe.D1,))
    client = TestClient(create_app(state))
    assert client.post("/api/backtest/bakeoff",
                       json={"symbol": "NOPE", "timeframe": "1d",
                             "duration": "30D"}).status_code == 422
    # fewer than two strategies is not a bake-off
    assert client.post("/api/backtest/bakeoff",
                       json={"symbol": "BTC-USD", "timeframe": "1d",
                             "duration": "30D",
                             "strategy_ids": ["momentum_v1"]}).status_code == 422
    # unknown objective
    assert client.post("/api/backtest/bakeoff",
                       json={"symbol": "BTC-USD", "timeframe": "1d",
                             "duration": "30D", "objective": "magic",
                             "strategy_ids": ["momentum_v1", "trend_following_v1"]}
                       ).status_code == 422
