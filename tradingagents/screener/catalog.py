"""The metrics catalog: every figure a screen can filter on, defined once.

Each ``Metric`` carries its key (the snapshot column, snake_case), the name and
aliases a query may use, a category, a unit, a description in our own words,
the function that computes it from a ``Company``, and whether it applies to
banks and lenders. The compute functions call ``dataflows.formulas``, the same
formulas the Company page runs, so the two always agree.

Units, as queries are written:

    Rs Cr    rupee amounts in crores (``Market Capitalization > 500`` is Rs 500 Cr)
    Rs       per-share prices and amounts, in rupees
    %        percentages (``ROCE > 20`` is 20%)
    % pts    changes in a percentage, in percentage points
    x        multiples (P/E, debt to equity)
    days     working-capital days
    shares   share counts, Cr shares in crores of shares
    score    Piotroski's 0 to 9

Missing data is None (NULL in the snapshot), never 0. A metric marked
``non_financial`` is None for banks and NBFCs (filers of the banking or NBFC
results formats): their interest is their main cost and they have no current
assets, so margins, ROCE, debt to equity and working-capital figures say nothing.

"TTM" is the trailing twelve months: the latest four quarters summed when the
newest quarter is after the newest fiscal year, else that fiscal year (the
Company page's last profit-and-loss column). "Last year" is the newest fiscal
year filed. Balance-sheet figures are the newest year-end balance sheet's, as on
the Company page.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from tradingagents.dataflows import formulas as f
from tradingagents.screener.company import Company

CATALOG_VERSION = 1

ALL, NON_FINANCIAL = "all", "non_financial"
NUMBER, TEXT = "number", "text"
RS_CR, RS, PCT, PTS, TIMES, DAYS, SCORE, SHARES, CR_SHARES, COUNT = (
    "Rs Cr", "Rs", "%", "% pts", "x", "days", "score", "shares", "Cr shares", "count")

CATEGORIES = ("Company", "Valuation", "Profitability", "Size", "Growth", "Quarterly results",
              "Balance sheet", "Cash flow", "Shareholding", "Price and technicals", "Composite")


@dataclass(frozen=True)
class Metric:
    key: str
    name: str
    category: str
    unit: str
    description: str
    compute: Callable[[Company], object]
    aliases: tuple[str, ...] = ()
    applies: str = ALL
    kind: str = NUMBER
    decimals: int = 2

    def value(self, company: Company):
        """This metric for ``company``: a finite number, a non-empty text or None."""
        if self.applies == NON_FINANCIAL and company.financial:
            return None
        raw = self.compute(company)
        if self.kind == TEXT:
            text = str(raw).strip() if raw is not None else ""
            return text or None
        return f.as_number(raw)

    def describe(self) -> dict:
        return {"key": self.key, "name": self.name, "aliases": list(self.aliases), "category": self.category,
                "unit": self.unit, "description": self.description, "kind": self.kind,
                "applies": self.applies, "decimals": self.decimals}


METRICS: dict[str, Metric] = {}


def _m(key, name, category, unit, description, compute, *aliases, applies=ALL, kind=NUMBER, decimals=2):
    assert key not in METRICS, key
    METRICS[key] = Metric(key, name, category, unit, " ".join(description.split()), compute, aliases,
                          applies, kind, decimals)


def _cr(value):
    return None if value is None else value / f.CRORE


def _positive(value):
    return value if value is not None and value > 0 else None


def _get(period: dict | None, name: str):
    return period.get(name) if period else None


# --- Shared intermediates ------------------------------------------------------------

def _eps_ttm(c: Company):
    return _get(c.trailing, "eps")


def _ev(c: Company):
    """Enterprise value in rupees: market cap plus borrowings minus cash."""
    return f.sub(f.add(c.market_cap, c.bs.get("total_debt")), c.bs.get("cash"))


def _bvps(c: Company):
    shares = c.shares.count if c.shares else None
    return f.ratio(c.bs.get("equity"), shares)


def _dma(c: Company, n: int):
    return f.sma(c.closes, n) if c.price is not None else None


def _high_52w(c: Company):
    rows = c.window(years=1)
    return max((r["high"] if r["high"] is not None else r["close"]) for r in rows) if rows else None


def _low_52w(c: Company):
    rows = c.window(years=1)
    return min((r["low"] if r["low"] is not None else r["close"]) for r in rows) if rows else None


def _return(c: Company, *, months=0, years=0):
    start = c.close_ago(months=months, years=years)
    if years > 1:
        return f.cagr(start, c.price, years)
    return f.change_pct(start, c.price)


def _fcf_years(c: Company) -> list[tuple[str, float]]:
    return [(end, p["free_cash_flow"]) for end, p in sorted(c.cashflow.items()) if "free_cash_flow" in p]


def _fcf_3y(c: Company):
    """The last three fiscal years' free cash flow, summed, when they are consecutive."""
    years = _fcf_years(c)[-3:]
    if len(years) < 3:
        return None
    ends = [f.years_before(date.fromisoformat(years[-1][0]), n) for n in (2, 1, 0)]
    if any(abs((date.fromisoformat(e) - t).days) > 45 for (e, _), t in zip(years, ends, strict=True)):
        return None
    return sum(v for _, v in years)


