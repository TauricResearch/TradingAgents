"""Macro-aware data tools for the structured equity ranking engine.

These tools fetch company profile, macro regime, sector rotation,
institutional flow, earnings estimates, and valuation data via yfinance.
They are used directly by analyst agents (not routed through interface.py).
"""

from langchain_core.tools import tool
from typing import Annotated
from datetime import datetime
from dateutil.relativedelta import relativedelta
import json


def _safe_get(info, key, default=None):
    """Safely get a value from yfinance info dict."""
    val = info.get(key)
    if val is None:
        return default
    return val


def _fmt_large_number(val):
    """Format large numbers for readability."""
    if val is None:
        return None
    if abs(val) >= 1e12:
        return f"${val/1e12:.2f}T"
    if abs(val) >= 1e9:
        return f"${val/1e9:.2f}B"
    if abs(val) >= 1e6:
        return f"${val/1e6:.2f}M"
    return f"${val:,.0f}"


def _market_cap_category(market_cap):
    """Classify market cap size."""
    if market_cap is None:
        return "unknown"
    if market_cap >= 10e9:
        return "large_cap"
    if market_cap >= 2e9:
        return "mid_cap"
    if market_cap >= 300e6:
        return "small_cap"
    return "micro_cap"


# Sector to ETF mapping
SECTOR_ETF_MAP = {
    "Technology": "XLK",
    "Information Technology": "XLK",
    "Communication Services": "XLC",
    "Healthcare": "XLV",
    "Health Care": "XLV",
    "Financials": "XLF",
    "Financial Services": "XLF",
    "Consumer Discretionary": "XLY",
    "Consumer Cyclical": "XLY",
    "Consumer Staples": "XLP",
    "Consumer Defensive": "XLP",
    "Industrials": "XLI",
    "Energy": "XLE",
    "Utilities": "XLU",
    "Materials": "XLB",
    "Basic Materials": "XLB",
    "Real Estate": "XLRE",
}

ALL_SECTOR_ETFS = ["XLK", "XLC", "XLV", "XLF", "XLY", "XLP", "XLI", "XLE", "XLU", "XLB", "XLRE"]


def _get_period_return(ticker_obj, period_months, ref_date=None):
    """Calculate return over a given period ending at ref_date."""
    import yfinance as yf
    import pandas as pd

    try:
        if ref_date:
            end_dt = pd.to_datetime(ref_date)
        else:
            end_dt = pd.Timestamp.today()

        start_dt = end_dt - pd.DateOffset(months=period_months)
        data = ticker_obj.history(
            start=start_dt.strftime("%Y-%m-%d"),
            end=end_dt.strftime("%Y-%m-%d"),
        )
        if data.empty or len(data) < 2:
            return None
        return ((data["Close"].iloc[-1] / data["Close"].iloc[0]) - 1) * 100
    except Exception:
        return None


