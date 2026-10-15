"""Finnhub vendor — JSON API as an *alternative* source, ticker-agnostic.

Finnhub (finnhub.io) is wired in as a secondary/alternative vendor, not as
the primary: it is selected only by the configured chain position, and it
degrades cleanly in two ways that keep any ticker analyzable:

* **Plan/coverage gate.** The free plan covers US-listed equities; every
  entry point first queries ``/stock/profile2`` and treats an empty profile
  as *not covered* (``NoMarketDataError``) so the router moves on to the
  next configured vendor instead of reporting zeros as a price or an empty
  profile as fact. This is verified behaviour: ``RHM:DE`` returns
  ``{"c": 0, ...}`` on ``/quote`` and ``{}`` on ``/stock/profile2``.
* **No token.** Missing ``FINNHUB_API_KEY`` raises ``VendorNotConfiguredError``
  and the chain skips this vendor; a run without a key is unaffected.

Honest scope (kept in the output headers so agents read it):

* Free-plan endpoints used here: ``/stock/profile2``, ``/stock/metric``
  (TTM snapshot), ``/stock/insider-transactions`` (SEC-sourced, carries the
  Form 4 *filing* date), ``/company-news`` (legacy endpoint, Yahoo-sourced).
* Price *history* (``/stock/candle``), ``/company-news2`` and the symbol
  directory are **paid-only** on the free plan and are therefore NOT used —
  Finnhub is not a price/series source here.

Point-in-time: insider transactions are dated by ``filingDate`` (when the
Form 4 became public), so historical runs can be filtered to trades that
were actually disclosed on or before the run date — unlike vendors that
date a trade by execution and are withheld entirely for past dates.
The profile/metric overview is a present-day snapshot and is withheld for
historical dates through the shared ``date_window.withhold_live_profile``
guard, the same rule every fundamentals vendor follows (#1300).

The token travels only as the ``token`` query parameter and only from the
environment; ``get_scrubbed`` (plus a vendor-level re-scrub) keeps it out of
every error path.
"""

from __future__ import annotations

import csv
import io
import os
from datetime import datetime, timezone

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.date_window import (
    coverage_gap,
    withhold_live_profile,
)
from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)
from tradingagents.dataflows.net import get_scrubbed
from tradingagents.dataflows.symbols import normalize_symbol

API_BASE = "https://finnhub.io/api/v1"
REQUEST_TIMEOUT = 30

# Repo ticker suffix -> Finnhub exchange code. Finnhub quotes US equities
# bare (AAPL), other exchanges as TICKER:EXCHANGE (RHM:DE). Unknown suffixes
# are passed through unchanged — the profile2 coverage gate below then
# decides whether the symbol is served by this plan.
_SUFFIX_MAP = {
    ".US": "",
    ".DE": ":DE",
    ".AT": ":AT",
    ".CH": ":CH",
    ".FR": ":FR",
    ".NL": ":NL",
    ".IT": ":IT",
    ".ES": ":ES",
    ".UK": ":UK",
    ".GB": ":UK",
}


def get_finnhub_api_key() -> str:
    """The Finnhub token, or empty when unset (callers raise/branch).

    Reads ``FINNHUB_API_KEY`` (canonical, what the wrapper injects) and
    falls back to ``FINNHUB_API_TOKEN`` for direct repo runs where the
    operator used the Finnhub docs' variable name.
    """
    return (
        os.getenv("FINNHUB_API_KEY") or os.getenv("FINNHUB_API_TOKEN") or ""
    ).strip()


def _finnhub_symbol(ticker: str) -> str:
    """The Finnhub-form symbol for this ticker, ticker-agnostic."""
    upper = ticker.upper()
    for suffix, exchange in _SUFFIX_MAP.items():
        if upper.endswith(suffix):
            return ticker[: -len(suffix)].upper() + exchange
    return upper


