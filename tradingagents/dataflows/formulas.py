"""The formulas behind every derived figure: one place, shared by the Company page
and the stock screener, so a stock's ROCE is the same number on both.

Pure functions over plain field dicts, with no I/O and no notion of time: they
compute whatever figures they are handed. ``company_profile`` (the live Company
page) hands them today's figures; the screener's snapshot hands them figures
read as of a date. The field names are the ones ``company_profile.CompanyData``
documents (sales, operating_income, depreciation, pbt, net_profit, equity,
total_debt, ...), in the reporting currency's full units.

``p`` is one period's income statement, ``b`` the balance sheet at the same
period end and ``c`` that year's cash flows.
"""

from __future__ import annotations

import calendar
import math
from datetime import date
from itertools import pairwise

Period = dict[str, float]  # field -> value; a field with no value is left out
Statement = dict[str, Period]  # ISO period end -> that period's fields

CRORE = 1e7
MILLION = 1e6


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


# --- Arithmetic over blanks ---------------------------------------------------------
# A blank in, a blank out: a derived figure never stands in for a missing one.

def add(*values):
    return None if any(v is None for v in values) else sum(values)


def sub(a, b):
    return None if a is None or b is None else a - b


def ratio(a, b):
    return None if a is None or not b else a / b


def pct(a, b):
    r = ratio(a, b)
    return None if r is None else r * 100


def days_of(a, b):
    r = ratio(a, b)
    return None if r is None else r * 365


def first(*values):
    return next((v for v in values if v is not None), None)


# --- One period ---------------------------------------------------------------------

def operating_income(p):
    """Operating income as reported (after depreciation, before interest and other
    income), else sales minus total expenses."""
    return first(p.get("operating_income"), sub(p.get("sales"), p.get("total_expenses")))


def operating_profit(p):
    """Operating income plus depreciation: profit from operations before depreciation,
    interest, other income and tax."""
    return add(operating_income(p), p.get("depreciation"))


def expenses(p):
    """Sales minus operating profit: operating costs, depreciation excluded."""
    return sub(p.get("sales"), operating_profit(p))


def opm(p):
    """Operating profit as a % of sales."""
    return pct(operating_profit(p), p.get("sales"))


def npm(p):
    """Net profit as a % of sales."""
    return pct(p.get("net_profit"), p.get("sales"))


def gross_margin(p):
    """Sales minus cost of goods sold, as a % of sales."""
    return pct(sub(p.get("sales"), p.get("cogs")), p.get("sales"))


def other_income(p):
    """PBT minus operating income, plus interest: everything between operating profit
    and profit before tax except interest, so exceptional items are included."""
    return add(sub(p.get("pbt"), operating_income(p)), p.get("interest"))


def tax_rate(p):
    """Tax as a % of profit before tax."""
    return pct(p.get("tax"), p.get("pbt"))


def ebit(p):
    """Profit before interest and tax: PBT plus interest."""
    return add(p.get("pbt"), p.get("interest"))


def net_interest_income(p):
    """A bank's interest earned minus interest expended, unless reported."""
    return first(p.get("net_interest_income"), sub(p.get("interest_income"), p.get("interest")))


def bank_other_income(p):
    """A bank's net revenue minus net interest income: fees and other income."""
    return sub(p.get("sales"), net_interest_income(p))


def reserves(b):
    """Shareholders' equity minus share capital."""
    return sub(b.get("equity"), b.get("share_capital"))


def other_liabilities(b):
    """Total assets minus shareholders' equity and borrowings: the rest of the
    liabilities side, minority interest (and a bank's deposits) included."""
    return sub(sub(b.get("total_assets"), b.get("equity")), b.get("total_debt"))


def fixed_assets(b):
    """Net PPE without capital work in progress, plus goodwill and intangibles. The
    vendor's net PPE includes CWIP; an absent CWIP or intangibles figure counts as 0."""
    return add(sub(b.get("net_ppe"), b.get("cwip", 0.0)), b.get("intangibles", 0.0))


def investments(b, financial: bool):
    """Investments plus current investments. A bank's short-term investments are
    already inside its investments figure, so they are not added twice."""
    if financial:
        return b.get("investments")
    parts = [b[k] for k in ("investments", "current_investments") if k in b]
    return sum(parts) if parts else None


