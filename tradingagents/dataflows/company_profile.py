"""One company's fundamentals laid out the way stock screeners show them.

This is a live, present-day view for the browser UI's Company page, not a
point-in-time one: the quote is today's and the statements carry no filing
dates. Nothing an agent or a backtest runs may use it; their look-ahead-safe
data comes through the routed ``get_*`` tools.

A vendor fills a ``CompanyData``: the quote, each statement's fields by period
end in the reporting currency's full units, and the daily price history.
``build_profile`` derives the screener rows, ratios, growth figures and pros and
cons from it and returns a plain JSON-serialisable dict, the shape the page
reads. Yahoo Finance is the only vendor today; another (NSE/BSE filings, say)
fills the same ``CompanyData`` and gets the same page. Every field is optional,
and a missing one shows as a blank, never as a guess:

    quote     name exchange sector industry website summary currency
              financial_currency quote_type price previous_close change
              change_pct market_cap high_52w low_52w pe book_value
              dividend_yield (in percent)
    income    sales total_expenses operating_income cogs interest depreciation
              pbt tax net_profit (minority interest included) net_income (to
              shareholders) eps interest_income net_interest_income
    balance   share_capital equity total_debt lease_liabilities total_assets
              current_assets current_liabilities net_ppe (CWIP included) cwip
              intangibles investments current_investments receivables
              inventory payables shares
    cashflow  operating investing financing free_cash_flow
"""

from __future__ import annotations

import calendar
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from itertools import pairwise
from typing import NamedTuple

Period = dict[str, float]  # field -> value; a field with no value is left out
Statement = dict[str, Period]  # ISO period end -> that period's fields

CRORE = 1e7
MILLION = 1e6


@dataclass
class CompanyData:
    """What a vendor supplies for one company."""

    symbol: str
    quote: dict = field(default_factory=dict)
    quarterly: Statement = field(default_factory=dict)  # income statement, by quarter
    annual: Statement = field(default_factory=dict)  # income statement, by fiscal year
    balance: Statement = field(default_factory=dict)  # fiscal year ends
    cashflow: Statement = field(default_factory=dict)  # fiscal years
    prices: list[tuple[str, float, float | None]] = field(default_factory=list)  # (day, close, volume), oldest first
    prices_from: str | None = None  # another listing of the same shares, when the prices are its
    source: str = "Yahoo Finance"
    fetched: datetime = field(default_factory=datetime.now)
    # Where a section came from when it is not ``source`` (quarterly, annual,
    # balance, cashflow, prices), and a note to show under it.
    sources: dict[str, str] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)
    financial: bool | None = None  # a bank or lender; None decides from the industry name


