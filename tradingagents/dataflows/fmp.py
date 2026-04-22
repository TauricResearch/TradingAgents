"""FMP data source — primary market data for TradingAgents.

Public API mirrors the shape of the (now deprecated) ``y_finance`` module
so callers in ``interface.py`` and the structured analyst tiers get drop-in
replacements. One extra function, :func:`get_ticker_info`, returns a dict
keyed by the same field names yfinance's ``Ticker.info`` emits — this lets
``tier1.py`` / ``tier2.py`` / ``portfolio.py`` swap ``yf.Ticker(t).info``
for ``get_ticker_info(t)`` without touching dict-lookup sites.

Data paths, in order:
  1. Postgres ``fmp_bulk`` (nightly ETL) — zero-cost, fast.
  2. FMP live API (``/stable/*``) — fills gaps and today's data before ETL.
  3. Alpaca (for bars) — already used by :mod:`alpaca_data` as an OHLCV layer.

Fields that FMP genuinely does not expose (e.g. yfinance's extended
``insider_transactions`` DataFrame) return N/A — callers already handle
missing keys gracefully via ``.get(key, 'N/A')`` patterns.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional

from dateutil.relativedelta import relativedelta

from .fmp_client import get_client

_logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Market cap bucket helpers (used by company profile)
# ══════════════════════════════════════════════════════════════════════

def _market_cap_category(mc: Optional[float]) -> str:
    if not mc:
        return "unknown"
    if mc >= 10e9:
        return "large_cap"
    if mc >= 2e9:
        return "mid_cap"
    if mc >= 300e6:
        return "small_cap"
    return "micro_cap"


def _fmt_num(val: Optional[float]) -> Optional[str]:
    if val is None:
        return None
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    if abs(v) >= 1e12:
        return f"${v/1e12:.2f}T"
    if abs(v) >= 1e9:
        return f"${v/1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"${v/1e6:.2f}M"
    return f"${v:,.0f}"


def _to_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _mul(a: Any, b: Any) -> Optional[float]:
    """Multiply two potentially-string FMP values. Returns None if either is missing/invalid."""
    fa, fb = _to_float(a), _to_float(b)
    if fa is None or fb is None:
        return None
    return fa * fb


# ══════════════════════════════════════════════════════════════════════
# yfinance-compatible Ticker.info
# ══════════════════════════════════════════════════════════════════════

_SECTOR_ETF_MAP = {
    "Technology": "XLK",
    "Financial Services": "XLF",
    "Financials": "XLF",
    "Energy": "XLE",
    "Healthcare": "XLV",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Consumer Cyclical": "XLY",
    "Consumer Discretionary": "XLY",
    "Consumer Defensive": "XLP",
    "Consumer Staples": "XLP",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Basic Materials": "XLB",
    "Materials": "XLB",
    "Communication Services": "XLC",
}


def get_ticker_info(ticker: str) -> Dict[str, Any]:
    """Return an FMP-backed dict shaped like ``yf.Ticker(t).info``.

    Keys emitted match yfinance's field names so downstream code works
    without conditionals. Missing fields are simply absent — callers
    already handle ``.get('key', default)``.
    """
    symbol = ticker.upper()
    client = get_client()

    # 1. Profile (fast path: fmp_bulk, fallback: /profile/{symbol})
    profile = client.bulk_lookup("profile-bulk", symbol) or client.live_get(
        f"/profile/{symbol}"
    ) or {}

    # 2. Ratios TTM + Key Metrics TTM for valuation/returns/margins
    ratios = client.bulk_lookup("ratios-ttm-bulk", symbol) or client.live_get(
        f"/ratios-ttm/{symbol}"
    ) or {}
    km = client.bulk_lookup("key-metrics-ttm-bulk", symbol) or client.live_get(
        f"/key-metrics-ttm/{symbol}"
    ) or {}

    # 3. Analyst estimates / price targets (for forward EPS)
    estimates = client.live_get_list(
        f"/analyst-estimates/{symbol}", params={"period": "annual", "limit": 2}
    )
    pt_consensus = client.live_get(f"/price-target-consensus/{symbol}") or {}

    # 4. Quote (for current price / 52W / MAs if profile missed them)
    quote = client.live_get(f"/quote/{symbol}") or {}

    # --- Assemble yfinance-shaped dict ---------------------------------

    mc = _to_float(profile.get("mktCap") or quote.get("marketCap"))
    price = _to_float(profile.get("price") or quote.get("price"))
    hi52 = _to_float(quote.get("yearHigh") or profile.get("yearHigh"))
    lo52 = _to_float(quote.get("yearLow") or profile.get("yearLow"))

    # Forward EPS: use next-year consensus if available
    forward_eps = None
    if estimates:
        # Pick the estimate with the latest date that is after today
        today = datetime.utcnow().date()
        future = []
        for e in estimates:
            try:
                d = datetime.strptime(str(e.get("date", ""))[:10], "%Y-%m-%d").date()
                if d >= today:
                    future.append((d, e))
            except Exception:
                continue
        future.sort()
        if future:
            forward_eps = _to_float(future[0][1].get("estimatedEpsAvg"))

    # TTM margins/returns: FMP ratios-ttm uses grossProfitMarginTTM etc.
    info: Dict[str, Any] = {
        # Identity / profile
        "symbol": symbol,
        "longName": profile.get("companyName"),
        "shortName": profile.get("companyName"),
        "sector": profile.get("sector"),
        "industry": profile.get("industry"),
        "longBusinessSummary": profile.get("description"),
        "fullTimeEmployees": profile.get("fullTimeEmployees"),
        "exchange": profile.get("exchangeShortName") or profile.get("exchange"),
        "website": profile.get("website"),
        "country": profile.get("country"),
        "city": profile.get("city"),
        "currency": profile.get("currency"),
        # Prices
        "currentPrice": price,
        "regularMarketPrice": price,
        "marketCap": mc,
        "fiftyTwoWeekHigh": hi52,
        "fiftyTwoWeekLow": lo52,
        "fiftyDayAverage": _to_float(quote.get("priceAvg50")),
        "twoHundredDayAverage": _to_float(quote.get("priceAvg200")),
        "beta": _to_float(profile.get("beta")),
        # Volume / float
        "averageVolume": _to_float(profile.get("volAvg") or quote.get("avgVolume")),
        "averageVolume10days": _to_float(quote.get("avgVolume")),
        "floatShares": _to_float(km.get("sharesFloatTTM") or profile.get("floatShares")),
        "sharesOutstanding": _to_float(km.get("sharesOutTTM")),
        # Valuation
        "trailingPE": _to_float(ratios.get("priceEarningsRatioTTM") or km.get("peRatioTTM")),
        "forwardPE": _to_float(km.get("peRatioTTM")),
        "pegRatio": _to_float(ratios.get("priceEarningsToGrowthRatioTTM")),
        "priceToBook": _to_float(ratios.get("priceBookValueRatioTTM") or km.get("pbRatioTTM")),
        "priceToSales": _to_float(km.get("priceToSalesRatioTTM")),
        "priceToSalesTrailing12Months": _to_float(km.get("priceToSalesRatioTTM")),
        "enterpriseToEbitda": _to_float(km.get("enterpriseValueOverEBITDATTM")),
        "enterpriseValue": _to_float(km.get("enterpriseValueTTM")),
        "trailingEps": _to_float(km.get("netIncomePerShareTTM")),
        "forwardEps": forward_eps,
        "bookValue": _to_float(km.get("bookValuePerShareTTM")),
        "dividendYield": _to_float(ratios.get("dividendYieldTTM")),
        # Margins / returns (TTM)
        "revenueGrowth": _to_float(km.get("revenueGrowthTTM")),
        "earningsGrowth": _to_float(km.get("netIncomeGrowthTTM")),
        "profitMargins": _to_float(ratios.get("netProfitMarginTTM")),
        "operatingMargins": _to_float(ratios.get("operatingProfitMarginTTM")),
        "grossMargins": _to_float(ratios.get("grossProfitMarginTTM")),
        "ebitdaMargins": _to_float(km.get("ebitdaMarginTTM")),
        "returnOnEquity": _to_float(ratios.get("returnOnEquityTTM") or km.get("roeTTM")),
        "returnOnAssets": _to_float(ratios.get("returnOnAssetsTTM") or km.get("roaTTM")),
        # Balance sheet
        "debtToEquity": _to_float(ratios.get("debtEquityRatioTTM") or km.get("debtToEquityTTM")),
        "currentRatio": _to_float(ratios.get("currentRatioTTM") or km.get("currentRatioTTM")),
        "quickRatio": _to_float(ratios.get("quickRatioTTM")),
        # Cash flow / income statement (per-share × shares-out reconstruction)
        "freeCashflow": _mul(km.get("freeCashFlowPerShareTTM"), km.get("sharesOutTTM")),
        "totalRevenue": _mul(km.get("revenuePerShareTTM"), km.get("sharesOutTTM")),
        "netIncomeToCommon": _mul(km.get("netIncomePerShareTTM"), km.get("sharesOutTTM")),
        "grossProfits": None,  # requires income-statement fetch, not in TTM bulk
        "ebitda": None,        # requires income-statement fetch
        # Analyst coverage
        "targetHighPrice": _to_float(pt_consensus.get("targetHigh")),
        "targetLowPrice": _to_float(pt_consensus.get("targetLow")),
        "targetMeanPrice": _to_float(pt_consensus.get("targetConsensus")),
        "targetMedianPrice": _to_float(pt_consensus.get("targetMedian")),
        "recommendationKey": pt_consensus.get("recommendationKey"),
        # Short interest / institutional / insider (FMP exposes these via other endpoints)
        "heldPercentInstitutions": None,
        "heldPercentInsiders": None,
        "sharesShort": None,
        "sharesShortPriorMonth": None,
        "shortRatio": None,
    }
    # Drop explicit-None keys so callers' `.get(key)` returns None naturally
    # (identical behavior to yfinance, where missing keys aren't present).
    return {k: v for k, v in info.items() if v is not None}


# ══════════════════════════════════════════════════════════════════════
# Router-facing functions (match y_finance signatures used by interface.py)
# ══════════════════════════════════════════════════════════════════════

def get_YFin_data_online(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Daily OHLCV CSV for ``symbol`` between ``start_date`` and ``end_date``.

    Tries Alpaca first (high rate limit, fast); falls back to FMP live API.
    Returned CSV matches the header yfinance callers already expect:
    ``Date,Open,High,Low,Close,Adj Close,Volume``.
    """
    # Validate date format
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    # Alpaca first
    try:
        from .alpaca_data import alpaca_available, get_bars_csv
        if alpaca_available():
            result = get_bars_csv(symbol, start_date, end_date)
            if result and not result.startswith("Error"):
                return result
            _logger.info("Alpaca bars failed, falling back to FMP for %s", symbol)
    except Exception as e:
        _logger.debug("Alpaca unavailable: %s", e)

    # FMP live
    client = get_client()
    rows = client.live_get_list(
        "/historical-price-eod/full",
        params={"symbol": symbol.upper(), "from": start_date, "to": end_date},
    )
    if not rows:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"

    # Sort ascending and format as CSV (matches yfinance default)
    rows_sorted = sorted(rows, key=lambda r: r.get("date", ""))
    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(rows_sorted)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    lines = ["Date,Open,High,Low,Close,Adj Close,Volume"]
    for r in rows_sorted:
        adj = r.get("adjClose", r.get("close"))
        lines.append(
            f"{r.get('date')},{_round(r.get('open'))},{_round(r.get('high'))},"
            f"{_round(r.get('low'))},{_round(r.get('close'))},{_round(adj)},"
            f"{int(r.get('volume') or 0)}"
        )
    return header + "\n".join(lines) + "\n"


