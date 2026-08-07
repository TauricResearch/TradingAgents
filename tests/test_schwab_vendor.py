"""Schwab vendor: whitelist, look-ahead trimming, tz handling, dedup/sort,
dropna(Close) without ffill, empty/404/429/not-configured routing, indicator
rendering, cross-path cleaning parity, client-cache isolation, partial windows,
and VENDOR_METHODS ⊆ VENDOR_LIST consistency.

All tests monkeypatch ``schwab_common.get_client`` to return a fake schwab-py
client whose ``get_price_history`` returns a minimal fake ``httpx.Response`` duck
object (``.status_code`` + ``.json()``) — no network, no OAuth, no schwab-py.
"""

import copy
import os
import tempfile
import time
import unittest
from enum import Enum
from unittest import mock

import pandas as pd
import pytest

import tradingagents.dataflows.config as config_module
import tradingagents.dataflows.schwab as schwab
import tradingagents.dataflows.schwab_common as schwab_common
import tradingagents.default_config as default_config
from tradingagents.dataflows import interface
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.schwab import get_schwab_indicators, get_schwab_stock
from tradingagents.dataflows.schwab_common import (
    SchwabNotConfiguredError,
    SchwabRateLimitError,
    candles_to_ohlcv_df,
)

# US/Eastern midnight and UTC midnight epoch-ms for the same trading day, used to
# assert the tz handling collapses both onto the intended calendar date.
# 2026-01-05 00:00 UTC:
_UTC_MIDNIGHT_MS_20260105 = 1767571200000
# 2026-01-05 00:00 US/Eastern (EST, UTC-5) == 2026-01-05 05:00 UTC:
_ET_MIDNIGHT_MS_20260105 = _UTC_MIDNIGHT_MS_20260105 + 5 * 3600 * 1000


def _ms(date_str: str) -> int:
    """Epoch ms at UTC midnight for a yyyy-mm-dd date (matches vendor tz choice)."""
    return int(pd.Timestamp(date_str, tz="UTC").timestamp() * 1000)


class _FakeResponse:
    """Minimal httpx.Response duck: only ``.status_code`` and ``.json()``."""

    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):  # pragma: no cover - must never be called
        raise AssertionError(
            "vendor must not call raise_for_status(); classify on status_code"
        )


class _PriceHistory:
    """Stand-in for schwab-py's Client.PriceHistory enum namespace."""

    class PeriodType(Enum):
        YEAR = "year"

    class Period(Enum):
        FIVE_YEARS = 5

    class FrequencyType(Enum):
        DAILY = "daily"

    class Frequency(Enum):
        # schwab-py aliases Frequency.DAILY onto the wire value 1 (candles per
        # day). The fake mirrors that: DAILY carries value 1.
        DAILY = 1


class _FakeClient:
    """Fake schwab-py Client capturing call args and returning a canned response."""

    PriceHistory = _PriceHistory

    def __init__(self, response):
        self._response = response
        self.calls = []

    def get_price_history(self, symbol, **kwargs):
        self.calls.append((symbol, kwargs))
        return self._response


def _candles(rows):
    """Build a Schwab-style payload from (date_str, o, h, l, c, v) tuples."""
    return {
        "candles": [
            {
                "datetime": _ms(d),
                "open": o,
                "high": h,
                "low": lo,
                "close": c,
                "volume": v,
            }
            for (d, o, h, lo, c, v) in rows
        ]
    }


class _SchwabTestBase(unittest.TestCase):
    """Isolate config (temp cache dir) and client cache across tests."""

    def setUp(self):
        schwab_common._reset_client_cache()
        self._orig_get_client = schwab_common.get_client
        self._orig_schwab_get_client = schwab.get_client
        self._tmp = tempfile.TemporaryDirectory()
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)
        set_config({"data_cache_dir": self._tmp.name})

    def tearDown(self):
        schwab_common.get_client = self._orig_get_client
        schwab.get_client = self._orig_schwab_get_client
        schwab_common._reset_client_cache()
        self._tmp.cleanup()
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def _patch_client(self, response):
        client = _FakeClient(response)
        # Both names must point at the fake: schwab.py imported get_client by name.
        schwab_common.get_client = lambda: client
        schwab.get_client = lambda: client
        return client


