"""Tests for the cross-ticker dataflow cache.

Pins:
  1. ``get_global_news`` is cached by date — second call same day reuses, even
     when invoked from a different ticker context.
  2. Financial statements are cached by (ticker, fiscal_quarter) — same ticker
     queried on different days within a quarter reuses; new quarter refetches.
  3. Non-cacheable methods (e.g. get_stock_data) fall through every time.
"""

from datetime import date

import pytest

from tradingagents.dataflows import dataflow_cache as dc
from tradingagents.dataflows.config import set_config


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path):
    set_config({"data_cache_dir": str(tmp_path)})
    yield


def _counting_fetch(payload, counter):
    def fetch():
        counter[0] += 1
        return payload
    return fetch


def test_fiscal_quarter_end_buckets():
    assert dc.fiscal_quarter_end("2026-05-08") == "2026-03-31"
    assert dc.fiscal_quarter_end("2026-07-15") == "2026-06-30"
    assert dc.fiscal_quarter_end("2026-12-31") == "2026-12-31"
    assert dc.fiscal_quarter_end("2026-01-02") == "2025-12-31"


def test_global_news_cache_reused_same_day():
    counter = [0]
    args = ("2026-05-08", 7, 10)
    fetch = _counting_fetch("global news payload", counter)

    a = dc.cached_call("get_global_news", args, {}, fetch)
    b = dc.cached_call("get_global_news", args, {}, fetch)

    assert a == b == "global news payload"
    assert counter[0] == 1, "Second call should hit the cache"


def test_global_news_cache_invalidates_on_new_day():
    counter = [0]
    fetch = _counting_fetch("payload", counter)

    dc.cached_call("get_global_news", ("2026-05-08", 7, 10), {}, fetch)
    dc.cached_call("get_global_news", ("2026-05-09", 7, 10), {}, fetch)

    assert counter[0] == 2


def test_fundamentals_cache_reused_within_quarter():
    counter = [0]
    fetch = _counting_fetch("fundamentals body", counter)

    # Two different days, same ticker, same calendar quarter (Q2 2026).
    dc.cached_call("get_fundamentals", ("AAPL", "2026-04-15"), {}, fetch)
    dc.cached_call("get_fundamentals", ("AAPL", "2026-05-08"), {}, fetch)

    assert counter[0] == 1


def test_fundamentals_cache_separates_tickers():
    counter = [0]
    fetch = _counting_fetch("body", counter)

    dc.cached_call("get_fundamentals", ("AAPL", "2026-05-08"), {}, fetch)
    dc.cached_call("get_fundamentals", ("MSFT", "2026-05-08"), {}, fetch)

    assert counter[0] == 2


def test_balance_sheet_cache_keyed_by_freq():
    counter = [0]
    fetch = _counting_fetch("body", counter)

    dc.cached_call("get_balance_sheet", ("AAPL", "quarterly", "2026-05-08"), {}, fetch)
    dc.cached_call("get_balance_sheet", ("AAPL", "annual", "2026-05-08"), {}, fetch)

    assert counter[0] == 2


def test_uncacheable_method_falls_through():
    counter = [0]
    fetch = _counting_fetch("body", counter)

    dc.cached_call("get_stock_data", ("AAPL", "2026-01-01", "2026-05-08"), {}, fetch)
    dc.cached_call("get_stock_data", ("AAPL", "2026-01-01", "2026-05-08"), {}, fetch)

    assert counter[0] == 2, "Non-cacheable methods should always fetch"


def test_cache_key_for_returns_none_on_missing_args():
    assert dc.cache_key_for("get_global_news", (), {}) is None
    assert dc.cache_key_for("get_fundamentals", ("AAPL",), {}) is None
    assert dc.cache_key_for("nonexistent_method", ("AAPL",), {}) is None