@tool
def get_company_profile(
    ticker: Annotated[str, "Ticker symbol of the company"],
) -> str:
    """Fetch company profile: name, sector, industry, description, market cap, business model.
    Returns structured text with all fields for the Company Intelligence Analyst.
    """
    import yfinance as yf

    try:
        t = yf.Ticker(ticker.upper())
        info = t.info

        if not info or not info.get("longName"):
            return json.dumps({"error": f"No company data found for {ticker}", "ticker": ticker})

        market_cap = _safe_get(info, "marketCap")

        profile = {
            "company_name": _safe_get(info, "longName", "Unknown"),
            "ticker": ticker.upper(),
            "sector": _safe_get(info, "sector", "Unknown"),
            "industry": _safe_get(info, "industry", "Unknown"),
            "description": _safe_get(info, "longBusinessSummary", "No description available"),
            "market_cap": market_cap,
            "market_cap_formatted": _fmt_large_number(market_cap),
            "market_cap_category": _market_cap_category(market_cap),
            "trailing_pe": _safe_get(info, "trailingPE"),
            "forward_pe": _safe_get(info, "forwardPE"),
            "peg_ratio": _safe_get(info, "pegRatio"),
            "price_to_book": _safe_get(info, "priceToBook"),
            "dividend_yield": _safe_get(info, "dividendYield"),
            "beta": _safe_get(info, "beta"),
            "trailing_eps": _safe_get(info, "trailingEps"),
            "forward_eps": _safe_get(info, "forwardEps"),
            "revenue": _safe_get(info, "totalRevenue"),
            "revenue_formatted": _fmt_large_number(_safe_get(info, "totalRevenue")),
            "gross_profits": _safe_get(info, "grossProfits"),
            "ebitda": _safe_get(info, "ebitda"),
            "net_income": _safe_get(info, "netIncomeToCommon"),
            "profit_margins": _safe_get(info, "profitMargins"),
            "operating_margins": _safe_get(info, "operatingMargins"),
            "return_on_equity": _safe_get(info, "returnOnEquity"),
            "return_on_assets": _safe_get(info, "returnOnAssets"),
            "debt_to_equity": _safe_get(info, "debtToEquity"),
            "current_ratio": _safe_get(info, "currentRatio"),
            "book_value": _safe_get(info, "bookValue"),
            "free_cashflow": _safe_get(info, "freeCashflow"),
            "fifty_two_week_high": _safe_get(info, "fiftyTwoWeekHigh"),
            "fifty_two_week_low": _safe_get(info, "fiftyTwoWeekLow"),
            "fifty_day_average": _safe_get(info, "fiftyDayAverage"),
            "two_hundred_day_average": _safe_get(info, "twoHundredDayAverage"),
            "average_volume": _safe_get(info, "averageVolume"),
            "average_volume_10d": _safe_get(info, "averageVolume10days"),
            "shares_outstanding": _safe_get(info, "sharesOutstanding"),
            "float_shares": _safe_get(info, "floatShares"),
            "shares_short": _safe_get(info, "sharesShort"),
            "short_ratio": _safe_get(info, "shortRatio"),
            "held_percent_insiders": _safe_get(info, "heldPercentInsiders"),
            "held_percent_institutions": _safe_get(info, "heldPercentInstitutions"),
            "current_price": _safe_get(info, "currentPrice") or _safe_get(info, "regularMarketPrice"),
        }

        return json.dumps(profile, default=str)

    except Exception as e:
        return json.dumps({"error": f"Error fetching company profile for {ticker}: {str(e)}", "ticker": ticker})


