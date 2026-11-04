"""ASX company announcements, the exchange's own disclosure feed for .AX listings.

ASX-listed companies must disclose price-sensitive information to the market
through the ASX announcements platform before anywhere else, so for an ASX
ticker these are the primary source the press reports on. The ASX website reads
them from a public JSON endpoint that needs no account or key:

    https://asx.api.markitdigital.com/asx-research/1.0/companies/{code}/announcements

It returns the company's latest few announcements (five at the time of writing),
newest first, each with a UTC timestamp, a headline, a type and a
price-sensitive flag. It has no date parameter, so a run dated in the past sees
only those of them published by its date, and a window older than the oldest
returned item is reported as unavailable rather than empty.

Dates are compared in Sydney time: ASX trading days are Sydney days, and an
announcement made at 9am AEDT carries the previous day's date in UTC.
"""

from __future__ import annotations

import logging
import string
from datetime import UTC, date, datetime

import pytz
import requests

from tradingagents.dataflows.date_window import coverage_gap
from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError
from tradingagents.dataflows.symbols import asx_code

logger = logging.getLogger(__name__)

ANNOUNCEMENTS_URL = "https://asx.api.markitdigital.com/asx-research/1.0/companies/{code}/announcements"
REQUEST_TIMEOUT = 15
_UA = "tradingagents (+https://github.com/TauricResearch/TradingAgents)"
SYDNEY = pytz.timezone("Australia/Sydney")


def _parse_timestamp(value: str | None) -> datetime | None:
    """Parse the feed's ISO timestamp (``2026-10-22T03:38:31.000Z``) to UTC."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def sydney_date(ts: datetime) -> date:
    """The ASX trading-day date of a UTC timestamp."""
    return ts.astimezone(SYDNEY).date()


def fetch_announcements(code: str, timeout: float = REQUEST_TIMEOUT) -> list[dict]:
    """The feed's announcements for ``code``, newest first, each with a parsed
    ``published`` UTC datetime. Raises VendorUnavailableError when the feed
    cannot be read."""
    url = ANNOUNCEMENTS_URL.format(code=code.lower())
    try:
        resp = requests.get(url, headers={"User-Agent": _UA, "Accept": "application/json"}, timeout=timeout)
    except requests.RequestException as exc:
        raise VendorUnavailableError(f"ASX announcements request failed: {exc}") from exc
    if resp.status_code == 404:
        return []  # The code is not an ASX listing the feed knows.
    if resp.status_code != 200:
        raise VendorUnavailableError(f"ASX announcements returned HTTP {resp.status_code}")
    try:
        items = (resp.json().get("data") or {}).get("items") or []
    except (ValueError, AttributeError) as exc:
        raise VendorUnavailableError(f"ASX announcements returned unreadable JSON: {exc}") from exc
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        out.append({**item, "published": _parse_timestamp(item.get("date"))})
    return out


def _format(item: dict) -> str:
    published = item["published"]
    when = f"{published.astimezone(SYDNEY):%Y-%m-%d %H:%M} Sydney" if published else "undated"
    flag = " **[PRICE SENSITIVE]**" if item.get("isPriceSensitive") else ""
    headline = (item.get("headline") or "").replace("\n", " ").strip() or "(no headline)"
    # capwords, not title(): "CHAIRMAN'S" -> "Chairman's", not "Chairman'S".
    kind = string.capwords((item.get("announcementType") or "").strip().lower())
    kind = f" ({kind})" if kind and kind.lower() != headline.lower() else ""
    return f"- {when}{flag}: {headline}{kind}"


def get_announcements(ticker: str, start_date: str, end_date: str) -> str:
    """ASX announcements for an ASX ``ticker`` published in ``[start_date, end_date]``
    (Sydney dates, inclusive), as a markdown block.

    Raises NoMarketDataError for a ticker that is not an ASX listing, and
    VendorUnavailableError when the feed cannot be read.
    """
    code = asx_code(ticker)
    if not code:
        raise NoMarketDataError(ticker, detail="not an ASX listing; ASX announcements cover .AX tickers only")

    items = fetch_announcements(code)
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    in_range = [i for i in items if i["published"] and start <= sydney_date(i["published"]) <= end]
    subject = f"ASX announcements by {code}"
    dates = [i["published"] for i in items]

    if not in_range:
        gap = coverage_gap(dates, start_date, end_date, "ASX announcements feed", subject)
        return gap or f"<no ASX announcements by {code} between {start_date} and {end_date}>"

    header = f"## ASX announcements by {code}, from {start_date} to {end_date} (Sydney dates)"
    lines = [header, ""]
    lines += [_format(i) for i in in_range]
    oldest = min((d for d in dates if d), default=None)
    if oldest and sydney_date(oldest) > start:
        lines += ["", f"<The ASX feed lists only the latest {len(items)} announcements, so any "
                      f"before {sydney_date(oldest)} in this window are not shown.>"]
    return "\n".join(lines)
