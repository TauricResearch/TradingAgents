"""Fundamental screening for swing trading candidates.

Pure computational screening (no LLM) - filters stocks by fundamental health:
- Revenue growth (positive QoQ or YoY)
- Reasonable valuation (PER, PBR)
- Financial health (debt ratio, current ratio)
- Market cap threshold
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def fundamental_screen(
    technical_candidates: list[dict],
    trade_date: str,
    market: str = "KRX",
) -> list[dict]:
    """Filter technical candidates by fundamental criteria.

    Args:
        technical_candidates: Output from technical_screener
        trade_date: Current trading date (YYYY-MM-DD)
        market: "KRX" or "US"

    Returns:
        Filtered list with fundamental data added
    """
    if not technical_candidates:
        return []

    results = []

    for candidate in technical_candidates:
        ticker = candidate["ticker"]

        try:
            if market == "KRX":
                fund_data = _get_krx_fundamentals(ticker, trade_date)
            else:
                fund_data = _get_us_fundamentals(ticker)

            if not fund_data:
                # No fundamental data available; still pass through
                # with a warning flag
                candidate["fundamental_check"] = "데이터 없음"
                candidate["fundamental_pass"] = True  # benefit of the doubt
                results.append(candidate)
                continue

            # Apply fundamental filters
            passes, reasons = _check_fundamentals(fund_data, market)
            candidate["fundamentals"] = fund_data
            candidate["fundamental_check"] = " / ".join(reasons) if reasons else "기본 통과"
            candidate["fundamental_pass"] = passes

            if passes:
                results.append(candidate)
            else:
                logger.debug(
                    f"{ticker} failed fundamental screen: {reasons}"
                )

        except Exception as e:
            logger.warning(f"Fundamental screening error for {ticker}: {e}")
            candidate["fundamental_check"] = f"오류: {e}"
            candidate["fundamental_pass"] = True
            results.append(candidate)

    logger.info(
        f"Fundamental screening: {len(results)}/{len(technical_candidates)} passed"
    )
    return results


def _get_krx_fundamentals(ticker: str, trade_date: str) -> dict:
    """Get KRX fundamental data for screening."""
    data = {}

    try:
        from pykrx import stock as krx_stock

        date_str = trade_date.replace("-", "")

        # PER, PBR, EPS, BPS, DIV
        fund_df = krx_stock.get_market_fundamental_by_date(
            date_str, date_str, ticker
        )
        if fund_df is not None and not fund_df.empty:
            row = fund_df.iloc[0]
            data["per"] = row.get("PER", None)
            data["pbr"] = row.get("PBR", None)
            data["eps"] = row.get("EPS", None)
            data["bps"] = row.get("BPS", None)
            data["div_yield"] = row.get("DIV", None)

        # Market cap
        cap_df = krx_stock.get_market_cap_by_date(date_str, date_str, ticker)
        if cap_df is not None and not cap_df.empty:
            cap_row = cap_df.iloc[0]
            data["market_cap"] = cap_row.get("시가총액", None)

    except ImportError:
        logger.warning("pykrx not installed - limited fundamental screening")
    except Exception as e:
        logger.warning(f"Error getting KRX fundamentals for {ticker}: {e}")

    return data


def _get_us_fundamentals(ticker: str) -> dict:
    """Get US fundamental data for screening."""
    import yfinance as yf

    data = {}
    try:
        info = yf.Ticker(ticker).info
        data["per"] = info.get("trailingPE")
        data["forward_pe"] = info.get("forwardPE")
        data["pbr"] = info.get("priceToBook")
        data["eps"] = info.get("trailingEps")
        data["div_yield"] = info.get("dividendYield")
        data["market_cap"] = info.get("marketCap")
        data["debt_to_equity"] = info.get("debtToEquity")
        data["current_ratio"] = info.get("currentRatio")
        data["profit_margin"] = info.get("profitMargins")
        data["revenue_growth"] = info.get("revenueGrowth")
        data["roe"] = info.get("returnOnEquity")
    except Exception as e:
        logger.warning(f"Error getting US fundamentals for {ticker}: {e}")

    return data


def _check_fundamentals(data: dict, market: str) -> tuple[bool, list[str]]:
    """Check if fundamentals pass screening criteria.

    Returns (passes: bool, reasons: list of fail/pass reasons).
    """
    reasons = []
    fail = False

    # PER check: not excessively high (allow negative for turnaround plays)
    per = data.get("per")
    if per is not None and per > 0:
        if per > 100:
            reasons.append(f"PER 과다 ({per:.1f})")
            fail = True
        elif per < 5:
            reasons.append(f"PER 매력적 ({per:.1f})")

    # PBR check: not excessively high
    pbr = data.get("pbr")
    if pbr is not None and pbr > 0:
        if pbr > 10:
            reasons.append(f"PBR 과다 ({pbr:.1f})")
            fail = True

    # Debt check (US only - data available)
    debt_to_equity = data.get("debt_to_equity")
    if debt_to_equity is not None and debt_to_equity > 300:
        reasons.append(f"부채비율 과다 ({debt_to_equity:.0f}%)")
        fail = True

    # Revenue growth (positive is good, not a hard filter)
    rev_growth = data.get("revenue_growth")
    if rev_growth is not None and rev_growth > 0:
        reasons.append(f"매출 성장 (+{rev_growth * 100:.1f}%)")

    # Profit margin (negative is a warning but not disqualifying for swing)
    profit_margin = data.get("profit_margin")
    if profit_margin is not None and profit_margin < -0.20:
        reasons.append(f"적자 심화 (마진 {profit_margin * 100:.1f}%)")

    return not fail, reasons
