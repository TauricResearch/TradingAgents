from datetime import datetime, timezone
from typing import Annotated

import yfinance as yf

from tradingagents.dataflows.date_window import (
    withhold_live_profile,
    withhold_undated_statements,
    withhold_undisclosed_trades,
)
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.net import vendor_reachable
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.common import (
    YAHOO_HOST,
    raise_for_empty,
    yf_retry,
)

# Quote currencies Yahoo gives in a minor unit, and the main unit of each.
_MAIN_UNIT = {"GBp": "GBP", "GBX": "GBP", "ZAc": "ZAR", "ILA": "ILS"}


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company"],
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None
):
    """Get company fundamentals overview from yfinance.

    ``Ticker.info`` is a present-day snapshot with no historical vintage, so a
    past ``as_of_date`` withholds it through the shared point-in-time guard
    (``date_window.withhold_live_profile``, #1300).
    """
    canonical = normalize_symbol(ticker)

    # Guard before the request: the response would only be discarded, and the
    # answer does not depend on it.
    withheld = withhold_live_profile(as_of_date, canonical)
    if withheld:
        return withheld

    info = yf_retry(lambda: yf.Ticker(canonical).info)
    if not info:
        raise_for_empty(ticker, canonical, "fundamentals")

    # Yahoo gives these two in percent (dividendYield 0.41 is 0.41%; debtToEquity
    # 78.4 is 78.4%, a ratio of 0.78) but the margins and returns as fractions,
    # so each carries its unit.
    dividend_yield, debt_to_equity = info.get("dividendYield"), info.get("debtToEquity")
    # Money figures come in three currencies (#1456): price levels in the quote
    # currency, which can be a minor unit (London in pence, GBp); market cap and
    # per-share figures in that currency's main unit (GBP), as Yahoo's own P/E
    # and P/B are computed against them; income figures in the currency the
    # company reports in (an ADR quotes in USD, reports in TWD), or bare when
    # Yahoo does not say which.
    quote = info.get("currency")
    main = _MAIN_UNIT.get(quote, quote)
    reported = info.get("financialCurrency")
    quote_timestamp = info.get("regularMarketTime")
    if quote_timestamp is not None:
        try:
            quote_timestamp = datetime.fromtimestamp(
                float(quote_timestamp), tz=timezone.utc
            ).isoformat()
        except (TypeError, ValueError, OSError, OverflowError):
            quote_timestamp = None

    revenue_growth = info.get("revenueGrowth")
    analyst_target = info.get("targetMeanPrice")

    def money(key, currency):
        value = info.get(key)
        return None if value is None else f"{value} {currency}" if currency else value

    fields = [
        ("Name", info.get("longName")),
        ("Sector", info.get("sector")),
        ("Industry", info.get("industry")),
        ("Quote Currency", quote),
        ("Financial Reporting Currency", reported),
        ("Regular-Market Quote", money("regularMarketPrice", quote)),
        ("Quote timestamp (UTC)", quote_timestamp),
        ("Shares Outstanding", info.get("sharesOutstanding")),
        ("Revenue Growth (YoY)", None if revenue_growth is None else f"{revenue_growth * 100:.1f}%"),
        ("Operating Cash Flow", money("operatingCashflow", reported)),
        ("Total Cash", money("totalCash", reported)),
        ("Total Debt", money("totalDebt", reported)),
        ("Analyst Target (Mean)", money("targetMeanPrice", quote)),
        ("Analyst Recommendation", info.get("recommendationKey")),
        ("Analyst Opinions", info.get("numberOfAnalystOpinions")),
        ("Full-Time Employees", info.get("fullTimeEmployees")),
        ("Market Cap", money("marketCap", main)),
        ("PE Ratio (TTM)", info.get("trailingPE")),
        ("Forward PE", info.get("forwardPE")),
        ("PEG Ratio", info.get("pegRatio")),
        ("Price to Book", info.get("priceToBook")),
        ("EPS (TTM)", money("trailingEps", main)),
        ("Forward EPS", money("forwardEps", main)),
        ("Dividend Yield", None if dividend_yield is None else f"{dividend_yield}%"),
        ("Beta", info.get("beta")),
        ("52 Week High", money("fiftyTwoWeekHigh", quote)),
        ("52 Week Low", money("fiftyTwoWeekLow", quote)),
        ("50 Day Average", money("fiftyDayAverage", quote)),
        ("200 Day Average", money("twoHundredDayAverage", quote)),
        ("Revenue (TTM)", money("totalRevenue", reported)),
        ("Gross Profit", money("grossProfits", reported)),
        ("EBITDA", money("ebitda", reported)),
        ("Net Income", money("netIncomeToCommon", reported)),
        ("Profit Margin", info.get("profitMargins")),
        ("Operating Margin", info.get("operatingMargins")),
        ("Return on Equity", info.get("returnOnEquity")),
        ("Return on Assets", info.get("returnOnAssets")),
        ("Debt to Equity", None if debt_to_equity is None
         else f"{debt_to_equity}% ({debt_to_equity / 100:.2f}x)"),
        ("Current Ratio", info.get("currentRatio")),
        ("Book Value", money("bookValue", main)),
        ("Free Cash Flow", money("freeCashflow", reported)),
    ]

    lines = [f"{label}: {v}" for label, v in fields if v is not None]

    # ETF profile. Yahoo serves fund-specific fields (NAV, TER, YTD, AUM,
    # inception) for ETFs and leaves them null for plain equities, so the
    # block is present-or-absent, never "None". Detection is generic — an
    # instrument is treated as an ETF when Yahoo supplies a NAV or labels it
    # an exchange-traded fund — so it works for any listing, not one name.
    etf_lines: list[str] = []
    if info.get("navPrice") is not None or (info.get("legalType") or "").lower().find("exchange traded fund") >= 0:
        if info.get("navPrice") is not None:
            etf_lines.append(f"ETF NAV: {money('navPrice', quote)}")
        ner = info.get("netExpenseRatio")
        if ner is not None:
            etf_lines.append(f"Expense ratio (TER): {float(ner):.2f}%")
        ytd = info.get("ytdReturn")
        if ytd is not None:
            etf_lines.append(f"YTD return: {float(ytd):+.1f}%")
        if info.get("totalAssets") is not None:
            etf_lines.append(f"Total assets (approx): {info['totalAssets']}")
        inc = info.get("fundInceptionDate")
        if inc:
            try:
                etf_lines.append(f"Inception: {datetime.fromtimestamp(float(inc), tz=timezone.utc).date().isoformat()}")
            except (TypeError, ValueError, OverflowError, OSError):
                pass
        if info.get("yield") is not None:
            etf_lines.append(f"Distribution yield: {float(info['yield']) * 100:.2f}%")
        for label, key in (("Legal type", "legalType"), ("Category", "category")):
            if info.get(key):
                etf_lines.append(f"{label}: {info[key]}")

    # yfinance returns a stub dict (e.g. {"trailingPegRatio": None}) for
    # unknown symbols, so `info` is truthy but every field is empty. Treat
    # "no usable fields" as no data rather than emitting a bare header the
    # agent might fabricate around.
    if not lines and not etf_lines:
        raise_for_empty(ticker, canonical, "fundamental fields")

    # Analyst consensus spread. The mean target hides how far apart the
    # covering analysts are; the low/high fields from the same live snapshot
    # make the dispersion visible (a wide band weakens a consensus-anchored
    # call regardless of the mean). Present when Yahoo supplies at least the
    # mean plus a bound or a headcount; omitted, never "None", otherwise.
    target_spread: list[str] = []
    t_mean, t_low, t_high = info.get("targetMeanPrice"), info.get("targetLowPrice"), info.get("targetHighPrice")
    if t_mean is not None and (t_low is not None or t_high is not None or info.get("numberOfAnalystOpinions") is not None):
        if t_low is not None and t_high is not None:
            if t_mean:
                target_spread.append(
                    f"Analyst Target Spread: {money('targetLowPrice', quote)} to {money('targetHighPrice', quote)} "
                    f"({(t_high - t_low) / t_mean * 100:.0f}% band around the mean)"
                )
            else:
                target_spread.append(
                    f"Analyst Target Spread: {money('targetLowPrice', quote)} to {money('targetHighPrice', quote)}"
                )
        if info.get("targetMedianPrice") is not None:
            target_spread.append(f"Analyst Target (Median): {money('targetMedianPrice', quote)}")
        if info.get("averageAnalystRating") is not None:
            target_spread.append(f"Analyst Rating (Yahoo text): {info['averageAnalystRating']}")

    body = "\n".join(lines + etf_lines + target_spread)
    if etf_lines:
        body += "\n\nETF profile note: values are Yahoo's live fund snapshot (NAV, TER, YTD return, AUM, inception) as of the quote time. Top holdings/positions are not provided by this vendor."
    if target_spread:
        body += "\n\nAnalyst consensus note: values are Yahoo's live aggregate of covering analysts as of the quote time — no per-house targets or as-of date. The spread is dispersion among analysts, not a range of scenarios."
    return f"# Company Fundamentals for {canonical}\n\n" + body