def _cfo_to_profit(c: Company):
    if not c.cashflow:
        return None
    end = max(c.cashflow)
    return f.ratio(c.cashflow[end].get("operating"), _positive(c.annual.get(end, {}).get("net_profit")))


def _holding_change(c: Company, field: str, months: int):
    before = c.holding_before(months)
    return f.sub(_get(c.holding, field), _get(before, field))


def _pledged(c: Company):
    h = c.holding
    if not h:
        return None
    return h["pledged_pct"] if h["pledged_pct"] is not None else h["encumbered_pct"]


def _quarter_growth(c: Company, field: str, months: int):
    return f.change_pct(_get(c.quarter_before(months), field), _get(c.q, field))


def piotroski(c: Company) -> int | None:
    """Piotroski's nine pass-or-fail tests on the newest fiscal year against the one
    before, one point each. None unless all nine can be scored."""
    ends = [e for e in sorted(c.balance) if e in c.annual]
    if len(ends) < 2:
        return None
    t, prev = ends[-1], ends[-2]
    if abs((date.fromisoformat(prev) - f.years_before(date.fromisoformat(t), 1)).days) > 45:
        return None
    p1, p0, b1, b0 = c.annual[t], c.annual[prev], c.balance[t], c.balance[prev]
    cfo = c.cashflow.get(t, {}).get("operating")
    roa1, roa0 = f.roa(p1, b1), f.roa(p0, b0)
    lev1, lev0 = f.ratio(b1.get("total_debt"), b1.get("total_assets")), f.ratio(b0.get("total_debt"), b0.get("total_assets"))
    cr1, cr0 = f.current_ratio(b1), f.current_ratio(b0)
    shares1, shares0 = b1.get("shares"), b0.get("shares")
    margin = f.gross_margin if p1.get("cogs") is not None and p0.get("cogs") is not None else f.opm
    m1, m0 = margin(p1), margin(p0)
    turn1, turn0 = f.ratio(p1.get("sales"), b1.get("total_assets")), f.ratio(p0.get("sales"), b0.get("total_assets"))
    inputs = (roa1, roa0, cfo, p1.get("net_income"), lev1, lev0, cr1, cr0, shares1, shares0, m1, m0, turn1, turn0)
    if any(v is None for v in inputs):
        return None
    shares0 *= c.factor_between(prev, date.fromisoformat(t))  # splits and bonuses are not new shares
    tests = (
        roa1 > 0,                       # profitable
        cfo > 0,                        # cash from operations
        roa1 > roa0,                    # return on assets improved
        cfo > p1["net_income"],         # earnings backed by cash
        lev1 < lev0 or lev1 == lev0 == 0,  # less (or still no) debt
        cr1 > cr0,                      # liquidity improved
        shares1 <= shares0 * 1.001,     # no new shares issued
        m1 > m0,                        # margin improved
        turn1 > turn0,                  # assets used better
    )
    return sum(tests)


# --- Company ------------------------------------------------------------------------

_m("name", "Name", "Company", "", "The company's name as NSE lists it.",
   lambda c: c.security.get("name"), "Company name", "Company", kind=TEXT)
_m("nse_symbol", "NSE symbol", "Company", "", "The symbol the shares trade under on NSE.",
   lambda c: c.security.get("nse_symbol"), "Symbol", "NSE code", "Ticker", kind=TEXT)