def other_assets(b, financial: bool):
    """Total assets minus fixed assets, CWIP and investments."""
    known = add(fixed_assets(b), b.get("cwip", 0.0), investments(b, financial) or 0.0)
    return sub(b.get("total_assets"), known)


def net_cash_flow(c):
    """Operating plus investing plus financing cash flow."""
    return add(c.get("operating"), c.get("investing"), c.get("financing"))


def debtor_days(p, b):
    """Receivables as days of sales."""
    return days_of(b.get("receivables"), p.get("sales"))


def inventory_days(p, b):
    """Inventory as days of cost of goods sold."""
    return days_of(b.get("inventory"), p.get("cogs"))


def days_payable(p, b):
    """Trade payables as days of cost of goods sold."""
    return days_of(b.get("payables"), p.get("cogs"))


def cash_conversion_cycle(p, b):
    """Debtor days plus inventory days minus days payable."""
    return sub(add(debtor_days(p, b), inventory_days(p, b)), days_payable(p, b))


def working_capital_days(p, b):
    """Current assets minus current liabilities, as days of sales."""
    return days_of(sub(b.get("current_assets"), b.get("current_liabilities")), p.get("sales"))


def roce(p, b):
    """EBIT as a % of capital employed (total assets minus current liabilities) at the
    year end; the vendor has too few years to average opening and closing."""
    return pct(ebit(p), sub(b.get("total_assets"), b.get("current_liabilities")))


def roe(p, b):
    """Profit to shareholders as a % of shareholders' equity at the year end."""
    return pct(p.get("net_income"), b.get("equity"))


def roa(p, b):
    """Profit to shareholders as a % of total assets at the year end."""
    return pct(p.get("net_income"), b.get("total_assets"))


def interest_coverage(p):
    """EBIT over interest: how many times operating earnings cover the interest bill."""
    return ratio(ebit(p), p.get("interest"))


def leverage(b):
    """Borrowings other than lease liabilities, over shareholders' equity."""
    return ratio(sub(b.get("total_debt"), b.get("lease_liabilities", 0.0)), b.get("equity"))


def current_ratio(b):
    """Current assets over current liabilities."""
    return ratio(b.get("current_assets"), b.get("current_liabilities"))


def face_value(b):
    """Share capital per share. Indian companies carry share capital at face value;
    elsewhere it often includes paid-in capital, so only rupee reporters use this."""
    return ratio(b.get("share_capital"), b.get("shares"))


# --- Across periods -----------------------------------------------------------------

def cagr(start, end, years) -> float | None:
    """Compound annual growth in %, or None unless both ends are positive."""
    if start is None or end is None or years <= 0 or start <= 0 or end <= 0:
        return None
    return ((end / start) ** (1 / years) - 1) * 100


def change_pct(old, new) -> float | None:
    """Growth from ``old`` to ``new`` in %, or None unless ``old`` is positive (growth
    from a loss or from nothing has no meaningful percentage)."""
    if old is None or new is None or old <= 0:
        return None
    return (new / old - 1) * 100


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


def trailing_year(quarterly: Statement, annual: Statement) -> Period | None:
    """The latest twelve months, as the Company page's last profit-and-loss column
    has them: the trailing four quarters when the newest quarter is after the newest
    fiscal year, else that fiscal year. None when the newest figures are a quarter
    without three consecutive ones before it, since a stale year is not the TTM."""
    newest_year = max(annual) if annual else None
    newest_quarter = max(quarterly) if quarterly else None
    if newest_quarter is not None and (newest_year is None or newest_quarter > newest_year):
        return ttm(quarterly)
    return annual[newest_year] if newest_year is not None else None


