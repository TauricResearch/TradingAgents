import logging
import os

import numpy as np
import pandas as pd

from tradingagents.config import get_settings

logger = logging.getLogger(__name__)


def calculate_volume_ratio(current_volume: float, avg_volume_20d: float) -> float:
    if avg_volume_20d == 0:
        return 0.0
    return current_volume / avg_volume_20d


def calculate_volume_trend(volume_series: list[float]) -> tuple[str, float]:
    if len(volume_series) < 2:
        return ("flat", 0.0)

    x = np.arange(len(volume_series))
    y = np.array(volume_series)

    coeffs = np.polyfit(x, y, 1)
    slope = coeffs[0]

    avg_volume = np.mean(y)
    if avg_volume == 0:
        return ("flat", 0.0)

    normalized_slope = slope / avg_volume

    if normalized_slope > 0.02:
        return ("increasing", float(slope))
    elif normalized_slope < -0.02:
        return ("decreasing", float(slope))
    else:
        return ("flat", float(slope))


def calculate_dollar_volume(price: float, volume: float) -> float:
    return price * volume


def calculate_volume_score(
    volume_ratio: float,
    trend: str,
    dollar_volume: float,
    price_change: float,
    min_dollar_volume: float,
) -> float:
    score = 0.5

    if volume_ratio >= 2.0:
        if price_change > 0:
            score += 0.35
        else:
            score += 0.15
    elif volume_ratio >= 1.5:
        if price_change > 0:
            score += 0.25
        else:
            score += 0.10
    elif volume_ratio >= 1.0:
        score += 0.05
    else:
        score -= 0.1

    if trend == "increasing":
        score += 0.1
    elif trend == "decreasing":
        score -= 0.05

    if dollar_volume < min_dollar_volume:
        liquidity_penalty = min(
            0.3, (min_dollar_volume - dollar_volume) / min_dollar_volume * 0.3
        )
        score -= liquidity_penalty

    return max(0.0, min(1.0, score))


def _get_volume_price_data(ticker: str, curr_date: str) -> dict:
    from tradingagents.dataflows.config import get_config

    config = get_config()
    online = config["data_vendors"]["technical_indicators"] != "local"

    result = {
        "volumes": [],
        "prices": [],
        "current_price": None,
        "current_volume": None,
        "price_change_pct": 0.0,
    }

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
        data = data[data["Date"] <= curr_date].tail(30)

        if len(data) > 0:
            volumes = data["Volume"].tolist()
            prices = data["Close"].tolist()

            result["volumes"] = volumes[:-1] if len(volumes) > 1 else volumes
            result["prices"] = prices[:-1] if len(prices) > 1 else prices
            result["current_volume"] = volumes[-1] if volumes else None
            result["current_price"] = prices[-1] if prices else None

            if len(prices) >= 2:
                result["price_change_pct"] = (
                    (prices[-1] - prices[-2]) / prices[-2] * 100
                    if prices[-2] != 0
                    else 0
                )

    except (FileNotFoundError, KeyError, ValueError) as e:
        logger.warning("Failed to get volume/price data for %s: %s", ticker, str(e))

    return result


def calculate_volume_metrics(ticker: str, curr_date: str) -> dict:
    result = {
        "volume_ratio": None,
        "volume_trend": None,
        "volume_trend_slope": None,
        "dollar_volume": None,
        "volume_score": 0.5,
    }

    try:
        settings = get_settings()
        min_dollar_volume = settings.min_dollar_volume

        data = _get_volume_price_data(ticker, curr_date)

        volumes = data["volumes"]
        current_volume = data["current_volume"]
        current_price = data["current_price"]
        price_change = data["price_change_pct"]

        if not volumes or current_volume is None or current_price is None:
            return result

        avg_volume_20d = (
            sum(volumes[-20:]) / min(len(volumes[-20:]), 20) if volumes else 0
        )

        volume_ratio = calculate_volume_ratio(current_volume, avg_volume_20d)
        result["volume_ratio"] = volume_ratio

        trend_volumes = (
            volumes[-10:] + [current_volume] if volumes else [current_volume]
        )
        trend, slope = calculate_volume_trend(trend_volumes)
        result["volume_trend"] = trend
        result["volume_trend_slope"] = slope

        dollar_volume = calculate_dollar_volume(current_price, current_volume)
        result["dollar_volume"] = dollar_volume

        result["volume_score"] = calculate_volume_score(
            volume_ratio=volume_ratio,
            trend=trend,
            dollar_volume=dollar_volume,
            price_change=price_change,
            min_dollar_volume=min_dollar_volume,
        )

    except (KeyError, ValueError, RuntimeError) as e:
        logger.warning("Failed to calculate volume metrics for %s: %s", ticker, str(e))

    return result
