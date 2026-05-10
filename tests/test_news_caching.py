"""Tests for per-vendor news caching in the auto-router.

Pins:
  1. Eastmoney / CLS / yfinance bucket by day.
  2. Cninfo buckets by ISO week (filings move slower).
  3. Multi-source merge calls each vendor through the per-vendor cache,
     so two consecutive runs for the same ticker hit the cache for every
     vendor — no live network calls on the second run.
  4. A vendor that returns a skip-marker is NOT cached (cheap to regen,
     don't lock in mis-routing).
  5. Per-vendor cache is independent — a CLS hit doesn't suppress a
     fresh Cninfo fetch when only Cninfo's bucket has rolled over.
"""

from unittest.mock import MagicMock

import pytest

from tradingagents.dataflows import dataflow_cache as dc
from tradingagents.dataflows import interface as iface
from tradingagents.dataflows.config import set_config


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path):
    set_config({
        "data_cache_dir": str(tmp_path),
        "data_vendors": {"news_data": "auto"},
        "tool_vendors": {},
    })
    yield


def test_iso_week_monday_buckets():
    """Mon 4 May 2026 through Sun 10 May 2026 are the same ISO week."""
    assert dc.iso_week_monday("2026-05-04") == "2026-05-04"  # Monday
    assert dc.iso_week_monday("2026-05-08") == "2026-05-04"  # Friday
    assert dc.iso_week_monday("2026-05-10") == "2026-05-04"  # Sunday — same ISO week
    assert dc.iso_week_monday("2026-05-11") == "2026-05-11"  # next Monday — new week


def test_vendor_cache_key_eastmoney_daily():
    key = dc.vendor_cache_key("eastmoney", "get_news", ("0700.HK", "2026-05-01", "2026-05-10"), {})
    assert key == "eastmoney::news::0700.HK::2026-05-10"


def test_vendor_cache_key_cninfo_weekly():
    key = dc.vendor_cache_key("cninfo", "get_news", ("600519.SS", "2026-05-01", "2026-05-10"), {})
    # 2026-05-10 is a Sunday → ISO Mon = 2026-05-04
    assert key == "cninfo::600519.SS::2026-05-04"


def test_vendor_cached_call_reuses_on_second_call():
    """Second invocation must NOT re-run fetch."""
    call_count = {"n": 0}

    def fetch():
        call_count["n"] += 1
        return "<news body>"

    a = dc.vendor_cached_call("eastmoney", "get_news",
                              ("0700.HK", "2026-05-01", "2026-05-10"), {}, fetch)
    b = dc.vendor_cached_call("eastmoney", "get_news",
                              ("0700.HK", "2026-05-01", "2026-05-10"), {}, fetch)
    assert a == b == "<news body>"
    assert call_count["n"] == 1


def test_vendor_cached_call_skips_caching_skip_markers():
    """Skip-markers must regenerate — cheap to recompute, harmful to lock in."""
    call_count = {"n": 0}

    def fetch():
        call_count["n"] += 1
        return "[Cninfo skip — A-share only]"

    dc.vendor_cached_call("cninfo", "get_news",
                          ("0700.HK", "2026-05-01", "2026-05-10"), {}, fetch)
    dc.vendor_cached_call("cninfo", "get_news",
                          ("0700.HK", "2026-05-01", "2026-05-10"), {}, fetch)
    assert call_count["n"] == 2, "skip markers should not be cached"


def test_vendor_caches_are_independent():
    """Eastmoney hot, Cninfo cold → only Cninfo fetches on second run."""
    em_calls = {"n": 0}
    cninfo_calls = {"n": 0}

    def em_fetch():
        em_calls["n"] += 1
        return "<eastmoney body>"

    def cninfo_fetch():
        cninfo_calls["n"] += 1
        return "<cninfo body>"

    args = ("600519.SS", "2026-05-01", "2026-05-10")

    # First pass: both fetch.
    dc.vendor_cached_call("eastmoney", "get_news", args, {}, em_fetch)
    dc.vendor_cached_call("cninfo", "get_news", args, {}, cninfo_fetch)
    assert em_calls["n"] == 1 and cninfo_calls["n"] == 1

    # Second pass: both cached.
    dc.vendor_cached_call("eastmoney", "get_news", args, {}, em_fetch)
    dc.vendor_cached_call("cninfo", "get_news", args, {}, cninfo_fetch)
    assert em_calls["n"] == 1 and cninfo_calls["n"] == 1


def test_route_to_vendor_caches_each_source_in_merge():
    """End-to-end: route_to_vendor for SH ticker calls 3 vendors first run,
    then 0 vendors on the second (everything cached)."""
    em = MagicMock(return_value="<eastmoney body>")
    cls = MagicMock(return_value="<cls body>")
    cninfo = MagicMock(return_value="<cninfo body>")

    iface_orig = iface.VENDOR_METHODS["get_news"].copy()
    try:
        iface.VENDOR_METHODS["get_news"]["eastmoney"] = em
        iface.VENDOR_METHODS["get_news"]["cls"] = cls
        iface.VENDOR_METHODS["get_news"]["cninfo"] = cninfo

        # First run: each vendor called once.
        out1 = iface.route_to_vendor("get_news", "600519.SS", "2026-05-01", "2026-05-10")
        assert em.call_count == 1
        assert cls.call_count == 1
        assert cninfo.call_count == 1

        # Second run: zero new fetches.
        out2 = iface.route_to_vendor("get_news", "600519.SS", "2026-05-01", "2026-05-10")
        assert em.call_count == 1
        assert cls.call_count == 1
        assert cninfo.call_count == 1
        assert out1 == out2
    finally:
        iface.VENDOR_METHODS["get_news"] = iface_orig
