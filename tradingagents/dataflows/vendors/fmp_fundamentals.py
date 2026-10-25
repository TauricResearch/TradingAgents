"""Financial Modeling Prep: company statements and a fundamentals overview. Needs ``FMP_API_KEY``.

Every statement period carries FMP's filing date, so a run dated ``as_of_date``
sees only the periods filed on or before it. The values are FMP's current ones:
a period restated after ``as_of_date`` shows the restated figure, unlike SEC
EDGAR's facts at the values filed then. For US filers put ``sec_edgar`` first
(``sec_edgar,fmp,yfinance``) and let FMP serve the rest, or fill in when EDGAR
has nothing.

Basic FMP plans return at most five periods per request, so the vendor asks for
five and a past run sees whichever of those were already filed.

The overview (profile plus trailing-twelve-month metrics) is live-only with no
historical vintage, so a past run withholds it through the shared guard
(``date_window.withhold_live_profile``), as every fundamentals vendor does.
"""

from datetime import date

from tradingagents.dataflows.date_window import withhold_live_profile
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.fmp import fetch

PERIODS = 5

# (row label, FMP field, kind); kind "money" is shown in millions of the
# reporting currency, "per_share" as is, "shares" in millions.
_STATEMENTS = {
    "income_statement": ("income-statement", "Income Statement", [
        ("Revenue", "revenue", "money"),
        ("Cost of revenue", "costOfRevenue", "money"),
        ("Gross profit", "grossProfit", "money"),
        ("Research and development", "researchAndDevelopmentExpenses", "money"),
        ("Selling, general and administrative", "sellingGeneralAndAdministrativeExpenses", "money"),
        ("Operating expenses", "operatingExpenses", "money"),
        ("Operating income", "operatingIncome", "money"),
        ("Interest income", "interestIncome", "money"),
        ("Interest expense", "interestExpense", "money"),
        ("Income before tax", "incomeBeforeTax", "money"),
        ("Income tax expense", "incomeTaxExpense", "money"),
        ("Net income", "netIncome", "money"),
        ("EBITDA", "ebitda", "money"),
        ("EPS", "eps", "per_share"),
        ("EPS diluted", "epsDiluted", "per_share"),
        ("Diluted shares", "weightedAverageShsOutDil", "shares"),
    ]),
    "balance_sheet": ("balance-sheet-statement", "Balance Sheet", [
        ("Cash and equivalents", "cashAndCashEquivalents", "money"),
        ("Short-term investments", "shortTermInvestments", "money"),
        ("Receivables", "netReceivables", "money"),
        ("Inventory", "inventory", "money"),
        ("Total current assets", "totalCurrentAssets", "money"),
        ("Property, plant and equipment", "propertyPlantEquipmentNet", "money"),
        ("Goodwill and intangibles", "goodwillAndIntangibleAssets", "money"),
        ("Long-term investments", "longTermInvestments", "money"),
        ("Total assets", "totalAssets", "money"),
        ("Accounts payable", "accountPayables", "money"),
        ("Short-term debt", "shortTermDebt", "money"),
        ("Total current liabilities", "totalCurrentLiabilities", "money"),
        ("Long-term debt", "longTermDebt", "money"),
        ("Total liabilities", "totalLiabilities", "money"),
        ("Total stockholders' equity", "totalStockholdersEquity", "money"),
        ("Total debt", "totalDebt", "money"),
        ("Net debt", "netDebt", "money"),
    ]),
    "cashflow": ("cash-flow-statement", "Cash Flow Statement", [
        ("Net income", "netIncome", "money"),
        ("Depreciation and amortization", "depreciationAndAmortization", "money"),
        ("Stock-based compensation", "stockBasedCompensation", "money"),
        ("Change in working capital", "changeInWorkingCapital", "money"),
        ("Operating cash flow", "operatingCashFlow", "money"),
        ("Capital expenditure", "capitalExpenditure", "money"),
        ("Free cash flow", "freeCashFlow", "money"),
        ("Acquisitions", "acquisitionsNet", "money"),
        ("Investing cash flow", "netCashProvidedByInvestingActivities", "money"),
        ("Net debt issuance", "netDebtIssuance", "money"),
        ("Share repurchases", "commonStockRepurchased", "money"),
        ("Dividends paid", "commonDividendsPaid", "money"),
        ("Financing cash flow", "netCashProvidedByFinancingActivities", "money"),
        ("Net change in cash", "netChangeInCash", "money"),
    ]),
}


def _filed(row: dict) -> str:
    """The day FMP says the period was filed; undated rows count as not yet filed."""
    return row.get("filingDate") or (row.get("acceptedDate") or "")[:10] or "9999-12-31"


def _cell(value, kind: str) -> str:
    if value is None or value == "":
        return ""
    if kind == "per_share":
        return f"{value:.2f}"
    # Plain numbers: a thousands separator would split the CSV field.
    return f"{value / 1e6:.0f}"


