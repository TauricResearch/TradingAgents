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
from datetime import date, datetime, tzinfo
from importlib import metadata
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.errors import NoMarketDataError, VendorRateLimitError
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.ohlcv import yf_retry

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
        (
            "Stockholders Equity",
            (
                "StockholdersEquity",
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            ),
        ),
    ],
    "income_statement": [
        (
            "Revenue",
            ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"),
        ),
        ("Cost of Revenue", ("CostOfRevenue", "CostOfGoodsAndServicesSold")),
        ("Gross Profit", ("GrossProfit",)),
        ("Operating Income", ("OperatingIncomeLoss",)),
        ("Net Income", ("NetIncomeLoss",)),
        ("Diluted EPS", ("EarningsPerShareDiluted",)),
    ],
    "cashflow": [
        (
            "Operating Cash Flow",
            (
                "NetCashProvidedByUsedInOperatingActivities",
                "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
            ),
        ),
        ("Investing Cash Flow", ("NetCashProvidedByUsedInInvestingActivities",)),
        ("Financing Cash Flow", ("NetCashProvidedByUsedInFinancingActivities",)),
        (
            "Capital Expenditure",
            ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"),
        ),
    ],
}

# A statement's figures cover a span: a quarter is about 90 days, a year about
# 365. One filing reports both the quarter and the year to date under the same
# end date, so a match on the end date alone can report half a year as a quarter.
_SPANS = {"quarterly": (60, 115), "annual": (300, 400)}

# A fiscal year is a period an annual report covers. A 10-Q balance has no span
# to reject, and some filers' 10-Qs report twelve-month totals that pass the span
# check, so either would read as a fiscal year. The value is still the latest
# filing of any form: a recast after a split or spin-off counts from its filing.
_ANNUAL_FORMS = ("10-K", "20-F", "40-F")


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
        raise VendorRateLimitError(
            f"SEC EDGAR request failed ({status or type(exc).__name__})"
        ) from exc
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


def _as_of(
    facts: dict,
    tags: tuple[str, ...],
    curr_date: str,
    span: tuple[int, int],
    forms: tuple[str, ...] = (),
) -> tuple[dict, str]:
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
            covered: set[str] = set()  # period ends a filing of ``forms`` reports
            for fact in unit_values:
                if fact["filed"] > curr_date or fact["end"] in values:
                    continue
                # A duration fact (revenue, cash flow) must cover the span asked
                # for. An instant fact (a balance) has no span and serves both.
                if "start" in fact:
                    days = (
                        date.fromisoformat(fact["end"]) - date.fromisoformat(fact["start"])
                    ).days
                    if not low <= days <= high:
                        continue
                if not forms or fact.get("form", "").startswith(forms):
                    covered.add(fact["end"])
                seen = latest.get(fact["end"])
                if seen is None or fact["filed"] >= seen["filed"]:
                    latest[fact["end"]] = fact
            latest = {end: fact for end, fact in latest.items() if end in covered}
            if latest:
                chosen_unit = unit
                values.update({end: fact["val"] for end, fact in latest.items()})
    return dict(sorted(values.items())), chosen_unit