def _round(v: Any, nd: int = 2) -> str:
    f = _to_float(v)
    return "" if f is None else f"{f:.{nd}f}"


_INDICATOR_DESC = {
    "close_50_sma": "50 SMA: A medium-term trend indicator. Usage: Identify trend direction and serve as dynamic support/resistance.",
    "close_200_sma": "200 SMA: A long-term trend benchmark. Usage: Confirm overall market trend and identify golden/death cross setups.",
    "close_10_ema": "10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum and potential entry points.",
    "macd": "MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers and divergence as signals of trend changes.",
    "macds": "MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers with the MACD line to trigger trades.",
    "macdh": "MACD Histogram: Shows the gap between the MACD line and its signal. Usage: Visualize momentum strength and spot divergence early.",
    "rsi": "RSI: Measures momentum to flag overbought/oversold conditions. Usage: Apply 70/30 thresholds and watch for divergence to signal reversals.",
    "boll": "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. Usage: Acts as a dynamic benchmark for price movement.",
    "boll_ub": "Bollinger Upper Band: Typically 2 standard deviations above the middle line. Usage: Signals potential overbought conditions and breakout zones.",
    "boll_lb": "Bollinger Lower Band: Typically 2 standard deviations below the middle line. Usage: Indicates potential oversold conditions.",
    "atr": "ATR: Averages true range to measure volatility. Usage: Set stop-loss levels and adjust position sizes based on current market volatility.",
    "vwma": "VWMA: A moving average weighted by volume. Usage: Confirm trends by integrating price action with volume data.",
    "mfi": "MFI: The Money Flow Index is a momentum indicator that uses both price and volume to measure buying and selling pressure.",
}