def _statement(kind: str, ticker: str, freq: str, as_of_date: str | None) -> str:
    canonical = normalize_symbol(ticker)
    as_of = as_of_date or date.today().isoformat()
    endpoint, title, lines = _STATEMENTS[kind]
    quarterly = freq.lower() == "quarterly"
    rows = fetch(endpoint, {"symbol": canonical, "period": "quarter" if quarterly else "annual", "limit": PERIODS},
                 ticker, canonical)
    rows = sorted((r for r in rows if _filed(r) <= as_of), key=lambda r: r.get("date", ""))
    if not rows:
        raise NoMarketDataError(ticker, canonical,
                                f"no {freq} {title.lower()} filed by {as_of} among FMP's latest {PERIODS} periods")
    currency = rows[-1].get("reportedCurrency") or "USD"
    header = (
        f"# {title} for {canonical} ({freq}), {currency} in millions unless the row says otherwise\n"
        f"# Financial Modeling Prep: periods filed on or before {as_of}, at FMP's current values "
        f"(a later restatement shows the restated figure)\n\n"
    )
    columns = [f"{r['date']} {r.get('period', '')} FY{r.get('fiscalYear', '')} filed {_filed(r)}".replace(",", " ")
               for r in rows]
    out = [",".join([""] + columns)]
    for label, field, kind_ in lines:
        name = {"per_share": f"{label} ({currency} per share)", "shares": f"{label} (millions)"}.get(kind_, label)
        out.append(",".join([name] + [_cell(r.get(field), kind_) for r in rows]))
    return header + "\n".join(out) + "\n"


def get_balance_sheet(ticker: str, freq: str = "quarterly", as_of_date: str | None = None) -> str:
    """Balance sheet periods filed on or before ``as_of_date``."""
    return _statement("balance_sheet", ticker, freq, as_of_date)


def get_income_statement(ticker: str, freq: str = "quarterly", as_of_date: str | None = None) -> str:
    """Income statement periods filed on or before ``as_of_date``."""
    return _statement("income_statement", ticker, freq, as_of_date)


def get_cashflow(ticker: str, freq: str = "quarterly", as_of_date: str | None = None) -> str:
    """Cash flow periods filed on or before ``as_of_date``."""
    return _statement("cashflow", ticker, freq, as_of_date)


def _pct(v):
    return None if v is None else f"{v * 100:.1f}%"


def _x(v):
    return None if v is None else f"{v:.2f}"


def get_fundamentals(ticker: str, as_of_date: str | None = None) -> str:
    """Profile and trailing-twelve-month metrics, for a run dated today."""
    canonical = normalize_symbol(ticker)
    withheld = withhold_live_profile(as_of_date, canonical)
    if withheld:
        return withheld
    profile = fetch("profile", {"symbol": canonical}, ticker, canonical)
    if not profile:
        raise NoMarketDataError(ticker, canonical, "FMP has no profile for this symbol")
    p = profile[0]
    extra = {}
    for endpoint in ("key-metrics-ttm", "ratios-ttm"):
        try:
            rows = fetch(endpoint, {"symbol": canonical}, ticker, canonical)
        except NoMarketDataError:
            rows = []  # the profile alone is still worth serving
        if rows:
            extra.update(rows[0])
    cur = p.get("currency") or ""

    def money(v):
        return None if v is None else f"{v / 1e6:.0f}M {cur}".strip()

    fields = [
        ("Name", p.get("companyName")),
        ("Sector", p.get("sector")),
        ("Industry", p.get("industry")),
        ("Country", p.get("country")),
        ("Price", None if p.get("price") is None else f"{p['price']} {cur}".strip()),
        ("Market Cap", money(p.get("marketCap"))),
        ("Beta", p.get("beta")),
        ("PE Ratio (TTM)", _x(extra.get("priceToEarningsRatioTTM"))),
        ("Price to Sales (TTM)", _x(extra.get("priceToSalesRatioTTM"))),
        ("Price to Book (TTM)", _x(extra.get("priceToBookRatioTTM"))),
        ("EV to EBITDA (TTM)", _x(extra.get("evToEBITDATTM"))),
        ("Gross Margin (TTM)", _pct(extra.get("grossProfitMarginTTM"))),
        ("Operating Margin (TTM)", _pct(extra.get("operatingProfitMarginTTM"))),
        ("Net Margin (TTM)", _pct(extra.get("netProfitMarginTTM"))),
        ("Return on Equity (TTM)", _pct(extra.get("returnOnEquityTTM"))),
        ("Return on Invested Capital (TTM)", _pct(extra.get("returnOnInvestedCapitalTTM"))),
        ("Current Ratio (TTM)", _x(extra.get("currentRatioTTM"))),
        ("Debt to Equity (TTM)", None if extra.get("debtToEquityRatioTTM") is None
         else f"{extra['debtToEquityRatioTTM']:.2f}x"),
        ("Net Debt to EBITDA (TTM)", _x(extra.get("netDebtToEBITDATTM"))),
        ("Free Cash Flow Yield (TTM)", _pct(extra.get("freeCashFlowYieldTTM"))),
        ("Dividend Yield (TTM)", _pct(extra.get("dividendYieldTTM"))),
    ]
    lines = [f"{label}: {v}" for label, v in fields if v is not None]
    return (f"# Company Fundamentals for {canonical}\n"
            f"# Financial Modeling Prep, live values as of {date.today().isoformat()}\n\n" + "\n".join(lines))
