"""Finnhub fundamental data functions.

Provides company profiles, financial statements, and key financial metrics
using the Finnhub REST API.  Output formats mirror the Alpha Vantage
equivalents where possible for consistent agent-facing data.
"""

import json
from typing import Literal

from .finnhub_common import (
    FinnhubError,
    ThirdPartyParseError,
    _make_api_request,
    _now_str,
)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

StatementType = Literal["balance_sheet", "income_statement", "cash_flow"]
Frequency = Literal["annual", "quarterly"]

# Mapping from our canonical statement_type names to Finnhub's "statement" param
_STATEMENT_MAP: dict[str, str] = {
    "balance_sheet": "bs",
    "income_statement": "ic",
    "cash_flow": "cf",
}


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def get_company_profile(symbol: str) -> str:
    """Fetch company profile and overview via Finnhub /stock/profile2.

    Returns a formatted text block with key company metadata including name,
    industry, sector, market cap, and shares outstanding — mirroring the
    information returned by Alpha Vantage OVERVIEW.

    Args:
        symbol: Equity ticker symbol (e.g. "AAPL").

    Returns:
        Formatted multi-line string with company profile fields.

    Raises:
        FinnhubError: When the API returns an error or the symbol is invalid.
        ThirdPartyParseError: When the response cannot be parsed.
    """
    data = _make_api_request("stock/profile2", {"symbol": symbol})

    if not data:
        raise FinnhubError(
            f"Empty profile response for symbol={symbol}. "
            "Symbol may be invalid or not covered."
        )

    name = data.get("name", "N/A")
    ticker = data.get("ticker", symbol)
    exchange = data.get("exchange", "N/A")
    ipo_date = data.get("ipo", "N/A")
    industry = data.get("finnhubIndustry", "N/A")
    # Finnhub does not return a top-level sector — the industry string is the
    # finest granularity available in the free profile endpoint.
    market_cap = data.get("marketCapitalization", None)
    shares_outstanding = data.get("shareOutstanding", None)
    currency = data.get("currency", "USD")
    country = data.get("country", "N/A")
    website = data.get("weburl", "N/A")
    logo = data.get("logo", "N/A")
    phone = data.get("phone", "N/A")

    # Format market cap in billions for readability
    if market_cap is not None:
        try:
            market_cap_str = f"${float(market_cap):,.2f}M"
        except (ValueError, TypeError):
            market_cap_str = str(market_cap)
    else:
        market_cap_str = "N/A"

    if shares_outstanding is not None:
        try:
            shares_str = f"{float(shares_outstanding):,.2f}M"
        except (ValueError, TypeError):
            shares_str = str(shares_outstanding)
    else:
        shares_str = "N/A"

    lines: list[str] = [
        f"# Company Profile: {name} ({ticker}) — Finnhub",
        f"# Data retrieved on: {_now_str()}",
        "",
        f"Name:                 {name}",
        f"Symbol:               {ticker}",
        f"Exchange:             {exchange}",
        f"Country:              {country}",
        f"Currency:             {currency}",
        f"Industry:             {industry}",
        f"IPO Date:             {ipo_date}",
        f"Market Cap:           {market_cap_str}",
        f"Shares Outstanding:   {shares_str}",
        f"Website:              {website}",
        f"Phone:                {phone}",
        f"Logo:                 {logo}",
    ]

    return "\n".join(lines)