@tool
def get_macro_indicators(
    curr_date: Annotated[str, "Current trading date in yyyy-mm-dd format"],
) -> str:
    """Fetch macro regime indicators: VIX, 10Y yield, dollar strength, credit spreads, sector ETF performance.
    Returns structured text for the Company Intelligence and Macro Regime Analyst.
    """
    import yfinance as yf
    import pandas as pd

    try:
        results = {}

        # VIX
        try:
            vix = yf.Ticker("^VIX")
            vix_data = vix.history(period="5d")
            if not vix_data.empty:
                results["vix_level"] = round(vix_data["Close"].iloc[-1], 2)
                if results["vix_level"] < 15:
                    results["vix_regime"] = "low"
                elif results["vix_level"] < 20:
                    results["vix_regime"] = "moderate"
                elif results["vix_level"] < 30:
                    results["vix_regime"] = "elevated"
                else:
                    results["vix_regime"] = "stressed"
        except Exception:
            results["vix_level"] = None
            results["vix_regime"] = "unknown"

        # 10Y yield
        try:
            tnx = yf.Ticker("^TNX")
            tnx_data = tnx.history(period="5d")
            if not tnx_data.empty:
                results["ten_year_yield"] = round(tnx_data["Close"].iloc[-1], 3)
        except Exception:
            results["ten_year_yield"] = None

        # Dollar strength (UUP as proxy)
        try:
            uup = yf.Ticker("UUP")
            uup_1m = _get_period_return(uup, 1)
            uup_3m = _get_period_return(uup, 3)
            results["dollar_1m_return"] = round(uup_1m, 2) if uup_1m is not None else None
            results["dollar_3m_return"] = round(uup_3m, 2) if uup_3m is not None else None
            if uup_1m is not None:
                if uup_1m > 1:
                    results["dollar_strength"] = "strong"
                elif uup_1m < -1:
                    results["dollar_strength"] = "weak"
                else:
                    results["dollar_strength"] = "neutral"
        except Exception:
            results["dollar_strength"] = "unknown"

        # Credit spreads: HYG vs LQD
        try:
            hyg = yf.Ticker("HYG")
            lqd = yf.Ticker("LQD")
            hyg_1m = _get_period_return(hyg, 1)
            lqd_1m = _get_period_return(lqd, 1)
            if hyg_1m is not None and lqd_1m is not None:
                spread_change = hyg_1m - lqd_1m
                results["hyg_1m_return"] = round(hyg_1m, 2)
                results["lqd_1m_return"] = round(lqd_1m, 2)
                results["credit_spread_change"] = round(spread_change, 2)
                if spread_change > 0.5:
                    results["credit_spread_direction"] = "tightening"
                elif spread_change < -0.5:
                    results["credit_spread_direction"] = "widening"
                else:
                    results["credit_spread_direction"] = "stable"
        except Exception:
            results["credit_spread_direction"] = "unknown"

        # SPY and sector ETF performance
        sector_etfs = {
            "SPY": "S&P 500",
            "XLK": "Technology",
            "XLC": "Communication Services",
            "XLV": "Healthcare",
            "XLF": "Financials",
            "XLY": "Consumer Discretionary",
            "XLP": "Consumer Staples",
            "XLI": "Industrials",
            "XLE": "Energy",
            "XLU": "Utilities",
            "XLB": "Materials",
            "XLRE": "Real Estate",
        }

        sector_performance = {}
        for etf_ticker, sector_name in sector_etfs.items():
            try:
                etf = yf.Ticker(etf_ticker)
                ret_1m = _get_period_return(etf, 1)
                ret_3m = _get_period_return(etf, 3)
                sector_performance[etf_ticker] = {
                    "name": sector_name,
                    "return_1m": round(ret_1m, 2) if ret_1m is not None else None,
                    "return_3m": round(ret_3m, 2) if ret_3m is not None else None,
                }
            except Exception:
                sector_performance[etf_ticker] = {
                    "name": sector_name,
                    "return_1m": None,
                    "return_3m": None,
                }

        results["sector_performance"] = sector_performance

        return json.dumps(results, default=str)

    except Exception as e:
        return json.dumps({"error": f"Error fetching macro indicators: {str(e)}"})


