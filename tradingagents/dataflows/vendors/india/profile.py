"""The Company page for Indian stocks: the India database first, Yahoo Finance
for whatever it lacks.

A live, present-day view like Phase 1's (``company_profile``): the latest filed
figures, today's quote. For a ``.NS`` or ``.BO`` symbol the database's sections
replace Yahoo's one by one: results quarters and years, balance sheets and cash
flows from the filings imported, prices from NSE's bhavcopies (adjusted for
splits, bonuses and rights), plus the shareholding pattern and document links
Yahoo does not have. A section the database lacks stays Yahoo's, and the page
says which source each section came from. With no database, or nothing in it
for the company, the page is exactly Phase 1's.

The screener's metrics are computed here too, by the code that builds its live
snapshot (``screener.company`` and ``screener.catalog``) on the same rows, so
every figure a screen filters on reads the same on this page. The key ratios
take them where the database has them; Yahoo's quote fills the rest, and says so.

Yahoo's statements are consolidated. A standalone view therefore never falls
back to them: a section without standalone filings is left empty and says why,
rather than mixing two bases on one page.
"""

from __future__ import annotations

import threading
import time
from datetime import date, datetime

from tradingagents.dataflows.company_profile import CompanyData, build_profile, period_label, scale
from tradingagents.dataflows.errors import NoMarketDataError, VendorRateLimitError
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.india import store
from tradingagents.dataflows.vendors.india.statements import load_statements
from tradingagents.dataflows.vendors.yahoo import company_profile as yahoo
from tradingagents.screener import catalog
from tradingagents.screener.company import dividends_covered, load_company
from tradingagents.screener.snapshot import newest_price_day