def get_financial_statements(
    symbol: str,
    statement_type: StatementType = "income_statement",
    freq: Frequency = "quarterly",
) -> str:
    """Fetch financial statement data via Finnhub /financials-reported.

    Returns a structured text representation of the most recent reported
    financial data.  Mirrors the pattern of the Alpha Vantage INCOME_STATEMENT,
    BALANCE_SHEET, and CASH_FLOW endpoints.

    Args:
        symbol: Equity ticker symbol (e.g. "AAPL").
        statement_type: One of ``'balance_sheet'``, ``'income_statement'``,
            or ``'cash_flow'``.
        freq: Reporting frequency — ``'annual'`` or ``'quarterly'``.

    Returns:
        Formatted multi-line string with the financial statement data.

    Raises:
        ValueError: When an unsupported ``statement_type`` is provided.
        FinnhubError: On API-level errors or missing data.
        ThirdPartyParseError: When the response cannot be parsed.
    """
    if statement_type not in _STATEMENT_MAP:
        raise ValueError(
            f"Invalid statement_type '{statement_type}'. "
            f"Must be one of: {list(_STATEMENT_MAP.keys())}"
        )

    finnhub_statement = _STATEMENT_MAP[statement_type]
    # Finnhub uses "annual" / "quarterly" directly
    params = {
        "symbol": symbol,
        "freq": freq,
    }

    data = _make_api_request("financials-reported", params)

    reports: list[dict] = data.get("data", [])
    if not reports:
        raise FinnhubError(
            f"No financial reports returned for symbol={symbol}, "
            f"statement_type={statement_type}, freq={freq}"
        )

    # Use the most recent report
    latest_report = reports[0]
    period = latest_report.get("period", "N/A")
    year = latest_report.get("year", "N/A")
    quarter = latest_report.get("quarter", "")
    filing_date = latest_report.get("filedDate", "N/A")
    accepted_date = latest_report.get("acceptedDate", "N/A")
    form = latest_report.get("form", "N/A")
    cik = latest_report.get("cik", "N/A")

    # The 'report' sub-dict holds the three statement types under keys "bs", "ic", "cf"
    report_data: dict = latest_report.get("report", {})
    statement_rows: list[dict] = report_data.get(finnhub_statement, [])

    period_label = f"Q{quarter} {year}" if quarter else str(year)
    header = (
        f"# {statement_type.replace('_', ' ').title()} — {symbol} "
        f"({period_label}, {freq.title()}) — Finnhub\n"
        f"# Data retrieved on: {_now_str()}\n"
        f"# Filing: {form} | Filed: {filing_date} | Accepted: {accepted_date}\n"
        f"# CIK: {cik} | Period: {period}\n\n"
    )

    if not statement_rows:
        return header + "_No line items found in this report._\n"

    lines: list[str] = [header]
    lines.append(f"{'Concept':<50} {'Unit':<10} {'Value':>20}")
    lines.append("-" * 82)

    for row in statement_rows:
        concept = row.get("concept", "N/A")
        label = row.get("label", concept)
        unit = row.get("unit", "USD")
        value = row.get("value", None)

        if value is None:
            value_str = "N/A"
        else:
            try:
                value_str = f"{float(value):>20,.0f}"
            except (ValueError, TypeError):
                value_str = str(value)

        # Truncate long labels to keep alignment readable
        display_label = label[:49] if len(label) > 49 else label
        lines.append(f"{display_label:<50} {unit:<10} {value_str}")

    return "\n".join(lines)