def as_number(value) -> float | None:
    """A usable number, or None for a blank (None, NaN, infinity, text)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def is_financial(industry: str | None) -> bool:
    """Banks, lenders and insurers: interest or claims are their main cost and
    there is no inventory, so margins, ROCE and working-capital days mean nothing."""
    name = industry or ""
    return (name.startswith(("Banks", "Insurance -"))
            or name in {"Credit Services", "Mortgage Finance", "Financial Conglomerates"})


def display_unit(currency: str | None) -> dict:
    """How money figures are shown: Rs. Crores for rupees, millions otherwise."""
    if currency == "INR":
        return {"currency": "INR", "label": "Rs. Crores", "short": "Cr", "divisor": CRORE,
                "locale": "en-IN"}
    code = currency or ""
    return {"currency": code, "label": f"{code} Millions".strip(), "short": "M",
            "divisor": MILLION, "locale": "en-US"}


def scale(value: float | None, divisor: float) -> float | None:
    """``value`` in display units, to 2 places: ``scale(2.5e9, CRORE) == 250.0``."""
    return None if value is None else round(value / divisor, 2)


# --- Arithmetic over blanks ---------------------------------------------------------
# A blank in, a blank out: a derived figure never stands in for a missing one.

def _add(*values):
    return None if any(v is None for v in values) else sum(values)


def _sub(a, b):
    return None if a is None or b is None else a - b


def _ratio(a, b):
    return None if a is None or not b else a / b


def _pct(a, b):
    r = _ratio(a, b)
    return None if r is None else r * 100


def _days(a, b):
    r = _ratio(a, b)
    return None if r is None else r * 365


def _first(*values):
    return next((v for v in values if v is not None), None)


# --- Formulas -----------------------------------------------------------------------
# Every derived figure on the page. ``p`` is one period's income statement, ``b`` the
# balance sheet at the same period end and ``c`` that year's cash flows.

def operating_income(p):
    """Operating income as reported (after depreciation, before interest and other
    income), else sales minus total expenses."""
    return _first(p.get("operating_income"), _sub(p.get("sales"), p.get("total_expenses")))


def operating_profit(p):
    """Operating income plus depreciation: profit from operations before depreciation,
    interest, other income and tax."""
    return _add(operating_income(p), p.get("depreciation"))


def expenses(p):
    """Sales minus operating profit: operating costs, depreciation excluded."""
    return _sub(p.get("sales"), operating_profit(p))


def opm(p):
    """Operating profit as a % of sales."""
    return _pct(operating_profit(p), p.get("sales"))


def other_income(p):
    """PBT minus operating income, plus interest: everything between operating profit
    and profit before tax except interest, so exceptional items are included."""
    return _add(_sub(p.get("pbt"), operating_income(p)), p.get("interest"))


def tax_rate(p):
    """Tax as a % of profit before tax."""
    return _pct(p.get("tax"), p.get("pbt"))


def ebit(p):
    """Profit before interest and tax: PBT plus interest."""
    return _add(p.get("pbt"), p.get("interest"))


def net_interest_income(p):
    """A bank's interest earned minus interest expended, unless reported."""
    return _first(p.get("net_interest_income"), _sub(p.get("interest_income"), p.get("interest")))


def bank_other_income(p):
    """A bank's net revenue minus net interest income: fees and other income."""
    return _sub(p.get("sales"), net_interest_income(p))


def reserves(b):
    """Shareholders' equity minus share capital."""
    return _sub(b.get("equity"), b.get("share_capital"))


def other_liabilities(b):
    """Total assets minus shareholders' equity and borrowings: the rest of the
    liabilities side, minority interest (and a bank's deposits) included."""
    return _sub(_sub(b.get("total_assets"), b.get("equity")), b.get("total_debt"))


def fixed_assets(b):
    """Net PPE without capital work in progress, plus goodwill and intangibles. The
    vendor's net PPE includes CWIP; an absent CWIP or intangibles figure counts as 0."""
    return _add(_sub(b.get("net_ppe"), b.get("cwip", 0.0)), b.get("intangibles", 0.0))


def investments(b, financial: bool):
    """Investments plus current investments. A bank's short-term investments are
    already inside its investments figure, so they are not added twice."""
    if financial:
        return b.get("investments")
    parts = [b[k] for k in ("investments", "current_investments") if k in b]
    return sum(parts) if parts else None


def other_assets(b, financial: bool):
    """Total assets minus fixed assets, CWIP and investments."""
    known = _add(fixed_assets(b), b.get("cwip", 0.0), investments(b, financial) or 0.0)
    return _sub(b.get("total_assets"), known)


def net_cash_flow(c):
    """Operating plus investing plus financing cash flow."""
    return _add(c.get("operating"), c.get("investing"), c.get("financing"))


def debtor_days(p, b):
    """Receivables as days of sales."""
    return _days(b.get("receivables"), p.get("sales"))


def inventory_days(p, b):
    """Inventory as days of cost of goods sold."""
    return _days(b.get("inventory"), p.get("cogs"))


def days_payable(p, b):
    """Trade payables as days of cost of goods sold."""
    return _days(b.get("payables"), p.get("cogs"))


def cash_conversion_cycle(p, b):
    """Debtor days plus inventory days minus days payable."""
    return _sub(_add(debtor_days(p, b), inventory_days(p, b)), days_payable(p, b))


def working_capital_days(p, b):
    """Current assets minus current liabilities, as days of sales."""
    return _days(_sub(b.get("current_assets"), b.get("current_liabilities")), p.get("sales"))


def roce(p, b):
    """EBIT as a % of capital employed (total assets minus current liabilities) at the
    year end; the vendor has too few years to average opening and closing."""
    return _pct(ebit(p), _sub(b.get("total_assets"), b.get("current_liabilities")))