def get_stock_stats_indicators_window(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    """Technical indicator window. Reuses ``stockstats`` library on FMP OHLCV.

    This mirrors the y_finance implementation but sources bars from FMP
    instead of yfinance. The heavy lifting stays in ``stockstats``.
    """
    from stockstats import wrap
    import pandas as pd

    desc = _INDICATOR_DESC.get(indicator)
    if desc is None:
        raise ValueError(
            f"Indicator {indicator} is not supported. Choose from: {list(_INDICATOR_DESC.keys())}"
        )

    end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = end_dt - relativedelta(years=15)

    client = get_client()
    rows = client.live_get_list(
        "/historical-price-eod/full",
        params={
            "symbol": symbol.upper(),
            "from": start_dt.strftime("%Y-%m-%d"),
            "to": end_dt.strftime("%Y-%m-%d"),
        },
    )
    if not rows:
        return f"No price history for {symbol} up to {curr_date}."

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["date"])
    df = df.rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume",
    }).sort_values("Date").reset_index(drop=True)

    wrapped = wrap(df.copy())
    try:
        wrapped[indicator]  # trigger calculation
    except Exception as e:
        return f"Error computing {indicator} for {symbol}: {e}"

    wrapped["DateStr"] = wrapped["Date"].dt.strftime("%Y-%m-%d")
    value_map = dict(zip(wrapped["DateStr"], wrapped[indicator]))

    # Build window (inclusive of curr_date, walking back look_back_days)
    before = end_dt - relativedelta(days=look_back_days)
    out_lines = []
    cursor = end_dt
    while cursor >= before:
        k = cursor.strftime("%Y-%m-%d")
        v = value_map.get(k)
        if v is None:
            out_lines.append(f"{k}: N/A: Not a trading day (weekend or holiday)")
        elif pd.isna(v):
            out_lines.append(f"{k}: N/A")
        else:
            out_lines.append(f"{k}: {v}")
        cursor -= relativedelta(days=1)

    return (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
        + "\n".join(out_lines)
        + "\n\n"
        + desc
    )


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date"] = None,
):
    """Company fundamentals overview (text)."""
    info = get_ticker_info(ticker)
    if not info.get("longName"):
        return f"No fundamentals data found for symbol '{ticker}'"

    fields = [
        ("Name", info.get("longName")),
        ("Sector", info.get("sector")),
        ("Industry", info.get("industry")),
        ("Market Cap", info.get("marketCap")),
        ("PE Ratio (TTM)", info.get("trailingPE")),
        ("Forward PE", info.get("forwardPE")),
        ("PEG Ratio", info.get("pegRatio")),
        ("Price to Book", info.get("priceToBook")),
        ("EPS (TTM)", info.get("trailingEps")),
        ("Forward EPS", info.get("forwardEps")),
        ("Dividend Yield", info.get("dividendYield")),
        ("Beta", info.get("beta")),
        ("52 Week High", info.get("fiftyTwoWeekHigh")),
        ("52 Week Low", info.get("fiftyTwoWeekLow")),
        ("50 Day Average", info.get("fiftyDayAverage")),
        ("200 Day Average", info.get("twoHundredDayAverage")),
        ("Revenue (TTM)", info.get("totalRevenue")),
        ("EBITDA", info.get("ebitda")),
        ("Net Income", info.get("netIncomeToCommon")),
        ("Profit Margin", info.get("profitMargins")),
        ("Operating Margin", info.get("operatingMargins")),
        ("Return on Equity", info.get("returnOnEquity")),
        ("Return on Assets", info.get("returnOnAssets")),
        ("Debt to Equity", info.get("debtToEquity")),
        ("Current Ratio", info.get("currentRatio")),
        ("Book Value", info.get("bookValue")),
        ("Free Cash Flow", info.get("freeCashflow")),
    ]
    lines = [f"{label}: {value}" for label, value in fields if value is not None]
    header = f"# Company Fundamentals for {ticker.upper()}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + "\n".join(lines)


