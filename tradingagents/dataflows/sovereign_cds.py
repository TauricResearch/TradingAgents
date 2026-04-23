"""Dedicated World Government Bonds sovereign CDS client."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

import requests
from bs4 import BeautifulSoup

from .stockstats_utils import YFinanceError

_SOVEREIGN_CDS_ENDPOINT = "https://www.worldgovernmentbonds.com/wp-json/cds/v1/main"
_SOVEREIGN_CDS_HEADERS = {
    "Content-Type": "application/json; charset=UTF-8",
    "Origin": "https://www.worldgovernmentbonds.com",
    "Referer": "https://www.worldgovernmentbonds.com/sovereign-cds/",
    "User-Agent": "TradingAgents/1.0 (+https://github.com)",
}
_MAJOR_SOVEREIGN_CDS_COUNTRIES = [
    "United States",
    "China",
    "Japan",
    "Germany",
    "United Kingdom",
    "France",
    "Italy",
    "Canada",
    "India",
]
_NUMBER_RE = re.compile(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?")
_LAST_UPDATE_RE = re.compile(r"Last Update:<br>\s*([^<]+)")


@dataclass(frozen=True)
class SovereignCDSRow:
    country: str
    rating: str
    cds_5y: float
    var_1m_pct: float | None
    var_6m_pct: float | None
    implied_pd_pct: float | None
    date_label: str


@dataclass(frozen=True)
class SovereignCDSSnapshot:
    rows: list[SovereignCDSRow]
    last_update: datetime


def _parse_numeric_value(raw: str) -> float | None:
    match = _NUMBER_RE.search((raw or "").replace("%", ""))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _parse_last_update(raw: str) -> datetime:
    try:
        return datetime.strptime(raw.replace("GMT+0", "+0000"), "%d %b %Y %H:%M %z").astimezone(UTC)
    except ValueError as exc:
        raise YFinanceError(f"Unexpected World Government Bonds last-update format: {raw!r}") from exc


class WorldGovernmentBondsCDSClient:
    """Fetch sovereign CDS data directly from World Government Bonds."""

    def __init__(self, timeout: int = 20):
        self.timeout = timeout

    def fetch_snapshot(self) -> SovereignCDSSnapshot:
        response = requests.post(
            _SOVEREIGN_CDS_ENDPOINT,
            json={},
            headers=_SOVEREIGN_CDS_HEADERS,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()

        if not payload.get("success"):
            raise YFinanceError("World Government Bonds CDS endpoint returned an unsuccessful payload.")

        table_html = str(payload.get("table") or "")
        chart_html = str(payload.get("chart") or "")
        if not table_html:
            raise YFinanceError("World Government Bonds CDS endpoint returned no table payload.")

        last_update_match = _LAST_UPDATE_RE.search(chart_html)
        if not last_update_match:
            raise YFinanceError("World Government Bonds CDS endpoint returned no last-update timestamp.")
        last_update = _parse_last_update(last_update_match.group(1).strip())

        soup = BeautifulSoup(table_html, "html.parser")
        rows: list[SovereignCDSRow] = []
        for row in soup.select("tbody tr"):
            cells = row.find_all("td")
            if len(cells) < 8:
                continue

            country = cells[1].get_text(" ", strip=True)
            cds = _parse_numeric_value(cells[3].get_text(" ", strip=True))
            if not country or cds is None:
                continue

            rows.append(
                SovereignCDSRow(
                    country=country,
                    rating=cells[2].get_text(" ", strip=True) or "N/A",
                    cds_5y=cds,
                    var_1m_pct=_parse_numeric_value(cells[4].get_text(" ", strip=True)),
                    var_6m_pct=_parse_numeric_value(cells[5].get_text(" ", strip=True)),
                    implied_pd_pct=_parse_numeric_value(cells[6].get_text(" ", strip=True)),
                    date_label=cells[7].get_text(" ", strip=True) or "N/A",
                )
            )

        if not rows:
            raise YFinanceError("World Government Bonds CDS endpoint returned no CDS rows.")

        return SovereignCDSSnapshot(rows=rows, last_update=last_update)

    @staticmethod
    def is_current_snapshot(snapshot: SovereignCDSSnapshot, now: datetime | None = None) -> bool:
        reference = now or datetime.now(UTC)
        return snapshot.last_update.astimezone(UTC).date() == reference.astimezone(UTC).date()


def format_todays_sovereign_cds(snapshot: SovereignCDSSnapshot) -> str:
    selected_rows = [
        row for row in snapshot.rows if row.country in _MAJOR_SOVEREIGN_CDS_COUNTRIES
    ]
    ordered_rows = sorted(
        selected_rows,
        key=lambda row: _MAJOR_SOVEREIGN_CDS_COUNTRIES.index(row.country),
    )

    lines = [
        "# Sovereign CDS Snapshot",
        f"_Source last update: {snapshot.last_update.strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "| Country | Rating | 5Y CDS | Var 1m | Var 6m | Implied PD | Date |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for row in ordered_rows:
        var_1m = f"{row.var_1m_pct:.2f}%" if row.var_1m_pct is not None else "N/A"
        var_6m = f"{row.var_6m_pct:.2f}%" if row.var_6m_pct is not None else "N/A"
        implied_pd = f"{row.implied_pd_pct:.2f}%" if row.implied_pd_pct is not None else "N/A"
        lines.append(
            f"| {row.country} | {row.rating} | {row.cds_5y:.2f} | {var_1m} | {var_6m} | {implied_pd} | {row.date_label} |"
        )
    return "\n".join(lines)


def get_todays_sovereign_cds_snapshot(now: datetime | None = None) -> str:
    client = WorldGovernmentBondsCDSClient()
    snapshot = client.fetch_snapshot()
    reference = now or datetime.now(UTC)
    snapshot_utc_date = snapshot.last_update.astimezone(UTC).date()
    reference_utc_date = reference.astimezone(UTC).date()
    if not client.is_current_snapshot(snapshot, now=reference):
        return (
            "# Sovereign CDS Snapshot\n"
            f"Skipped: World Government Bonds last update date was {snapshot_utc_date.isoformat()}, "
            f"which does not match today ({reference_utc_date.isoformat()} UTC)."
        )
    return format_todays_sovereign_cds(snapshot)
