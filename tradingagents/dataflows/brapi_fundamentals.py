"""brapi.dev fundamentals vendor for B3 tickers.

Mirrors ``get_fundamentals`` in y_finance.py and alpha_vantage_fundamentals.py:
a present-day company snapshot (market cap, multiples, margins), withheld for
past analysis dates through the same point-in-time guard every fundamentals
vendor in this package uses, so switching vendors never reintroduces a
look-ahead leak (#1300).

Field names below follow brapi.dev's `defaultKeyStatistics` / `financialData` /
`summaryProfile` modules, which mirror Yahoo's schema. Verify against a live
response for your token/plan before relying on this in a backtest — brapi's
module contents can vary by plan tier, and a field silently missing just
drops that line rather than failing loudly.
"""

from __future__ import annotations

from typing import Annotated

from .brapi_common import brapi_request, strip_b3_suffix
from .date_window import withhold_live_profile
from .errors import NoMarketDataError

_MODULES = "defaultKeyStatistics,financialData,summaryProfile"


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company (e.g. PETR4 or PETR4.SA)"],
    curr_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None,
) -> str:
    """Get company fundamentals overview for a B3 ticker from brapi.dev."""
    canonical = strip_b3_suffix(ticker)

    # Guard before the request: same present-day-only limitation as the
    # yfinance/Alpha Vantage overview endpoints, so a backtest can't see it.
    withheld = withhold_live_profile(curr_date, canonical)
    if withheld:
        return withheld

    payload = brapi_request(f"quote/{canonical}", {
        "modules": _MODULES,
        "dividends": "true",
    })

    results = payload.get("results") or []
    if not results:
        raise NoMarketDataError(ticker, canonical, "no fundamentals")

    result = results[0]
    key_stats = result.get("defaultKeyStatistics") or {}
    fin_data = result.get("financialData") or {}
    profile = result.get("summaryProfile") or {}

    fields = [
        ("Name", result.get("longName") or result.get("shortName")),
        ("Sector", profile.get("sector")),
        ("Industry", profile.get("industry")),
        ("Currency", result.get("currency")),
        ("Market Cap", result.get("marketCap")),
        ("PE Ratio (TTM)", result.get("priceEarnings") or key_stats.get("trailingPE")),
        ("Forward PE", key_stats.get("forwardPE")),
        ("Price to Book", key_stats.get("priceToBook")),
        ("EPS (TTM)", result.get("earningsPerShare") or key_stats.get("trailingEps")),
        ("Beta", key_stats.get("beta")),
        ("52 Week Range", result.get("fiftyTwoWeekRange")),
        ("Revenue (TTM)", fin_data.get("totalRevenue")),
        ("Gross Margin", fin_data.get("grossMargins")),
        ("Operating Margin", fin_data.get("operatingMargins")),
        ("Profit Margin", fin_data.get("profitMargins")),
        ("Return on Equity", fin_data.get("returnOnEquity")),
        ("Return on Assets", fin_data.get("returnOnAssets")),
        ("Debt to Equity", fin_data.get("debtToEquity")),
        ("Current Ratio", fin_data.get("currentRatio")),
        ("Free Cash Flow", fin_data.get("freeCashflow")),
        ("Dividend Yield", key_stats.get("dividendYield")),
    ]

    lines = [f"{label}: {v}" for label, v in fields if v is not None]

    if not lines:
        raise NoMarketDataError(ticker, canonical, "fundamentals returned no usable fields")

    header = f"# Company Fundamentals for {canonical}\n"
    if curr_date:
        header += f"# Point-in-time as of: {curr_date} (live snapshot, see limitation above)\n"
    header += "\n"

    return header + "\n".join(lines)
