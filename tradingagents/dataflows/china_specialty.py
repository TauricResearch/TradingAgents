"""Safe, degradable A-share specialty-data capability adapters.

The specialty layer intentionally exposes *facts returned by a named source*,
not inferred trading signals.  Exchange announcements are a useful example:
the Shanghai and Shenzhen exchanges are the primary records, while EastMoney's
public bulletin feed is only a keyless fallback when an official endpoint is
unavailable or changes shape.  A failed source never becomes an empty or
invented announcement report.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

import requests

from .china_data import ChinaDataUnavailableError
from .eastmoney import EASTMONEY_DATACENTER_URL, em_get
from .errors import VendorHTTPError
from .ticker_utils import is_a_share_ticker, normalize_ticker_symbol, to_akshare_symbol

SSE_ANNOUNCEMENT_URL = "https://query.sse.com.cn/security/stock/queryCompanyBulletin.do"
SZSE_ANNOUNCEMENT_URL = "https://www.szse.cn/api/disc/announcement/annList"


@dataclass(frozen=True)
class AnnouncementRecord:
    """One source-labeled announcement without interpreted investment meaning."""

    title: str
    published_at: str | None
    source_provider: str
    source_uri: str | None = None
    announcement_id: str | None = None


class AnnouncementProvider(Protocol):
    """Capability contract for a keyless A-share announcement source."""

    name: str

    def fetch(
        self,
        ticker: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Sequence[AnnouncementRecord]: ...


class SSEAnnouncementProvider:
    """Shanghai Stock Exchange primary announcement provider (zero key)."""

    name = "sse"

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    def fetch(
        self,
        ticker: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Sequence[AnnouncementRecord]:
        code = _require_exchange(ticker, allowed_suffixes=(".SS", ".SH"))
        response = self._session.get(
            SSE_ANNOUNCEMENT_URL,
            params={
                "isPagination": "true",
                "productId": code,
                "securityType": "0101",
                "reportType": "ALL",
                "beginDate": start_date or "",
                "endDate": end_date or "",
                "pageHelp.pageSize": "50",
                "pageHelp.pageNo": "1",
            },
            headers={"Referer": "https://www.sse.com.cn/", "Accept": "application/json"},
            timeout=10,
        )
        payload = _json_object(response, self.name)
        records = _parse_sse_records(payload)
        if not records:
            raise ChinaDataUnavailableError(f"SSE returned no announcement records for {ticker}.")
        _capture_vendor_raw(payload, metadata={"provider": self.name, "dataset": "announcements", "ticker": ticker})
        return records


class SZSEAnnouncementProvider:
    """Shenzhen Stock Exchange primary announcement provider (zero key)."""

    name = "szse"

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    def fetch(
        self,
        ticker: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Sequence[AnnouncementRecord]:
        code = _require_exchange(ticker, allowed_suffixes=(".SZ",))
        response = self._session.get(
            SZSE_ANNOUNCEMENT_URL,
            params={
                "secCode": code,
                "channelCode": "fixed_disc",
                "pageSize": "50",
                "pageNum": "1",
                "seDate": _date_window(start_date, end_date),
            },
            headers={"Referer": "https://www.szse.cn/", "Accept": "application/json"},
            timeout=10,
        )
        payload = _json_object(response, self.name)
        records = _parse_szse_records(payload)
        if not records:
            raise ChinaDataUnavailableError(f"SZSE returned no announcement records for {ticker}.")
        _capture_vendor_raw(payload, metadata={"provider": self.name, "dataset": "announcements", "ticker": ticker})
        return records


class EastMoneyAnnouncementFallback:
    """Keyless public fallback; never presented as an exchange primary record."""

    name = "eastmoney"

    def fetch(
        self,
        ticker: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Sequence[AnnouncementRecord]:
        code = _require_a_share_code(ticker)
        payload = em_get(
            EASTMONEY_DATACENTER_URL,
            params={
                "reportName": "RPT_PUBLIC_BULLETIN",
                "columns": "SECURITY_CODE,SECURITY_NAME,NOTICE_DATE,TITLE,ARTICLE_CODE,INFO_CODE",
                "filter": f'(SECURITY_CODE="{code}")',
                "pageNumber": "1",
                "pageSize": "50",
                "sortColumns": "NOTICE_DATE",
                "sortTypes": "-1",
                "source": "WEB",
                "client": "WEB",
            },
        )
        records = _parse_eastmoney_records(payload)
        records = _filter_records(records, start_date=start_date, end_date=end_date)
        if not records:
            raise ChinaDataUnavailableError(f"EastMoney returned no announcement records for {ticker}.")
        _capture_vendor_raw(payload, metadata={"provider": self.name, "dataset": "announcements", "ticker": ticker})
        return records


def get_a_share_exchange_announcements(
    ticker: str,
    start_date: str | None = None,
    end_date: str | None = None,
    *,
    providers: Iterable[AnnouncementProvider] | None = None,
) -> str:
    """Fetch announcements via primary exchange then keyless public fallback.

    The returned report identifies the provider used.  If every eligible
    provider fails, a typed ``ChinaDataUnavailableError`` carries the attempted
    provider names; callers can safely continue their wider research workflow.
    """
    canonical = normalize_ticker_symbol(ticker)
    records = fetch_a_share_exchange_announcements(
        canonical,
        start_date=start_date,
        end_date=end_date,
        providers=providers,
    )
    return render_announcement_report(canonical, records, start_date=start_date, end_date=end_date)


def fetch_a_share_exchange_announcements(
    ticker: str,
    start_date: str | None = None,
    end_date: str | None = None,
    *,
    providers: Iterable[AnnouncementProvider] | None = None,
) -> Sequence[AnnouncementRecord]:
    """Return source-labelled official announcement facts for a public fallback."""
    canonical = normalize_ticker_symbol(ticker)
    candidates = tuple(providers or _providers_for(canonical))
    failures: list[str] = []
    for provider in candidates:
        try:
            records = provider.fetch(canonical, start_date=start_date, end_date=end_date)
        except (ChinaDataUnavailableError, VendorHTTPError, requests.RequestException) as exc:
            failures.append(f"{provider.name}: {type(exc).__name__}")
            continue
        if records:
            return records
        failures.append(f"{provider.name}: empty")
    attempted = ", ".join(failures) or "no eligible provider"
    raise ChinaDataUnavailableError(f"No announcement source available for {canonical} ({attempted}).")


def get_a_share_official_news(
    ticker: str,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Present exchange announcements in the common curated-news item format.

    This is intentionally a fallback-only, public official-record adapter.  It
    does not scrape a commercial news site or make the unsupported claim that
    an announcement is a complete replacement for market news.
    """
    records = fetch_a_share_exchange_announcements(
        ticker,
        start_date=start_date,
        end_date=end_date,
    )
    return {
        "source": "china_exchange",
        "items": [
            {
                "title": record.title,
                "url": record.source_uri or "",
                "content": "Official exchange announcement",
                "published": record.published_at or "",
                "publisher": record.source_provider,
                "source": "china_exchange",
                "announcement_id": record.announcement_id,
            }
            for record in records
        ],
    }