@tool
def get_sector_rotation(
    ticker: Annotated[str, "Ticker symbol of the company"],
    curr_date: Annotated[str, "Current trading date in yyyy-mm-dd format"],
) -> str:
    """Fetch sector rotation data: sector ETF relative strength vs SPY over 1M/3M/6M, breadth indicators.
    Returns structured text for the Sector Rotation and Institutional Flow Analyst.
    """
    import yfinance as yf

    try:
        # Get the company's sector
        t = yf.Ticker(ticker.upper())
        info = t.info
        sector = _safe_get(info, "sector", "Unknown")

        # Map sector to ETF
        sector_etf = SECTOR_ETF_MAP.get(sector, None)

        # Get SPY returns
        spy = yf.Ticker("SPY")
        spy_1m = _get_period_return(spy, 1)
        spy_3m = _get_period_return(spy, 3)
        spy_6m = _get_period_return(spy, 6)

        # Get all sector ETF returns for ranking
        sector_returns = {}
        for etf_sym in ALL_SECTOR_ETFS:
            try:
                etf = yf.Ticker(etf_sym)
                ret_1m = _get_period_return(etf, 1)
                ret_3m = _get_period_return(etf, 3)
                ret_6m = _get_period_return(etf, 6)
                sector_returns[etf_sym] = {
                    "return_1m": round(ret_1m, 2) if ret_1m is not None else None,
                    "return_3m": round(ret_3m, 2) if ret_3m is not None else None,
                    "return_6m": round(ret_6m, 2) if ret_6m is not None else None,
                    "vs_spy_1m": round(ret_1m - spy_1m, 2) if (ret_1m is not None and spy_1m is not None) else None,
                    "vs_spy_3m": round(ret_3m - spy_3m, 2) if (ret_3m is not None and spy_3m is not None) else None,
                    "vs_spy_6m": round(ret_6m - spy_6m, 2) if (ret_6m is not None and spy_6m is not None) else None,
                }
            except Exception:
                sector_returns[etf_sym] = {
                    "return_1m": None, "return_3m": None, "return_6m": None,
                    "vs_spy_1m": None, "vs_spy_3m": None, "vs_spy_6m": None,
                }

        # Rank sectors by 1M relative strength
        ranked = sorted(
            [(sym, data) for sym, data in sector_returns.items() if data["vs_spy_1m"] is not None],
            key=lambda x: x[1]["vs_spy_1m"],
            reverse=True,
        )
        rank_map = {sym: i + 1 for i, (sym, _) in enumerate(ranked)}

        # Stock's sector data
        stock_sector_data = {}
        stock_sector_rank = None
        if sector_etf and sector_etf in sector_returns:
            stock_sector_data = sector_returns[sector_etf]
            stock_sector_rank = rank_map.get(sector_etf)

        result = {
            "ticker": ticker.upper(),
            "sector": sector,
            "sector_etf": sector_etf,
            "stock_sector_vs_spy_1m": stock_sector_data.get("vs_spy_1m"),
            "stock_sector_vs_spy_3m": stock_sector_data.get("vs_spy_3m"),
            "stock_sector_vs_spy_6m": stock_sector_data.get("vs_spy_6m"),
            "stock_sector_rank": stock_sector_rank,
            "total_sectors": len(ranked),
            "spy_1m_return": round(spy_1m, 2) if spy_1m is not None else None,
            "spy_3m_return": round(spy_3m, 2) if spy_3m is not None else None,
            "spy_6m_return": round(spy_6m, 2) if spy_6m is not None else None,
            "all_sector_returns": sector_returns,
            "sector_rankings_1m": [{"etf": sym, "vs_spy_1m": data["vs_spy_1m"]} for sym, data in ranked],
        }

        return json.dumps(result, default=str)

    except Exception as e:
        return json.dumps({"error": f"Error fetching sector rotation data for {ticker}: {str(e)}"})