def _get_json(path: str, params: dict, token: str):
    """GET one Finnhub endpoint, raising VendorUnavailableError on failure.

    The token is injected as the ``token`` query param here (callers never
    handle it); ``get_scrubbed`` keeps it out of every error message by
    passing it as the ``secret``. Returns the parsed JSON, or None for a
    404 (the caller treats that as "not covered", a coverage gap, not a
    fault).
    """
    query = dict(params)
    query["token"] = token
    try:
        response = get_scrubbed(
            f"{API_BASE}{path}",
            params=query,
            timeout=REQUEST_TIMEOUT,
            secret=token,
            passthrough=(401, 403, 404, 429),
        )
    except Exception as exc:  # HTTP/transport error; scrub the token before re-raising
        msg = str(exc)
        if token:
            msg = msg.replace(token, "***")  # defense in depth on top of get_scrubbed
        raise VendorUnavailableError(f"finnhub request failed: {msg}") from None
    if response.status_code in (401, 403):
        # 403 on the free plan means the endpoint/symbol is not on this plan
        # or the rate limit is hit — either way this vendor cannot answer now.
        raise VendorUnavailableError(
            "finnhub rejected the request (401/403) — check FINNHUB_API_KEY "
            "or the free-plan rate limit / endpoint access"
        )
    if response.status_code == 429:
        raise VendorUnavailableError(
            "finnhub rate limit reached (429) — free plan allows 60 requests/minute"
        )
    if response.status_code == 404:
        return None  # not covered — a coverage gap, not a fault
    if not response.ok:
        raise VendorUnavailableError(
            f"finnhub returned HTTP {response.status_code} for {path}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise VendorUnavailableError(f"finnhub returned invalid JSON: {exc}") from None


def _require_coverage(token: str, symbol: str, ticker: str) -> dict:
    """The Finnhub profile for ``symbol``, or NoMarketDataError when absent.

    ``/stock/profile2`` is the coverage gate: an empty profile means the
    symbol is not served by this plan (verified: DE tickers return ``{}``
    while US tickers return a full profile). Raising the typed error lets
    the router fall through to the next configured vendor.
    """
    payload = _get_json("/stock/profile2", {"symbol": symbol}, token)
    if payload is None or not payload.get("ticker"):
        raise NoMarketDataError(
            ticker,
            symbol,
            "no profile (symbol not covered by this Finnhub plan — free plan "
            "serves US-listed equities)",
        )
    return payload


# ---------------------------------------------------------------------------
# Fundamentals overview
# ---------------------------------------------------------------------------


def get_finnhub_fundamentals(ticker: str, as_of_date: str | None = None) -> str:
    """Company fundamentals overview from Finnhub (profile + TTM metrics).

    Present-day snapshot; withheld for historical dates by the shared
    point-in-time guard, like every other fundamentals vendor.
    """
    token = get_finnhub_api_key()
    if not token:
        raise VendorNotConfiguredError(
            "FINNHUB_API_KEY environment variable is not set; "
            "add the key to the profile .env to enable the finnhub vendor"
        )
    canonical = normalize_symbol(ticker)
    withheld = withhold_live_profile(as_of_date, canonical)
    if withheld:
        return withheld

    symbol = _finnhub_symbol(ticker)
    profile = _require_coverage(token, symbol, ticker)
    metrics = (_get_json("/stock/metric", {"symbol": symbol, "metric": "all"}, token) or {}).get("metric") or {}

    def m(key: str):
        return metrics.get(key)

    def money(key: str, currency: str | None):
        value = metrics.get(key)
        if value is None:
            return None
        return f"{value} {currency}".strip()

    currency = profile.get("currency")
    fields = [
        ("Name", profile.get("name")),
        ("Exchange", profile.get("exchange")),
        ("Country", profile.get("country")),
        ("Currency", currency),
        ("Industry", profile.get("finnhubIndustry")),
        ("IPO", profile.get("ipo")),
        ("Market Cap (M)", profile.get("marketCapitalization")),
        ("Shares Outstanding (M)", profile.get("shareOutstanding")),
        ("P/E (TTM)", m("peTTM")),
        ("Forward P/E", m("forwardPE")),
        ("EPS (TTM)", money("epsTTM", currency)),
        ("Beta", m("beta")),
        ("Dividend Yield (%)", m("dividendYieldTTM") or m("currentDividendYieldTTM")),
        ("Revenue Growth (TTM, x)", m("revenueGrowthTTM") or m("revenueGrowth3Y")),
        ("ROE (TTM, %)", m("roeTTM")),
        ("52-Week High", m("52WeekHigh")),
        ("52-Week Low", m("52WeekLow")),
        ("52-Week High Date", m("52WeekHighDate")),
        ("52-Week Low Date", m("52WeekLowDate")),
    ]
    lines = [f"{label}: {v}" for label, v in fields if v is not None]
    if not lines:
        raise NoMarketDataError(ticker, symbol, "profile present but no usable fields")
    return (
        f"# Finnhub fundamentals for {ticker} (queried as {symbol})\n"
        f"# Source: finnhub.io — profile2 + TTM metrics, present-day snapshot, "
        f"free-plan US-listed coverage. TTM figures are trailing, as of now.\n\n"
        + "\n".join(lines)
    )


# ---------------------------------------------------------------------------
# Insider transactions
# ---------------------------------------------------------------------------


def get_finnhub_insider_transactions(
    ticker: str, as_of_date: str | None = None
) -> str:
    """Insider (Form 4) transactions from Finnhub, SEC-sourced.

    Each record carries the Form 4 ``filingDate`` (when it became public), so
    a historical run is filtered to trades actually disclosed on or before
    the run date — instead of being withheld, as with vendors that date a
    trade by execution.
    """
    token = get_finnhub_api_key()
    if not token:
        raise VendorNotConfiguredError(
            "FINNHUB_API_KEY environment variable is not set; "
            "add the key to the profile .env to enable the finnhub vendor"
        )
    canonical = normalize_symbol(ticker)
    symbol = _finnhub_symbol(ticker)
    profile = _require_coverage(token, symbol, ticker)  # coverage gate

    payload = _get_json("/stock/insider-transactions", {"symbol": symbol}, token)
    records = [r for r in (payload or {}).get("data") or [] if isinstance(r, dict)]

    # The free-plan insider feed is a clamped recent sample (verified: AAPL
    # returns ~12 months of Form 4 filings, not a complete history). Its
    # observed coverage is the span of filing dates actually returned.
    filing_dates = sorted((r.get("filingDate") or "")[:10] for r in records if r.get("filingDate"))
    coverage_min = filing_dates[0] if filing_dates else None
    coverage_max = filing_dates[-1] if filing_dates else None

    if as_of_date:
        try:
            datetime.strptime(as_of_date, "%Y-%m-%d")  # validate format
        except ValueError:
            as_of_date = None

    if as_of_date and coverage_min and as_of_date < coverage_min:
        # The as-of date is before this feed's observed coverage: it cannot
        # answer for that date, so it must not claim "no filings" for it.
        # Raise the typed error so the chain continues to the next vendor
        # (yfinance, which withholds past insider data by its own rule).
        raise NoMarketDataError(
            ticker,
            symbol,
            (f"insider feed covers only {coverage_min}..{coverage_max} (clamped recent "
             f"sample); {as_of_date} is before that window, so this vendor cannot "
             f"answer for it"),
        )

    if not records:
        # Covered symbol, no filings in the feed's observed window — say so
        # plainly (source coverage is unverified; an empty feed does not prove
        # no trades occurred). A returned string stops the chain: that is
        # correct here because the next vendor (yfinance) serves the same
        # underlying SEC data with no filing-date field, so it adds nothing.
        return (
            f"No insider transactions returned by Finnhub (SEC filings) for "
            f"symbol '{symbol}'{f' in {coverage_min}..{coverage_max}' if coverage_min else ''}. "
            f"Source coverage is unverified; this does not establish that no "
            f"transactions occurred. Do not infer an insider-trade count or "
            f"neutral sentiment from this empty feed. Check issuer/regulatory "
            f"PDMR disclosures separately."
        )

    if as_of_date:
        disclosed = [r for r in records if (r.get("filingDate") or "")[:10] <= as_of_date]
        if not disclosed:
            # Within the feed's observed coverage, genuinely none on/before the
            # as-of date: that is a real (coverage-verified) absence, so a
            # returned string is an honest terminal answer.
            return (
                f"No Finnhub insider transactions for {symbol} were filed on or "
                f"before {as_of_date}, within this feed's observed coverage "
                f"({coverage_min}..{coverage_max}). Nothing public for this date "
                f"in this source; do not infer from later disclosures or from a "
                f"different source's coverage."
            )
        records = disclosed

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "name", "symbol", "transactionDate", "transactionCode",
        "transactionPrice", "change", "share", "filingDate",
        "isDerivative", "source", "id",
    ])
    for r in sorted(records, key=lambda r: r.get("filingDate") or "", reverse=True):
        writer.writerow([
            r.get("name"), r.get("symbol"), r.get("transactionDate"),
            r.get("transactionCode"), r.get("transactionPrice"),
            r.get("change"), r.get("share"), r.get("filingDate"),
            r.get("isDerivative"), r.get("source"), r.get("id"),
        ])
    note = (
        "filtered to Form 4 filings on or before "
        f"{as_of_date} (point-in-time)" if as_of_date else "all available filings"
    )
    return (
        f"# Insider Transactions data for {ticker} (queried as {symbol})\n"
        f"# Source: finnhub.io /stock/insider-transactions — SEC-sourced Form 4 "
        f"filings, {note}. transactionCode: A=open-market buy, S=open-market "
        f"sale, P=exercise, M=grant; filingDate is when it became public.\n"
        f"# Company profile: {profile.get('name')} ({profile.get('exchange')})\n"
        + buf.getvalue().strip()
    )


