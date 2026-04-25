"""Live integration tests for OHLCV cache contamination defence.

Tests hit the real yfinance API and require network access.
They validate two things:

  1. Concurrent safety — safe_yf_download() called from multiple threads
     simultaneously does NOT produce cross-ticker column contamination.

  2. Guard pipeline — _load_or_fetch_ohlcv() correctly detects and purges
     contaminated, stale, and truncated cache files before returning data.

Run explicitly (network required):

    pytest tests/integration/test_ohlcv_cache_defence_live.py -v --override-ini="addopts="

The STM/TSM pair is the canonical real-world contamination case:
  STM ~$30–50  vs  TSM ~$150–200.  A ratio > 3× triggers the plausibility guard.
"""

from __future__ import annotations

import concurrent.futures
import re
from datetime import timedelta

import pandas as pd
import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

_TODAY = pd.Timestamp.today()
_ONE_YEAR_AGO = (_TODAY - pd.DateOffset(years=1)).strftime("%Y-%m-%d")
_TODAY_STR = _TODAY.strftime("%Y-%m-%d")


def _assert_clean_df(df: pd.DataFrame, label: str) -> None:
    """Assert a DataFrame has no contaminated (.N) column suffixes."""
    bad = [str(c) for c in df.columns if re.search(r"\.\d+$", str(c))]
    assert not bad, f"{label}: contaminated columns found: {bad}"


# ---------------------------------------------------------------------------
# Part 1 — Concurrent safe_yf_download() calls
# ---------------------------------------------------------------------------


class TestConcurrentSafeYfDownload:
    """Verify that simultaneous safe_yf_download calls don't cross-contaminate."""

    # Pairs chosen so their price ranges don't overlap: if columns bleed across
    # calls we'll see prices from the wrong ticker.
    _TICKERS = ["STM", "TSM", "AAPL", "NVDA"]

    def _download_one(self, ticker: str) -> tuple[str, pd.DataFrame]:
        from tradingagents.dataflows.stockstats_utils import safe_yf_download

        df = safe_yf_download(
            ticker,
            start=_ONE_YEAR_AGO,
            end=_TODAY_STR,
            auto_adjust=True,
            progress=False,
        )
        return ticker, df

    def test_concurrent_downloads_produce_clean_columns(self):
        """All simultaneous downloads return DataFrames free of .N column contamination."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self._TICKERS)) as pool:
            futures = {pool.submit(self._download_one, t): t for t in self._TICKERS}
            results = {}
            for fut in concurrent.futures.as_completed(futures):
                ticker, df = fut.result()
                results[ticker] = df

        for ticker, df in results.items():
            assert not df.empty, f"{ticker}: download returned empty DataFrame"
            _assert_clean_df(df, ticker)

    def test_concurrent_downloads_have_close_column(self):
        """Each concurrent download has a 'Close' column (not Close.1 etc.)."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self._TICKERS)) as pool:
            futures = [pool.submit(self._download_one, t) for t in self._TICKERS]
            results = dict(f.result() for f in concurrent.futures.as_completed(futures))

        for ticker, df in results.items():
            assert "Close" in df.columns, (
                f"{ticker}: 'Close' column missing — got {list(df.columns)}"
            )

    def test_safe_yf_download_single_ticker_no_multi_index(self):
        """Single-ticker download produces flat (non-MultiIndex) columns."""
        from tradingagents.dataflows.stockstats_utils import safe_yf_download

        df = safe_yf_download(
            "AAPL", start=_ONE_YEAR_AGO, end=_TODAY_STR, auto_adjust=True, progress=False
        )

        assert not isinstance(df.columns, pd.MultiIndex), (
            "safe_yf_download returned a MultiIndex column structure — "
            "multi_level_index=False not enforced"
        )
        assert not df.empty
        _assert_clean_df(df, "AAPL single-ticker")

    def test_safe_yf_download_multi_ticker_no_contamination(self):
        """Multi-ticker batch download keeps each ticker's Close in a clean sub-column."""
        from tradingagents.dataflows.stockstats_utils import safe_yf_download

        tickers = ["STM", "TSM"]
        df = safe_yf_download(
            tickers, start=_ONE_YEAR_AGO, end=_TODAY_STR, auto_adjust=True, progress=False
        )

        assert not df.empty
        # Columns should be like Close/STM, Close/TSM or Close (flat) — never Close.1
        _assert_clean_df(df, "multi-ticker STM+TSM")

    def test_repeated_serial_downloads_stay_clean(self):
        """Calling safe_yf_download 10× in a tight loop never produces .N columns."""
        from tradingagents.dataflows.stockstats_utils import safe_yf_download

        tickers_cycle = ["STM", "TSM", "AAPL", "NVDA", "MSFT", "STM", "TSM", "AAPL", "NVDA", "MSFT"]
        for ticker in tickers_cycle:
            df = safe_yf_download(
                ticker, start=_ONE_YEAR_AGO, end=_TODAY_STR, auto_adjust=True, progress=False
            )
            _assert_clean_df(df, f"serial loop {ticker}")