@pytest.mark.unit
class CandlesToOhlcvDfTests(_SchwabTestBase):
    def test_titlecase_columns_and_tz_naive_date(self):
        df = candles_to_ohlcv_df(
            _candles([("2026-01-05", 1, 2, 0.5, 1.5, 100)])
        )
        self.assertEqual(
            list(df.columns), ["Date", "Open", "High", "Low", "Close", "Volume"]
        )
        # tz-naive datetime64 (no tz-aware TypeError downstream)
        self.assertIsNone(df["Date"].dt.tz)
        self.assertEqual(df["Date"].iloc[0], pd.Timestamp("2026-01-05"))

    def test_tz_utc_and_eastern_midnight_map_to_same_day(self):
        # Both UTC-midnight and ET-midnight ms for 2026-01-05 must resolve to a
        # tz-naive calendar date (2026-01-05); neither raises and both join.
        for ms in (_UTC_MIDNIGHT_MS_20260105, _ET_MIDNIGHT_MS_20260105):
            payload = {
                "candles": [
                    {"datetime": ms, "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 9}
                ]
            }
            df = candles_to_ohlcv_df(payload)
            self.assertIsNone(df["Date"].dt.tz)
            self.assertEqual(df["Date"].iloc[0], pd.Timestamp("2026-01-05"))

    def test_sorts_ascending_and_dedupes_keep_last(self):
        df = candles_to_ohlcv_df(
            _candles(
                [
                    ("2026-01-07", 3, 3, 3, 3.0, 30),
                    ("2026-01-05", 1, 1, 1, 1.0, 10),
                    ("2026-01-05", 9, 9, 9, 9.0, 99),  # duplicate day, later wins
                    ("2026-01-06", 2, 2, 2, 2.0, 20),
                ]
            )
        )
        self.assertEqual(
            list(df["Date"]),
            [pd.Timestamp("2026-01-05"), pd.Timestamp("2026-01-06"), pd.Timestamp("2026-01-07")],
        )
        # keep="last": the 9.0 close for 2026-01-05 must win over 1.0.
        self.assertEqual(df.loc[df["Date"] == pd.Timestamp("2026-01-05"), "Close"].iloc[0], 9.0)

    def test_dropna_close_without_ffill(self):
        payload = {
            "candles": [
                {"datetime": _ms("2026-01-05"), "open": 1, "high": 1, "low": 1, "close": 1.0, "volume": 5},
                {"datetime": _ms("2026-01-06"), "open": 2, "high": 2, "low": 2, "close": None, "volume": 6},
                {"datetime": _ms("2026-01-07"), "open": 3, "high": 3, "low": 3, "close": 3.0, "volume": 7},
            ]
        }
        df = candles_to_ohlcv_df(payload)
        # The null-close row is dropped (halted session), and the surviving rows
        # keep their true prices — no ffill fabricates a close.
        self.assertEqual(list(df["Date"]), [pd.Timestamp("2026-01-05"), pd.Timestamp("2026-01-07")])
        self.assertEqual(list(df["Close"]), [1.0, 3.0])

    def test_empty_when_candles_missing_or_empty(self):
        self.assertTrue(candles_to_ohlcv_df({}).empty)
        self.assertTrue(candles_to_ohlcv_df({"candles": []}).empty)
        # Does NOT rely on an ``empty`` field being present.
        self.assertTrue(candles_to_ohlcv_df({"empty": True}).empty)


def _five_year_rows(end_date="2026-01-09", n=260):
    """Generate n consecutive daily rows ending at end_date (no NaN close)."""
    end = pd.Timestamp(end_date)
    dates = [(end - pd.Timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]
    dates.reverse()
    return [(d, 10.0, 11.0, 9.0, 10.5, 1000 + i) for i, d in enumerate(dates)]


@pytest.mark.unit
class GetSchwabStockTests(_SchwabTestBase):
    def test_whitelist_lets_plain_tickers_through(self):
        self._patch_client(
            _FakeResponse(200, _candles(_five_year_rows()))
        )
        out = get_schwab_stock("AAPL", "2026-01-01", "2026-01-09")
        self.assertIn("# Stock data for AAPL", out)
        self.assertIn("Date,Open,High,Low,Close,Volume", out)

    def test_whitelist_blocks_class_preferred_crypto_index_forex(self):
        # Never even builds a client for these; all raise NoMarketDataError.
        self._patch_client(_FakeResponse(200, _candles(_five_year_rows())))
        for sym in ("BRK.B", "BF.B", "BRK-A", "BAC-PL", "BTC-USD", "^GSPC", "EURUSD=X"):
            with self.subTest(sym=sym), self.assertRaises(NoMarketDataError):
                get_schwab_stock(sym, "2026-01-01", "2026-01-09")

    def test_look_ahead_rows_after_end_date_are_trimmed(self):
        rows = [
            ("2026-01-05", 1, 1, 1, 1.0, 10),
            ("2026-01-06", 2, 2, 2, 2.0, 20),
            ("2026-01-07", 3, 3, 3, 3.0, 30),  # after end_date -> must be excluded
        ]
        self._patch_client(_FakeResponse(200, _candles(rows)))
        out = get_schwab_stock("AAPL", "2026-01-05", "2026-01-06")
        self.assertIn("2026-01-05", out)
        self.assertIn("2026-01-06", out)
        self.assertNotIn("2026-01-07", out)

    def test_closed_interval_includes_end_date_row(self):
        rows = [("2026-01-05", 1, 1, 1, 1.0, 10), ("2026-01-06", 2, 2, 2, 2.0, 20)]
        self._patch_client(_FakeResponse(200, _candles(rows)))
        out = get_schwab_stock("AAPL", "2026-01-05", "2026-01-06")
        self.assertIn("2026-01-06,", out)  # end_date row present

    def test_string_dates_vs_datetime64_do_not_raise(self):
        # Trimming converts str dates with pd.to_datetime; Date is tz-naive.
        rows = _five_year_rows()
        self._patch_client(_FakeResponse(200, _candles(rows)))
        # Would raise a tz/dtype TypeError if compared naively — must not.
        get_schwab_stock("AAPL", "2026-01-01", "2026-01-09")

    def test_partial_window_flagged_in_header(self):
        rows = [("2026-01-05", 1, 1, 1, 1.0, 10), ("2026-01-06", 2, 2, 2, 2.0, 20)]
        self._patch_client(_FakeResponse(200, _candles(rows)))
        out = get_schwab_stock("AAPL", "2020-01-01", "2026-01-06")
        self.assertIn("earliest available Schwab bar is 2026-01-05", out)
        self.assertIn("window is partial", out)

    def test_404_raises_no_market_data(self):
        self._patch_client(_FakeResponse(404, {}))
        with self.assertRaises(NoMarketDataError):
            get_schwab_stock("AAPL", "2026-01-01", "2026-01-09")

    def test_empty_candles_raise_no_market_data(self):
        self._patch_client(_FakeResponse(200, {"candles": []}))
        with self.assertRaises(NoMarketDataError):
            get_schwab_stock("AAPL", "2026-01-01", "2026-01-09")

    def test_401_raises_not_configured(self):
        self._patch_client(_FakeResponse(401, {}))
        with self.assertRaises(SchwabNotConfiguredError):
            get_schwab_stock("AAPL", "2026-01-01", "2026-01-09")

    def test_429_raises_rate_limit(self):
        self._patch_client(_FakeResponse(429, {}))
        with self.assertRaises(SchwabRateLimitError):
            get_schwab_stock("AAPL", "2026-01-01", "2026-01-09")

    def test_5xx_raises_generic_exception(self):
        self._patch_client(_FakeResponse(503, {}))
        with self.assertRaises(Exception) as ctx:
            get_schwab_stock("AAPL", "2026-01-01", "2026-01-09")
        self.assertNotIsInstance(ctx.exception, NoMarketDataError)

    def test_vendor_never_calls_raise_for_status(self):
        # _FakeResponse.raise_for_status asserts if called; a 200 path must pass.
        self._patch_client(_FakeResponse(200, _candles(_five_year_rows())))
        get_schwab_stock("AAPL", "2026-01-01", "2026-01-09")

    def test_stale_frame_raises_no_market_data(self):
        # Latest row far older than the requested end -> stale -> NoMarketDataError.
        rows = [
            ("2025-01-05", 1, 1, 1, 1.0, 10),
            ("2025-01-06", 2, 2, 2, 2.0, 20),
        ]
        self._patch_client(_FakeResponse(200, _candles(rows)))
        with self.assertRaises(NoMarketDataError):
            get_schwab_stock("AAPL", "2025-01-01", "2026-01-09")

    def test_ohlcv_null_close_row_dropped_not_ffilled(self):
        rows_payload = {
            "candles": [
                {"datetime": _ms("2026-01-05"), "open": 1, "high": 1, "low": 1, "close": 1.0, "volume": 5},
                {"datetime": _ms("2026-01-06"), "open": 2, "high": 2, "low": 2, "close": None, "volume": 6},
                {"datetime": _ms("2026-01-07"), "open": 3, "high": 3, "low": 3, "close": 3.0, "volume": 7},
            ]
        }
        self._patch_client(_FakeResponse(200, rows_payload))
        out = get_schwab_stock("AAPL", "2026-01-05", "2026-01-07")
        self.assertNotIn("2026-01-06,", out)  # halted row dropped
        self.assertIn("2026-01-05,", out)
        self.assertIn("2026-01-07,", out)
        # No fabricated 1.0-ffill for 2026-01-06 anywhere.
        self.assertNotIn("2026-01-06", out)

    def test_disk_cache_reused_within_ttl(self):
        client = self._patch_client(_FakeResponse(200, _candles(_five_year_rows())))
        get_schwab_stock("AAPL", "2026-01-01", "2026-01-09")
        get_schwab_stock("AAPL", "2026-01-01", "2026-01-09")
        # Second call served from the per-symbol CSV cache -> one network call.
        self.assertEqual(len(client.calls), 1)

    def test_get_price_history_called_with_explicit_5y_daily_enums(self):
        client = self._patch_client(_FakeResponse(200, _candles(_five_year_rows())))
        get_schwab_stock("AAPL", "2026-01-01", "2026-01-09")
        symbol, kwargs = client.calls[0]
        self.assertEqual(symbol, "AAPL")
        self.assertEqual(kwargs["period_type"], _PriceHistory.PeriodType.YEAR)
        self.assertEqual(kwargs["period"], _PriceHistory.Period.FIVE_YEARS)
        self.assertEqual(kwargs["frequency_type"], _PriceHistory.FrequencyType.DAILY)
        # Explicit daily frequency (wire value 1); never left to the server default.
        self.assertEqual(kwargs["frequency"], _PriceHistory.Frequency.DAILY)
        self.assertEqual(kwargs["frequency"].value, 1)
        # Never uses start/end datetime (would trigger full-history semantics).
        self.assertNotIn("start_datetime", kwargs)
        self.assertNotIn("end_datetime", kwargs)

    def test_historical_request_reuses_cache_regardless_of_ttl(self):
        # A cache written for a historical (past) as-of date must be reused even
        # when its mtime is older than the TTL: historical rows are immutable, so
        # a long backtest reuses one download instead of refetching per day.
        client = self._patch_client(_FakeResponse(200, _candles(_five_year_rows())))
        get_schwab_stock("AAPL", "2025-12-20", "2025-12-31")
        # Age the cache file well past the TTL window.
        data_file = os.path.join(
            self._tmp.name, "AAPL-Schwab-daily.csv"
        )
        old = time.time() - (schwab.SCHWAB_CACHE_TTL_SECONDS + 3600)
        os.utime(data_file, (old, old))
        get_schwab_stock("AAPL", "2025-12-20", "2025-12-31")
        # Still one network call: the historical request short-circuits the TTL.
        self.assertEqual(len(client.calls), 1)

    def test_current_day_stale_cache_refetches_after_ttl(self):
        # By contrast a current-day request past the TTL must refetch (the still
        # forming bar may have changed). Uses today's date as the as-of date.
        today = pd.Timestamp.today().strftime("%Y-%m-%d")
        start = (pd.Timestamp.today() - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
        rows = _five_year_rows(end_date=today, n=60)
        client = self._patch_client(_FakeResponse(200, _candles(rows)))
        get_schwab_stock("AAPL", start, today)
        data_file = os.path.join(self._tmp.name, "AAPL-Schwab-daily.csv")
        old = time.time() - (schwab.SCHWAB_CACHE_TTL_SECONDS + 3600)
        os.utime(data_file, (old, old))
        get_schwab_stock("AAPL", start, today)
        # Two network calls: the current-day cache was past its TTL.
        self.assertEqual(len(client.calls), 2)

    def test_corrupt_cache_missing_ohlcv_columns_is_a_miss(self):
        # A cache file missing required title-case OHLCV columns must be treated
        # as a miss and refetched, not served (partially) to downstream code.
        client = self._patch_client(_FakeResponse(200, _candles(_five_year_rows())))
        get_schwab_stock("AAPL", "2025-12-20", "2025-12-31")
        data_file = os.path.join(self._tmp.name, "AAPL-Schwab-daily.csv")
        # Overwrite with a file that has Date+Close but no Open/High/Low/Volume.
        pd.DataFrame(
            {"Date": ["2025-12-31"], "Close": [1.0]}
        ).to_csv(data_file, index=False)
        get_schwab_stock("AAPL", "2025-12-20", "2025-12-31")
        # The corrupt cache forced a second fetch.
        self.assertEqual(len(client.calls), 2)


@pytest.mark.unit
class GetSchwabIndicatorsTests(_SchwabTestBase):
    def test_established_stock_has_200_sma_value(self):
        # 260 consecutive trading rows ending 2026-01-09 -> 200 SMA has a value.
        self._patch_client(_FakeResponse(200, _candles(_five_year_rows(n=260))))
        out = get_schwab_indicators("AAPL", "close_200_sma", "2026-01-09", 5)
        self.assertIn("2026-01-09:", out)
        # The curr_date line should carry a numeric value, not N/A.
        line = [ln for ln in out.splitlines() if ln.startswith("2026-01-09:")][0]
        self.assertNotIn("N/A", line)

    def test_young_stock_200_sma_na_is_allowed(self):
        # Only 20 rows -> 200 SMA legitimately N/A; not an error.
        self._patch_client(_FakeResponse(200, _candles(_five_year_rows(n=20))))
        out = get_schwab_indicators("AAPL", "close_200_sma", "2026-01-09", 3)
        self.assertIn("2026-01-09:", out)  # renders without raising

    def test_indicator_look_ahead_filter(self):
        rows = _five_year_rows(end_date="2026-01-20", n=30)
        self._patch_client(_FakeResponse(200, _candles(rows)))
        out = get_schwab_indicators("AAPL", "close_50_sma", "2026-01-10", 3)
        # No date after curr_date appears in the rendered window.
        self.assertNotIn("2026-01-11:", out)
        self.assertNotIn("2026-01-20:", out)

    def test_indicator_whitelist_blocks_non_equity(self):
        self._patch_client(_FakeResponse(200, _candles(_five_year_rows())))
        with self.assertRaises(NoMarketDataError):
            get_schwab_indicators("BRK.B", "rsi", "2026-01-09", 5)

    def test_indicator_empty_raises_no_market_data(self):
        self._patch_client(_FakeResponse(200, {"candles": []}))
        with self.assertRaises(NoMarketDataError):
            get_schwab_indicators("AAPL", "rsi", "2026-01-09", 5)

    def test_indicator_stale_frame_raises_no_market_data(self):
        # Latest available bar far older than curr_date (all rows > MAX stale
        # days before it) -> the indicator path must reject it like the OHLCV
        # path, not silently compute indicators off year-old prices.
        rows = _five_year_rows(end_date="2025-01-09", n=30)
        self._patch_client(_FakeResponse(200, _candles(rows)))
        with self.assertRaises(NoMarketDataError):
            get_schwab_indicators("AAPL", "close_50_sma", "2026-01-09", 5)

    def test_cross_path_cleaning_parity_with_yfinance(self):
        # Feed the same clean OHLCV frame through the Schwab clean+render path and
        # a direct render (as yfinance's load_ohlcv would feed) and assert the
        # per-day indicator values match. Uses NaN-free fake data so no basis diff.
        from tradingagents.dataflows.stockstats_utils import (
            _clean_dataframe,
            render_indicator_window,
        )

        rows = _five_year_rows(end_date="2026-01-09", n=80)
        df = pd.DataFrame(
            {
                "Date": pd.to_datetime([r[0] for r in rows]),
                "Open": [r[1] for r in rows],
                "High": [r[2] for r in rows],
                "Low": [r[3] for r in rows],
                "Close": [r[4] for r in rows],
                "Volume": [r[5] for r in rows],
            }
        )
        for indicator in ("close_50_sma", "rsi", "vwma"):
            with self.subTest(indicator=indicator):
                schwab_out = render_indicator_window(
                    _clean_dataframe(df.copy()), indicator, "2026-01-09", 5
                )
                yfin_out = render_indicator_window(
                    df.copy(), indicator, "2026-01-09", 5
                )
                self.assertEqual(schwab_out, yfin_out)


@pytest.mark.unit
class ClientCacheAndConfigTests(_SchwabTestBase):
    def test_not_configured_without_key_falls_back_via_router(self):
        # No fake client patched; no SCHWAB_APP_KEY -> SchwabNotConfiguredError,
        # so a "schwab,yfinance" chain falls back to yfinance's data.
        os.environ.pop("SCHWAB_APP_KEY", None)
        os.environ.pop("SCHWAB_APP_SECRET", None)
        schwab_common._reset_client_cache()
        set_config({"data_vendors": {"core_stock_apis": "schwab,yfinance"}})

        def _yf_ok(symbol, *a, **k):
            return "YF_DATA"

        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_stock_data": {"schwab": get_schwab_stock, "yfinance": _yf_ok}},
            clear=False,
        ):
            result = interface.route_to_vendor(
                "get_stock_data", "AAPL", "2026-01-01", "2026-01-09"
            )
        self.assertEqual(result, "YF_DATA")

    def test_reset_client_cache_prevents_fake_leak(self):
        # A fake injected in one case must not leak into the next.
        self._patch_client(_FakeResponse(200, _candles(_five_year_rows())))
        get_schwab_stock("AAPL", "2026-01-01", "2026-01-09")
        # Reset + restore real get_client, drop credentials -> NotConfigured.
        schwab_common.get_client = self._orig_get_client
        schwab.get_client = self._orig_schwab_get_client
        schwab_common._reset_client_cache()
        os.environ.pop("SCHWAB_APP_KEY", None)
        os.environ.pop("SCHWAB_APP_SECRET", None)
        with self.assertRaises(SchwabNotConfiguredError):
            get_schwab_stock("MSFT", "2026-01-01", "2026-01-09")


@pytest.mark.unit
class VendorRegistrationConsistencyTests(unittest.TestCase):
    def test_vendor_methods_subset_of_vendor_list(self):
        listed = set(interface.VENDOR_LIST)
        for method, vendors in interface.VENDOR_METHODS.items():
            for vendor in vendors:
                self.assertIn(
                    vendor,
                    listed,
                    f"{vendor!r} (in VENDOR_METHODS[{method!r}]) missing from VENDOR_LIST",
                )

    def test_schwab_registered_after_yfinance(self):
        for method in ("get_stock_data", "get_indicators"):
            keys = list(interface.VENDOR_METHODS[method].keys())
            self.assertIn("schwab", keys)
            self.assertIn("yfinance", keys)
            self.assertGreater(keys.index("schwab"), keys.index("yfinance"))


if __name__ == "__main__":
    unittest.main()