def render_announcement_report(
    ticker: str,
    records: Sequence[AnnouncementRecord],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """Render only source facts; absent dates/links remain explicitly absent."""
    if not records:
        raise ChinaDataUnavailableError(f"No announcement records available for {ticker}.")
    source = records[0].source_provider
    lines = [
        f"# China A-share announcements for {normalize_ticker_symbol(ticker)}",
        f"# Source: {source}",
        "# Primary records are exchange announcements; EastMoney is a public fallback.",
        f"# Requested window: {start_date or '?'} to {end_date or '?'}",
        "",
        "| Published at | Title | Source URI | Announcement ID |",
        "|---|---|---|---|",
    ]
    for record in records:
        lines.append(
            "| {date} | {title} | {uri} | {announcement_id} |".format(
                date=_markdown_cell(record.published_at or "N/A"),
                title=_markdown_cell(record.title),
                uri=_markdown_cell(record.source_uri or "N/A"),
                announcement_id=_markdown_cell(record.announcement_id or "N/A"),
            )
        )
    return "\n".join(lines)


def _providers_for(canonical: str) -> tuple[AnnouncementProvider, ...]:
    if canonical.endswith((".SS", ".SH")):
        return (SSEAnnouncementProvider(), EastMoneyAnnouncementFallback())
    if canonical.endswith(".SZ"):
        return (SZSEAnnouncementProvider(), EastMoneyAnnouncementFallback())
    # Beijing listings do not share either of the two official endpoint
    # contracts above, so only expose the explicit public fallback for now.
    if canonical.endswith(".BJ"):
        return (EastMoneyAnnouncementFallback(),)
    raise ChinaDataUnavailableError(f"{canonical} is not recognized as an A-share ticker.")


def _require_a_share_code(ticker: str) -> str:
    if not is_a_share_ticker(ticker):
        raise ChinaDataUnavailableError(f"{ticker} is not recognized as an A-share ticker.")
    return to_akshare_symbol(ticker)


def _require_exchange(ticker: str, *, allowed_suffixes: tuple[str, ...]) -> str:
    canonical = normalize_ticker_symbol(ticker)
    if not canonical.endswith(allowed_suffixes):
        raise ChinaDataUnavailableError(f"{canonical} is not served by this exchange announcement provider.")
    return _require_a_share_code(canonical)


def _json_object(response: requests.Response, provider: str) -> Mapping[str, Any]:
    if not 200 <= int(response.status_code) < 300:
        raise VendorHTTPError(provider, int(response.status_code))
    try:
        payload = response.json()
    except ValueError as exc:
        raise VendorHTTPError(provider, int(response.status_code), "invalid JSON response") from exc
    if not isinstance(payload, Mapping):
        raise VendorHTTPError(provider, int(response.status_code), "JSON root is not an object")
    return payload


def _parse_sse_records(payload: Mapping[str, Any]) -> list[AnnouncementRecord]:
    rows = payload.get("result") or payload.get("data") or []
    if isinstance(rows, Mapping):
        rows = rows.get("data") or rows.get("list") or []
    if not isinstance(rows, list):
        return []
    return [_record_from_mapping(row, "sse") for row in rows if isinstance(row, Mapping) and _title(row)]


def _parse_szse_records(payload: Mapping[str, Any]) -> list[AnnouncementRecord]:
    rows = payload.get("data") or []
    if isinstance(rows, Mapping):
        rows = rows.get("list") or rows.get("data") or []
    if not isinstance(rows, list):
        return []
    return [_record_from_mapping(row, "szse") for row in rows if isinstance(row, Mapping) and _title(row)]


def _parse_eastmoney_records(payload: Mapping[str, Any]) -> list[AnnouncementRecord]:
    result = payload.get("result")
    rows = result.get("data") if isinstance(result, Mapping) else payload.get("data")
    if not isinstance(rows, list):
        return []
    return [_record_from_mapping(row, "eastmoney") for row in rows if isinstance(row, Mapping) and _title(row)]


def _record_from_mapping(row: Mapping[str, Any], provider: str) -> AnnouncementRecord:
    announcement_id = _first_text(row, "ARTICLE_CODE", "announcementId", "id", "bulletinId")
    uri = _first_text(row, "URL", "url", "adjunctUrl", "pdfUrl", "attachPath")
    # SZSE annList returns attachPath as a server-relative path; prepend the
    # static CDN prefix so the record carries a directly downloadable PDF link.
    if provider == "szse" and uri and not uri.startswith("http"):
        uri = "https://disc.static.szse.cn/download" + uri
    return AnnouncementRecord(
        title=_title(row) or "N/A",
        published_at=_first_text(row, "NOTICE_DATE", "publishTime", "publishDate", "SSEDATE", "disclosureTime"),
        source_provider=provider,
        source_uri=uri,
        announcement_id=announcement_id,
    )


def _title(row: Mapping[str, Any]) -> str | None:
    return _first_text(row, "TITLE", "title", "bulletinTitle", "announcementTitle")


def _first_text(row: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _filter_records(
    records: Sequence[AnnouncementRecord], *, start_date: str | None, end_date: str | None
) -> list[AnnouncementRecord]:
    if not start_date and not end_date:
        return list(records)
    return [record for record in records if not record.published_at or _in_window(record.published_at, start_date, end_date)]


def _in_window(value: str, start_date: str | None, end_date: str | None) -> bool:
    observed = value[:10]
    try:
        date.fromisoformat(observed)
    except ValueError:
        return True  # unknown provider format: retain it rather than falsifying a date filter.
    return (not start_date or observed >= start_date) and (not end_date or observed <= end_date)


def _date_window(start_date: str | None, end_date: str | None) -> str:
    if not start_date and not end_date:
        return ""
    return f"{start_date or ''}~{end_date or ''}"


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _capture_vendor_raw(payload: Any, *, metadata: Mapping[str, str]) -> None:
    """Load cross-cutting observability after a successful data call only."""
    from tradingagents.observability.provenance import capture_vendor_raw

    capture_vendor_raw(payload, metadata=dict(metadata))