_m("industry", "Industry", "Company", "",
   """NSE's classification from its index lists, such as 'Financial Services' or 'Capital
   Goods'. Only index members (about 750 stocks) carry one. NSE gives a single level, so
   Sector is accepted as another name for it.""",
   lambda c: c.security.get("industry"), "Sector", kind=TEXT)

# --- Valuation ----------------------------------------------------------------------

_m("market_cap", "Market Capitalization", "Valuation", RS_CR,
   """The last close times the shares outstanding (see the README for where the share count
   comes from).""",
   lambda c: _cr(c.market_cap), "Market cap", "Mcap", "M cap")
_m("current_price", "Current price", "Valuation", RS,
   """The last close in the database. Blank when the stock has not traded in the 15 days
   before the snapshot date.""",
   lambda c: c.price, "Price", "CMP", "Last price", "Close price")
_m("pe", "Price to earnings", "Valuation", TIMES,
   "The current price over TTM diluted earnings per share. Blank when TTM EPS is zero or negative.",
   lambda c: f.ratio(c.price, _positive(_eps_ttm(c))), "P/E", "PE", "PE ratio", "Stock P/E",
   "Price to earning")
_m("pb", "Price to book value", "Valuation", TIMES,
   "Market capitalisation over shareholders' equity. Blank when equity is zero or negative.",
   lambda c: f.ratio(c.market_cap, _positive(c.bs.get("equity"))), "P/B", "PB", "Price to book", "PB ratio")
_m("ev", "Enterprise value", "Valuation", RS_CR,
   "Market capitalisation plus borrowings minus cash and cash equivalents.",
   lambda c: _cr(_ev(c)), "EV", applies=NON_FINANCIAL)
_m("ev_ebitda", "EV to EBITDA", "Valuation", TIMES,
   """Enterprise value over TTM operating profit (operating income plus depreciation). Blank when
   operating profit is zero or negative.""",
   lambda c: f.ratio(_ev(c), _positive(f.operating_profit(c.trailing or {}))), "EV/EBITDA", "EV / EBITDA",
   applies=NON_FINANCIAL)
_m("peg", "PEG ratio", "Valuation", TIMES,
   """P/E over the 3-year EPS growth rate (in %). Blank unless both are positive.""",
   lambda c: f.ratio(METRICS["pe"].value(c), _positive(METRICS["eps_growth_3y"].value(c))), "PEG")
_m("dividend_yield", "Dividend yield", "Valuation", PCT,
   """Dividends per share with an ex-date in the past year, over the current price. 0 for a stock
   that paid none; blank when the corporate-actions sync does not cover the year.""",
   lambda c: f.pct(c.dividends_ttm, c.price), "Div yield", "Dividend yield %")
_m("payout_ratio", "Dividend payout ratio", "Valuation", PCT,
   "Dividends per share of the past year as a % of TTM EPS. Blank when EPS is zero or negative.",
   lambda c: f.pct(c.dividends_ttm, _positive(_eps_ttm(c))), "Payout ratio", "Dividend payout")
_m("earnings_yield", "Earnings yield", "Valuation", PCT,
   "TTM EBIT (profit before interest and tax) as a % of enterprise value.",
   lambda c: f.pct(f.ebit(c.trailing or {}), _positive(_ev(c))), applies=NON_FINANCIAL)
_m("graham_number", "Graham number", "Valuation", RS,
   """The square root of 22.5 times TTM EPS times book value per share: Benjamin Graham's ceiling
   on a defensive buyer's price. Blank unless both are positive.""",
   lambda c: (math.sqrt(22.5 * e * b) if (e := _positive(_eps_ttm(c))) and (b := _positive(_bvps(c)))
              else None), "Graham value")
_m("price_to_sales", "Price to sales", "Valuation", TIMES,
   "Market capitalisation over TTM sales.",
   lambda c: f.ratio(c.market_cap, _positive(_get(c.trailing, "sales"))), "P/S", "PS ratio",
   "Price to sales ratio")

# --- Profitability ------------------------------------------------------------------

_m("roce", "Return on capital employed", "Profitability", PCT,
   """EBIT of the newest fiscal year as a % of capital employed (total assets minus current
   liabilities) at that year end.""",
   lambda c: f.roce(c.bs_income, c.bs), "ROCE", "ROCE %", "Return on capital", applies=NON_FINANCIAL)
