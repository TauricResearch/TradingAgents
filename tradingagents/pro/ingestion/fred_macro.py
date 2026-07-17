"""Typed FRED adapter for the macro series gold cares about.

The base framework's dataflows.fred returns markdown reports for agent
prompts; this adapter returns numeric MetricReading contracts for the
deterministic snapshot layer instead. Same free API, same FRED_API_KEY,
same not-configured error type — a missing key routes through the standard
taxonomy so the snapshot builder records the feed as missing.

FRED rate limit: 120 requests/minute (free key). One snapshot build issues
one request per series (~6), far below the limit. The ``units`` transform
is applied server-side by FRED (pc1 = percent change vs year ago, chg =
change from previous value), keeping all math out of this process.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from tradingagents.contracts import MetricReading
from tradingagents.dataflows.fred import FredNotConfiguredError
from tradingagents.pro.ingestion.base import HttpTransport, RequestsTransport

API_BASE = "https://api.stlouisfed.org/fred"

# metric name -> (FRED series id, units transform, unit label)
DEFAULT_SERIES: dict[str, tuple[str, str, str]] = {
    "FED_FUNDS_RATE": ("DFF", "lin", "percent"),
    "US10Y": ("DGS10", "lin", "percent"),
    "US10Y_REAL": ("DFII10", "lin", "percent"),
    "DXY_BROAD": ("DTWEXBGS", "lin", "index"),
    "CPI_YOY": ("CPIAUCSL", "pc1", "percent"),
    # PPIFIS = headline PPI (final demand) — what traders mean by "PPI YoY".
    # The previous PPIACO (all-commodities) runs ~3x hotter and repeatedly
    # steered macro debates toward "staggering 10% PPI" (trader review).
    "PPI_YOY": ("PPIFIS", "pc1", "percent"),
    "NFP_CHANGE": ("PAYEMS", "chg", "thousands"),
    "GDP_YOY": ("GDP", "pc1", "percent"),
}


class FredMacroFeed:
    name = "fred_macro"

    def __init__(
        self,
        transport: HttpTransport | None = None,
        series: dict[str, tuple[str, str, str]] | None = None,
        api_key: str | None = None,
    ):
        self._transport = transport or RequestsTransport()
        self._series = series or DEFAULT_SERIES
        self._api_key = api_key

    def _key(self) -> str:
        key = self._api_key or os.environ.get("FRED_API_KEY", "")
        if not key:
            raise FredNotConfiguredError(
                "FRED_API_KEY not set; get a free key at https://fred.stlouisfed.org/docs/api/api_key.html"
            )
        return key

    def get_release_dates(self, days_ahead: int = 30) -> list[dict]:
        """Upcoming release dates (economic calendar). Returns
        [{"date": "YYYY-MM-DD", "release": name, "release_id": id}, ...]."""
        from datetime import date, timedelta

        key = self._key()
        today = date.today()
        payload = self._transport.get_json(
            f"{API_BASE}/releases/dates",
            {
                "api_key": key,
                "file_type": "json",
                "include_release_dates_with_no_data": "true",
                "realtime_start": today.isoformat(),
                "realtime_end": (today + timedelta(days=days_ahead)).isoformat(),
                "sort_order": "asc",
                "limit": 200,
            },
        )
        import re

        # market-moving releases surface first in briefing widgets;
        # everything still ships (the calendar page shows all)
        major = re.compile(
            r"consumer price index|employment situation|fomc|"
            r"gross domestic product|producer price index|retail sales|"
            r"personal income and outlays|advance monthly sales|"
            r"unemployment insurance weekly claims|"
            r"university of michigan|ism report|jolts|gdpnow",
            re.IGNORECASE,
        )
        return [
            {
                "date": row["date"],
                "release": row.get("release_name", ""),
                "release_id": row.get("release_id"),
                "major": bool(major.search(row.get("release_name", ""))),
            }
            for row in payload.get("release_dates", [])
            if today.isoformat() <= row.get("date", "")
        ]

    def get_metrics(self) -> list[MetricReading]:
        key = self._key()
        readings: list[MetricReading] = []
        for name, (series_id, units, unit_label) in self._series.items():
            payload = self._transport.get_json(
                f"{API_BASE}/series/observations",
                {
                    "series_id": series_id,
                    "api_key": key,
                    "file_type": "json",
                    "units": units,
                    "sort_order": "desc",
                    "limit": 5,  # tolerate a few leading "." placeholders
                },
            )
            for obs in payload.get("observations", []):
                if obs.get("value") in (".", "", None):
                    continue
                readings.append(
                    MetricReading(
                        name=name,
                        value=float(obs["value"]),
                        unit=unit_label,
                        as_of=datetime.fromisoformat(obs["date"]).replace(tzinfo=timezone.utc),
                        source=f"fred:{series_id}",
                    )
                )
                break
        return readings