def _statement_csv(ticker: str, endpoint: str, period: str, label: str) -> str:
    """Fetch a financial statement and render as CSV (period as column headers)."""
    client = get_client()
    rows = client.live_get_list(
        f"/{endpoint}/{ticker.upper()}",
        params={"period": period, "limit": 5},
    )
    if not rows:
        return f"No {label} data found for symbol '{ticker}'"

    # Use date as column header, field name as row. Matches yfinance.to_csv shape.
    dates = [r.get("date") for r in rows]
    keys: List[str] = []
    seen = set()
    for r in rows:
        for k in r.keys():
            if k in ("date", "symbol", "reportedCurrency", "cik", "fillingDate",
                     "acceptedDate", "calendarYear", "period", "link", "finalLink"):
                continue
            if k not in seen:
                seen.add(k)
                keys.append(k)

    out = [",".join([""] + dates)]
    for k in keys:
        row_vals = [str(r.get(k, "")) for r in rows]
        out.append(",".join([k] + row_vals))

    header = f"# {label} data for {ticker.upper()} ({period})\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + "\n".join(out) + "\n"


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date"] = None,
):
    period = "quarter" if freq.lower().startswith("q") else "annual"
    return _statement_csv(ticker, "balance-sheet-statement", period, "Balance Sheet")


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date"] = None,
):
    period = "quarter" if freq.lower().startswith("q") else "annual"
    return _statement_csv(ticker, "cash-flow-statement", period, "Cash Flow")


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date"] = None,
):
    period = "quarter" if freq.lower().startswith("q") else "annual"
    return _statement_csv(ticker, "income-statement", period, "Income Statement")


