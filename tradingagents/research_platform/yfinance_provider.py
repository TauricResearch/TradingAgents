"""Direct yfinance provider for normalized research-platform data contracts."""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from tradingagents.dataflows.symbol_utils import normalize_symbol

from .data_contracts import (
    DataProvenance,
    FundamentalSnapshot,
    InstrumentIdentity,
    NewsItem,
    PriceBar,
)

TickerFactory = Callable[[str], Any]


class YFinanceDataUnavailableError(RuntimeError):
    """Raised when yfinance returns no usable data for a requested artifact."""


class YFinanceProvider:
    """Fetch yfinance data directly into normalized platform contracts.

    This provider bypasses legacy markdown/CSV formatting. When using the real
    yfinance ticker factory it also points yfinance's SQLite timezone cache at a
    writable directory, because the library's default cache path can fail in
    restricted desktop/sandbox environments.
    """

    name = "yfinance"

    def __init__(
        self,
        *,
        ticker_factory: TickerFactory | None = None,
        news_limit: int = 20,
        cache_dir: str | Path | None = None,
    ):
        if ticker_factory is None:
            _configure_yfinance_cache(cache_dir)
        self._ticker_factory = ticker_factory or _default_ticker_factory
        self._news_limit = news_limit

    def get_price_bars(
        self,
        identity: InstrumentIdentity,
        start: date,
        end: date,
        *,
        as_of_date: date | None = None,
    ) -> Sequence[PriceBar]:
        if end < start:
            raise ValueError("end must be on or after start")

        availability_date = as_of_date or end
        canonical = _canonical_symbol(identity)
        ticker = self._ticker_factory(canonical)
        end_exclusive = (end + timedelta(days=1)).isoformat()
        try:
            frame = ticker.history(start=start.isoformat(), end=end_exclusive)
        except Exception as exc:
            raise YFinanceDataUnavailableError(
                f"yfinance price data unavailable for {identity.symbol}: {exc}"
            ) from exc

        if frame is None or frame.empty:
            raise YFinanceDataUnavailableError(
                f"no yfinance price rows for {identity.symbol} between {start} and {end}"
            )

        bars: list[PriceBar] = []
        for row_date, row in frame.iterrows():
            bar_date = _index_date(row_date)
            if bar_date < start or bar_date > end or bar_date > availability_date:
                continue
            bars.append(
                PriceBar(
                    symbol=identity.symbol,
                    date=bar_date,
                    open=_required_float(row, "Open"),
                    high=_required_float(row, "High"),
                    low=_required_float(row, "Low"),
                    close=_required_float(row, "Close"),
                    adjusted_close=_optional_float(row, "Adj Close")
                    or _required_float(row, "Close"),
                    volume=_optional_int(row, "Volume"),
                    currency=identity.currency,
                    provenance=_provenance(
                        self.name,
                        availability_date,
                        source="yfinance.Ticker.history",
                        vendor_symbol=canonical,
                    ),
                )
            )
        return bars

    def get_fundamentals(
        self,
        identity: InstrumentIdentity,
        *,
        as_of_date: date | None = None,
    ) -> Sequence[FundamentalSnapshot]:
        availability_date = as_of_date or date.today()
        canonical = _canonical_symbol(identity)
        ticker = self._ticker_factory(canonical)
        try:
            info = getattr(ticker, "info", None)
            if callable(info):
                info = info()
        except Exception as exc:
            raise YFinanceDataUnavailableError(
                f"yfinance fundamentals unavailable for {identity.symbol}: {exc}"
            ) from exc
        if not isinstance(info, Mapping) or not info:
            raise YFinanceDataUnavailableError(f"no yfinance fundamentals for {identity.symbol}")

        metrics = _normalize_info_metrics(info)
        if not metrics:
            raise YFinanceDataUnavailableError(
                f"no usable yfinance fundamental fields for {identity.symbol}"
            )

        return [
            FundamentalSnapshot(
                symbol=identity.symbol,
                period_end=availability_date,
                fiscal_period="snapshot",
                currency=identity.currency or _string_or_none(info.get("currency")),
                metrics=metrics,
                provenance=_provenance(
                    self.name,
                    availability_date,
                    source="yfinance.Ticker.info",
                    vendor_symbol=canonical,
                ),
            )
        ]

    def get_news(
        self,
        identity: InstrumentIdentity,
        start: date,
        end: date,
        *,
        as_of_date: date | None = None,
    ) -> Sequence[NewsItem]:
        if end < start:
            raise ValueError("end must be on or after start")

        availability_date = as_of_date or end
        canonical = _canonical_symbol(identity)
        ticker = self._ticker_factory(canonical)
        try:
            raw_news = ticker.get_news(count=self._news_limit)
        except Exception as exc:
            raise YFinanceDataUnavailableError(
                f"yfinance news unavailable for {identity.symbol}: {exc}"
            ) from exc
        if not raw_news:
            return []

        items: list[NewsItem] = []
        for article in raw_news:
            parsed = _parse_yfinance_article(article)
            if parsed is None:
                continue
            published_at = parsed["published_at"]
            published_date = published_at.date()
            if published_date < start or published_date > end:
                continue
            if published_date > availability_date:
                continue
            items.append(
                NewsItem(
                    symbol=identity.symbol,
                    title=parsed["title"],
                    published_at=published_at,
                    as_of_date=availability_date,
                    provider=parsed["provider"],
                    url=parsed["url"],
                    summary=parsed["summary"],
                    source_id=_stable_source_id(
                        self.name,
                        canonical,
                        parsed["title"],
                        parsed["url"],
                    ),
                )
            )
        return items