_m("roe", "Return on equity", "Profitability", PCT,
   "Profit attributable to shareholders in the newest fiscal year as a % of equity at that year end.",
   lambda c: f.roe(c.bs_income, c.bs), "ROE", "ROE %")
_m("roa", "Return on assets", "Profitability", PCT,
   "Profit attributable to shareholders in the newest fiscal year as a % of total assets at its end.",
   lambda c: f.roa(c.bs_income, c.bs), "ROA", "ROA %")
_m("opm", "Operating profit margin", "Profitability", PCT,
   "TTM operating profit (before depreciation, interest, other income and tax) as a % of TTM sales.",
   lambda c: f.opm(c.trailing or {}), "OPM", "OPM %", applies=NON_FINANCIAL)
_m("npm", "Net profit margin", "Profitability", PCT,
   "TTM net profit as a % of TTM sales (a bank's net revenue).",
   lambda c: f.npm(c.trailing or {}), "NPM", "NPM %", "Net margin")
for _n in (3, 5):
    _m(f"roce_{_n}y", f"Average ROCE {_n} years", "Profitability", PCT,
       f"""The mean of the last {_n} fiscal years' ROCE, counting years with a balance sheet and
       results. Blank with fewer than {_n}.""",
       lambda c, n=_n: f.average_of_last(c.roce_series, n), f"ROCE {_n}Y", f"ROCE {_n} years",
       f"Average ROCE {_n}Y", f"Average return on capital employed {_n} years", applies=NON_FINANCIAL)
    _m(f"roe_{_n}y", f"Average ROE {_n} years", "Profitability", PCT,
       f"""The mean of the last {_n} fiscal years' ROE (as in the Company page's Return on Equity
       box). Blank with fewer than {_n}.""",
       lambda c, n=_n: f.average_of_last(c.roe_series, n), f"ROE {_n}Y", f"ROE {_n} years",
       f"Average ROE {_n}Y", f"Average return on equity {_n} years")

# --- Size ---------------------------------------------------------------------------

_m("sales", "Sales", "Size", RS_CR, "TTM revenue from operations (a bank's net revenue).",
   lambda c: _cr(_get(c.trailing, "sales")), "Sales TTM", "Revenue", "Revenue TTM", "Turnover")
_m("sales_ly", "Sales last year", "Size", RS_CR, "Revenue from operations in the newest fiscal year.",
   lambda c: _cr(c.fy.get("sales")), "Annual sales", "Revenue last year", "Sales latest year")
_m("operating_profit", "Operating profit", "Size", RS_CR,
   "TTM operating income plus depreciation: profit before depreciation, interest, other income and tax.",
   lambda c: _cr(f.operating_profit(c.trailing or {})), "Operating profit TTM", "EBITDA", applies=NON_FINANCIAL)
_m("operating_profit_ly", "Operating profit last year", "Size", RS_CR,
   "Operating profit in the newest fiscal year.",
   lambda c: _cr(f.operating_profit(c.fy)), "EBITDA last year", applies=NON_FINANCIAL)
_m("net_profit", "Net profit", "Size", RS_CR, "TTM profit after tax, minority interest included.",
   lambda c: _cr(_get(c.trailing, "net_profit")), "Net profit TTM", "Profit after tax", "PAT", "Profit")
_m("net_profit_ly", "Net profit last year", "Size", RS_CR, "Profit after tax in the newest fiscal year.",
   lambda c: _cr(c.fy.get("net_profit")), "PAT last year", "Profit last year")
_m("eps", "EPS", "Size", RS,
   "TTM diluted earnings per share, restated for splits and bonuses since it was filed.",
   _eps_ttm, "EPS TTM", "Earnings per share")
_m("eps_ly", "EPS last year", "Size", RS, "Diluted EPS of the newest fiscal year, restated for splits and bonuses.",
   lambda c: c.fy.get("eps"), "EPS latest year", "Annual EPS")

# --- Growth -------------------------------------------------------------------------


def _years_name(n: int) -> str:
    return f"{n} year" if n == 1 else f"{n} years"