def roe(p, b):
    """Profit to shareholders as a % of shareholders' equity at the year end."""
    return _pct(p.get("net_income"), b.get("equity"))


def interest_coverage(p):
    """EBIT over interest: how many times operating earnings cover the interest bill."""
    return _ratio(ebit(p), p.get("interest"))


def leverage(b):
    """Borrowings other than lease liabilities, over shareholders' equity."""
    return _ratio(_sub(b.get("total_debt"), b.get("lease_liabilities", 0.0)), b.get("equity"))


def face_value(b):
    """Share capital per share. Indian companies carry share capital at face value;
    elsewhere it often includes paid-in capital, so only rupee reporters use this."""
    return _ratio(b.get("share_capital"), b.get("shares"))


def cagr(start, end, years) -> float | None:
    """Compound annual growth in %, or None unless both ends are positive."""
    if start is None or end is None or years <= 0 or start <= 0 or end <= 0:
        return None
    return ((end / start) ** (1 / years) - 1) * 100


def ttm(quarterly: Statement) -> Period | None:
    """The latest four quarters summed, or None without four consecutive quarters. A
    field missing from any of them is left out, so it shows as a blank."""
    ends = sorted(quarterly, reverse=True)[:4]
    if len(ends) < 4:
        return None
    days = [date.fromisoformat(e) for e in ends]
    if any(not 80 <= (newer - older).days <= 100 for newer, older in pairwise(days)):
        return None
    quarters = [quarterly[e] for e in ends]
    fields = set().union(*quarters)
    return {f: sum(q[f] for q in quarters) for f in fields if all(f in q for q in quarters)}


# --- Tables -------------------------------------------------------------------------

class Row(NamedTuple):
    key: str
    label: str
    kind: str  # money (shown in the display unit) | pct | eps | days
    value: Callable
    hint: str = ""
    strong: bool = False


def _field(name: str) -> Callable:
    return lambda x: x.get(name)


def _doc(fn) -> str:
    return " ".join((fn.__doc__ or "").split())


INCOME_ROWS = (
    Row("sales", "Sales", "money", _field("sales"), "Revenue from operations", True),
    Row("expenses", "Expenses", "money", expenses, _doc(expenses)),
    Row("operating_profit", "Operating Profit", "money", operating_profit, _doc(operating_profit), True),
    Row("opm", "OPM %", "pct", opm, _doc(opm)),
    Row("other_income", "Other Income", "money", other_income, _doc(other_income)),
    Row("interest", "Interest", "money", _field("interest")),
    Row("depreciation", "Depreciation", "money", _field("depreciation")),
    Row("pbt", "Profit before tax", "money", _field("pbt")),
    Row("tax", "Tax %", "pct", tax_rate, _doc(tax_rate)),
    Row("net_profit", "Net Profit", "money", _field("net_profit"),
        "Profit after tax, minority interest included", True),
    Row("eps", "EPS", "eps", _field("eps"), "Diluted earnings per share, in the reporting currency"),
)

BANK_INCOME_ROWS = (
    Row("interest_income", "Interest Earned", "money", _field("interest_income")),
    Row("interest", "Interest Expended", "money", _field("interest")),
    Row("net_interest_income", "Net Interest Income", "money", net_interest_income,
        _doc(net_interest_income), True),
    Row("other_income", "Other Income", "money", bank_other_income, _doc(bank_other_income)),
    Row("sales", "Net Revenue", "money", _field("sales"),
        "Net interest income plus other income: the vendor's revenue figure for a bank", True),
    Row("depreciation", "Depreciation", "money", _field("depreciation")),
    Row("pbt", "Profit before tax", "money", _field("pbt")),
    Row("tax", "Tax %", "pct", tax_rate, _doc(tax_rate)),
    Row("net_profit", "Net Profit", "money", _field("net_profit"),
        "Profit after tax, minority interest included", True),
    Row("eps", "EPS", "eps", _field("eps"), "Diluted earnings per share, in the reporting currency"),
)


