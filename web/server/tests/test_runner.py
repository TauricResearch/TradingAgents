"""Tests for ``web.server.runner.enqueue`` and terminal-site writes."""
from __future__ import annotations

import asyncio
from pathlib import Path

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


def test_enqueue_writes_model_fields_from_default_config(data_root, monkeypatch):
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