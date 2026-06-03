from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterable

import pandas as pd

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