for _n in (1, 3, 5, 10):
    for _key, _label, _field, _what, _extra in (
            ("sales", "Sales", "sales", "sales", ("Revenue growth",)),
            ("profit", "Profit", "net_profit", "net profit", ("Net profit growth",)),
            ("eps", "EPS", "eps", "EPS", ())):
        _names = [f"{_label} growth {_n}Y", f"{_label} growth {_n}Years", f"{_label} growth {_n} yrs"]
        _names += [f"{e} {_years_name(_n)}" for e in _extra] + [f"{e} {_n}Y" for e in _extra]
        if _n == 1:
            _names.append(f"{_label} growth")
        _m(f"{_key}_growth_{_n}y", f"{_label} growth {_years_name(_n)}", "Growth", PCT,
           f"""Compound annual growth of fiscal-year {_what} over the last {_years_name(_n)}: from the
           year ending within 45 days of {_years_name(_n)} before the newest, to the newest. Blank
           unless both ends are positive.""",
           lambda c, n=_n, fld=_field: f.growth(c.annual_series(lambda p, fld=fld: p.get(fld)), n), *_names)

# --- Quarterly results ------------------------------------------------------------------

_m("sales_q", "Sales latest quarter", "Quarterly results", RS_CR, "Revenue from operations in the newest quarter.",
   lambda c: _cr(c.q.get("sales")), "Quarterly sales", "Sales last quarter")
_m("net_profit_q", "Net profit latest quarter", "Quarterly results", RS_CR, "Profit after tax in the newest quarter.",
   lambda c: _cr(c.q.get("net_profit")), "Quarterly profit", "Profit latest quarter", "Net profit last quarter")
_m("opm_q", "OPM latest quarter", "Quarterly results", PCT, "Operating profit margin in the newest quarter.",
   lambda c: f.opm(c.q), "Quarterly OPM", "OPM last quarter", applies=NON_FINANCIAL)
_m("eps_q", "EPS latest quarter", "Quarterly results", RS, "Diluted EPS of the newest quarter, restated for splits and bonuses.",
   lambda c: c.q.get("eps"), "Quarterly EPS", "EPS last quarter")
_m("sales_growth_yoy_q", "YoY quarterly sales growth", "Quarterly results", PCT,
   "Newest quarter's sales against the same quarter a year earlier, in %.",
   lambda c: _quarter_growth(c, "sales", 12), "Quarterly sales growth YoY", "Sales growth YoY")
_m("profit_growth_yoy_q", "YoY quarterly profit growth", "Quarterly results", PCT,
   "Newest quarter's net profit against the same quarter a year earlier, in %. Blank after a loss.",
   lambda c: _quarter_growth(c, "net_profit", 12), "Quarterly profit growth YoY", "Profit growth YoY")
_m("sales_growth_qoq", "QoQ sales growth", "Quarterly results", PCT,
   "Newest quarter's sales against the quarter before, in %.",
   lambda c: _quarter_growth(c, "sales", 3), "Quarterly sales growth QoQ", "Sales growth QoQ")
_m("profit_growth_qoq", "QoQ profit growth", "Quarterly results", PCT,
   "Newest quarter's net profit against the quarter before, in %. Blank after a loss.",
   lambda c: _quarter_growth(c, "net_profit", 3), "Quarterly profit growth QoQ", "Profit growth QoQ")

# --- Balance sheet -----------------------------------------------------------------------

_m("debt", "Debt", "Balance sheet", RS_CR, "Borrowings, non-current plus current, as filed (lease liabilities excluded).",
   lambda c: _cr(c.bs.get("total_debt")), "Borrowings", "Total debt")
_m("debt_to_equity", "Debt to equity", "Balance sheet", TIMES,
   "Borrowings other than lease liabilities over shareholders' equity.",
   lambda c: f.leverage(c.bs), "D/E", "Debt/Equity", "Debt equity ratio", applies=NON_FINANCIAL)
_m("interest_coverage", "Interest coverage ratio", "Balance sheet", TIMES,
   "Newest fiscal year's EBIT over its interest cost. Blank when there was no interest to cover.",
   lambda c: f.interest_coverage(c.fy), "Interest coverage", "ICR", applies=NON_FINANCIAL)
_m("current_ratio", "Current ratio", "Balance sheet", TIMES, "Current assets over current liabilities.",
   lambda c: f.current_ratio(c.bs), applies=NON_FINANCIAL)
