from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Iterable

import pandas as pd

from tradingagents.dataflows.errors import DataVendorError


class FreshnessStatus(StrEnum):
    FRESH = "fresh"
    DELAYED = "delayed"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class MarketDataUnavailable(DataVendorError):
    """Raised when one provider cannot return usable market data."""


@dataclass(frozen=True)
class MarketBar:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class MarketSnapshot:
    ticker: str
    requested_date: str
    source: str
    as_of_utc: str
    freshness: FreshnessStatus
    last_bar: MarketBar | None
    bars: list[MarketBar]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["freshness"] = self.freshness.value
        return data


def _parse_dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_freshness(
    *,
    last_bar_ts: datetime | None,
    requested_date: str,
    now_utc: datetime | None = None,
    stale_after_seconds: int = 900,
) -> FreshnessStatus:
    if last_bar_ts is None:
        return FreshnessStatus.UNAVAILABLE

    now = now_utc or datetime.now(timezone.utc)
    last_bar_utc = _parse_dt(last_bar_ts)
    requested = pd.Timestamp(requested_date).date()

    if last_bar_utc.date() < requested:
        return FreshnessStatus.STALE

    age_seconds = (now - last_bar_utc).total_seconds()
    if age_seconds <= stale_after_seconds:
        return FreshnessStatus.FRESH
    return FreshnessStatus.STALE


def normalize_ohlcv_frame(df: pd.DataFrame, *, source: str) -> pd.DataFrame:
    if df is None or df.empty:
        raise MarketDataUnavailable(f"{source}: empty OHLCV frame")

    renamed = {}
    for col in df.columns:
        key = str(col).strip().lower()
        if key in {"date", "datetime", "timestamp", "time"}:
            renamed[col] = "timestamp"
        elif key in {"open", "开盘"}:
            renamed[col] = "open"
        elif key in {"high", "最高"}:
            renamed[col] = "high"
        elif key in {"low", "最低"}:
            renamed[col] = "low"
        elif key in {"close", "收盘", "adj close", "adjusted close"}:
            renamed[col] = "close"
        elif key in {"volume", "vol", "成交量"}:
            renamed[col] = "volume"

    out = df.rename(columns=renamed).copy()
    if "timestamp" not in out.columns:
        out = out.reset_index().rename(columns={out.index.name or "index": "timestamp"})

    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [col for col in required if col not in out.columns]
    if missing:
        raise MarketDataUnavailable(f"{source}: missing OHLCV columns {missing}")

    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce", utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["timestamp", "close"]).sort_values("timestamp")
    if out.empty:
        raise MarketDataUnavailable(f"{source}: no valid OHLCV rows")
    return out[required]


def bars_from_frame(df: pd.DataFrame, *, source: str) -> list[MarketBar]:
    clean = normalize_ohlcv_frame(df, source=source)
    bars: list[MarketBar] = []
    for row in clean.itertuples(index=False):
        bars.append(
            MarketBar(
                timestamp=row.timestamp.isoformat(),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
            )
        )
    return bars


def snapshot_from_bars(
    *,
    ticker: str,
    requested_date: str,
    source: str,
    bars: Iterable[MarketBar],
    stale_after_seconds: int = 900,
    warnings: list[str] | None = None,
) -> MarketSnapshot:
    materialized = list(bars)
    last_bar = materialized[-1] if materialized else None
    freshness = classify_freshness(
        last_bar_ts=_parse_dt(last_bar.timestamp) if last_bar else None,
        requested_date=requested_date,
        stale_after_seconds=stale_after_seconds,
    )
    return MarketSnapshot(
        ticker=ticker.upper(),
        requested_date=requested_date,
        source=source,
        as_of_utc=utc_now_iso(),
        freshness=freshness,
        last_bar=last_bar,
        bars=materialized,
        warnings=list(warnings or []),
    )


def format_market_snapshot(snapshot: MarketSnapshot) -> str:
    lines = [
        f"# Market snapshot for {snapshot.ticker}",
        "",
        f"- Requested date: {snapshot.requested_date}",
        f"- Source: {snapshot.source}",
        f"- As of UTC: {snapshot.as_of_utc}",
        f"- Freshness: {snapshot.freshness.value}",
    ]
    if snapshot.last_bar:
        lines.extend(
            [
                f"- Last close: {snapshot.last_bar.close}",
                f"- Last bar timestamp: {snapshot.last_bar.timestamp}",
                f"- Last bar volume: {snapshot.last_bar.volume}",
            ]
        )
    if snapshot.warnings:
        lines.append("")
        lines.append("## Warnings")
        for warning in snapshot.warnings:
            lines.append(f"- {warning}")

    lines.append("")
    lines.append("## Recent OHLCV")
    lines.append("| timestamp | open | high | low | close | volume |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for bar in snapshot.bars[-10:]:
        lines.append(
            f"| {bar.timestamp} | {bar.open:.4f} | {bar.high:.4f} | "
            f"{bar.low:.4f} | {bar.close:.4f} | {bar.volume:.0f} |"
        )
    return "\n".join(lines) + "\n"