def _statement(ticker, freq, as_of_date, title, quarterly_attr, annual_attr) -> str:
    """One financial statement as CSV, for a run dated today."""
    canonical = normalize_symbol(ticker)
    withheld = withhold_undated_statements(as_of_date, canonical, title)
    if withheld:
        return withheld
    what = title.lower()
    attr = quarterly_attr if freq.lower() == "quarterly" else annual_attr
    data = yf_retry(lambda: getattr(yf.Ticker(canonical), attr))
    if data is None or data.empty:
        raise_for_empty(ticker, canonical, f"{what} data")
    return f"# {title} data for {canonical} ({freq})\n" + data.to_csv()


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    as_of_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get balance sheet data from yfinance."""
    return _statement(ticker, freq, as_of_date, "Balance Sheet", "quarterly_balance_sheet", "balance_sheet")


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    as_of_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get cash flow data from yfinance."""
    return _statement(ticker, freq, as_of_date, "Cash Flow", "quarterly_cashflow", "cashflow")


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    as_of_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get income statement data from yfinance."""
    return _statement(ticker, freq, as_of_date, "Income Statement", "quarterly_income_stmt", "income_stmt")


def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol of the company"],
    as_of_date: Annotated[str | None, "analysis date, yyyy-mm-dd"] = None,
):
    """Get insider transactions data from yfinance, for a run dated today."""
    canonical = normalize_symbol(ticker)
    withheld = withhold_undisclosed_trades(as_of_date, canonical)
    if withheld:
        return withheld
    data = yf_retry(lambda: yf.Ticker(canonical).insider_transactions)

    # Empty is normal here (many valid symbols have no insider filings),
    # so report it plainly rather than treating the symbol as invalid.
    if data is None or data.empty:
        if not vendor_reachable(YAHOO_HOST):
            raise VendorUnavailableError("Yahoo Finance is unreachable; insider filings were not retrieved")
        return (
            f"No insider transactions returned by Yahoo Finance for symbol '{canonical}'. "
            "Source coverage is unverified; this does not establish that no transactions occurred. "
            "Do not infer an insider-trade count or neutral sentiment from this empty feed. "
            "Check issuer/regulatory PDMR disclosures separately."
        )

    return f"# Insider Transactions data for {canonical}\n" + data.to_csv()


def get_company_profile(ticker: str) -> dict:
    """Yahoo's current profile for ``ticker``: name, sector, industry and the like."""
    return yf_retry(lambda: yf.Ticker(normalize_symbol(ticker)).info) or {}