def years_before(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February
        return day.replace(year=day.year - years, day=28)


def months_before(day: date, months: int) -> date:
    """The same day ``months`` calendar months earlier, or that month's last day."""
    index = day.year * 12 + day.month - 1 - months
    year, month = divmod(index, 12)
    last = calendar.monthrange(year, month + 1)[1]
    return date(year, month + 1, min(day.day, last))


def series(statement: Statement, fn) -> list[tuple[date, float]]:
    """``fn`` of each period with a value, oldest first, as (period end, value)."""
    out = []
    for end in sorted(statement):
        value = as_number(fn(statement[end]))
        if value is not None:
            out.append((date.fromisoformat(end), value))
    return out


def value_years_ago(values: list[tuple[date, float]], years: int):
    """The value of the period ending within 45 days of ``years`` before the latest one."""
    if not values:
        return None
    target = years_before(values[-1][0], years)
    return next((v for d, v in values if abs((d - target).days) <= 45), None)


def growth(values: list[tuple[date, float]], years: int) -> float | None:
    """CAGR of a fiscal-year series over ``years`` to its latest value, or None when
    the series has no year that many years back."""
    if not values:
        return None
    return cagr(value_years_ago(values, years), values[-1][1], years)


def _years_label(n: int) -> str:
    return f"{n} Year" if n == 1 else f"{n} Years"


def _rounded(value):
    return None if value is None else round(value, 2)


def annual_growth(values: list[tuple[date, float]], horizons=(3, 5)) -> list[dict]:
    """CAGR of a fiscal-year series over each horizon it covers, then over all of it.

    A horizon is covered when a fiscal year ends within 45 days of that many years
    before the latest one. The whole span is listed only when it differs from those.
    """
    if len(values) < 2:
        return []
    last_day, last = values[-1]
    items, spans = [], set()
    for n in horizons:
        start = value_years_ago(values, n)
        if start is not None:
            items.append({"label": _years_label(n), "value": _rounded(cagr(start, last, n))})
            spans.add(n)
    first_day, first_value = values[0]
    span = round((last_day - first_day).days / 365.25)
    if span >= 1 and span not in spans:
        items.append({"label": _years_label(span), "value": _rounded(cagr(first_value, last, span))})
    return items


def close_before(dates: list[date], closes: list[float], target: date, slack_days: int = 10):
    """The last close on or before ``target``, if it is within ``slack_days`` of it
    (weekends and holidays), else None."""
    start = next(((d, c) for d, c in zip(reversed(dates), reversed(closes), strict=True) if d <= target), None)
    if start is None or (target - start[0]).days > slack_days:
        return None
    return start[1]


def price_growth(dates: list[date], closes: list[float], horizons=(1, 3, 5)) -> list[dict]:
    """Price CAGR over each horizon the history covers, then over all of it. A horizon
    starts at the last close within 10 days before its date (weekends and holidays)."""
    if len(dates) < 2:
        return []
    last_day, last = dates[-1], closes[-1]
    items, spans = [], set()
    for n in horizons:
        start = close_before(dates, closes, years_before(last_day, n))
        if start is None:
            continue
        items.append({"label": _years_label(n), "value": _rounded(cagr(start, last, n))})
        spans.add(n)
    years = (last_day - dates[0]).days / 365.25
    if years >= 1 and round(years) not in spans:
        items.append({"label": _years_label(round(years)), "value": _rounded(cagr(closes[0], last, years))})
    return items


def sma(closes: list[float], n: int) -> float | None:
    """The mean of the last ``n`` closes, or None with fewer than ``n``."""
    return sum(closes[-n:]) / n if n > 0 and len(closes) >= n else None


def rsi(closes: list[float], n: int = 14) -> float | None:
    """Wilder's relative strength index of the closes, 0 to 100: the first average
    gain and loss over ``n`` changes, then smoothed by (n - 1)/n each day after.
    None with fewer than ``n + 1`` closes, or when the price never moved."""
    if len(closes) < n + 1:
        return None
    changes = [b - a for a, b in pairwise(closes)]
    gain = sum(max(c, 0.0) for c in changes[:n]) / n
    loss = sum(max(-c, 0.0) for c in changes[:n]) / n
    for c in changes[n:]:
        gain = (gain * (n - 1) + max(c, 0.0)) / n
        loss = (loss * (n - 1) + max(-c, 0.0)) / n
    if loss == 0:
        return 100.0 if gain > 0 else None
    return 100 - 100 / (1 + gain / loss)


def average_of_last(values: list[float], n: int) -> float | None:
    """The mean of the last ``n`` values, or None with fewer than ``n``."""
    return sum(values[-n:]) / n if n > 0 and len(values) >= n else None


def roe_averages(values: list[float]) -> list[dict]:
    """The latest ROE, then its average over the last 3 and 5 years and all years held."""
    if not values:
        return []
    items = [{"label": "Last Year", "value": _rounded(values[-1])}]
    for n in sorted({3, 5, len(values)}):
        if 1 < n <= len(values):
            items.append({"label": _years_label(n), "value": _rounded(average_of_last(values, n))})
    return items
