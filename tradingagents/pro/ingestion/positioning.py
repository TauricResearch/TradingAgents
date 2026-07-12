"""Gold positioning & implied-vol feeds (DR-1).

Two datasets the gold roster lacked, both keyless:

- **CFTC Commitment of Traders** (weekly, legacy futures-only report):
  net non-commercial ("speculative") COMEX gold positioning. Fetched
  straight from CFTC's public Socrata API — the same endpoint OpenBB's
  ``cftc`` provider wraps; the dependency gate chose direct REST over
  the 30-package openbb tree (see docs/DECISIONS.md).
- **GVZ** (CBOE Gold Volatility Index) via the existing yfinance daily
  bars plumbing: implied vol, complementing the realized-vol metrics.

COT is weekly (released Fridays for Tuesday data), so the feed caches
the latest rows on disk: a network failure inside the report's week
serves the cache as fresh data, not degradation. Both feeds follow the
house rules — typed MetricReadings only, probe-gating, and the
``PRO_DISABLE_LIVE_VENDORS=1`` hermetic-test kill switch.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tradingagents.contracts import MetricReading, Timeframe
from tradingagents.pro.ingestion.base import HttpTransport, RequestsTransport

logger = logging.getLogger(__name__)

CFTC_BASE = "https://publicreporting.cftc.gov/resource"
LEGACY_FUTURES_DATASET = "6dca-aqww"
COMEX_GOLD_CODE = "088691"
COT_MAX_CACHE_AGE_DAYS = 9  # one weekly cycle + weekend slack


class GoldCotFeed:
    """Weekly CFTC COT: net non-commercial gold futures positioning."""

    name = "gold_cot"

    def __init__(self, transport: HttpTransport | None = None,
                 base_url: str = CFTC_BASE,
                 contract_code: str = COMEX_GOLD_CODE,
                 cache_path: str | Path | None = None):
        self._transport = transport or RequestsTransport()
        self._base = base_url.rstrip("/")
        self._code = contract_code
        self._cache_path = Path(cache_path) if cache_path else None

    @classmethod
    def probe(cls, timeout: float = 8.0) -> bool:
        if os.environ.get("PRO_DISABLE_LIVE_VENDORS") == "1":
            return False
        try:
            feed = cls(transport=RequestsTransport(timeout=timeout))
            return bool(feed._fetch_rows(limit=1))
        except Exception:
            return False

    # --- data ------------------------------------------------------------------

    def _fetch_rows(self, limit: int = 2) -> list[dict]:
        rows = self._transport.get_json(
            f"{self._base}/{LEGACY_FUTURES_DATASET}.json",
            params={
                "cftc_contract_market_code": self._code,
                "$order": "report_date_as_yyyy_mm_dd DESC",
                "$limit": limit,
                "$select": ("report_date_as_yyyy_mm_dd,"
                            "noncomm_positions_long_all,"
                            "noncomm_positions_short_all,"
                            "open_interest_all"),
            },
        )
        if not isinstance(rows, list):
            raise ValueError(f"unexpected CFTC payload: {type(rows)}")
        return rows

    def _rows_with_cache(self) -> list[dict]:
        try:
            rows = self._fetch_rows()
            if rows and self._cache_path is not None:
                from tradingagents.pro.persistence import atomic_write_json

                atomic_write_json(self._cache_path, {"rows": rows})
            return rows
        except Exception:
            cached = self._read_cache()
            if cached:
                logger.warning("CFTC fetch failed; serving cached COT report "
                               "dated %s", cached[0]["report_date_as_yyyy_mm_dd"])
                return cached
            raise

    def _read_cache(self) -> list[dict]:
        if self._cache_path is None or not self._cache_path.exists():
            return []
        try:
            rows = json.loads(self._cache_path.read_text(encoding="utf-8"))["rows"]
            report = datetime.fromisoformat(
                rows[0]["report_date_as_yyyy_mm_dd"]).replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - report > timedelta(
                    days=COT_MAX_CACHE_AGE_DAYS):
                return []  # a stale report is degradation, not data
            return rows
        except Exception:
            logger.warning("corrupt COT cache %s; ignoring", self._cache_path,
                           exc_info=True)
            return []

    def get_metrics(self) -> list[MetricReading]:
        rows = self._rows_with_cache()
        if not rows:
            raise ValueError("CFTC returned no COT rows for gold")
        latest = rows[0]
        report_date = datetime.fromisoformat(
            latest["report_date_as_yyyy_mm_dd"]).replace(tzinfo=timezone.utc)
        net = (float(latest["noncomm_positions_long_all"])
               - float(latest["noncomm_positions_short_all"]))
        readings = [
            MetricReading(name="GOLD_COT_NET_NONCOMM", value=net,
                          unit="contracts", as_of=report_date, source=self.name),
        ]
        open_interest = float(latest.get("open_interest_all") or 0)
        if open_interest > 0:
            readings.append(MetricReading(
                name="GOLD_COT_NET_PCT_OI", value=100.0 * net / open_interest,
                unit="pct", as_of=report_date, source=self.name))
        if len(rows) > 1:
            prior = rows[1]
            prior_net = (float(prior["noncomm_positions_long_all"])
                         - float(prior["noncomm_positions_short_all"]))
            readings.append(MetricReading(
                name="GOLD_COT_NET_CHANGE_1W", value=net - prior_net,
                unit="contracts", as_of=report_date, source=self.name))
        return readings


class GoldVolFeed:
    """CBOE Gold Volatility Index (GVZ) — implied vol via yfinance bars."""

    name = "gold_vol"
    GVZ_SYMBOL = "^GVZ"

    def __init__(self, bars_feed):
        self._bars = bars_feed  # YFinanceDailyBarsFeed (injectable loader)

    @classmethod
    def probe(cls, timeout: float = 8.0) -> bool:
        if os.environ.get("PRO_DISABLE_LIVE_VENDORS") == "1":
            return False
        try:
            from tradingagents.pro.ingestion.gold_feeds import YFinanceDailyBarsFeed

            return bool(cls(YFinanceDailyBarsFeed()).get_metrics())
        except Exception:
            return False

    def get_metrics(self) -> list[MetricReading]:
        bars = self._bars.get_bars(self.GVZ_SYMBOL, Timeframe.D1, limit=2)
        if not bars:
            raise ValueError("no GVZ bars returned")
        latest = bars[-1]
        readings = [MetricReading(
            name="GOLD_VOL_INDEX", value=latest.close, unit="vol_points",
            as_of=latest.start, source=self.name)]
        if len(bars) > 1 and bars[-2].close:
            readings.append(MetricReading(
                name="GOLD_VOL_INDEX_CHANGE_1D",
                value=latest.close - bars[-2].close,
                unit="vol_points", as_of=latest.start, source=self.name))
        return readings