@tool
def get_institutional_flow(
    ticker: Annotated[str, "Ticker symbol of the company"],
) -> str:
    """Fetch institutional flow data: volume ratios, float turnover, short interest, institutional ownership.
    Returns structured text for the Sector Rotation and Institutional Flow Analyst.
    """
    import yfinance as yf

    try:
        t = yf.Ticker(ticker.upper())
        info = t.info

        avg_vol = _safe_get(info, "averageVolume")
        avg_vol_10d = _safe_get(info, "averageVolume10days")
        shares_outstanding = _safe_get(info, "sharesOutstanding")
        float_shares = _safe_get(info, "floatShares")
        shares_short = _safe_get(info, "sharesShort")
        short_ratio = _safe_get(info, "shortRatio")
        held_institutions = _safe_get(info, "heldPercentInstitutions")
        held_insiders = _safe_get(info, "heldPercentInsiders")

        # Compute derived metrics
        volume_ratio = None
        if avg_vol and avg_vol_10d and avg_vol > 0:
            volume_ratio = round(avg_vol_10d / avg_vol, 2)

        float_turnover_5d = None
        float_turnover_20d = None
        if float_shares and float_shares > 0:
            if avg_vol_10d:
                float_turnover_5d = round((avg_vol_10d * 5) / float_shares * 100, 2)
            if avg_vol:
                float_turnover_20d = round((avg_vol * 20) / float_shares * 100, 2)

        short_pct_of_float = None
        if shares_short and float_shares and float_shares > 0:
            short_pct_of_float = round(shares_short / float_shares * 100, 2)

        result = {
            "ticker": ticker.upper(),
            "average_volume": avg_vol,
            "average_volume_10d": avg_vol_10d,
            "volume_ratio": volume_ratio,
            "shares_outstanding": shares_outstanding,
            "float_shares": float_shares,
            "shares_short": shares_short,
            "short_ratio": short_ratio,
            "short_pct_of_float": short_pct_of_float,
            "float_turnover_5d_pct": float_turnover_5d,
            "float_turnover_20d_pct": float_turnover_20d,
            "held_percent_institutions": round(held_institutions * 100, 2) if held_institutions else None,
            "held_percent_insiders": round(held_insiders * 100, 2) if held_insiders else None,
        }

        return json.dumps(result, default=str)

    except Exception as e:
        return json.dumps({"error": f"Error fetching institutional flow data for {ticker}: {str(e)}"})


@tool
def get_earnings_estimates(
    ticker: Annotated[str, "Ticker symbol of the company"],
) -> str:
    """Fetch earnings revision data: analyst recommendations, price targets, EPS estimates.
    Returns structured text for the Earnings Revision and News Catalyst Analyst.
    """
    import yfinance as yf

    try:
        t = yf.Ticker(ticker.upper())
        info = t.info

        result = {
            "ticker": ticker.upper(),
            "current_price": _safe_get(info, "currentPrice") or _safe_get(info, "regularMarketPrice"),
            "trailing_eps": _safe_get(info, "trailingEps"),
            "forward_eps": _safe_get(info, "forwardEps"),
        }

        # Analyst recommendations
        try:
            recs = t.recommendations
            if recs is not None and not recs.empty:
                # Get the most recent recommendations
                recent_recs = recs.tail(20)
                rec_list = []
                for _, row in recent_recs.iterrows():
                    rec_entry = {}
                    for col in recent_recs.columns:
                        val = row[col]
                        if hasattr(val, 'item'):
                            val = val.item()
                        rec_entry[col] = val
                    rec_list.append(rec_entry)
                result["recent_recommendations"] = rec_list
            else:
                result["recent_recommendations"] = []
        except Exception:
            result["recent_recommendations"] = []

        # Analyst price targets
        try:
            targets = t.analyst_price_targets
            if targets is not None:
                target_dict = {}
                if hasattr(targets, 'items'):
                    for k, v in targets.items():
                        if hasattr(v, 'item'):
                            target_dict[k] = v.item()
                        else:
                            target_dict[k] = v
                elif isinstance(targets, dict):
                    target_dict = targets
                result["price_targets"] = target_dict

                # Calculate upside
                current = result.get("current_price")
                mean_target = target_dict.get("mean") or target_dict.get("current")
                if current and mean_target and current > 0:
                    result["price_target_upside_pct"] = round(((mean_target / current) - 1) * 100, 2)
            else:
                result["price_targets"] = {}
        except Exception:
            result["price_targets"] = {}

        # Earnings estimates if available
        try:
            earnings_est = t.earnings_estimate
            if earnings_est is not None and not earnings_est.empty:
                est_dict = {}
                for col in earnings_est.columns:
                    est_dict[str(col)] = {}
                    for idx in earnings_est.index:
                        val = earnings_est.loc[idx, col]
                        if hasattr(val, 'item'):
                            val = val.item()
                        est_dict[str(col)][str(idx)] = val
                result["earnings_estimates"] = est_dict
            else:
                result["earnings_estimates"] = {}
        except Exception:
            result["earnings_estimates"] = {}

        # Revenue estimates if available
        try:
            rev_est = t.revenue_estimate
            if rev_est is not None and not rev_est.empty:
                rev_dict = {}
                for col in rev_est.columns:
                    rev_dict[str(col)] = {}
                    for idx in rev_est.index:
                        val = rev_est.loc[idx, col]
                        if hasattr(val, 'item'):
                            val = val.item()
                        rev_dict[str(col)][str(idx)] = val
                result["revenue_estimates"] = rev_dict
            else:
                result["revenue_estimates"] = {}
        except Exception:
            result["revenue_estimates"] = {}

        return json.dumps(result, default=str)

    except Exception as e:
        return json.dumps({"error": f"Error fetching earnings estimates for {ticker}: {str(e)}"})