CACHE_TTL_SECONDS = 15 * 60
_CACHE: dict[tuple, tuple[float, dict]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_MAX = 64

SHAREHOLDING_ROWS = (
    ("promoter_pct", "Promoters", "pct"), ("fii_pct", "FIIs", "pct"), ("dii_pct", "DIIs", "pct"),
    ("govt_pct", "Government", "pct"), ("public_pct", "Public", "pct"), ("others_pct", "Others", "pct"),
    ("num_shareholders", "No. of Shareholders", "count"), ("pledged", "Pledged (% of promoter shares)", "pct"),
)
DOCUMENT_GROUPS = (
    ("results", "Results"), ("annual_report", "Annual reports"), ("concall", "Concalls and investor meets"),
    ("investor_presentation", "Investor presentations"), ("credit_rating", "Credit ratings"),
    ("shareholding", "Shareholding patterns"), ("board_meeting", "Board meetings"),
    ("announcement", "Other announcements"),
)


def fiscal_label(end: str) -> str:
    """``2026-03-31`` -> ``FY2026``; a year not ending in March keeps its month."""
    day = date.fromisoformat(end)
    return f"FY{day.year}" if day.month == 3 else period_label(end)


def _span(ends: list[str], label=period_label) -> str:
    if not ends:
        return ""
    return label(ends[0]) if len(ends) == 1 else f"{label(ends[0])}–{label(ends[-1])}"


def load(conn, security: dict, basis: str | None = None) -> dict:
    """Everything the database has for one company, laid out for the page. The
    statements come from ``statements``, the loader the screener's snapshot uses."""
    isin = security["isin"]
    s = load_statements(conn, security, basis)
    prices = store.get_prices(isin, conn=conn)
    return {
        "security": security, "bases": s.bases, "basis": s.basis,
        "quarterly": s.quarterly, "annual": s.annual, "balance": s.balance, "cashflow": s.cashflow,
        "financial": s.financial,
        "prices": [(p["date"], p["close"], p["volume"]) for p in prices],
        "price_events": s.events,
        "shares": store.get_shares_outstanding(isin, conn=conn),
        "shareholding": store.get_shareholding(isin, conn=conn),
        "documents": store.get_documents(isin, conn=conn, limit=400),
        "filings": s.filings,
    }


def _is_empty(india: dict) -> bool:
    return not any(india[k] for k in ("quarterly", "annual", "balance", "cashflow", "prices",
                                      "shareholding", "documents"))


def overlay(data: CompanyData, india: dict) -> CompanyData:
    """``data`` (Yahoo's) with each section the database has replaced by it."""
    basis = india["basis"]
    sec = india["security"]
    yahoo_quote = bool(data.quote)
    filed = f"NSE filings ({basis})"
    standalone = basis == "standalone"
    for section, fmt in (("quarterly", period_label), ("annual", fiscal_label), ("balance", fiscal_label),
                         ("cashflow", fiscal_label)):
        mine = india[section]
        if mine:
            setattr(data, section, mine)
            ends = sorted(mine)
            unit = "quarter" if section == "quarterly" else "year"
            data.sources[section] = f"{filed} · {_span(ends, fmt)}, {len(ends)} {unit}{'s' * (len(ends) != 1)}"
        elif standalone:
            setattr(data, section, {})
            data.sources[section] = "NSE filings (standalone)"
            data.notes[section] = ("No standalone filing in the database has these figures, and Yahoo "
                                   "Finance has consolidated figures only.")
        elif getattr(data, section):
            data.sources[section] = f"{data.source} (consolidated)"
    if india["balance"]:
        data.notes["balance"] = " ".join(n for n in (
            data.notes.get("balance"), "Borrowings are as filed, non-current plus current, without lease "
            "liabilities. Balance sheets are filed with the second- and fourth-quarter results.") if n)
    if india["quarterly"] and not india["cashflow"] and data.cashflow and not standalone:
        data.notes["cashflow"] = "Cash flows are Yahoo Finance's: no fourth-quarter filing in the database has them."
    if len(india["prices"]) >= 2:
        data.prices, data.prices_from = india["prices"], None
        adjusted = sorted({e["type"] for e in india["price_events"]})
        first, last = india["prices"][0][0], india["prices"][-1][0]
        data.sources["prices"] = f"NSE bhavcopy · {first} to {last}"
        data.notes["prices"] = (
            "Daily closes from NSE's bhavcopies"
            + (f", adjusted for {' and '.join(adjusted)} ex-dates" if adjusted else "")
            + ". Not adjusted for dividends or demergers.")
    q = data.quote
    q.setdefault("name", sec.get("name"))
    if sec.get("industry"):
        q.setdefault("industry", sec["industry"])
    q.setdefault("exchange", "NSE" if sec.get("nse_symbol") else "BSE")
    q.setdefault("currency", "INR")
    q.setdefault("financial_currency", "INR")
    if india["prices"] and q.get("price") is None:
        q["price"] = india["prices"][-1][1]
        if (shares := india["shares"]) and shares.get("shares"):
            q.setdefault("market_cap", q["price"] * shares["shares"])
    if india["financial"] is not None:
        data.financial = india["financial"]
    statements = [data.sources.get(s, "") for s in ("quarterly", "annual", "balance", "cashflow", "prices")]
    if any(s.startswith("NSE") for s in statements):
        yahoo_too = yahoo_quote or any(s and not s.startswith("NSE") for s in statements)
        data.source = "NSE filings and Yahoo Finance" if yahoo_too else "NSE filings"
    return data


def shareholding_section(rows: list[dict]) -> dict:
    """Quarters across, categories down, plus the promoter/FII/DII series for the trend."""
    rows = rows[-12:]
    def value(r, key):
        if key == "pledged":
            return r["pledged_pct"] if r["pledged_pct"] is not None else r["encumbered_pct"]
        return r[key]
    old_pledge = any(r["pledged_pct"] is None and r["encumbered_pct"] is not None for r in rows)
    notes = ["Percentages of total shares, from the quarterly shareholding-pattern filings (shares behind "
             "depository receipts excluded, as the filings count them)."]
    if old_pledge:
        notes.append("Before the 2025 filing format, pledged and otherwise encumbered promoter shares were "
                     "reported together; those quarters show the combined figure.")
    return {
        "periods": [{"label": period_label(r["quarter_end"]), "end": r["quarter_end"], "filed": r["filed_at"]}
                    for r in rows],
        "rows": [{"key": key, "label": label, "kind": kind, "values": [value(r, key) for r in rows]}
                 for key, label, kind in SHAREHOLDING_ROWS if any(value(r, key) is not None for r in rows)],
        "trend": {k: [r[k] for r in rows] for k in ("promoter_pct", "fii_pct", "dii_pct")},
        "source": f"NSE shareholding-pattern filings · {_span([r['quarter_end'] for r in rows])}" if rows else "",
        "note": " ".join(notes),
    }


def documents_section(docs: list[dict]) -> dict:
    groups = []
    for kind, label in DOCUMENT_GROUPS:
        items = [{"date": d["date"], "title": d["title"], "url": d["url"], "source": d["source"]}
                 for d in docs if d["kind"] == kind][:25]
        if items:
            groups.append({"kind": kind, "label": label, "items": items})
    return {
        "groups": groups,
        "note": ("Results and shareholding links open the filing's XBRL on NSE. Announcements come from NSE's "
                 "daily archive, which carries no attachment links, so they open NSE's announcements page "
                 "for the company. Nothing is downloaded."),
    }


def _with_india(profile: dict, india: dict, data: CompanyData) -> dict:
    sec = india["security"]
    divisor = profile["unit"]["divisor"]
    sources = [{"section": name, "source": profile[key].get("source") or ""}
               for name, key in (("Quarterly results", "quarters"), ("Profit & loss", "profitLoss"),
                                 ("Balance sheet", "balanceSheet"), ("Cash flows", "cashFlows"))]
    sources.append({"section": "Price chart", "source": profile["chart"].get("source") or data.source})
    shareholding = shareholding_section(india["shareholding"])
    if shareholding["periods"]:
        sources.append({"section": "Shareholding", "source": shareholding["source"]})
    shares = india["shares"]
    return {
        **profile,
        "basis": {"current": india["basis"], "available": india["bases"]},
        "sources": sources,
        "india": {"isin": sec["isin"], "nseSymbol": sec.get("nse_symbol"), "bseCode": sec.get("bse_code"),
                  "industry": sec.get("industry"),
                  "sharesOutstanding": shares and shares.get("shares"),
                  "sharesAsOf": shares and shares.get("date"),
                  "filings": len(india["filings"]),
                  "marketCapFromDb": scale(shares["shares"] * india["prices"][-1][1], divisor)
                  if shares and india["prices"] else None},
        "shareholding": shareholding,
        "documents": documents_section(india["documents"]),
    }


# Key ratio -> the screener metric it shows, for India-database stocks.
KEY_RATIO_METRICS = {"market_cap": "market_cap", "price": "current_price", "pe": "pe", "book_value": "book_value",
                     "dividend_yield": "dividend_yield", "roce": "roce", "roe": "roe", "face_value": "face_value"}


def screener_metrics(conn, security: dict) -> dict:
    """Every catalog metric for one security, as the live snapshot computes it."""
    day = newest_price_day(conn) or date.today()
    company = load_company(conn, security, day, dividends_known=dividends_covered(conn, day))
    groups = {}
    for m in catalog.METRICS.values():
        value = m.value(company)
        groups.setdefault(m.category, []).append({
            "key": m.key, "name": m.name, "unit": m.unit, "kind": m.kind, "decimals": m.decimals,
            "description": m.description, "value": value,
            "applies": m.applies, "notApplicable": m.applies == catalog.NON_FINANCIAL and company.financial})
    return {
        "day": day.isoformat(), "basis": company.statements.basis if not company.statements.empty else None,
        "financial": company.financial,
        "shares": company.shares and {"count": company.shares.count, "source": company.shares.source,
                                      "date": company.shares.date},
        "groups": [{"category": c, "items": groups[c]} for c in catalog.CATEGORIES if c in groups],
        "values": {item["key"]: item["value"] for items in groups.values() for item in items},
    }


def _screened_key_ratios(profile: dict, metrics: dict) -> None:
    """The key ratios the screener also computes, set to its figures (same formulas,
    same rows); where it has none, Yahoo's figure stays and its hint says so."""
    values = metrics["values"]
    for r in profile["keyRatios"]:
        if r["key"] == "high_low":
            high, low = values.get("high_52w"), values.get("low_52w")
            if high is not None and low is not None:
                r["value"], r["hint"] = [high, low], "52 weeks, from the India database's adjusted prices"
            continue
        key = KEY_RATIO_METRICS.get(r["key"])
        if key is None:
            continue
        value = values.get(key)
        if value is not None:
            r["value"] = value
            r["hint"] = f"Screener figure: {catalog.METRICS[key].description}"
            r["screener"] = key
        elif r["value"] is not None:
            r["hint"] = ((r.get("hint") or "") + " · Yahoo Finance's figure: the India database has none, "
                         "so screens leave this stock out on it").lstrip(" ·")


def _db_stamp() -> float:
    try:
        return store.db_path().stat().st_mtime
    except OSError:
        return 0.0


def build_company_profile(symbol: str, basis: str | None = None) -> dict:
    """The Company page's data for ``symbol``: Phase 1's Yahoo page, with the India
    database's sections over it for Indian symbols it has. Raises like Yahoo's
    builder only when neither source has the company."""
    canonical = normalize_symbol(symbol)
    if not canonical.endswith((".NS", ".BO")):
        return yahoo.build_company_profile(symbol)
    conn = store.open_existing()
    if conn is None:
        return yahoo.build_company_profile(symbol)
    try:
        security = store.resolve(canonical, conn)
        india = load(conn, security, basis) if security else None
        metrics = screener_metrics(conn, security) if india is not None and not _is_empty(india) else None
    finally:
        conn.close()
    if india is None or _is_empty(india):
        return yahoo.build_company_profile(symbol)

    key = (canonical, india["basis"], _db_stamp())
    now = time.monotonic()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < CACHE_TTL_SECONDS:
            return hit[1]
    try:
        data = yahoo.fetch_company_data(symbol)
        yahoo_note = ""
    except (NoMarketDataError, VendorRateLimitError) as exc:
        data = CompanyData(symbol=canonical, source="NSE filings", fetched=datetime.now())
        yahoo_note = f"Yahoo Finance had nothing to add ({exc}); the quote and ratios that need it are blank."
    profile = _with_india(build_profile(overlay(data, india)), india, data)
    if metrics is not None:
        profile["metrics"] = metrics
        if metrics["basis"] in (None, india["basis"]):  # the standalone view keeps its own ratios
            _screened_key_ratios(profile, metrics)
    if yahoo_note:
        profile["notice"] = yahoo_note
    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.clear()
        _CACHE[key] = (now, profile)
    return profile
