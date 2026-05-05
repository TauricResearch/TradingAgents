# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Unit tests for tradingagents.dataflows._cache.simple_parquet_cache."""

import time
from pathlib import Path

import pandas as pd
import pytest

from tradingagents.dataflows import config as df_config
from tradingagents.dataflows._cache import simple_parquet_cache


@pytest.fixture
def temp_cache_dir(tmp_path, monkeypatch):
    """Point the cache at an isolated temp dir for each test."""
    monkeypatch.setattr(
        df_config,
        "_config",
        {
            "data_cache_dir": str(tmp_path),
            "cache_ttl": {"ohlcv": 60, "instant": 1, "off": 0},
        },
    )
    return tmp_path


def _df(rows=3):
    return pd.DataFrame({"a": list(range(rows)), "b": list(range(rows))})


def test_cache_miss_then_hit(temp_cache_dir):
    calls = {"n": 0}

    @simple_parquet_cache(kind="ohlcv")
    def fetch(x):
        calls["n"] += 1
        return _df()

    out1 = fetch("AAPL")
    out2 = fetch("AAPL")

    assert calls["n"] == 1
    pd.testing.assert_frame_equal(out1, out2)
    files = list(temp_cache_dir.rglob("*.parquet"))
    assert len(files) == 1


def test_distinct_args_distinct_files(temp_cache_dir):
    @simple_parquet_cache(kind="ohlcv")
    def fetch(x):
        return _df()

    fetch("AAPL")
    fetch("MSFT")
    files = list(temp_cache_dir.rglob("*.parquet"))
    assert len(files) == 2


def test_ttl_expires(temp_cache_dir):
    calls = {"n": 0}

    @simple_parquet_cache(kind="instant")  # ttl=1s
    def fetch(x):
        calls["n"] += 1
        return _df()

    fetch("X")
    time.sleep(1.2)
    fetch("X")
    assert calls["n"] == 2


def test_ttl_zero_disables_cache(temp_cache_dir):
    calls = {"n": 0}

    @simple_parquet_cache(kind="off")
    def fetch(x):
        calls["n"] += 1
        return _df()

    fetch("X")
    fetch("X")
    assert calls["n"] == 2


def test_empty_dataframe_not_cached(temp_cache_dir):
    calls = {"n": 0}

    @simple_parquet_cache(kind="ohlcv")
    def fetch(x):
        calls["n"] += 1
        return pd.DataFrame()

    fetch("X")
    fetch("X")
    assert calls["n"] == 2
    assert list(temp_cache_dir.rglob("*.parquet")) == []


def test_corrupt_file_falls_open(temp_cache_dir):
    @simple_parquet_cache(kind="ohlcv")
    def fetch(x):
        return _df()

    fetch("X")
    cached = next(temp_cache_dir.rglob("*.parquet"))
    cached.write_bytes(b"not a parquet")

    out = fetch("X")
    assert len(out) == 3


def test_func_exception_is_not_swallowed_or_retried(temp_cache_dir):
    """If the wrapped function raises, the exception must propagate immediately
    without a silent retry — earlier bug doubled API calls when cache was active."""
    calls = {"n": 0}

    @simple_parquet_cache(kind="ohlcv")
    def fetch(x):
        calls["n"] += 1
        raise RuntimeError("network down")

    with pytest.raises(RuntimeError, match="network down"):
        fetch("X")

    assert calls["n"] == 1, "function should be called exactly once"