_m("book_value", "Book value", "Balance sheet", RS, "Shareholders' equity per share outstanding.",
   _bvps, "Book value per share", "BVPS")
_m("net_worth", "Net worth", "Balance sheet", RS_CR, "Equity attributable to shareholders.",
   lambda c: _cr(c.bs.get("equity")), "Shareholders equity")
_m("reserves", "Reserves", "Balance sheet", RS_CR, "Shareholders' equity minus share capital.",
   lambda c: _cr(f.reserves(c.bs)))
_m("equity_capital", "Equity capital", "Balance sheet", RS_CR, "Paid-up equity share capital.",
   lambda c: _cr(c.bs.get("share_capital")), "Share capital")
_m("face_value", "Face value", "Balance sheet", RS, "Share capital per share at the newest year end.",
   lambda c: f.face_value(c.bs))
_m("cash", "Cash and equivalents", "Balance sheet", RS_CR, "Cash and cash equivalents at the newest year end.",
   lambda c: _cr(c.bs.get("cash")), "Cash", "Cash and cash equivalents")
_m("total_assets", "Total assets", "Balance sheet", RS_CR, "Total assets at the newest year end.",
   lambda c: _cr(c.bs.get("total_assets")))
_m("shares_outstanding", "Shares outstanding", "Balance sheet", CR_SHARES,
   "Shares in issue on the snapshot date, in crores of shares.",
   lambda c: c.shares.count / f.CRORE if c.shares else None, "Number of shares", "Share count")
_m("working_capital_days", "Working capital days", "Balance sheet", DAYS,
   "Current assets minus current liabilities, as days of the year's sales.",
   lambda c: f.working_capital_days(c.bs_income, c.bs), "WC days", applies=NON_FINANCIAL)
_m("cash_conversion_cycle", "Cash conversion cycle", "Balance sheet", DAYS,
   "Debtor days plus inventory days minus days payable.",
   lambda c: f.cash_conversion_cycle(c.bs_income, c.bs), "CCC", applies=NON_FINANCIAL)
_m("debtor_days", "Debtor days", "Balance sheet", DAYS, "Trade receivables as days of the year's sales.",
   lambda c: f.debtor_days(c.bs_income, c.bs), "Receivable days", applies=NON_FINANCIAL)
_m("inventory_days", "Inventory days", "Balance sheet", DAYS, "Inventory as days of the year's cost of goods sold.",
   lambda c: f.inventory_days(c.bs_income, c.bs), applies=NON_FINANCIAL)
_m("days_payable", "Days payable", "Balance sheet", DAYS, "Trade payables as days of the year's cost of goods sold.",
   lambda c: f.days_payable(c.bs_income, c.bs), "Payable days", applies=NON_FINANCIAL)

# --- Cash flow ---------------------------------------------------------------------------

_m("cfo", "Cash from operations last year", "Cash flow", RS_CR, "Net cash from operating activities in the newest fiscal year.",
   lambda c: _cr(c.cf.get("operating")), "CFO", "Operating cash flow", "Cash from operations",
   applies=NON_FINANCIAL)
_m("fcf", "Free cash flow last year", "Cash flow", RS_CR,
   "Cash from operations minus purchases of fixed and intangible assets, newest fiscal year.",
   lambda c: _cr(c.cf.get("free_cash_flow")), "FCF", "Free cash flow", applies=NON_FINANCIAL)
_m("fcf_3y", "Free cash flow 3 years", "Cash flow", RS_CR,
   "Free cash flow of the last three consecutive fiscal years, summed.",
   lambda c: _cr(_fcf_3y(c)), "FCF 3Y", "FCF 3 years", "Cumulative free cash flow 3 years",
   applies=NON_FINANCIAL)
_m("cfo_to_profit", "CFO to net profit", "Cash flow", TIMES,
   "Cash from operations over net profit in the newest fiscal year. Blank after a loss.",
   _cfo_to_profit, "CFO to PAT", "CFO/PAT", applies=NON_FINANCIAL)

# --- Shareholding ------------------------------------------------------------------------

_m("promoter_holding", "Promoter holding", "Shareholding", PCT, "Promoter and promoter group's % of shares, latest pattern.",
   lambda c: _get(c.holding, "promoter_pct"), "Promoters", "Promoter %", "Promoter stake")