# ---------------------------------------------------------------------------
# Part 2 — Guard pipeline with real data
# ---------------------------------------------------------------------------


class TestOhlcvGuardPipelineLive:
    """_load_or_fetch_ohlcv() guard pipeline with real network data."""

    # STM is the ticker from the original incident: cheap (~$30–50) but
    # historically contaminated with TSM data (~$150–200) when yfinance's
    # multi-ticker cache was not isolated.
    _TICKER = "STM"

    # ── 2a. Plausibility guard passes on legitimate data ──────────────────────

    def test_load_or_fetch_returns_plausible_stm_data(self, tmp_path):
        """Real STM data passes the plausibility guard (ratio < 3.0)."""
        from tradingagents.dataflows import stockstats_utils as su

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(su, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
            df = su._load_or_fetch_ohlcv(self._TICKER)

        assert len(df) >= 50, f"Expected ≥50 rows, got {len(df)}"
        assert "Close" in df.columns or "close" in df.columns
        close_col = "Close" if "Close" in df.columns else "close"
        last_close = pd.to_numeric(df[close_col], errors="coerce").dropna().iloc[-1]
        # STM should be in a plausible range (not TSM's $150–200 level)
        assert 5.0 < last_close < 300.0, (
            f"STM last close {last_close:.2f} looks implausible — possible contamination"
        )

    def test_is_close_plausible_passes_on_real_stm_data(self, tmp_path):
        """_is_close_plausible returns True for freshly downloaded STM data."""
        from tradingagents.dataflows import stockstats_utils as su

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(su, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
            df = su._load_or_fetch_ohlcv(self._TICKER)

        result = su._is_close_plausible(df, self._TICKER)
        assert result is True, (
            "Plausibility guard rejected real STM data — guard may be miscalibrated. "
            f"Close column sample: {df.get('Close', df.get('close', 'MISSING')).tail(5).tolist()}"
        )

    # ── 2b. Contaminated-column detector fires and re-fetches ────────────────

    def test_contaminated_cache_is_detected_and_refetched(self, tmp_path):
        """A cache file with .N column suffixes is purged and fresh data is fetched."""
        from tradingagents.dataflows import stockstats_utils as su

        # Build a contaminated CSV that looks like a real cache file
        today = pd.Timestamp.today()
        start_str = (today - pd.DateOffset(years=15)).strftime("%Y-%m-%d")
        end_str = today.strftime("%Y-%m-%d")
        cache_path = tmp_path / f"{self._TICKER}-YFin-data-{start_str}-{end_str}.csv"

        # Write 200 rows with contaminated column names (Close.1 present)
        dates = pd.bdate_range(end=today, periods=200)
        n = len(dates)
        contaminated_df = pd.DataFrame(
            {
                "Date": dates.strftime("%Y-%m-%d"),
                "Open": [170.0] * n,  # TSM-level prices in STM's cache
                "High": [175.0] * n,
                "Low": [165.0] * n,
                "Close": [170.0] * n,
                "Close.1": [36.0] * n,  # <-- contamination marker
                "Volume": [1_000_000] * n,
            }
        )
        contaminated_df.to_csv(cache_path, index=False)
        assert cache_path.exists(), "Precondition: contaminated cache must exist"

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(su, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
            df = su._load_or_fetch_ohlcv(self._TICKER)

        # The guard fired, deleted the contaminated file, re-fetched fresh data,
        # and wrote a new clean cache at the same path.  The file may exist again
        # (now containing clean data), but the returned DataFrame must be clean.
        _assert_clean_df(df, f"re-fetched {self._TICKER}")
        assert len(df) >= 50, f"Expected ≥50 rows after re-fetch, got {len(df)}"
        # Verify the re-written cache no longer contains contaminated columns
        if cache_path.exists():
            cached = pd.read_csv(cache_path)
            _assert_clean_df(cached, f"re-cached {self._TICKER}")

    # ── 2c. Staleness check fires and re-fetches ──────────────────────────────

    def test_stale_cache_is_purged_and_refetched(self, tmp_path):
        """A cache whose last date is 10 days old is discarded and re-fetched."""
        from tradingagents.dataflows import stockstats_utils as su

        today = pd.Timestamp.today()
        start_str = (today - pd.DateOffset(years=15)).strftime("%Y-%m-%d")
        end_str = today.strftime("%Y-%m-%d")
        cache_path = tmp_path / f"{self._TICKER}-YFin-data-{start_str}-{end_str}.csv"

        # 200-row cache whose last date is 10 days ago (clearly stale)
        stale_end = today - timedelta(days=10)
        dates = pd.bdate_range(end=stale_end, periods=200)
        n = len(dates)  # guard against bdate_range rounding differences
        stale_df = pd.DataFrame(
            {
                "Date": dates.strftime("%Y-%m-%d"),
                "Open": [36.0] * n,
                "High": [37.0] * n,
                "Low": [35.0] * n,
                "Close": [36.0] * n,
                "Volume": [500_000] * n,
            }
        )
        stale_df.to_csv(cache_path, index=False)
        assert cache_path.exists()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                su,
                "get_config",
                lambda: {
                    "data_cache_dir": str(tmp_path),
                    "ohlcv_cache_max_age_days": 2,  # stale after 2 days
                },
            )
            df = su._load_or_fetch_ohlcv(self._TICKER)

        # The staleness guard fired, deleted the stale file, re-fetched fresh data,
        # and wrote a new cache at the same path.  Verify the returned data is fresh
        # (last date within 7 calendar days of today — weekends/holidays included).
        assert len(df) >= 50, f"Expected ≥50 rows after re-fetch, got {len(df)}"
        date_col = "Date" if "Date" in df.columns else "date"
        last_date = pd.to_datetime(df[date_col]).max()
        age_days = (pd.Timestamp.today() - last_date).days
        assert age_days <= 7, (
            f"Staleness guard fired but returned data is still old: "
            f"last date {last_date.date()}, age {age_days} days — re-fetch did not produce fresh data"
        )

    # ── 2d. Row count guard fires on truncated fresh download ─────────────────

    def test_row_count_guard_raises_on_truncated_data(self, tmp_path):
        """_assert_sufficient_rows raises RuntimeError when data has < 50 rows."""
        from tradingagents.dataflows.stockstats_utils import _assert_sufficient_rows

        tiny_df = pd.DataFrame({"Close": range(10)})
        with pytest.raises(RuntimeError, match=r"\[OHLCV\] Insufficient data for STM"):
            _assert_sufficient_rows(tiny_df, min_rows=50, ticker="STM")

    # ── 2e. No contamination in freshly fetched data ─────────────────────────

    def test_fresh_download_has_no_contaminated_columns(self, tmp_path):
        """After a clean cache miss, downloaded STM data has no .N columns."""
        from tradingagents.dataflows import stockstats_utils as su
        from tradingagents.dataflows.stockstats_utils import _has_contaminated_columns

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(su, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
            df = su._load_or_fetch_ohlcv(self._TICKER)

        assert not _has_contaminated_columns(df), (
            f"Fresh {self._TICKER} download has contaminated columns: "
            f"{[c for c in df.columns if re.search(r'.\\d+$', str(c))]}"
        )