# ---------------------------------------------------------------------------
# Company news
# ---------------------------------------------------------------------------


def get_news_finnhub(ticker: str, start_date: str, end_date: str) -> str:
    """Company news for ``ticker`` in the window, from Finnhub.

    Uses the legacy ``/company-news`` endpoint (the free plan does not serve
    ``/company-news2``); articles are Yahoo-sourced and dated by publication
    time, so the window is applied in UTC.
    """
    for label, value in (("start_date", start_date), ("end_date", end_date)):
        datetime.strptime(value, "%Y-%m-%d")  # ValueError on malformed dates
    if start_date > end_date:
        raise ValueError("start_date must not be after end_date")

    token = get_finnhub_api_key()
    if not token:
        raise VendorNotConfiguredError(
            "FINNHUB_API_KEY environment variable is not set; "
            "add the key to the profile .env to enable the finnhub vendor"
        )
    canonical = normalize_symbol(ticker)
    symbol = _finnhub_symbol(ticker)
    _require_coverage(token, symbol, ticker)  # coverage gate

    payload = _get_json(
        "/company-news",
        {"symbol": symbol, "from": start_date, "to": end_date},
        token,
    )
    if payload is None:
        raise VendorUnavailableError(
            f"finnhub company-news endpoint 404 for {symbol}"
        )
    articles = [a for a in (payload if isinstance(payload, list) else []) if isinstance(a, dict)]

    def pub(item: dict) -> str:
        try:
            ts = int(item.get("datetime") or 0)
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d") if ts else ""
        except (TypeError, ValueError, OverflowError):
            return ""

    def pub_dt(item: dict) -> datetime | None:
        # A real datetime (or None) so coverage_gap can bound the observed
        # window; it expects datetime objects, not date strings.
        try:
            ts = int(item.get("datetime") or 0)
            return datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
        except (TypeError, ValueError, OverflowError):
            return None

    in_range = [a for a in articles if start_date <= pub(a) <= end_date]
    resolved = "" if canonical == ticker else f" (resolved to {canonical})"

    if not in_range:
        # A returned string would stop the vendor chain (first string wins),
        # suppressing the remaining news vendors. Raise the typed error so the
        # chain continues; the terminal vendor delivers the user-facing
        # "no news" answer. The coverage caveat, if any, rides in the detail.
        gap = coverage_gap(
            (pub_dt(a) for a in articles),
            start_date, end_date, "Finnhub company news",
            f"{ticker} news",
        )
        raise NoMarketDataError(
            ticker,
            symbol,
            (gap or f"no {symbol} articles in window {start_date}..{end_date} "
                    "(legacy endpoint, Yahoo-sourced sample) — not proof that "
                    f"no {ticker} news exists"),
        )

    in_range.sort(key=lambda a: (pub(a), a.get("headline") or ""), reverse=True)
    limit = max(1, int(get_config().get("news_article_limit", 20)))
    lines = [
        f"## Finnhub news: {ticker}{resolved} (queried as {symbol}), "
        f"from {start_date} to {end_date}",
        f"- Source: finnhub.io /company-news (free plan; legacy endpoint, "
        f"Yahoo-sourced) | {len(articles)} fetched, {len(in_range)} in window",
        "",
    ]
    for item in in_range[:limit]:
        date = pub(item) or "undated"
        headline = (item.get("headline") or "untitled").strip()
        source = item.get("source") or "unknown source"
        url = item.get("url") or ""
        summary = (item.get("summary") or "").strip()
        lines.append(f"### {date} — {headline} (source: {source})")
        if summary:
            lines.append(summary)
        if url:
            lines.append(f"Link: {url}")
        lines.append("")
    if len(in_range) > limit:
        lines.append(f"_(showing {limit} of {len(in_range)} matched articles)_")
    return "\n".join(lines).strip()