_m("promoter_change_1q", "Change in promoter holding", "Shareholding", PTS,
   "Promoter holding now minus a quarter earlier, in percentage points.",
   lambda c: _holding_change(c, "promoter_pct", 3), "Change in promoter holding 1Q",
   "Change in promoter holding 1 quarter", "Promoter holding change")
_m("promoter_change_1y", "Change in promoter holding 1 year", "Shareholding", PTS,
   "Promoter holding now minus four quarters earlier, in percentage points.",
   lambda c: _holding_change(c, "promoter_pct", 12), "Change in promoter holding 1Y",
   "Promoter holding change 1 year")
_m("pledged", "Pledged percentage", "Shareholding", PCT,
   """Promoter shares pledged, as a % of promoter shares. Before the 2025 filing format this
   counts shares pledged or otherwise encumbered.""",
   _pledged, "Pledged", "Pledge", "Pledged %", "Promoter pledge")
for _who, _label in (("fii", "FII"), ("dii", "DII")):
    _long = "Foreign" if _who == "fii" else "Domestic"
    _m(f"{_who}_holding", f"{_label} holding", "Shareholding", PCT,
       f"{_long} institutional investors' % of shares, latest pattern.",
       lambda c, w=_who: _get(c.holding, f"{w}_pct"), _label, f"{_label}s", f"{_long} institutional holding",
       *(("FPI holding",) if _who == "fii" else ()))
    _m(f"{_who}_change_1q", f"Change in {_label} holding", "Shareholding", PTS,
       f"{_label} holding now minus a quarter earlier, in percentage points.",
       lambda c, w=_who: _holding_change(c, f"{w}_pct", 3), f"Change in {_label} holding 1Q")
    _m(f"{_who}_change_1y", f"Change in {_label} holding 1 year", "Shareholding", PTS,
       f"{_label} holding now minus four quarters earlier, in percentage points.",
       lambda c, w=_who: _holding_change(c, f"{w}_pct", 12), f"Change in {_label} holding 1Y")
_m("num_shareholders", "Number of shareholders", "Shareholding", COUNT,
   "Shareholders on the latest pattern.",
   lambda c: _get(c.holding, "num_shareholders"), "Shareholders", "No. of shareholders", decimals=0)
_m("shareholders_change_1q", "Change in number of shareholders", "Shareholding", PCT,
   "Shareholders on the latest pattern against a quarter earlier, in %.",
   lambda c: f.change_pct(_get(c.holding_before(3), "num_shareholders"), _get(c.holding, "num_shareholders")),
   "Change in shareholders", "Change in number of shareholders 1Q")
_m("shareholders_change_1y", "Change in number of shareholders 1 year", "Shareholding", PCT,
   "Shareholders on the latest pattern against four quarters earlier, in %.",
   lambda c: f.change_pct(_get(c.holding_before(12), "num_shareholders"), _get(c.holding, "num_shareholders")),
   "Change in number of shareholders 1Y", "Change in shareholders 1 year")

# --- Price and technicals ----------------------------------------------------------------

for _key, _name, _kw, _short in (
        ("return_1m", "Return over 1 month", {"months": 1}, "1M"),
        ("return_3m", "Return over 3 months", {"months": 3}, "3M"),
        ("return_6m", "Return over 6 months", {"months": 6}, "6M"),
        ("return_1y", "Return over 1 year", {"years": 1}, "1Y"),
        ("return_3y", "Return over 3 years", {"years": 3}, "3Y"),
        ("return_5y", "Return over 5 years", {"years": 5}, "5Y")):
    _span = _name.removeprefix("Return over ")
    _years = _kw.get("years", 0)
    _desc = (f"Annualised price return (CAGR) over the last {_span}" if _years > 1
             else f"Price change over the last {_span}")
    _m(_key, _name, "Price and technicals", PCT,
       f"""{_desc}, from the last close on or before the same day {_span} earlier, on prices adjusted
       for splits, bonuses and rights (not dividends).""",
       lambda c, kw=_kw: _return(c, **kw), f"Return {_short}", f"{_span} return",
       f"Return over {_span.replace(' ', '')}")
