from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Iterable

import pandas as pd
from dateutil.relativedelta import relativedelta

from tradingagents.dataflows import akshare, futu, polygon, y_finance
from tradingagents.dataflows.errors import DataVendorError
from tradingagents.dataflows.market_calendar import (
    expected_trading_sessions,
    is_allowed_market_closure,
)
from tradingagents.dataflows.market_snapshot import (
    MarketDataUnavailable,
    classify_freshness,
    normalize_ohlcv_frame,
    utc_now_iso,
)


@dataclass(frozen=True)
class FusedMarketBar:
    date: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str


@dataclass(frozen=True)
class FusedMarketSnapshot:
    ticker: str
    requested_date: str
    as_of_utc: str
    freshness: str
    expected_sessions: list[str]
    missing_sessions: list[str]
    allowed_missing_sessions: list[str]
    provider_errors: dict[str, str] = field(default_factory=dict)
    bars: list[FusedMarketBar] = field(default_factory=list)

    @property
    def coverage_ratio(self) -> float:
        if not self.expected_sessions:
            return 1.0
        covered = len(self.expected_sessions) - len(self.missing_sessions)
        return covered / len(self.expected_sessions)

    def to_dict(self) -> dict:
        return asdict(self)


def _bars_from_source_frame(source: str, frame: pd.DataFrame) -> list[FusedMarketBar]:
    clean = normalize_ohlcv_frame(frame, source=source)
    bars: list[FusedMarketBar] = []
    for row in clean.itertuples(index=False):
        date = row.timestamp.date().isoformat()
        bars.append(
            FusedMarketBar(
                date=date,
                timestamp=row.timestamp.isoformat(),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
                source=source,
            )
        )
    return bars


def fuse_source_frames(
    *,
    ticker: str,
    requested_date: str,
    expected_sessions: list[str],
    source_frames: Iterable[tuple[str, pd.DataFrame]],
    allowed_missing_sessions: list[str] | None = None,
    provider_errors: dict[str, str] | None = None,
    stale_after_seconds: int = 900,
) -> FusedMarketSnapshot:
    bars_by_date: dict[str, FusedMarketBar] = {}
    expected = set(expected_sessions)
    errors = dict(provider_errors or {})

    for source, frame in source_frames:
        try:
            for bar in _bars_from_source_frame(source, frame):
                if bar.date in expected and bar.date not in bars_by_date:
                    bars_by_date[bar.date] = bar
        except MarketDataUnavailable as exc:
            errors[source] = str(exc)

    bars = [bars_by_date[session] for session in expected_sessions if session in bars_by_date]
    missing = [session for session in expected_sessions if session not in bars_by_date]
    last_bar = bars[-1] if bars else None
    freshness = classify_freshness(
        last_bar_ts=pd.Timestamp(last_bar.timestamp).to_pydatetime() if last_bar else None,
        requested_date=requested_date,
        stale_after_seconds=stale_after_seconds,
    ).value

    return FusedMarketSnapshot(
        ticker=ticker.upper(),
        requested_date=requested_date,
        as_of_utc=utc_now_iso(),
        freshness=freshness,
        expected_sessions=expected_sessions,
        missing_sessions=missing,
        allowed_missing_sessions=list(allowed_missing_sessions or []),
        provider_errors=errors,
        bars=bars,
    )


def format_fused_market_snapshot(snapshot: FusedMarketSnapshot) -> str:
    covered = len(snapshot.expected_sessions) - len(snapshot.missing_sessions)
    coverage = f"{snapshot.coverage_ratio:.2%}"
    lines = [
        f"# Market snapshot for {snapshot.ticker}",
        "",
        f"- Requested date: {snapshot.requested_date}",
        "- Source: fused",
        f"- As of UTC: {snapshot.as_of_utc}",
        f"- Freshness: {snapshot.freshness}",
        f"- Coverage: {covered}/{len(snapshot.expected_sessions)} expected sessions ({coverage})",
    ]
    if snapshot.missing_sessions:
        lines.append(f"- Missing sessions: {', '.join(snapshot.missing_sessions)}")
    if snapshot.allowed_missing_sessions:
        lines.append(
            f"- Allowed missing sessions: {', '.join(snapshot.allowed_missing_sessions)}"
        )
    if snapshot.provider_errors:
        lines.append("")
        lines.append("## Provider Errors")
        for provider, error in snapshot.provider_errors.items():
            lines.append(f"- {provider}: {error}")

    lines.append("")
    lines.append("## Fused OHLCV Chart")
    lines.append("| date | open | high | low | close | volume | source |")
    lines.append("|---|---:|---:|---:|---:|---:|---|")
    for bar in snapshot.bars:
        lines.append(
            f"| {bar.date} | {bar.open:.4f} | {bar.high:.4f} | "
            f"{bar.low:.4f} | {bar.close:.4f} | {bar.volume:.0f} | {bar.source} |"
        )
    return "\n".join(lines) + "\n"