@tool
def get_valuation_peers(
    ticker: Annotated[str, "Ticker symbol of the company"],
) -> str:
    """Fetch valuation metrics and peer comparison data.
    Returns structured text for the Business Quality, Valuation, and Entry Timing Analyst.
    """
    import yfinance as yf

    try:
        t = yf.Ticker(ticker.upper())
        info = t.info

        current_price = _safe_get(info, "currentPrice") or _safe_get(info, "regularMarketPrice")
        fifty_two_high = _safe_get(info, "fiftyTwoWeekHigh")
        fifty_two_low = _safe_get(info, "fiftyTwoWeekLow")

        # Calculate position in 52-week range
        vs_52w_range_pct = None
        if fifty_two_high and fifty_two_low and current_price and (fifty_two_high - fifty_two_low) > 0:
            vs_52w_range_pct = round(
                ((current_price - fifty_two_low) / (fifty_two_high - fifty_two_low)) * 100, 1
            )

        result = {
            "ticker": ticker.upper(),
            "current_price": current_price,
            "trailing_pe": _safe_get(info, "trailingPE"),
            "forward_pe": _safe_get(info, "forwardPE"),
            "peg_ratio": _safe_get(info, "pegRatio"),
            "price_to_book": _safe_get(info, "priceToBook"),
            "price_to_sales": _safe_get(info, "priceToSalesTrailing12Months"),
            "enterprise_value": _safe_get(info, "enterpriseValue"),
            "ev_to_ebitda": _safe_get(info, "enterpriseToEbitda"),
            "ev_to_revenue": _safe_get(info, "enterpriseToRevenue"),
            "market_cap": _safe_get(info, "marketCap"),
            "fifty_two_week_high": fifty_two_high,
            "fifty_two_week_low": fifty_two_low,
            "vs_52w_range_pct": vs_52w_range_pct,
            "fifty_day_average": _safe_get(info, "fiftyDayAverage"),
            "two_hundred_day_average": _safe_get(info, "twoHundredDayAverage"),
            "profit_margins": _safe_get(info, "profitMargins"),
            "operating_margins": _safe_get(info, "operatingMargins"),
            "gross_margins": _safe_get(info, "grossMargins"),
            "return_on_equity": _safe_get(info, "returnOnEquity"),
            "return_on_assets": _safe_get(info, "returnOnAssets"),
            "revenue_growth": _safe_get(info, "revenueGrowth"),
            "earnings_growth": _safe_get(info, "earningsGrowth"),
            "debt_to_equity": _safe_get(info, "debtToEquity"),
            "current_ratio": _safe_get(info, "currentRatio"),
            "free_cashflow": _safe_get(info, "freeCashflow"),
            "book_value": _safe_get(info, "bookValue"),
        }

        return json.dumps(result, default=str)

    except Exception as e:
        return json.dumps({"error": f"Error fetching valuation data for {ticker}: {str(e)}"})
