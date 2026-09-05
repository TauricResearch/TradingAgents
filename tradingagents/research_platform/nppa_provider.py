"""Official National Press and Publication Administration approval adapter."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from datetime import date, datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from parsel import Selector

from .game_approvals import GameApprovalKind, GameApprovalRecord, make_approval_id

_INDEX_URLS = {
    GameApprovalKind.DOMESTIC: "https://www.nppa.gov.cn/bsfw/jggs/yxspjg/gcwlyxspxx/",
    GameApprovalKind.IMPORTED: "https://www.nppa.gov.cn/bsfw/jggs/yxspjg/jkwlyxspxx/",
}
_PAGE_DATE = re.compile(r"/t(?P<date>\d{8})_\d+\.html$")


class NppaProviderError(RuntimeError):
    """Raised when an official page cannot be fetched or normalized."""


class NppaApprovalProvider:
    """Fetch and normalize NPPA domestic/imported approval tables."""

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        fetch_text: Callable[[str], str] | None = None,
        now: Callable[[], datetime] | None = None,
    ):
        self.timeout = timeout
        self._fetch_text = fetch_text or self._request_text
        self._now = now or (lambda: datetime.now(timezone.utc))

    def fetch(
        self,
        start: date,
        end: date,
        *,
        kinds: Iterable[GameApprovalKind] = (
            GameApprovalKind.DOMESTIC,
            GameApprovalKind.IMPORTED,
        ),
    ) -> list[GameApprovalRecord]:
        if start > end:
            raise ValueError("start must not be after end")
        records: dict[str, GameApprovalRecord] = {}
        for kind in kinds:
            for source_url, available_as_of in self.discover_pages(kind):
                # Annual imported pages may be published before later rows are appended.
                if available_as_of.year < start.year or available_as_of.year > end.year + 1:
                    continue
                for record in self.parse_page(
                    self._fetch_text(source_url),
                    source_url=source_url,
                    kind=kind,
                    available_as_of=available_as_of,
                ):
                    if start <= record.approval_date <= end:
                        records[record.approval_id] = record
        return sorted(records.values(), key=lambda item: (item.approval_date, item.approval_id))

    def discover_pages(self, kind: GameApprovalKind) -> list[tuple[str, date]]:
        index_url = _INDEX_URLS[kind]
        selector = Selector(self._fetch_text(index_url))
        pages: dict[str, date] = {}
        for anchor in selector.xpath("//a[@href]"):
            href = anchor.xpath("./@href").get() or ""
            source_url = urljoin(index_url, href)
            if urlparse(source_url).hostname != "www.nppa.gov.cn":
                continue
            match = _PAGE_DATE.search(urlparse(source_url).path)
            if match:
                pages[source_url] = date.fromisoformat(
                    f"{match['date'][:4]}-{match['date'][4:6]}-{match['date'][6:]}"
                )
        return sorted(pages.items(), key=lambda item: item[1], reverse=True)

    def parse_page(
        self,
        html: str,
        *,
        source_url: str,
        kind: GameApprovalKind,
        available_as_of: date,
    ) -> list[GameApprovalRecord]:
        selector = Selector(html)
        records: list[GameApprovalRecord] = []
        retrieved_at = self._now()
        for row in selector.xpath("//table//tr"):
            cells = [_cell_text(cell) for cell in row.xpath("./th|./td")]
            if not cells or cells[0] == "\u5e8f\u53f7":
                continue
            parsed = _parse_cells(cells)
            if parsed is None:
                continue
            game_name, category, publisher, operator, number, isbn, approved_on = parsed
            records.append(
                GameApprovalRecord(
                    approval_id=make_approval_id(kind, number, game_name),
                    kind=kind,
                    game_name=game_name,
                    application_category=category,
                    publishing_entity=publisher,
                    operating_entity=operator,
                    approval_number=number,
                    isbn=isbn or None,
                    approval_date=approved_on,
                    source_url=source_url,
                    available_as_of=max(available_as_of, approved_on),
                    retrieved_at=retrieved_at,
                )
            )
        if not records:
            raise NppaProviderError(f"No approval rows found at {source_url}")
        return records

    def _request_text(self, url: str) -> str:
        try:
            response = requests.get(
                url,
                timeout=self.timeout,
                headers={"User-Agent": "TradingAgents personal research/0.3"},
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise NppaProviderError(f"NPPA request failed for {url}: {error}") from error
        response.encoding = response.apparent_encoding or "utf-8"
        return response.text


def _cell_text(cell) -> str:
    return " ".join(part.strip() for part in cell.xpath(".//text()").getall() if part.strip())


def _parse_cells(
    cells: list[str],
) -> tuple[str, str | None, str, str, str, str | None, date] | None:
    # NPPA currently publishes seven-cell rows when the category column is blank,
    # while some historical/imported tables include all eight columns.
    if len(cells) == 7:
        _, game_name, publisher, operator, number, isbn, raw_date = cells
        category = None
    elif len(cells) >= 8:
        _, game_name, category, publisher, operator, number, isbn, raw_date = cells[:8]
        category = category or None
    else:
        return None
    try:
        approved_on = _parse_date(raw_date)
    except ValueError:
        return None
    if not all((game_name, publisher, operator, number)):
        return None
    return game_name, category, publisher, operator, number, isbn or None, approved_on


def _parse_date(value: str) -> date:
    normalized = re.sub(r"[\u5e74/.]", "-", value.strip())
    normalized = re.sub(r"\u6708", "-", normalized)
    normalized = normalized.replace("\u65e5", "").strip("-")
    parts = normalized.split("-")
    if len(parts) != 3:
        raise ValueError(f"Unsupported approval date: {value}")
    return date(int(parts[0]), int(parts[1]), int(parts[2]))