def _balance_rows(financial: bool) -> tuple[Row, ...]:
    return (
        Row("equity_capital", "Equity Capital", "money", _field("share_capital"), "Share capital"),
        Row("reserves", "Reserves", "money", reserves, _doc(reserves)),
        Row("borrowings", "Borrowings", "money", _field("total_debt"), "Total debt, lease liabilities included"),
        Row("other_liabilities", "Deposits & Other Liabilities" if financial else "Other Liabilities",
            "money", other_liabilities, _doc(other_liabilities)),
        Row("total_liabilities", "Total Liabilities", "money", _field("total_assets"),
            "The liabilities side of the balance sheet, equity included; equal to total assets", True),
        Row("fixed_assets", "Fixed Assets", "money", fixed_assets, _doc(fixed_assets)),
        Row("cwip", "CWIP", "money", _field("cwip"), "Capital work in progress"),
        Row("investments", "Investments", "money", lambda b: investments(b, financial), _doc(investments)),
        Row("other_assets", "Other Assets", "money", lambda b: other_assets(b, financial), _doc(other_assets)),
        Row("total_assets", "Total Assets", "money", _field("total_assets"), "", True),
    )


CASHFLOW_ROWS = (
    Row("operating", "Cash from Operating Activity", "money", _field("operating")),
    Row("investing", "Cash from Investing Activity", "money", _field("investing")),
    Row("financing", "Cash from Financing Activity", "money", _field("financing")),
    Row("net", "Net Cash Flow", "money", net_cash_flow, _doc(net_cash_flow), True),
    Row("free_cash_flow", "Free Cash Flow", "money", _field("free_cash_flow"),
        "Operating cash flow minus capital expenditure"),
)


def _pair(fn) -> Callable:
    return lambda pb: fn(*pb)


RATIO_ROWS = (
    Row("debtor_days", "Debtor Days", "days", _pair(debtor_days), _doc(debtor_days)),
    Row("inventory_days", "Inventory Days", "days", _pair(inventory_days), _doc(inventory_days)),
    Row("days_payable", "Days Payable", "days", _pair(days_payable), _doc(days_payable)),
    Row("cash_conversion_cycle", "Cash Conversion Cycle", "days", _pair(cash_conversion_cycle),
        _doc(cash_conversion_cycle)),
    Row("working_capital_days", "Working Capital Days", "days", _pair(working_capital_days),
        _doc(working_capital_days)),
    Row("roce", "ROCE %", "pct", _pair(roce), _doc(roce), True),
    Row("roe", "ROE %", "pct", _pair(roe), _doc(roe)),
)
BANK_RATIO_ROWS = (RATIO_ROWS[-1],)

BANK_NOTE = ("Banks and lenders pay interest as their main cost and carry no inventory, so "
             "operating profit, OPM, ROCE and the working-capital ratios do not apply and are left out.")


def period_label(end: str) -> str:
    """``2026-03-31`` -> ``Mar 2026``."""
    return date.fromisoformat(end).strftime("%b %Y")


def _shown(row: Row, source, divisor: float):
    value = as_number(row.value(source))
    if value is None:
        return None
    return scale(value, divisor) if row.kind == "money" else round(value, 2)


def _table(columns: list[tuple[dict, object]], rows, divisor: float, note: str = "",
           anchor: str | None = None) -> dict:
    """Rows by period, oldest first, in display units. ``columns`` pairs each period's
    header with what the row formulas read for it. A period without the ``anchor`` row
    (a stray column of leftovers) is dropped, or without any figure if none has it."""
    grid = [[_shown(row, source, divisor) for _, source in columns] for row in rows]
    anchored = [values for row, values in zip(rows, grid, strict=True) if row.key == anchor]
    if not (anchored and any(v is not None for v in anchored[0])):
        anchored = grid
    keep = [i for i in range(len(columns)) if any(values[i] is not None for values in anchored)]
    return {
        "periods": [columns[i][0] for i in keep],
        "rows": [{"key": row.key, "label": row.label, "kind": row.kind, "hint": row.hint,
                  "strong": row.strong, "values": [values[i] for i in keep]}
                 for row, values in zip(rows, grid, strict=True)] if keep else [],
        "note": note,
    }


def _header(end: str, ttm_: bool = False) -> dict:
    return {"label": "TTM" if ttm_ else period_label(end), "end": end, "ttm": ttm_}


def _add_months(day: date, months: int) -> date:
    """The last day of the month ``months`` after ``day``'s month (quarter ends are month ends)."""
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    return date(year, month + 1, calendar.monthrange(year, month + 1)[1])


