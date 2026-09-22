"""Company statements as they were filed, from SEC EDGAR.

Every other fundamentals vendor serves a period's current value and cuts the
statement at the fiscal period end. That is two claims a run should not make: a
period that has ended is not public until the company files, weeks later, and a
figure that was later restated is not what investors saw at the time.

EDGAR reports every fact with the date it was filed, so a run dated ``curr_date``
serves exactly what was on file by then, restatements included at the vintage
that was current: Apple's 2008 total assets read 39.6B until the 2010 amendment
restated them to 36.2B.

Access needs no key or account, only a User-Agent identifying the caller, which
SEC requires and refuses requests without. US filers only: anything absent from
EDGAR's ticker map falls through to the next configured vendor.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime
from importlib import metadata
from pathlib import Path

import requests

from .config import get_config
from .errors import NoMarketDataError, VendorRateLimitError
from .stockstats_utils import load_ohlcv

logger = logging.getLogger(__name__)

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# A filing history only changes when something new is filed, so one fetch per
# company per day serves every date a run asks about.
_CACHE_TTL_SECONDS = 24 * 60 * 60

# Line items, each with the tags filers use for it, best first. First match wins
# and values are never summed across tags: a company reporting revenue under two
# tags would otherwise be counted twice.
_STATEMENTS: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "balance_sheet": [
        ("Total Assets", ("Assets",)),
        ("Current Assets", ("AssetsCurrent",)),
        ("Cash and Equivalents", ("CashAndCashEquivalentsAtCarryingValue",)),
        ("Total Liabilities", ("Liabilities",)),
        ("Current Liabilities", ("LiabilitiesCurrent",)),
        ("Stockholders Equity", ("StockholdersEquity",
                                 "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")),
    ],
    "income_statement": [
        ("Revenue", ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                     "SalesRevenueNet")),
        ("Cost of Revenue", ("CostOfRevenue", "CostOfGoodsAndServicesSold")),
        ("Gross Profit", ("GrossProfit",)),
        ("Operating Income", ("OperatingIncomeLoss",)),
        ("Net Income", ("NetIncomeLoss",)),
        ("Diluted EPS", ("EarningsPerShareDiluted",)),
    ],
    "cashflow": [
        ("Operating Cash Flow", ("NetCashProvidedByUsedInOperatingActivities",
                                 "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations")),
        ("Investing Cash Flow", ("NetCashProvidedByUsedInInvestingActivities",)),
        ("Financing Cash Flow", ("NetCashProvidedByUsedInFinancingActivities",)),
        ("Capital Expenditure", ("PaymentsToAcquirePropertyPlantAndEquipment",)),
    ],
}

# A statement's figures cover a span: a quarter is about 90 days, a year about
# 365. One filing reports both the quarter and the year to date under the same
# end date, so a match on the end date alone can report half a year as a quarter.
_SPANS = {"quarterly": (60, 115), "annual": (300, 400)}


def _user_agent() -> str:
    """Who SEC sees. No account or key exists; callers identify themselves.

    www.sec.gov, which serves the ticker map, refuses a User-Agent carrying no
    contact address: a client name alone or with a project URL gets 403, one
    with an address gets 200. So the default carries a placeholder address and
    the package version. Set SEC_EDGAR_USER_AGENT to your own name and address
    so SEC can reach you about your traffic rather than the project.
    """
    configured = os.getenv("SEC_EDGAR_USER_AGENT", "").strip()
    return configured or f"TradingAgents/{_version()} (contact@example.com)"


def _version() -> str:
    """The installed package version, so a release identifies itself correctly."""
    try:
        return metadata.version("tradingagents")
    except metadata.PackageNotFoundError:
        return "dev"


def _fetch_json(url: str) -> dict:
    """Read a public EDGAR document, respecting SEC's identification rule."""
    try:
        response = requests.get(url, headers={"User-Agent": _user_agent()}, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        # Every failure here is "this vendor cannot serve it now", so the router
        # moves on instead of seeing a transport exception it has no rule for.
        raise VendorRateLimitError(f"SEC EDGAR request failed ({status or type(exc).__name__})") from exc
    except ValueError as exc:
        raise VendorRateLimitError("SEC EDGAR returned an unreadable response") from exc


def _cached_json(url: str, name: str) -> dict:
    path = Path(get_config()["data_cache_dir"]) / "sec_edgar" / name
    if path.exists() and time.time() - path.stat().st_mtime < _CACHE_TTL_SECONDS:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            pass  # a truncated file is a miss, not a failure
    data = _fetch_json(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(temp, path)
    return data


def cik_for(ticker: str) -> str | None:
    """The filer's CIK, or None when the ticker is not a US filer."""
    table = _cached_json(_TICKERS_URL, "company_tickers.json")
    wanted = ticker.strip().upper()
    for entry in table.values():
        if entry.get("ticker", "").upper() == wanted:
            return f"{int(entry['cik_str']):010d}"
    return None


def _as_of(facts: dict, tags: tuple[str, ...], curr_date: str, span: tuple[int, int]) -> tuple[dict, str]:
    """({period end: value}, unit) for the first tag the filer reports, as known then.

    A period reported more than once takes its latest filing on or before the
    date, so an amendment counts from the day it was filed and not before. The
    unit comes from the filing: most lines are USD, earnings per share are
    USD/shares, and scaling those alike would print a real figure as zero.
    """
    low, high = span
    values: dict[str, float] = {}
    chosen_unit = "USD"
    # Tags are tried in order and a period keeps the first one that reports it:
    # filers renamed lines over the years, so one tag covers only part of the
    # history. Values are never added across tags, which would double count.
    for tag in tags:
        for unit, unit_values in ((facts.get(tag) or {}).get("units", {})).items():
            latest: dict[str, dict] = {}
            for fact in unit_values:
                if fact["filed"] > curr_date or fact["end"] in values:
                    continue
                # A duration fact (revenue, cash flow) must cover the span asked
                # for. An instant fact (a balance) has no span and serves both.
                if "start" in fact:
                    days = (date.fromisoformat(fact["end"]) - date.fromisoformat(fact["start"])).days
                    if not low <= days <= high:
                        continue
                seen = latest.get(fact["end"])
                if seen is None or fact["filed"] >= seen["filed"]:
                    latest[fact["end"]] = fact
            if latest:
                chosen_unit = unit
                values.update({end: fact["val"] for end, fact in latest.items()})
    return dict(sorted(values.items())), chosen_unit


def _filer_facts(ticker: str, curr_date: str) -> tuple[str, dict]:
    """Resolve the filer and load its facts, the shared preamble of the tools.

    ``curr_date`` defaults to today for a live run, and a non-filer is reported
    as such: the router reads that as "no data from this vendor" instead of a
    transport error.
    """
    curr_date = curr_date or datetime.now().strftime("%Y-%m-%d")
    cik = cik_for(ticker)
    if cik is None:
        raise NoMarketDataError(ticker, ticker, "not a US SEC filer")
    facts = _cached_json(_FACTS_URL.format(cik=cik), f"CIK{cik}.json")
    return curr_date, facts


def _statement(kind: str, ticker: str, freq: str, curr_date: str, title: str) -> str:
    curr_date, facts = _filer_facts(ticker, curr_date)
    us_gaap = (facts.get("facts") or {}).get("us-gaap")
    if not us_gaap:
        raise NoMarketDataError(ticker, ticker, "US filer with no us-gaap facts")

    span = _SPANS["quarterly" if freq.lower() == "quarterly" else "annual"]
    lines = {label: _as_of(us_gaap, tags, curr_date, span) for label, tags in _STATEMENTS[kind]}
    periods = sorted({end for values, _ in lines.values() for end in values})
    if not periods:
        raise NoMarketDataError(ticker, ticker, f"no {freq} {title.lower()} filed by {curr_date}")

    header = (
        f"# {title} for {ticker.upper()} ({freq}), USD in millions unless the row says otherwise\n"
        f"# SEC EDGAR facts filed on or before {curr_date}, at the values filed then\n\n"
    )
    rows = [",".join([""] + periods)]
    for label, (values, unit) in lines.items():
        # Every row spans the same columns, or a reader lines the table up wrong.
        if not values:
            rows.append(",".join([label] + ["unavailable (not tagged by this filer)"] * len(periods)))
            continue
        name = label if unit == "USD" else f"{label} ({unit})"
        # Plain numbers: a thousands separator would split the CSV field.
        cells = [
            (f"{values[p] / 1e6:.0f}" if unit == "USD" else f"{values[p]:.2f}")
            if p in values else "" for p in periods
        ]
        rows.append(",".join([name] + cells))
    return header + "\n".join(rows) + "\n"


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    """Balance sheet as filed on or before ``curr_date``."""
    return _statement("balance_sheet", ticker, freq, curr_date, "Balance Sheet")


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    """Income statement as filed on or before ``curr_date``.

    A fourth quarter is never derived: filers report it only inside the annual
    figure, and subtracting three separately filed quarters would invent a number
    with no filing date behind it.
    """
    return _statement("income_statement", ticker, freq, curr_date, "Income Statement")


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    """Cash flow statement as filed on or before ``curr_date``."""
    return _statement("cashflow", ticker, freq, curr_date, "Cash Flow Statement")


def _latest_dei_share_count(facts: dict, curr_date: str) -> tuple[str, str, float] | None:
    """(cover date, filed date, shares) for the newest count filed by ``curr_date``.

    Filers state common shares outstanding on every cover page
    (``dei:EntityCommonStockSharesOutstanding``) with the date the count was
    measured, so a run dated in the past reads the count that was public then,
    not the one on today's cover. The filed date travels with it: a revision
    re-states the same cover date, and when it became known is the fact a
    point-in-time run depends on.
    """
    dei = (facts.get("facts") or {}).get("dei") or {}
    covers = (
        (dei.get("EntityCommonStockSharesOutstanding") or {}).get("units", {}).get("shares", [])
    )
    latest = None
    for cover in covers:
        if cover["filed"] > curr_date:
            continue
        end = cover.get("end") or cover["filed"]
        # (end, filed) decides recency: a higher cover date wins, and among
        # revisions of the same cover date the last filed wins — the count
        # known on the analysis date is the one the run reads.
        if latest is None or (end, cover["filed"]) >= (latest[0], latest[1]):
            latest = (end, cover["filed"], float(cover["val"]))
    if latest is None:
        return None
    return latest[0], latest[1], latest[2]


def _valuation_markdown(title: str, curr_date: str, rows: list[tuple[str, str, str]]) -> str:
    """A one-line-per-metric table; every row carries its own provenance."""
    lines = [
        f"# {title}",
        "",
        f"# Point-in-time as of: {curr_date}",
        "",
        "| Metric | Value | As-of / filed |",
        "|---|---|---|",
    ]
    lines += [f"| {metric} | {value} | {when} |" for metric, value, when in rows]
    return "\n".join(lines) + "\n"


def _newest_period(as_of_result: tuple[dict, str]) -> tuple[str, float] | None:
    """(period end, value) for the newest period a statement served, or None."""
    values = as_of_result[0] if as_of_result else {}
    if not values:
        return None
    end = max(values)
    return end, values[end]


def get_valuation(ticker: str, curr_date: str | None = None) -> str:
    """Valuation snapshot built only from what was public by ``curr_date``.

    Vendors' valuation fields (market cap, multiples) are present-day values
    with no historical vintage, so a run dated in the past gets them withheld
    (#1300, #1374). This builds a conservative replacement instead: the last
    settled close at or before ``curr_date`` times the most recently filed
    cover page share count for market cap; filed diluted EPS and stockholders
    equity for per-share and book multiples. Everything carries its as-of date,
    and what cannot be derived from filings is reported unavailable rather
    than invented. Enterprise value is deliberately not derived: filings
    carry carrying values, not the market value of debt that the formula needs.
    """
    curr_date, facts = _filer_facts(ticker, curr_date)
    us_gaap = (facts.get("facts") or {}).get("us-gaap") or {}

    shares = _latest_dei_share_count(facts, curr_date)
    # Equity is an instant fact, so the span argument is not consulted; EPS is
    # a duration fact, and the annual figure is taken first — a quarter alone
    # understates the denominator, and a trailing figure would sum filings
    # that were never filed together.
    equity = _newest_period(_as_of(
        us_gaap,
        ("StockholdersEquity",
         "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
        curr_date,
        _SPANS["annual"],  # instant fact: only the period key matters, not the span
    ))
    eps = _newest_period(_as_of(
        us_gaap, ("EarningsPerShareDiluted",), curr_date, _SPANS["annual"],
    ))
    eps_basis = "annual"
    if eps is None:
        eps = _newest_period(_as_of(
            us_gaap, ("EarningsPerShareDiluted",), curr_date, _SPANS["quarterly"],
        ))
        eps_basis = "quarterly"
    price, price_date = _last_settled_close(ticker, curr_date)

    rows: list[tuple[str, str, str]] = [
        ("Close", f"{price:.2f} USD" if price is not None else "unavailable",
         price_date or "no settled close on or before the analysis date"),
    ]

    if shares is not None:
        rows.append(("Shares Outstanding (cover page)", f"{shares[2]:,.0f}",
                     f"measured {shares[0]}, filed {shares[1]}"))
    else:
        rows.append(("Shares Outstanding (cover page)", "unavailable",
                     "no cover page count filed by the analysis date"))

    if price is not None and shares is not None:
        rows.append(("Market Cap", f"{price * shares[2] / 1e9:.2f}B USD",
                     f"close {price_date} x shares measured {shares[0]} (filed {shares[1]})"))
    else:
        rows.append(("Market Cap", "unavailable", "needs both a close and a share count"))

    if price is not None and equity is not None and equity[1] and shares:
        book_per_share = equity[1] / shares[2]
        if book_per_share <= 0:
            # Negative equity is a real state (insolvency), but a negative
            # multiple reads as a cheapness signal an agent will act on.
            rows.append(("Price / Book", "not meaningful",
                         f"book value per share is {book_per_share:.2f} (equity as of {equity[0]})"))
        else:
            rows.append(("Price / Book", f"{price / book_per_share:.2f}",
                         f"close {price_date} / book per share (equity as of {equity[0]})"))
    else:
        rows.append(("Price / Book", "unavailable",
                     "needs a close, a share count and filed stockholders equity"))

    if price is not None and eps is not None and eps[1]:
        if eps[1] < 0:
            rows.append(("Price / Earnings", "not meaningful",
                         f"diluted EPS is {eps[1]:.2f} for period ending {eps[0]} ({eps_basis})"))
        else:
            rows.append(("Price / Earnings", f"{price / eps[1]:.2f}",
                         f"close {price_date} / diluted EPS for period ending {eps[0]} ({eps_basis})"))
    else:
        rows.append(("Price / Earnings", "unavailable",
                     "needs a close and a nonzero filed diluted EPS"))

    rows.append(("Enterprise Value", "unavailable",
                 "not derivable from filings: they carry carrying values, not the market value of debt"))

    return _valuation_markdown(f"Valuation snapshot for {ticker.upper()}", curr_date, rows)


def _last_settled_close(ticker: str, curr_date: str) -> tuple[float | None, str | None]:
    """The last settled close at or before ``curr_date``, with its date.

    Prices come from the same OHLCV layer the market analyst uses, so the
    snapshot and the price history cannot disagree. A missing price leaves
    valuation rows unavailable rather than aborting the whole tool: the
    filings-side facts are still served.
    """
    try:
        data = load_ohlcv(ticker, curr_date, fill_gaps=False)
        row = data.iloc[-1]
        return float(row["Close"]), str(row["Date"].date())
    except Exception as exc:  # noqa: BLE001 — price is one factor, not the whole answer
        logger.warning("No settled close for %s by %s: %s", ticker, curr_date, exc)
        return None, None