OhlcvFetcher = Callable[[str, str, str], pd.DataFrame]


DEFAULT_FETCHERS: dict[str, OhlcvFetcher] = {
    "yfinance": y_finance.fetch_ohlcv_frame,
    "akshare": akshare.fetch_ohlcv_frame,
    "futu": futu.fetch_ohlcv_frame,
    "polygon": polygon.fetch_ohlcv_frame,
}


def _missing_sessions(snapshot: FusedMarketSnapshot) -> list[str]:
    return list(snapshot.missing_sessions)


def _date_bounds(sessions: list[str]) -> tuple[str, str]:
    return min(sessions), max(sessions)


def _allowed_missing_sessions(start_date: str, end_date: str) -> list[str]:
    allowed = []
    for day in pd.date_range(pd.Timestamp(start_date), pd.Timestamp(end_date), freq="D"):
        if is_allowed_market_closure(day):
            allowed.append(day.strftime("%Y-%m-%d"))
    return allowed


def fetch_fused_market_snapshot(
    ticker: str,
    curr_date: str,
    *,
    lookback_days: int = 10,
    stale_after_seconds: int = 900,
    providers: list[str] | None = None,
    fetchers: dict[str, OhlcvFetcher] | None = None,
) -> FusedMarketSnapshot:
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_date = (curr_dt - relativedelta(days=lookback_days)).strftime("%Y-%m-%d")
    expected = expected_trading_sessions(start_date, curr_date)
    allowed_missing = _allowed_missing_sessions(start_date, curr_date)
    provider_order = providers or ["yfinance", "akshare", "futu", "polygon"]
    fetcher_map = fetchers or DEFAULT_FETCHERS

    source_frames: list[tuple[str, pd.DataFrame]] = []
    provider_errors: dict[str, str] = {}
    remaining = list(expected)

    for index, provider in enumerate(provider_order):
        if not remaining:
            break
        fetcher = fetcher_map.get(provider)
        if fetcher is None:
            provider_errors[provider] = "provider has no OHLCV fetcher"
            continue
        if index == 0:
            fetch_start, fetch_end = start_date, curr_date
        else:
            fetch_start, fetch_end = _date_bounds(remaining)
        try:
            frame = fetcher(ticker, fetch_start, fetch_end)
            source_frames.append((provider, frame))
        except DataVendorError as exc:
            provider_errors[provider] = str(exc)
            continue

        partial = fuse_source_frames(
            ticker=ticker,
            requested_date=curr_date,
            expected_sessions=expected,
            source_frames=source_frames,
            allowed_missing_sessions=allowed_missing,
            provider_errors=provider_errors,
            stale_after_seconds=stale_after_seconds,
        )
        remaining = _missing_sessions(partial)

    return fuse_source_frames(
        ticker=ticker,
        requested_date=curr_date,
        expected_sessions=expected,
        source_frames=source_frames,
        allowed_missing_sessions=allowed_missing,
        provider_errors=provider_errors,
        stale_after_seconds=stale_after_seconds,
    )


def get_market_snapshot(
    ticker: str,
    curr_date: str,
    *,
    lookback_days: int = 10,
    stale_after_seconds: int = 900,
    providers: list[str] | None = None,
) -> str:
    snapshot = fetch_fused_market_snapshot(
        ticker,
        curr_date,
        lookback_days=lookback_days,
        stale_after_seconds=stale_after_seconds,
        providers=providers,
    )
    return format_fused_market_snapshot(snapshot)
