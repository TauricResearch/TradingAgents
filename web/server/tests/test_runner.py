"""Tests for ``web.server.runner.enqueue`` and terminal-site writes."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable, Optional

import pytest

from web.server import runner, storage
from web.server import price_feed
from tradingagents.default_config import DEFAULT_CONFIG


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    data = tmp_path / "data"
    cache = tmp_path / "cache"
    monkeypatch.setenv("TRADINGAGENTS_DATA_DIR", str(data))
    monkeypatch.setenv("TRADINGAGENTS_CACHE_DIR", str(cache))
    storage.init_settings(data_dir=str(data), cache_dir=str(cache))
    return data


@pytest.fixture(autouse=True)
def _reset_runner():
    runner._WORK_QUEUE = None
    runner._sem = None
    runner._workers.clear()
    runner._in_flight.clear()
    runner._active = 0
    yield
    runner._WORK_QUEUE = None
    runner._sem = None
    runner._workers.clear()
    runner._in_flight.clear()
    runner._active = 0


def test_enqueue_writes_model_fields_from_default_config(data_root):
    state = price_feed.PriceState(snapshots={}, tickers=lambda: [])
    asyncio.run(runner.start(num_workers=0))
    run_id = asyncio.run(runner.enqueue(
        "NVDA",
        "2026-06-04",
        force=False,
        price_state=state,
    ))
    rj = storage.read_run(run_id)
    assert rj["llm_provider"] == DEFAULT_CONFIG["llm_provider"]
    assert rj["deep_think_model"] == DEFAULT_CONFIG["deep_think_llm"]
    assert rj["quick_think_model"] == DEFAULT_CONFIG["quick_think_llm"]


def test_enqueue_writes_start_price_from_snapshot(data_root):
    snap = price_feed.PriceSnapshot(price=123.45, prev_close=120.0, change_pct=2.875, sparkline=[])
    state = price_feed.PriceState(snapshots={"NVDA": snap}, tickers=lambda: ["NVDA"])
    asyncio.run(runner.start(num_workers=0))
    run_id = asyncio.run(runner.enqueue(
        "NVDA",
        "2026-06-04",
        force=False,
        price_state=state,
    ))
    rj = storage.read_run(run_id)
    assert rj["start_price"] == 123.45
    assert rj["start_price_at"] is not None
    assert rj["start_price_at"].endswith("Z")


def test_enqueue_leaves_price_null_when_snapshot_missing_or_stale(data_root):
    snap = price_feed.PriceSnapshot(price=100.0, prev_close=100.0, change_pct=0.0, sparkline=[], stale=True)
    state = price_feed.PriceState(snapshots={"NVDA": snap}, tickers=lambda: ["NVDA"])
    asyncio.run(runner.start(num_workers=0))
    run_id = asyncio.run(runner.enqueue("NVDA", "2026-06-04", force=False, price_state=state))
    rj = storage.read_run(run_id)
    assert rj["start_price"] is None
    assert rj["start_price_at"] is None


# ---------------------------------------------------------------------------
# Task 5: total_duration_s is written at every terminal site
# ---------------------------------------------------------------------------


class _FakeSem:
    async def acquire(self) -> None:
        return None

    def release(self) -> None:
        return None


def test_terminal_sites_write_total_duration_s_on_cancel_before_start(data_root):
    """The early-cancel path (line ~370) writes total_duration_s to run.json."""
    asyncio.run(runner.start(num_workers=0))
    state = price_feed.PriceState(snapshots={}, tickers=lambda: [])
    run_id = asyncio.run(runner.enqueue("NVDA", "2026-06-04", force=False, price_state=state))
    runner_dir = storage.read_run_dir(run_id)

    # Mark cancel before _run_one even checks — exercises the first terminal site.
    storage.mark_run_status(run_id, cancel_requested=True)
    asyncio.run(runner._run_one(run_id, "NVDA", "2026-06-04", runner_dir, _FakeSem()))

    rj = storage.read_run(run_id)
    assert rj["status"] == "failed"
    assert rj["error"] == "cancelled"
    assert rj["total_duration_s"] is not None
    assert rj["total_duration_s"] >= 0


def test_success_path_writes_total_duration_s(monkeypatch, data_root):
    """The success path (line ~520) computes duration_s before mark_run_status
    and persists it via the total_duration_s kwarg. Drives ``_run_one`` end-to-end
    with a fake ``build_graph`` so the actual runner code is exercised.
    """
    final_state = {
        "decision": "HOLD",
        "final_trade_decision": "## Plan\nTarget 250.",
    }

    class _FakeGraph:
        def propagate(
            self, ticker: str, trade_date: str, *, event_callback: Optional[Callable] = None
        ):
            # Sleep briefly so the runner's monotonic-clock duration is
            # measurable (otherwise it rounds to 0.0 on fast machines).
            import time as _time
            _time.sleep(0.05)
            return final_state, "Hold"

    def _fake_build_graph(config=None, *, callbacks=None):
        return _FakeGraph()

    monkeypatch.setattr(runner, "build_graph", _fake_build_graph)

    asyncio.run(runner.start(num_workers=0))
    state = price_feed.PriceState(snapshots={}, tickers=lambda: [])
    run_id = asyncio.run(runner.enqueue("NVDA", "2026-06-04", force=False, price_state=state))
    runner_dir = storage.read_run_dir(run_id)

    asyncio.run(runner._run_one(run_id, "NVDA", "2026-06-04", runner_dir, _FakeSem()))

    rj = storage.read_run(run_id)
    assert rj["status"] == "done"
    assert rj["decision_action"] == "HOLD"
    assert rj["total_duration_s"] is not None
    assert rj["total_duration_s"] > 0