def get_basic_financials(symbol: str) -> str:
    """Fetch key financial ratios and metrics via Finnhub /stock/metric.

    Returns a formatted text block with P/E, P/B, ROE, debt/equity, 52-week
    range, and other standard financial metrics — mirroring the kind of data
    returned by Alpha Vantage OVERVIEW for ratio-focused consumers.

    Args:
        symbol: Equity ticker symbol (e.g. "AAPL").

    Returns:
        Formatted multi-line string with key financial metrics.

    Raises:
        FinnhubError: On API-level errors or missing data.
        ThirdPartyParseError: When the response cannot be parsed.
    """
    data = _make_api_request("stock/metric", {"symbol": symbol, "metric": "all"})

    metric: dict = data.get("metric", {})
    if not metric:
        raise FinnhubError(
            f"No metric data returned for symbol={symbol}. "
            "Symbol may be invalid or not covered on the free tier."
        )

    series: dict = data.get("series", {})

    def _fmt(key: str, prefix: str = "", suffix: str = "") -> str:
        """Format a metric value with optional prefix/suffix."""
        val = metric.get(key)
        if val is None:
            return "N/A"
        try:
            return f"{prefix}{float(val):,.4f}{suffix}"
        except (ValueError, TypeError):
            return str(val)

    def _fmt_int(key: str, prefix: str = "", suffix: str = "") -> str:
        """Format a metric value as an integer."""
        val = metric.get(key)
        if val is None:
            return "N/A"
        try:
            return f"{prefix}{int(float(val)):,}{suffix}"
        except (ValueError, TypeError):
            return str(val)

    lines: list[str] = [
        f"# Key Financial Metrics: {symbol} — Finnhub",
        f"# Data retrieved on: {_now_str()}",
        "",
        "## Valuation",
        f"  P/E (TTM):                    {_fmt('peTTM')}",
        f"  P/E (Annual):                 {_fmt('peAnnual')}",
        f"  P/B (Quarterly):              {_fmt('pbQuarterly')}",
        f"  P/B (Annual):                 {_fmt('pbAnnual')}",
        f"  P/S (TTM):                    {_fmt('psTTM')}",
        f"  P/CF (TTM):                   {_fmt('pcfShareTTM')}",
        f"  EV/EBITDA (TTM):              {_fmt('evEbitdaTTM')}",
        "",
        "## Price Range",
        f"  52-Week High:                 {_fmt('52WeekHigh', prefix='$')}",
        f"  52-Week Low:                  {_fmt('52WeekLow', prefix='$')}",
        f"  52-Week Return:               {_fmt('52WeekPriceReturnDaily', suffix='%')}",
        f"  Beta (5Y Monthly):            {_fmt('beta')}",
        "",
        "## Profitability",
        f"  ROE (TTM):                    {_fmt('roeTTM', suffix='%')}",
        f"  ROA (TTM):                    {_fmt('roaTTM', suffix='%')}",
        f"  ROIC (TTM):                   {_fmt('roicTTM', suffix='%')}",
        f"  Gross Margin (TTM):           {_fmt('grossMarginTTM', suffix='%')}",
        f"  Net Profit Margin (TTM):      {_fmt('netProfitMarginTTM', suffix='%')}",
        f"  Operating Margin (TTM):       {_fmt('operatingMarginTTM', suffix='%')}",
        "",
        "## Leverage",
        f"  Total Debt/Equity (Quarterly):{_fmt('totalDebt/totalEquityQuarterly')}",
        f"  Total Debt/Equity (Annual):   {_fmt('totalDebt/totalEquityAnnual')}",
        f"  Current Ratio (Quarterly):    {_fmt('currentRatioQuarterly')}",
        f"  Quick Ratio (Quarterly):      {_fmt('quickRatioQuarterly')}",
        "",
        "## Growth",
        f"  EPS Growth (TTM YoY):         {_fmt('epsGrowthTTMYoy', suffix='%')}",
        f"  Revenue Growth (TTM YoY):     {_fmt('revenueGrowthTTMYoy', suffix='%')}",
        f"  Dividend Yield (TTM):         {_fmt('dividendYieldIndicatedAnnual', suffix='%')}",
        f"  Payout Ratio (TTM):           {_fmt('payoutRatioTTM', suffix='%')}",
        "",
        "## Per Share",
        f"  EPS (TTM):                    {_fmt('epsTTM', prefix='$')}",
        f"  EPS (Annual):                 {_fmt('epsAnnual', prefix='$')}",
        f"  Revenue Per Share (TTM):      {_fmt('revenuePerShareTTM', prefix='$')}",
        f"  Free Cash Flow Per Share:     {_fmt('fcfPerShareTTM', prefix='$')}",
        f"  Book Value Per Share (Qtr):   {_fmt('bookValuePerShareQuarterly', prefix='$')}",
    ]

    return "\n".join(lines)