def missing_quarters(ends: list[str]) -> list[str]:
    """Quarters absent between the earliest and latest period ends, as labels."""
    days = sorted(date.fromisoformat(e) for e in ends)
    gaps = []
    for older, newer in pairwise(days):
        step = _add_months(older, 3)
        while (newer - step).days > 45:
            gaps.append(step.strftime("%b %Y"))
            step = _add_months(step, 3)
    return gaps


# --- Growth -------------------------------------------------------------------------

def _years_before(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February
        return day.replace(year=day.year - years, day=28)


def _years_label(n: int) -> str:
    return f"{n} Year" if n == 1 else f"{n} Years"


def _rounded(value):
    return None if value is None else round(value, 2)


def annual_growth(series: list[tuple[date, float]], horizons=(3, 5)) -> list[dict]:
    """CAGR of a fiscal-year series over each horizon it covers, then over all of it.

    A horizon is covered when a fiscal year ends within 45 days of that many years
    before the latest one. The whole span is listed only when it differs from those.
    """
    if len(series) < 2:
        return []
    last_day, last = series[-1]
    items, spans = [], set()
    for n in horizons:
        target = _years_before(last_day, n)
        start = next((v for d, v in series if abs((d - target).days) <= 45), None)
        if start is not None:
            items.append({"label": _years_label(n), "value": _rounded(cagr(start, last, n))})
            spans.add(n)
    first_day, first = series[0]
    span = round((last_day - first_day).days / 365.25)
    if span >= 1 and span not in spans:
        items.append({"label": _years_label(span), "value": _rounded(cagr(first, last, span))})
    return items


def price_growth(dates: list[date], closes: list[float], horizons=(1, 3, 5)) -> list[dict]:
    """Price CAGR over each horizon the history covers, then over all of it. A horizon
    starts at the last close within 10 days before its date (weekends and holidays)."""
    if len(dates) < 2:
        return []
    last_day, last = dates[-1], closes[-1]
    items, spans = [], set()
    for n in horizons:
        target = _years_before(last_day, n)
        start = next(((d, c) for d, c in zip(reversed(dates), reversed(closes), strict=True)
                      if d <= target), None)
        if start is None or (target - start[0]).days > 10:
            continue
        items.append({"label": _years_label(n), "value": _rounded(cagr(start[1], last, n))})
        spans.add(n)
    years = (last_day - dates[0]).days / 365.25
    if years >= 1 and round(years) not in spans:
        items.append({"label": _years_label(round(years)), "value": _rounded(cagr(closes[0], last, years))})
    return items


def roe_averages(values: list[float]) -> list[dict]:
    """The latest ROE, then its average over the last 3 and 5 years and all years held."""
    if not values:
        return []
    items = [{"label": "Last Year", "value": _rounded(values[-1])}]
    for n in sorted({3, 5, len(values)}):
        if 1 < n <= len(values):
            items.append({"label": _years_label(n), "value": _rounded(sum(values[-n:]) / n)})
    return items


# --- Pros and cons ------------------------------------------------------------------

def _below(value, limit) -> bool:
    return value is not None and value < limit


def _above(value, limit) -> bool:
    return value is not None and value > limit


def _at_least(value, limit) -> bool:
    return value is not None and value >= limit


class Rule(NamedTuple):
    kind: str  # "pro" or "con"
    banks: bool  # also applies to banks and lenders
    test: Callable[[dict], bool]
    message: str  # str.format over the facts


# Fixed rules over the facts ``_facts`` computes; add one by adding a row (and the fact
# it reads, if it is new). A rule whose fact is blank stays silent.
RULES = (
    Rule("pro", False, lambda f: _below(f["leverage"], 0.1),
         "Almost debt-free: borrowings other than leases are under 10% of equity."),
    Rule("pro", True, lambda f: _at_least(f["roe_min_3y"], 20),
         "Return on equity above 20% in each of the last 3 years."),
    Rule("pro", True, lambda f: _at_least(f["sales_cagr_3y"], 15),
         "{revenue} grew {sales_cagr_3y:.1f}% a year over the last 3 years."),
    Rule("pro", True, lambda f: _at_least(f["profit_cagr_3y"], 15),
         "Profit grew {profit_cagr_3y:.1f}% a year over the last 3 years."),
    Rule("pro", True, lambda f: _at_least(f["dividend_yield"], 2),
         "Dividend yield of {dividend_yield:.2f}%."),
    Rule("pro", False, lambda f: f["fcf_years"] >= 3 and f["fcf_negative"] == 0,
         "Positive free cash flow in each of the last {fcf_years} years."),
    Rule("pro", True, lambda f: _below(f["price_to_book"], 1),
         "Trades below book value, at {price_to_book:.2f} times book."),
    Rule("con", False, lambda f: _below(f["coverage"], 3),
         "Low interest coverage: EBIT covers interest {coverage:.1f} times."),
    Rule("con", False, lambda f: _above(f["leverage"], 1),
         "High debt: borrowings other than leases are {leverage:.1f} times equity."),
    Rule("con", True, lambda f: _below(f["sales_cagr_3y"], 5),
         "{revenue} growth below 5% a year over the last 3 years ({sales_cagr_3y:.1f}%)."),
    Rule("con", True, lambda f: _below(f["profit_cagr_3y"], 0),
         "Profit fell over the last 3 years ({profit_cagr_3y:.1f}% a year)."),
    Rule("con", True, lambda f: _below(f["net_profit"], 0), "Made a loss in the latest year."),
    Rule("con", True, lambda f: _below(f["roe_avg_3y"], 10),
         "Low return on equity: {roe_avg_3y:.1f}% on average over the last 3 years."),
    Rule("con", False, lambda f: _below(_sub(f["opm_now"], f["opm_3y_ago"]), -3),
         "Operating margin fell from {opm_3y_ago:.1f}% to {opm_now:.1f}% over the last 3 years."),
    Rule("con", False, lambda f: f["fcf_negative"] >= 2,
         "Negative free cash flow in {fcf_negative} of the last {fcf_years} years."),
    Rule("con", True, lambda f: _above(f["price_to_book"], 6),
         "Trades at {price_to_book:.1f} times book value."),
)


def pros_and_cons(facts: dict, financial: bool) -> tuple[list[str], list[str]]:
    """The messages of the rules that fire, pros first."""
    fired = {"pro": [], "con": []}
    for rule in RULES:
        if (rule.banks or not financial) and rule.test(facts):
            fired[rule.kind].append(rule.message.format(**facts))
    return fired["pro"], fired["con"]


def _series(statement: Statement, fn) -> list[tuple[date, float]]:
    out = []
    for end in sorted(statement):
        value = as_number(fn(statement[end]))
        if value is not None:
            out.append((date.fromisoformat(end), value))
    return out


def _value_years_ago(series: list[tuple[date, float]], years: int):
    if not series:
        return None
    target = _years_before(series[-1][0], years)
    return next((v for d, v in series if abs((d - target).days) <= 45), None)


def _facts(data: CompanyData, roes: list[float], price, financial: bool) -> dict:
    """The figures the rules read, each None when the data cannot give it."""
    q, annual = data.quote, data.annual
    sales = _series(annual, _field("sales"))
    profit = _series(annual, _field("net_profit"))
    margins = _series(annual, opm)
    fcf = [v for _, v in _series(data.cashflow, _field("free_cash_flow"))][-5:]
    latest_income = annual[max(annual)] if annual else {}
    latest_balance = data.balance[max(data.balance)] if data.balance else {}
    book = as_number(q.get("book_value"))
    same_currency = (q.get("currency") or "") == (q.get("financial_currency") or q.get("currency") or "")
    return {
        "revenue": "Revenue" if financial else "Sales",
        "leverage": leverage(latest_balance),
        "coverage": interest_coverage(latest_income),
        "roe_min_3y": min(roes[-3:]) if len(roes) >= 3 else None,
        "roe_avg_3y": sum(roes[-3:]) / 3 if len(roes) >= 3 else None,
        "sales_cagr_3y": cagr(_value_years_ago(sales, 3), sales[-1][1], 3) if sales else None,
        "profit_cagr_3y": cagr(_value_years_ago(profit, 3), profit[-1][1], 3) if profit else None,
        "net_profit": profit[-1][1] if profit else None,
        "dividend_yield": as_number(q.get("dividend_yield")),
        "price_to_book": _ratio(price, book) if same_currency and book and book > 0 else None,
        "opm_now": margins[-1][1] if margins else None,
        "opm_3y_ago": _value_years_ago(margins, 3),
        "fcf_years": len(fcf),
        "fcf_negative": sum(1 for v in fcf if v < 0),
    }


# --- The profile --------------------------------------------------------------------

def _price(data: CompanyData) -> dict:
    q = data.quote
    last = data.prices[-1] if data.prices else None
    price = _first(as_number(q.get("price")), last and last[1])
    previous = as_number(q.get("previous_close"))
    change = _first(as_number(q.get("change")), _sub(price, previous))
    change_pct = _first(as_number(q.get("change_pct")), _pct(change, previous))
    return {"value": price, "change": _rounded(change), "changePct": _rounded(change_pct),
            "date": last[0] if last else None}


def _source(data: CompanyData, section: str) -> str:
    return data.sources.get(section) or data.source


def _with_note(note: str, extra: str) -> str:
    return " ".join(n for n in (note, extra) if n)


def _chart(data: CompanyData) -> dict:
    prices = data.prices
    note = (f"{_source(data, 'prices')} has no price history for {data.symbol}, so the chart and price "
            f"CAGR use the same shares' {data.prices_from} listing." if data.prices_from else "")
    return {
        "symbol": data.prices_from or data.symbol,
        "note": _with_note(note, data.notes.get("prices", "")),
        "source": _source(data, "prices"),
        "dates": [d for d, _, _ in prices],
        "close": [round(c, 4 if abs(c) < 10 else 2) for _, c, _ in prices],
        "volume": [None if v is None else int(v) for _, _, v in prices],
    }


def build_profile(data: CompanyData) -> dict:
    """The Company page's data: header, key ratios, chart series, statements in
    screener layout, ratios, growth, and the pros and cons the rules find."""
    q = data.quote
    financial = data.financial if data.financial is not None else is_financial(q.get("industry"))
    currency = q.get("currency")
    reporting = q.get("financial_currency") or currency
    unit, cap_unit = display_unit(reporting), display_unit(currency)
    divisor = unit["divisor"]
    price = _price(data)

    # Statements, oldest period first.
    income_rows = BANK_INCOME_ROWS if financial else INCOME_ROWS
    quarter_ends = sorted(data.quarterly)
    gaps = missing_quarters(quarter_ends)
    quarter_notes = [BANK_NOTE] if financial else []
    if gaps:
        quarter_notes.append(f"{_source(data, 'quarterly')} has no figures for {', '.join(gaps)}.")
    quarter_notes.append(data.notes.get("quarterly", ""))
    quarters = _table([(_header(e), data.quarterly[e]) for e in quarter_ends],
                      income_rows, divisor, " ".join(n for n in quarter_notes if n), anchor="sales")

    annual_ends = sorted(data.annual)
    columns = [(_header(e), data.annual[e]) for e in annual_ends]
    trailing = ttm(data.quarterly)
    pl_notes = [BANK_NOTE] if financial else []
    if trailing and (not annual_ends or quarter_ends[-1] > annual_ends[-1]):
        columns.append((_header(quarter_ends[-1], True), trailing))
    elif quarter_ends and not trailing:
        pl_notes.append(f"No TTM column: that needs four consecutive quarters, and "
                        f"{_source(data, 'quarterly')} does not have them.")
    pl_notes.append(data.notes.get("annual", ""))
    profit_loss = _table(columns, income_rows, divisor, " ".join(n for n in pl_notes if n), anchor="sales")

    balance_ends = sorted(data.balance)
    balance_sheet = _table([(_header(e), data.balance[e]) for e in balance_ends],
                           _balance_rows(financial), divisor, data.notes.get("balance", ""),
                           anchor="total_assets")
    cash_flows = _table([(_header(e), data.cashflow[e]) for e in sorted(data.cashflow)],
                        CASHFLOW_ROWS, divisor, data.notes.get("cashflow", ""), anchor="operating")
    ratios = _table([(_header(e), (data.annual.get(e, {}), data.balance[e])) for e in balance_ends],
                    BANK_RATIO_ROWS if financial else RATIO_ROWS, divisor,
                    BANK_NOTE if financial else "")

    # ROE by fiscal year, for the key ratios, the growth boxes and the rules.
    roe_series = [(e, v) for e in balance_ends
                  if (v := as_number(roe(data.annual.get(e, {}), data.balance[e]))) is not None]
    roes = [v for _, v in roe_series]
    latest_year = balance_ends[-1] if balance_ends else None
    latest_roce = (as_number(roce(data.annual.get(latest_year, {}), data.balance[latest_year]))
                   if latest_year else None)
    year_hint = f"Fiscal year to {period_label(latest_year)}, from the statements" if latest_year else ""

    key_ratios = [
        {"key": "market_cap", "label": "Market Cap", "kind": "cap", "unit": cap_unit,
         "value": scale(as_number(q.get("market_cap")), cap_unit["divisor"])},
        {"key": "price", "label": "Current Price", "kind": "price", "currency": currency,
         "value": price["value"]},
        {"key": "high_low", "label": "High / Low", "kind": "range", "currency": currency,
         "value": [as_number(q.get("high_52w")), as_number(q.get("low_52w"))], "hint": "52 weeks"},
        {"key": "pe", "label": "Stock P/E", "kind": "number", "value": _rounded(as_number(q.get("pe"))),
         "hint": "Price over trailing twelve months' earnings per share"},
        {"key": "book_value", "label": "Book Value", "kind": "price", "currency": reporting,
         "value": as_number(q.get("book_value")), "hint": "Per share"},
        {"key": "dividend_yield", "label": "Dividend Yield", "kind": "pct",
         "value": _rounded(as_number(q.get("dividend_yield")))},
    ]
    if not financial:
        key_ratios.append({"key": "roce", "label": "ROCE", "kind": "pct", "value": _rounded(latest_roce),
                           "hint": year_hint})
    key_ratios.append({"key": "roe", "label": "ROE", "kind": "pct",
                       "value": _rounded(roes[-1]) if roe_series and roe_series[-1][0] == latest_year else None,
                       "hint": year_hint})
    key_ratios.append({"key": "face_value", "label": "Face Value", "kind": "price", "currency": reporting,
                       "value": _rounded(face_value(data.balance[latest_year]))
                       if reporting == "INR" and latest_year else None,
                       "hint": "Share capital over shares issued"})

    days = [date.fromisoformat(d) for d, _, _ in data.prices]
    closes = [c for _, c, _ in data.prices]
    growth = [
        {"key": "sales", "title": "Compounded Revenue Growth" if financial else "Compounded Sales Growth",
         "items": annual_growth(_series(data.annual, _field("sales")))},
        {"key": "profit", "title": "Compounded Profit Growth",
         "items": annual_growth(_series(data.annual, _field("net_profit")))},
        {"key": "price", "title": "Stock Price CAGR", "items": price_growth(days, closes)},
        {"key": "roe", "title": "Return on Equity", "items": roe_averages(roes)},
    ]
    pros, cons = pros_and_cons(_facts(data, roes, price["value"], financial), financial)

    return {
        "symbol": data.symbol,
        "name": q.get("name") or data.symbol,
        "exchange": q.get("exchange"),
        "sector": q.get("sector"),
        "industry": q.get("industry"),
        "website": q.get("website"),
        "summary": q.get("summary"),
        "quoteType": q.get("quote_type"),
        "currency": currency,
        "financialCurrency": reporting,
        "financial": financial,
        "price": price,
        "unit": unit,
        "keyRatios": key_ratios,
        "chart": _chart(data),
        "quarters": {**quarters, "source": _source(data, "quarterly")},
        "profitLoss": {**profit_loss, "source": _source(data, "annual")},
        "balanceSheet": {**balance_sheet, "source": _source(data, "balance")},
        "cashFlows": {**cash_flows, "source": _source(data, "cashflow")},
        "ratios": {**ratios, "source": " and ".join(dict.fromkeys(
            (_source(data, "annual"), _source(data, "balance"))))},
        "growth": [g for g in growth if g["items"]],
        "pros": pros,
        "cons": cons,
        "source": {
            "name": data.source,
            "fetched": data.fetched.isoformat(timespec="seconds"),
            "annual": sum(1 for p in profit_loss["periods"] if not p["ttm"]),
            "quarterly": len(quarters["periods"]),
        },
    }
