import pandas as pd
import yfinance as yf

from tradingagents.dataflows.y_finance import suppress_yfinance_warnings
from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)


def calculate_altman_z_score(ticker: str) -> float:
    """
    Calculate the Altman Z-Score for a manufacturing company.
    If the company is non-manufacturing/service, a modified Z-score is often used,
    but here we stick to the standard/modified approximation for simplicity.
    Formula: Z = 1.2(X1) + 1.4(X2) + 3.3(X3) + 0.6(X4) + 1.0(X5)
    X1 = Working Capital / Total Assets
    X2 = Retained Earnings / Total Assets
    X3 = EBIT / Total Assets
    X4 = Market Value of Equity / Total Liabilities
    X5 = Sales / Total Assets
    Returns: float (Z-score). Values < 1.81 indicate distress.
    """
    try:
        with suppress_yfinance_warnings():
            stock = yf.Ticker(ticker.upper())
            bs = stock.balance_sheet
            inc = stock.financials
            info = stock.info

        if bs.empty or inc.empty:
            return None

        # Get latest annual data
        latest_bs = bs.iloc[:, 0]
        latest_inc = inc.iloc[:, 0]

        total_assets = latest_bs.get("Total Assets")
        if not total_assets or total_assets == 0:
            return None

        total_liabilities = latest_bs.get(
            "Total Liabilities Net Minority Interest", latest_bs.get("Total Liabilities")
        )
        current_assets = latest_bs.get("Current Assets", 0)
        current_liabilities = latest_bs.get("Current Liabilities", 0)
        retained_earnings = latest_bs.get("Retained Earnings", 0)

        ebit = latest_inc.get("EBIT")
        if pd.isna(ebit):
            ebit = latest_inc.get("Operating Income", 0)

        sales = latest_inc.get("Total Revenue", 0)

        market_cap = info.get("marketCap", 0)

        # Handle NaNs
        total_liabilities = 0 if pd.isna(total_liabilities) else total_liabilities
        retained_earnings = 0 if pd.isna(retained_earnings) else retained_earnings

        working_capital = current_assets - current_liabilities

        x1 = working_capital / total_assets
        x2 = retained_earnings / total_assets
        x3 = ebit / total_assets
        x4 = market_cap / total_liabilities if total_liabilities > 0 else 0
        x5 = sales / total_assets

        z_score = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
        return round(z_score, 2)
    except Exception as e:
        logger.debug(f"Error calculating Altman Z-Score for {ticker}: {e}")
        return None


def calculate_piotroski_f_score(ticker: str) -> int:
    """
    Calculate the Piotroski F-Score (0-9).
    High score (7-9) indicates strong value/health.
    Low score (0-3) indicates poor financial health.
    """
    try:
        with suppress_yfinance_warnings():
            stock = yf.Ticker(ticker.upper())
            bs = stock.balance_sheet
            inc = stock.financials
            cf = stock.cashflow

        if (
            bs.empty
            or inc.empty
            or cf.empty
            or len(bs.columns) < 2
            or len(inc.columns) < 2
            or len(cf.columns) < 1
        ):
            return None

        latest_bs = bs.iloc[:, 0]
        prev_bs = bs.iloc[:, 1]

        latest_inc = inc.iloc[:, 0]
        prev_inc = inc.iloc[:, 1]

        latest_cf = cf.iloc[:, 0]

        total_assets = latest_bs.get("Total Assets")
        prev_total_assets = prev_bs.get("Total Assets")

        if not total_assets or not prev_total_assets or total_assets == 0 or prev_total_assets == 0:
            return None

        score = 0

        # Profitability
        # 1. ROA > 0
        net_income = latest_inc.get("Net Income", 0)
        roa = net_income / total_assets
        if roa > 0:
            score += 1

        # 2. Operating Cash Flow > 0
        cfo = latest_cf.get("Operating Cash Flow", 0)
        if pd.isna(cfo):
            cfo = latest_cf.get("Total Cash From Operating Activities", 0)
        if cfo > 0:
            score += 1

        # 3. Change in ROA > 0
        prev_net_income = prev_inc.get("Net Income", 0)
        prev_roa = prev_net_income / prev_total_assets
        if roa > prev_roa:
            score += 1

        # 4. CFO > Net Income
        if cfo > net_income:
            score += 1

        # Leverage, Liquidity
        # 5. Change in Leverage (Long-Term Debt / Assets) < 0
        ltd = latest_bs.get("Long Term Debt", 0)
        prev_ltd = prev_bs.get("Long Term Debt", 0)
        if (ltd / total_assets) < (prev_ltd / prev_total_assets):
            score += 1

        # 6. Change in Current Ratio > 0
        ca = latest_bs.get("Current Assets", 0)
        cl = latest_bs.get("Current Liabilities", 1)  # avoid div by zero
        prev_ca = prev_bs.get("Current Assets", 0)
        prev_cl = prev_bs.get("Current Liabilities", 1)
        cr = ca / cl
        prev_cr = prev_ca / prev_cl
        if cr > prev_cr:
            score += 1

        # 7. Change in Shares Outstanding < 0 (or constant)
        shares = latest_bs.get("Ordinary Shares Number", 0)
        prev_shares = prev_bs.get("Ordinary Shares Number", 0)
        if shares <= prev_shares:
            score += 1

        # Operating Efficiency
        # 8. Change in Gross Margin > 0
        gp = latest_inc.get("Gross Profit", 0)
        prev_gp = prev_inc.get("Gross Profit", 0)
        rev = latest_inc.get("Total Revenue", 1)
        prev_rev = prev_inc.get("Total Revenue", 1)
        if (gp / rev) > (prev_gp / prev_rev):
            score += 1

        # 9. Change in Asset Turnover > 0
        ato = rev / total_assets
        prev_ato = prev_rev / prev_total_assets
        if ato > prev_ato:
            score += 1

        return score
    except Exception as e:
        logger.debug(f"Error calculating Piotroski F-Score for {ticker}: {e}")
        return None