def _statement(kind: str, ticker: str, freq: str, curr_date: str, title: str) -> str:
    curr_date = curr_date or datetime.now().strftime("%Y-%m-%d")
    cik = cik_for(ticker)
    if cik is None:
        raise NoMarketDataError(ticker, ticker, "not a US SEC filer")

    facts = _cached_json(_FACTS_URL.format(cik=cik), f"CIK{cik}.json")
    us_gaap = (facts.get("facts") or {}).get("us-gaap")
    if not us_gaap:
        raise NoMarketDataError(ticker, ticker, "US filer with no us-gaap facts")

    quarterly = freq.lower() == "quarterly"
    span = _SPANS["quarterly" if quarterly else "annual"]
    forms = () if quarterly else _ANNUAL_FORMS
    lines = {
        label: _as_of(us_gaap, tags, curr_date, span, forms) for label, tags in _STATEMENTS[kind]
    }
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
            rows.append(
                ",".join([label] + ["unavailable (not tagged by this filer)"] * len(periods))
            )
            continue
        name = label if unit == "USD" else f"{label} ({unit})"
        # Plain numbers: a thousands separator would split the CSV field.
        cells = [
            (f"{values[p] / 1e6:.0f}" if unit == "USD" else f"{values[p]:.2f}")
            if p in values
            else ""
            for p in periods
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


# A valuation input older than this many days is not priced: the cover page
# count in particular goes stale between filings, and a market cap built on a
# year-old share count is a fabricated figure with a real-looking date on it.
_VALUATION_STALE_DAYS = 200


def get_valuation(ticker: str, curr_date: str | None = None) -> str:
    """Valuation snapshot built only from what was public by ``curr_date``.

    Vendors' valuation fields (market cap, multiples) are present-day values
    with no historical vintage, so a run dated in the past gets them withheld
    (#1300, #1374). This builds a conservative replacement instead: the last
    as-traded close at or before ``curr_date`` times the most recently filed
    cover page share count for market cap; filed diluted EPS and stockholders
    equity for per-share and book multiples. Everything carries its as-of date,
    and what cannot be derived from filings is reported unavailable rather
    than invented. Enterprise value is deliberately not derived: filings
    carry carrying values, not the market value of debt that the formula needs.

    The price must be the price that traded: the OHLCV layer serves
    split-adjusted closes, and multiplying an adjusted close by a filed share
    count is off by the ratio of every split between them (NVDA on 2024-05-15
    would read about $290B instead of about $2.9T). So the close is fetched
    unadjusted and the share count is scaled by the splits that happened
    between the cover date and the price date instead.
    """
    curr_date, facts = _filer_facts(ticker, curr_date)
    us_gaap = (facts.get("facts") or {}).get("us-gaap") or {}

    shares = _latest_dei_share_count(facts, curr_date)
    # Equity is an instant fact, so the span argument is not consulted; EPS is
    # a duration fact, and the annual figure is taken first — a quarter alone
    # understates the denominator, and a trailing figure would sum filings
    # that were never filed together.
    equity = _newest_period(
        _as_of(
            us_gaap,
            (
                "StockholdersEquity",
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            ),
            curr_date,
            _SPANS["annual"],  # instant fact: only the period key matters, not the span
        )
    )
    eps = _newest_period(
        _as_of(
            us_gaap,
            ("EarningsPerShareDiluted",),
            curr_date,
            _SPANS["annual"],
            _ANNUAL_FORMS,  # a 10-Q can report a twelve-month diluted EPS; only
            # an annual report's figure is a fiscal year
        )
    )
    eps_basis = "annual"
    if eps is None:
        eps = _newest_period(
            _as_of(
                us_gaap,
                ("EarningsPerShareDiluted",),
                curr_date,
                _SPANS["quarterly"],
                ("10-Q",),
            )
        )
        eps_basis = "quarterly"
    price, price_date = _last_as_traded_close(ticker, curr_date)
    stale_price = (
        price is not None
        and price_date is not None
        and (date.fromisoformat(curr_date) - date.fromisoformat(price_date)).days
        > _VALUATION_STALE_DAYS
    )
    if stale_price:
        # A close far in the past — a delisted name, or one whose only history
        # in the window is old — prices nothing: it is withheld with its date
        # rather than multiplied into a fabricated market cap.
        price = None

    # The cover page count is measured on its cover date; splits after it (and
    # before the price date) are undone onto the count, so count x price is the
    # capitalisation that actually stood on the price date.
    split_ratio = (
        _split_factor(ticker, shares[0], price_date)
        if (shares is not None and price_date is not None)
        else None
    )
    scaled_shares = None
    if shares is not None:
        scaled_shares = shares[2] * split_ratio if split_ratio else shares[2]
    stale_shares = (
        shares is not None
        and price_date is not None
        and (date.fromisoformat(price_date) - date.fromisoformat(shares[0])).days
        > _VALUATION_STALE_DAYS
    )

    if stale_price:
        close_row = (
            "Close",
            "unavailable",
            f"last settled close {price_date} is over {_VALUATION_STALE_DAYS} days old",
        )
    else:
        close_row = (
            "Close",
            f"{price:.2f} USD" if price is not None else "unavailable",
            price_date or "no settled close on or before the analysis date",
        )

    rows: list[tuple[str, str, str]] = [close_row]

    if shares is not None and not stale_shares:
        provenance = f"measured {shares[0]}, filed {shares[1]}" + (
            f", split-adjusted x{split_ratio:g}" if split_ratio and split_ratio != 1 else ""
        )
        rows.append(("Shares Outstanding (cover page)", f"{scaled_shares:,.0f}", provenance))
    elif stale_shares:
        rows.append(
            (
                "Shares Outstanding (cover page)",
                "unavailable",
                f"cover page count measured {shares[0]} is over {_VALUATION_STALE_DAYS} days old",
            )
        )
    else:
        rows.append(
            (
                "Shares Outstanding (cover page)",
                "unavailable",
                "no cover page count filed by the analysis date",
            )
        )

    if price is not None and scaled_shares is not None and not stale_shares:
        rows.append(
            (
                "Market Cap",
                f"{price * scaled_shares / 1e9:.2f}B USD",
                f"close {price_date} x shares measured {shares[0]} (filed {shares[1]})"
                + (f" x split {split_ratio:g}" if split_ratio and split_ratio != 1 else ""),
            )
        )
    else:
        rows.append(("Market Cap", "unavailable", "needs both a close and a recent share count"))

    if (
        price is not None
        and equity is not None
        and equity[1]
        and scaled_shares is not None
        and not stale_shares
    ):
        book_per_share = equity[1] / scaled_shares
        if book_per_share <= 0:
            # Negative equity is a real state (insolvency), but a negative
            # multiple reads as a cheapness signal an agent will act on.
            rows.append(
                (
                    "Price / Book",
                    "not meaningful",
                    f"book value per share is {book_per_share:.2f} (equity as of {equity[0]})",
                )
            )
        else:
            rows.append(
                (
                    "Price / Book",
                    f"{price / book_per_share:.2f}",
                    f"close {price_date} / book per share (equity as of {equity[0]})",
                )
            )
    else:
        rows.append(
            (
                "Price / Book",
                "unavailable",
                "needs a close, a recent share count and filed stockholders equity",
            )
        )

    if price is not None and eps is not None and eps[1]:
        if eps[1] < 0:
            rows.append(
                (
                    "Price / Earnings",
                    "not meaningful",
                    f"diluted EPS is {eps[1]:.2f} for period ending {eps[0]} ({eps_basis})",
                )
            )
        else:
            rows.append(
                (
                    "Price / Earnings",
                    f"{price / eps[1]:.2f}",
                    f"close {price_date} / diluted EPS for period ending {eps[0]} ({eps_basis})",
                )
            )
    else:
        rows.append(
            ("Price / Earnings", "unavailable", "needs a close and a nonzero filed diluted EPS")
        )

    rows.append(
        (
            "Enterprise Value",
            "unavailable",
            "not derivable from filings: they carry carrying values, not the market value of debt",
        )
    )

    return _valuation_markdown(f"Valuation snapshot for {ticker.upper()}", curr_date, rows)


def _filer_facts(ticker: str, curr_date: str | None) -> tuple[str, dict]:
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


def _day_end(day: str, tz: tzinfo | None) -> pd.Timestamp:
    """The last instant of ``day``, tz-aware iff the index it will be
    compared against is.

    yfinance serves exchange-local, tz-aware indexes while analysis dates
    arrive as naive ``YYYY-MM-DD`` strings; comparing the two directly raises.
    Day-level bounds also carry the semantics the snapshot needs: a close
    stamped during the analysis day settles that day, and a split executed on
    the cover date is already inside that day's count.
    """
    end = pd.Timestamp(day) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    return end.tz_localize(tz) if tz is not None else end


def _last_as_traded_close(ticker: str, curr_date: str) -> tuple[float | None, str | None]:
    """The last close at or before ``curr_date`` as it traded, with its date.

    This is deliberately not the OHLCV layer: that serves split-adjusted
    closes, and the filed share count below is not adjusted, so their product
    is off by every split ratio between the two dates. The unadjusted close —
    the price that actually traded — needs no reconciliation. Yahoo's own
    Close, even with ``auto_adjust=False``, still divides out every split
    that has happened since the session (including ones after the analysis
    date), so those splits are multiplied back onto it before it is returned.
    """
    canonical = normalize_symbol(ticker)
    try:
        history = yf_retry(
            lambda: yf.Ticker(canonical).history(
                period="5y",
                auto_adjust=False,
            )
        )
    except Exception as exc:  # noqa: BLE001 — price is one factor, not the whole answer
        logger.warning("No as-traded close for %s by %s: %s", ticker, curr_date, exc)
        return None, None
    if history is None or history.empty or "Close" not in history:
        return None, None
    cutoff = _day_end(curr_date, history.index.tz)
    history = history[history.index <= cutoff]
    if history.empty:
        return None, None
    row = history.iloc[-1]
    price = float(row["Close"])
    day = str(row.name.date())
    # Undo Yahoo's retroactive split adjustment: a split executed on the
    # price day itself already traded post-split, so only strictly later
    # events are multiplied back in.
    factor = _split_factor(ticker, day, datetime.now().strftime("%Y-%m-%d"))
    if factor:
        price *= factor
    return price, day


def _split_factor(ticker: str, cover_date: str, price_date: str) -> float | None:
    """The cumulative split factor between ``cover_date`` (exclusive) and
    ``price_date`` (inclusive).

    Yahoo's split rows carry each event's ratio. A split on the cover date
    itself belongs to the count already — the count was measured with that
    split in place — so only strictly later events rescale it. Only the
    day-end of ``cover_date`` is excluded, in whatever timezone the split
    index carries.
    """
    canonical = normalize_symbol(ticker)
    try:
        splits = yf_retry(lambda: yf.Ticker(canonical).splits)
    except Exception as exc:  # noqa: BLE001 — a missing split history is a ratio of 1
        logger.warning("No split history for %s: %s", ticker, exc)
        return None
    if splits is None or splits.empty:
        return None
    after = _day_end(cover_date, splits.index.tz)
    through = _day_end(price_date, splits.index.tz)
    window = splits[(splits.index > after) & (splits.index <= through)]
    if window.empty:
        return None
    factor = 1.0
    for ratio in window:
        factor *= float(ratio)
    return factor


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    """Cash flow statement as filed on or before ``curr_date``."""
    return _statement("cashflow", ticker, freq, curr_date, "Cash Flow Statement")