def _default_ticker_factory(symbol: str) -> Any:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise YFinanceDataUnavailableError(
            "yfinance is not installed; install it to use the live provider"
        ) from exc

    return yf.Ticker(symbol)


def _configure_yfinance_cache(cache_dir: str | Path | None) -> None:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise YFinanceDataUnavailableError(
            "yfinance is not installed; install it to use the live provider"
        ) from exc

    path = Path(
        cache_dir
        or os.getenv("TRADINGAGENTS_YFINANCE_CACHE_DIR")
        or Path(tempfile.gettempdir()) / "tradingagents-yfinance-cache"
    )
    try:
        path.mkdir(parents=True, exist_ok=True)
        if hasattr(yf, "set_tz_cache_location"):
            yf.set_tz_cache_location(str(path))
    except Exception as exc:
        raise YFinanceDataUnavailableError(
            f"could not initialize yfinance cache at {path}: {exc}"
        ) from exc


def _canonical_symbol(identity: InstrumentIdentity) -> str:
    return identity.vendor_symbol or normalize_symbol(identity.symbol)


def _provenance(
    provider: str,
    as_of_date: date,
    *,
    source: str,
    vendor_symbol: str,
) -> DataProvenance:
    return DataProvenance(
        provider=provider,
        as_of_date=as_of_date,
        retrieved_at=datetime.now(timezone.utc),
        source=source,
        vendor_symbol=vendor_symbol,
    )


def _index_date(value: Any) -> date:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is not None:
        parsed = parsed.tz_convert(None)
    return parsed.date()


def _required_float(row: pd.Series, column: str) -> float:
    value = _optional_float(row, column)
    if value is None:
        raise ValueError(f"missing required yfinance column: {column}")
    return value


def _optional_float(row: pd.Series, column: str) -> float | None:
    if column not in row:
        return None
    value = row[column]
    if pd.isna(value):
        return None
    return float(value)


def _optional_int(row: pd.Series, column: str) -> int | None:
    value = _optional_float(row, column)
    return None if value is None else int(value)


_INFO_FIELDS = {
    "longName": "name",
    "sector": "sector",
    "industry": "industry",
    "marketCap": "market_cap",
    "trailingPE": "pe_ratio_ttm",
    "forwardPE": "forward_pe",
    "pegRatio": "peg_ratio",
    "priceToBook": "price_to_book",
    "trailingEps": "eps_ttm",
    "forwardEps": "forward_eps",
    "dividendYield": "dividend_yield",
    "beta": "beta",
    "fiftyTwoWeekHigh": "fifty_two_week_high",
    "fiftyTwoWeekLow": "fifty_two_week_low",
    "fiftyDayAverage": "fifty_day_average",
    "twoHundredDayAverage": "two_hundred_day_average",
    "totalRevenue": "revenue_ttm",
    "grossProfits": "gross_profit",
    "ebitda": "ebitda",
    "netIncomeToCommon": "net_income_common",
    "profitMargins": "profit_margin",
    "operatingMargins": "operating_margin",
    "returnOnEquity": "return_on_equity",
    "returnOnAssets": "return_on_assets",
    "debtToEquity": "debt_to_equity",
    "currentRatio": "current_ratio",
    "bookValue": "book_value",
    "freeCashflow": "free_cash_flow",
    "currency": "currency",
}


def _normalize_info_metrics(info: Mapping[str, Any]) -> dict[str, float | int | str | None]:
    metrics: dict[str, float | int | str | None] = {}
    for source_key, target_key in _INFO_FIELDS.items():
        value = info.get(source_key)
        if value is None:
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float | str):
            metrics[target_key] = value
    return metrics


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _parse_yfinance_article(article: Mapping[str, Any]) -> dict[str, Any] | None:
    if "content" in article and isinstance(article["content"], Mapping):
        content = article["content"]
        title = _string_or_none(content.get("title"))
        summary = _string_or_none(content.get("summary"))
        provider_obj = content.get("provider") or {}
        provider = (
            _string_or_none(provider_obj.get("displayName"))
            if isinstance(provider_obj, Mapping)
            else None
        )
        url = _extract_url(content.get("canonicalUrl")) or _extract_url(
            content.get("clickThroughUrl")
        )
        published_at = _parse_pub_date(content.get("pubDate"))
    else:
        title = _string_or_none(article.get("title"))
        summary = _string_or_none(article.get("summary"))
        provider = _string_or_none(article.get("publisher"))
        url = _string_or_none(article.get("link"))
        published_at = _parse_provider_publish_time(article.get("providerPublishTime"))

    if not title or published_at is None:
        return None

    return {
        "title": title,
        "summary": summary,
        "provider": provider or "Yahoo Finance",
        "url": url,
        "published_at": published_at,
    }


def _extract_url(value: Any) -> str | None:
    if isinstance(value, Mapping):
        return _string_or_none(value.get("url"))
    return None


def _parse_pub_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_provider_publish_time(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _stable_source_id(provider: str, symbol: str, title: str, url: str | None) -> str:
    raw = "|".join([provider, symbol, title, url or ""])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"yfinance-news:{digest}"
