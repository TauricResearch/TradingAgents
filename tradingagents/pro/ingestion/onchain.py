"""Free on-chain and crypto-sentiment feeds.

- CoinMetrics Community API (keyless, ~10 req/6s): MVRV, realized cap,
  active addresses. The community tier covers our core valuation metric;
  SOPR and exchange reserves need a paid provider (see decision table).
- blockchain.com charts API (keyless): miner hash rate and revenue.
- alternative.me Fear & Greed index (keyless).
"""

from __future__ import annotations

from datetime import datetime, timezone

from tradingagents.contracts import MetricReading
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.pro.ingestion.base import HttpTransport, RequestsTransport

COINMETRICS_BASE = "https://community-api.coinmetrics.io/v4"
BLOCKCHAIN_BASE = "https://api.blockchain.info/charts"
FNG_URL = "https://api.alternative.me/fng/"

# metric name -> CoinMetrics community metric id
_COINMETRICS_METRICS = {
    "MVRV": "CapMVRVCur",
    "REALIZED_CAP_USD": "CapRealUSD",
    "ACTIVE_ADDRESSES": "AdrActCnt",
}

# metric name -> (blockchain.com chart slug, unit)
_BLOCKCHAIN_CHARTS = {
    "HASH_RATE": ("hash-rate", "TH/s"),
    "MINERS_REVENUE_USD": ("miners-revenue", "USD"),
}


class CoinMetricsFeed:
    name = "coinmetrics_community"

    def __init__(self, transport: HttpTransport | None = None, asset: str = "btc"):
        self._transport = transport or RequestsTransport()
        self._asset = asset

    def get_metrics(self) -> list[MetricReading]:
        payload = self._transport.get_json(
            f"{COINMETRICS_BASE}/timeseries/asset-metrics",
            {
                "assets": self._asset,
                "metrics": ",".join(_COINMETRICS_METRICS.values()),
                "frequency": "1d",
                "page_size": 1,
                "paging_from": "end",
            },
        )
        rows = payload.get("data", [])
        if not rows:
            raise NoMarketDataError(self._asset, detail="CoinMetrics returned no rows")
        row = rows[-1]
        as_of = datetime.fromisoformat(row["time"].replace("Z", "+00:00"))
        readings = []
        for name, metric_id in _COINMETRICS_METRICS.items():
            raw = row.get(metric_id)
            if raw is None:
                continue
            readings.append(
                MetricReading(
                    name=name, value=float(raw), as_of=as_of, source=self.name
                )
            )
        return readings


class BlockchainComFeed:
    name = "blockchain_com"

    def __init__(self, transport: HttpTransport | None = None, timespan: str = "30days"):
        self._transport = transport or RequestsTransport()
        self._timespan = timespan

    def get_metrics(self) -> list[MetricReading]:
        readings = []
        for name, (slug, unit) in _BLOCKCHAIN_CHARTS.items():
            payload = self._transport.get_json(
                f"{BLOCKCHAIN_BASE}/{slug}", {"timespan": self._timespan, "format": "json"}
            )
            values = payload.get("values", [])
            if not values:
                continue
            latest = values[-1]
            readings.append(
                MetricReading(
                    name=name,
                    value=float(latest["y"]),
                    unit=unit,
                    as_of=datetime.fromtimestamp(latest["x"], tz=timezone.utc),
                    source=self.name,
                )
            )
        if not readings:
            raise NoMarketDataError("BTC", detail="blockchain.com returned no chart values")
        return readings


class FearGreedFeed:
    name = "fear_greed"

    def __init__(self, transport: HttpTransport | None = None):
        self._transport = transport or RequestsTransport()

    def get_metrics(self) -> list[MetricReading]:
        payload = self._transport.get_json(FNG_URL, {"limit": 1})
        entries = payload.get("data", [])
        if not entries:
            raise NoMarketDataError("BTC", detail="fear&greed API returned no data")
        entry = entries[0]
        return [
            MetricReading(
                name="FEAR_GREED_INDEX",
                value=float(entry["value"]),
                unit="0-100",
                as_of=datetime.fromtimestamp(int(entry["timestamp"]), tz=timezone.utc),
                source=self.name,
            )
        ]