def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol of the company"],
):
    """Insider transactions via FMP /insider-trading."""
    client = get_client()
    rows = client.live_get_list(
        "/insider-trading",
        params={"symbol": ticker.upper(), "limit": 50},
    )
    if not rows:
        return f"No insider transactions data found for symbol '{ticker}'"

    keys = [
        "filingDate", "transactionDate", "reportingName", "typeOfOwner",
        "transactionType", "securitiesTransacted", "price", "securitiesOwned",
    ]
    out = [",".join(keys)]
    for r in rows:
        out.append(",".join(str(r.get(k, "")) for k in keys))

    header = f"# Insider Transactions data for {ticker.upper()}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + "\n".join(out) + "\n"


# ══════════════════════════════════════════════════════════════════════
# Plain functions used directly by tier1 / tier2 (no @tool decorator)
# ══════════════════════════════════════════════════════════════════════

def get_company_profile(ticker: str, curr_date: Optional[str] = None) -> str:
    info = get_ticker_info(ticker)
    if not info.get("longName"):
        return json.dumps({"error": f"No data for {ticker}", "ticker": ticker})
    mc = info.get("marketCap")
    profile = {
        "company_name": info.get("longName", "Unknown"),
        "ticker": ticker.upper(),
        "sector": info.get("sector", "Unknown"),
        "industry": info.get("industry", "Unknown"),
        "description": info.get("longBusinessSummary", ""),
        "market_cap": mc,
        "market_cap_formatted": _fmt_num(mc),
        "market_cap_category": _market_cap_category(mc),
        "current_price": info.get("currentPrice"),
    }
    return json.dumps(profile, default=str)


