import logging
import os

import pandas as pd

from tradingagents.dataflows.trending.sector_classifier import classify_sector

logger = logging.getLogger(__name__)

SECTOR_ETF_MAP = {
    "technology": "XLK",
    "finance": "XLF",
    "healthcare": "XLV",
    "energy": "XLE",
    "consumer_goods": "XLY",
    "industrials": "XLI",
    "other": "SPY",
}


def calculate_return(prices: list[float], days: int) -> float:
    if len(prices) < 2:
        return 0.0

    start_idx = max(0, len(prices) - days)
    start_price = prices[start_idx]
    end_price = prices[-1]

    if start_price == 0:
        return 0.0

    return ((end_price - start_price) / start_price) * 100


def calculate_relative_strength(stock_return: float, benchmark_return: float) -> float:
    return stock_return - benchmark_return


def get_sector_etf(ticker: str) -> str:
    sector = classify_sector(ticker)
    return SECTOR_ETF_MAP.get(sector, "SPY")


def _get_price_history(ticker: str, curr_date: str, days: int) -> list[float]:
    from tradingagents.dataflows.config import get_config

    config = get_config()
    online = config["data_vendors"]["technical_indicators"] != "local"

    try:
        if not online:
            data = pd.read_csv(
                os.path.join(
                    config.get("data_cache_dir", "data"),
                    f"{ticker}-YFin-data-2015-01-01-2025-03-25.csv",
                )
            )
        else:
            import yfinance as yf

            today_date = pd.Timestamp.today()

            end_date = today_date
            start_date = today_date - pd.DateOffset(years=15)
            start_date_str = start_date.strftime("%Y-%m-%d")
            end_date_str = end_date.strftime("%Y-%m-%d")

            os.makedirs(config["data_cache_dir"], exist_ok=True)

            data_file = os.path.join(
                config["data_cache_dir"],
                f"{ticker}-YFin-data-{start_date_str}-{end_date_str}.csv",
            )

            if os.path.exists(data_file):
                data = pd.read_csv(data_file)
            else:
                data = yf.download(
                    ticker,
                    start=start_date_str,
                    end=end_date_str,
                    multi_level_index=False,
                    progress=False,
                    auto_adjust=True,
                )
                data = data.reset_index()
                data.to_csv(data_file, index=False)

        data["Date"] = pd.to_datetime(data["Date"]).dt.strftime("%Y-%m-%d")
        data = data[data["Date"] <= curr_date].tail(days + 5)

        return data["Close"].tolist()

    except (FileNotFoundError, KeyError, ValueError) as e:
        logger.warning("Failed to get price history for %s: %s", ticker, str(e))
        return []


def _calculate_rs_score(
    rs_5d: float, rs_20d: float, rs_60d: float, rs_sector: float
) -> float:
    score = 0.5

    if rs_20d > 5:
        score += min(rs_20d / 20, 0.25)
    elif rs_20d < -5:
        score -= min(abs(rs_20d) / 20, 0.25)

    if rs_5d > 3:
        score += min(rs_5d / 15, 0.15)
    elif rs_5d < -3:
        score -= min(abs(rs_5d) / 15, 0.15)

    if rs_60d > 10:
        score += min(rs_60d / 40, 0.1)
    elif rs_60d < -10:
        score -= min(abs(rs_60d) / 40, 0.1)

    if rs_sector > 3:
        score += min(rs_sector / 15, 0.1)
    elif rs_sector < -3:
        score -= min(abs(rs_sector) / 15, 0.1)

    return max(0.0, min(1.0, score))


def calculate_relative_strength_metrics(ticker: str, curr_date: str) -> dict:
    result = {
        "rs_vs_spy_5d": None,
        "rs_vs_spy_20d": None,
        "rs_vs_spy_60d": None,
        "rs_vs_sector": None,
        "sector_etf": None,
        "relative_strength_score": 0.5,
    }

    try:
        stock_prices = _get_price_history(ticker, curr_date, 70)
        spy_prices = _get_price_history("SPY", curr_date, 70)

        if not stock_prices or not spy_prices:
            return result

        sector_etf = get_sector_etf(ticker)
        result["sector_etf"] = sector_etf

        sector_prices = []
        if sector_etf != "SPY":
            sector_prices = _get_price_history(sector_etf, curr_date, 70)

        stock_5d = calculate_return(stock_prices, 5)
        stock_20d = calculate_return(stock_prices, 20)
        stock_60d = calculate_return(stock_prices, 60)

        spy_5d = calculate_return(spy_prices, 5)
        spy_20d = calculate_return(spy_prices, 20)
        spy_60d = calculate_return(spy_prices, 60)

        result["rs_vs_spy_5d"] = calculate_relative_strength(stock_5d, spy_5d)
        result["rs_vs_spy_20d"] = calculate_relative_strength(stock_20d, spy_20d)
        result["rs_vs_spy_60d"] = calculate_relative_strength(stock_60d, spy_60d)

        if sector_prices and sector_etf != "SPY":
            sector_20d = calculate_return(sector_prices, 20)
            result["rs_vs_sector"] = calculate_relative_strength(stock_20d, sector_20d)
        else:
            result["rs_vs_sector"] = result["rs_vs_spy_20d"]

        result["relative_strength_score"] = _calculate_rs_score(
            result["rs_vs_spy_5d"],
            result["rs_vs_spy_20d"],
            result["rs_vs_spy_60d"],
            result["rs_vs_sector"],
        )

    except (KeyError, ValueError, RuntimeError) as e:
        logger.warning(
            "Failed to calculate relative strength for %s: %s", ticker, str(e)
        )

    return result