_m("high_52w", "52 week high", "Price and technicals", RS, "The highest adjusted price of the past year.",
   _high_52w, "52W high", "52wk high", "High 52 weeks")
_m("low_52w", "52 week low", "Price and technicals", RS, "The lowest adjusted price of the past year.",
   _low_52w, "52W low", "52wk low", "Low 52 weeks")
_m("from_52w_high", "Down from 52 week high", "Price and technicals", PCT,
   "How far the current price is below the 52-week high, in % of the high.",
   lambda c: f.pct(f.sub(_high_52w(c), c.price), _high_52w(c)), "Down from 52W high",
   "Distance from 52 week high")
_m("from_52w_low", "Up from 52 week low", "Price and technicals", PCT,
   "How far the current price is above the 52-week low, in % of the low.",
   lambda c: f.pct(f.sub(c.price, _low_52w(c)), _low_52w(c)), "Up from 52W low", "Distance from 52 week low")
for _n in (50, 200):
    _m(f"dma_{_n}", f"{_n} DMA", "Price and technicals", RS,
       f"The mean of the last {_n} adjusted closes.",
       lambda c, n=_n: _dma(c, n), f"DMA {_n}", f"{_n}DMA", f"{_n} day moving average")
    _m(f"price_vs_dma{_n}", f"Price vs {_n} DMA", "Price and technicals", PCT,
       f"How far the current price is above (or, negative, below) its {_n} DMA, in %.",
       lambda c, n=_n: f.change_pct(_dma(c, n), c.price), f"Price to {_n} DMA", f"Distance from {_n} DMA")
_m("rsi", "RSI", "Price and technicals", "",
   "Wilder's 14-day relative strength index of adjusted closes, 0 to 100.",
   lambda c: f.rsi(c.closes[-250:]) if c.price is not None else None, "RSI 14", "RSI(14)",
   "Relative strength index")
_m("volume_1m", "Average volume 1 month", "Price and technicals", SHARES,
   "The mean daily traded volume of the past month, in shares (adjusted for splits and bonuses).",
   lambda c: (sum(v) / len(v) if len(v := [r["volume"] for r in c.window(months=1) if r["volume"] is not None]) >= 10
              else None), "Volume 1M", "Average volume 1M", "1M average volume", decimals=0)

# --- Composite ---------------------------------------------------------------------------

_m("piotroski", "Piotroski score", "Composite", SCORE,
   """Nine pass-or-fail tests on the newest fiscal year against the one before: positive return on
   assets, positive operating cash flow, a better return on assets, cash flow above profit, less
   leverage, a better current ratio, no new shares, a better gross margin (operating margin when
   cost of goods is not filed) and a better asset turnover. One point each, 0 to 9; blank unless
   all nine can be scored.""",
   piotroski, "Piotroski", "F-score", "F score", "Piotroski F-score", applies=NON_FINANCIAL, decimals=0)

del _n, _key, _label, _field, _what, _extra, _names, _who, _long, _name, _kw, _short, _span, _years, _desc


# --- Names ---------------------------------------------------------------------------------

def normalize(name: str) -> str:
    """How names are compared: case-insensitive, runs of spaces as one."""
    return " ".join(name.split()).casefold()


def _build_names() -> dict[str, str]:
    names: dict[str, str] = {}
    for m in METRICS.values():
        for name in (m.name, *m.aliases):
            key = normalize(name)
            if key in names and names[key] != m.key:
                raise ValueError(f"{name!r} names both {names[key]} and {m.key}")
            names[key] = m.key
    return names


NAMES = _build_names()  # normalised name or alias -> metric key
NUMERIC = frozenset(k for k, m in METRICS.items() if m.kind == NUMBER)
TEXTUAL = frozenset(k for k, m in METRICS.items() if m.kind == TEXT)
_KEY = re.compile(r"^[a-z][a-z0-9_]*$")
assert all(_KEY.match(k) for k in METRICS)


def lookup(name: str) -> Metric | None:
    key = NAMES.get(normalize(name))
    return METRICS.get(key) if key else None


def catalog() -> list[dict]:
    """Every metric, by category, for the API and the docs."""
    order = {c: i for i, c in enumerate(CATEGORIES)}
    return [m.describe() for m in sorted(METRICS.values(), key=lambda m: order[m.category])]