def _fetch_etf_perf_fmp(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """3-month price window + 1m/3m returns for a set of ETF/index tickers."""
    client = get_client()
    end = datetime.utcnow().date()
    start = end - relativedelta(months=4)
    out: Dict[str, Dict[str, Any]] = {}
    for sym in symbols:
        rows = client.live_get_list(
            "/historical-price-eod/full",
            params={"symbol": sym, "from": start.isoformat(), "to": end.isoformat()},
        )
        if not rows:
            continue
        # FMP returns most-recent-first
        asc = sorted(rows, key=lambda r: r.get("date", ""))
        closes = [_to_float(r.get("close")) for r in asc]
        closes = [c for c in closes if c is not None]
        if len(closes) < 5:
            continue
        current = closes[-1]
        ret_1m = round((current - closes[-22]) / closes[-22] * 100, 2) if len(closes) >= 22 else None
        ret_3m = round((current - closes[-63]) / closes[-63] * 100, 2) if len(closes) >= 63 else None
        out[sym] = {"return_1m": ret_1m, "return_3m": ret_3m, "price": current}
    return out


_SECTOR_ETFS = {
    "SPY": "S&P 500",
    "XLK": "Technology", "XLF": "Financials", "XLE": "Energy",
    "XLV": "Health Care", "XLI": "Industrials", "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples", "XLU": "Utilities", "XLRE": "Real Estate",
    "XLB": "Materials", "XLC": "Communication Services",
}


def get_macro_indicators(curr_date: Optional[str] = None) -> str:
    """Macro indicators: VIX, 10Y yield, sector ETF performance."""
    results: Dict[str, Any] = {}
    client = get_client()

    # VIX and 10Y yield via FMP quote endpoints for indices
    vix_quote = client.live_get("/quote/^VIX")
    if vix_quote:
        results["vix_level"] = _to_float(vix_quote.get("price"))
    tnx_quote = client.live_get("/quote/^TNX")
    if tnx_quote:
        results["ten_year_yield"] = _to_float(tnx_quote.get("price"))

    # Sector ETF performance — Alpaca first, FMP fallback
    sector_performance: Dict[str, Any] = {}
    try:
        from .alpaca_data import alpaca_available, get_sector_etf_performance
        if alpaca_available():
            perf = get_sector_etf_performance(list(_SECTOR_ETFS.keys()))
            if perf:
                for sym, data in perf.items():
                    sector_performance[sym] = {
                        "name": _SECTOR_ETFS.get(sym, sym),
                        "return_1m": data.get("return_1m"),
                        "return_3m": data.get("return_3m"),
                        "price": data.get("price"),
                    }
    except Exception as e:
        _logger.debug("Alpaca sector ETFs failed: %s", e)

    if not sector_performance:
        perf = _fetch_etf_perf_fmp(list(_SECTOR_ETFS.keys()))
        for sym, data in perf.items():
            sector_performance[sym] = {
                "name": _SECTOR_ETFS.get(sym, sym),
                **data,
            }

    if sector_performance:
        results["sector_performance"] = sector_performance

    return json.dumps(results, default=str)


def get_sector_rotation(ticker: str, curr_date: Optional[str] = None) -> str:
    """Sector rotation data with relative performance vs SPY."""
    info = get_ticker_info(ticker)
    sector = info.get("sector", "Unknown")
    sector_etf = _SECTOR_ETF_MAP.get(sector)

    result: Dict[str, Any] = {"ticker": ticker.upper(), "sector": sector, "sector_etf": sector_etf}
    if not sector_etf:
        return json.dumps(result, default=str)

    etfs = [sector_etf, "SPY"]
    perf: Dict[str, Dict[str, Any]] = {}
    try:
        from .alpaca_data import alpaca_available, get_sector_etf_performance
        if alpaca_available():
            perf = get_sector_etf_performance(etfs) or {}
    except Exception:
        pass
    if not perf:
        perf = _fetch_etf_perf_fmp(etfs)

    spy_data = perf.get("SPY", {})
    etf_data = perf.get(sector_etf, {})
    spy_1m, spy_3m = spy_data.get("return_1m"), spy_data.get("return_3m")
    etf_1m, etf_3m = etf_data.get("return_1m"), etf_data.get("return_3m")

    if etf_1m is not None and spy_1m is not None:
        result["stock_sector_vs_spy_1m"] = round(etf_1m - spy_1m, 2)
    if etf_3m is not None and spy_3m is not None:
        result["stock_sector_vs_spy_3m"] = round(etf_3m - spy_3m, 2)

    try:
        macro = json.loads(get_macro_indicators())
        sector_perf = macro.get("sector_performance", {})
        ranked = sorted(
            [(s, d.get("return_1m", -999)) for s, d in sector_perf.items() if s != "SPY"],
            key=lambda x: x[1], reverse=True,
        )
        for i, (sym, _) in enumerate(ranked, 1):
            if sym == sector_etf:
                result["stock_sector_rank"] = i
                result["total_sectors"] = len(ranked)
                break
    except Exception:
        pass

    return json.dumps(result, default=str)


def get_institutional_flow(ticker: str) -> str:
    """Institutional flow: ownership, volume, short interest, 13F holders, insiders."""
    symbol = ticker.upper()
    client = get_client()

    profile = client.bulk_lookup("profile-bulk", symbol) or client.live_get(
        f"/profile/{symbol}"
    ) or {}
    quote = client.live_get(f"/quote/{symbol}") or {}

    # Institutional ownership (percentage)
    inst_ownership = client.live_get(f"/institutional-ownership/symbol-ownership",
                                      params={"symbol": symbol, "includeCurrentQuarter": "false"})
    held_pct_inst = None
    if isinstance(inst_ownership, dict):
        # Already a dict (single record)
        held_pct_inst = _to_float(inst_ownership.get("ownershipPercent"))
    elif isinstance(inst_ownership, list) and inst_ownership:
        held_pct_inst = _to_float(inst_ownership[0].get("ownershipPercent"))

    # Top institutional holders (13F)
    holders_raw = client.live_get_list(
        "/institutional-ownership/institutional-holders/symbol-ownership-percent",
        params={"symbol": symbol},
    )
    top_holders = []
    for h in holders_raw[:10]:
        top_holders.append({
            "holder": h.get("investorName") or h.get("holder") or "",
            "shares": _to_float(h.get("sharesNumber") or h.get("shares")),
            "pct_out": _to_float(h.get("ownershipPercent")),
            "value": _to_float(h.get("marketValue")),
        })

    # Insider transactions (recent 10)
    insiders_raw = client.live_get_list("/insider-trading",
                                        params={"symbol": symbol, "limit": 20})
    buys = sum(1 for r in insiders_raw if "Purchase" in str(r.get("transactionType", "")))
    sells = sum(1 for r in insiders_raw if "Sale" in str(r.get("transactionType", "")))
    insider_signal = "buying" if buys > sells else "selling" if sells > buys else "none"

    # Short interest (FMP SEC short interest endpoint)
    short_data = client.live_get(f"/short-interest", params={"symbol": symbol}) or {}

    avg_vol = _to_float(profile.get("volAvg") or quote.get("avgVolume"))
    avg_vol_10d = _to_float(quote.get("avgVolume"))
    float_shares = _to_float(short_data.get("floatShares"))
    shares_short = _to_float(short_data.get("sharesShort"))
    shares_short_prior = _to_float(short_data.get("sharesShortPriorMonth"))

    result: Dict[str, Any] = {
        "ticker": symbol,
        "average_volume": avg_vol,
        "average_volume_10d": avg_vol_10d,
        "float_shares": float_shares,
        "shares_short": shares_short,
        "shares_short_prior": shares_short_prior,
        "short_ratio": _to_float(short_data.get("shortRatio")),
        "held_percent_institutions": held_pct_inst,
        "held_percent_insiders": None,  # FMP doesn't expose this as a single field
        "insider_buys_recent": buys,
        "insider_sells_recent": sells,
        "insider_transaction_signal": insider_signal,
        "top_institutional_holders": top_holders,
        "top_holders_count": len(top_holders),
    }

    if avg_vol_10d and avg_vol and avg_vol > 0:
        result["volume_ratio"] = round(avg_vol_10d / avg_vol, 2)
    if float_shares and shares_short and float_shares > 0:
        result["short_pct_of_float"] = round(shares_short / float_shares * 100, 2)
    if shares_short is not None and shares_short_prior and shares_short_prior > 0:
        pct_change = (shares_short - shares_short_prior) / shares_short_prior * 100
        result["short_interest_change_pct"] = round(pct_change, 1)
        if pct_change > 5:
            result["short_interest_trend"] = "rising"
        elif pct_change < -5:
            result["short_interest_trend"] = "falling"
        else:
            result["short_interest_trend"] = "stable"
    if avg_vol_10d and float_shares and float_shares > 0:
        result["float_turnover_5d_pct"] = round(avg_vol_10d * 5 / float_shares * 100, 2)

    return json.dumps(result, default=str)


def get_earnings_estimates(ticker: str) -> str:
    """Earnings estimates (trailing/forward EPS, price)."""
    info = get_ticker_info(ticker)
    return json.dumps({
        "ticker": ticker.upper(),
        "trailing_eps": info.get("trailingEps"),
        "forward_eps": info.get("forwardEps"),
        "current_price": info.get("currentPrice"),
        "target_mean_price": info.get("targetMeanPrice"),
        "target_high_price": info.get("targetHighPrice"),
        "target_low_price": info.get("targetLowPrice"),
    }, default=str)


def get_valuation_peers(ticker: str) -> str:
    """Valuation metrics (P/E, PEG, P/B, EV/EBITDA, etc.)."""
    info = get_ticker_info(ticker)
    return json.dumps({
        "ticker": ticker.upper(),
        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "peg_ratio": info.get("pegRatio"),
        "price_to_book": info.get("priceToBook"),
        "ev_to_ebitda": info.get("enterpriseToEbitda"),
        "price_to_sales": info.get("priceToSales"),
        "revenue_growth": info.get("revenueGrowth"),
        "earnings_growth": info.get("earningsGrowth"),
    }, default=str)


# ══════════════════════════════════════════════════════════════════════
# News (FMP /stock-news or /stock_news — primary replacement for news paths)
# ══════════════════════════════════════════════════════════════════════

def get_news_fmp(ticker: str, curr_date: Optional[str] = None, look_back_days: int = 7) -> str:
    client = get_client()
    rows = client.live_get_list("/stock-news", params={"symbols": ticker.upper(), "limit": 30})
    if not rows:
        return f"No recent news for {ticker.upper()}"
    lines = [f"# Recent News for {ticker.upper()}\n"]
    for r in rows[:20]:
        date = r.get("publishedDate") or r.get("date") or ""
        title = r.get("title") or ""
        site = r.get("site") or ""
        url = r.get("url") or ""
        lines.append(f"- [{date[:10]}] {title} ({site}) {url}")
    return "\n".join(lines)


def get_global_news_fmp(curr_date: Optional[str] = None) -> str:
    client = get_client()
    rows = client.live_get_list("/general-news", params={"limit": 30})
    if not rows:
        return "No recent global news available."
    lines = ["# Recent Global News\n"]
    for r in rows[:20]:
        date = r.get("publishedDate") or ""
        title = r.get("title") or ""
        site = r.get("site") or ""
        url = r.get("url") or ""
        lines.append(f"- [{date[:10]}] {title} ({site}) {url}")
    return "\n".join(lines)
