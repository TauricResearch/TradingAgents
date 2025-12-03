import logging
import os

import pandas as pd

from tradingagents.agents.discovery.indicators.risk_reward import (
    calculate_reward_target,
    calculate_risk_reward_ratio,
    calculate_risk_reward_score,
    calculate_stop_loss,
)

logger = logging.getLogger(__name__)


def find_support_levels(
    lows: list[float], lookback_20: int, lookback_50: int
) -> tuple[float, float]:
    if not lows:
        return (0.0, 0.0)

    support_20d = (
        min(lows[-lookback_20:])
        if len(lows) >= lookback_20
        else min(lows)
        if lows
        else 0.0
    )
    support_50d = (
        min(lows[-lookback_50:])
        if len(lows) >= lookback_50
        else min(lows)
        if lows
        else 0.0
    )

    return (support_20d, support_50d)


def find_resistance_levels(
    highs: list[float], lookback_20: int, lookback_50: int
) -> tuple[float, float]:
    if not highs:
        return (0.0, 0.0)

    resistance_20d = (
        max(highs[-lookback_20:])
        if len(highs) >= lookback_20
        else max(highs)
        if highs
        else 0.0
    )
    resistance_50d = (
        max(highs[-lookback_50:])
        if len(highs) >= lookback_50
        else max(highs)
        if highs
        else 0.0
    )

    return (resistance_20d, resistance_50d)


def detect_swing_points(
    prices: list[float], n_bars: int = 5
) -> tuple[list[float], list[float]]:
    if len(prices) < (2 * n_bars + 1):
        return ([], [])

    swing_lows = []
    swing_highs = []

    for i in range(n_bars, len(prices) - n_bars):
        is_swing_low = True
        is_swing_high = True

        current = prices[i]

        for j in range(1, n_bars + 1):
            if prices[i - j] <= current or prices[i + j] <= current:
                is_swing_low = False
            if prices[i - j] >= current or prices[i + j] >= current:
                is_swing_high = False

        if is_swing_low:
            swing_lows.append(current)
        if is_swing_high:
            swing_highs.append(current)

    return (swing_lows, swing_highs)


def get_nearest_levels(
    price: float, supports: list[float], resistances: list[float]
) -> tuple[float, float]:
    supports_below = [s for s in supports if s < price]
    resistances_above = [r for r in resistances if r > price]

    nearest_support = max(supports_below) if supports_below else 0.0
    nearest_resistance = min(resistances_above) if resistances_above else 0.0

    return (nearest_support, nearest_resistance)


def _get_ohlc_data(ticker: str, curr_date: str) -> dict:
    from tradingagents.dataflows.config import get_config

    config = get_config()
    online = config["data_vendors"]["technical_indicators"] != "local"

    result = {
        "highs": [],
        "lows": [],
        "closes": [],
        "current_price": None,
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
        data = data[data["Date"] <= curr_date].tail(60)

        if len(data) > 0:
            result["highs"] = data["High"].tolist()
            result["lows"] = data["Low"].tolist()
            result["closes"] = data["Close"].tolist()
            result["current_price"] = data["Close"].iloc[-1] if len(data) > 0 else None

    except (FileNotFoundError, KeyError, ValueError) as e:
        logger.warning("Failed to get OHLC data for %s: %s", ticker, str(e))

    return result


def _get_atr(ticker: str, curr_date: str) -> float | None:
    from tradingagents.agents.discovery.indicators.momentum import _get_stock_stats_bulk

    try:
        atr_data = _get_stock_stats_bulk(ticker, "atr", curr_date)
        if curr_date in atr_data and atr_data[curr_date] != "N/A":
            return float(atr_data[curr_date])
    except (KeyError, ValueError, FileNotFoundError) as e:
        logger.warning("Failed to get ATR for %s: %s", ticker, str(e))

    return None


def calculate_support_resistance_metrics(ticker: str, curr_date: str) -> dict:
    result = {
        "support_level": None,
        "resistance_level": None,
        "atr": None,
        "suggested_stop": None,
        "reward_target": None,
        "risk_reward_ratio": None,
        "risk_reward_score": 0.5,
    }

    try:
        ohlc = _get_ohlc_data(ticker, curr_date)
        atr = _get_atr(ticker, curr_date)

        highs = ohlc["highs"]
        lows = ohlc["lows"]
        closes = ohlc["closes"]
        current_price = ohlc["current_price"]

        if not highs or not lows or current_price is None:
            return result

        result["atr"] = atr

        support_20d, support_50d = find_support_levels(lows, 20, 50)
        resistance_20d, resistance_50d = find_resistance_levels(highs, 20, 50)

        swing_lows, swing_highs = detect_swing_points(closes, n_bars=5)

        all_supports = [s for s in [support_20d, support_50d] + swing_lows if s > 0]
        all_resistances = [
            r for r in [resistance_20d, resistance_50d] + swing_highs if r > 0
        ]

        nearest_support, nearest_resistance = get_nearest_levels(
            current_price, all_supports, all_resistances
        )

        result["support_level"] = (
            nearest_support if nearest_support > 0 else support_20d
        )
        result["resistance_level"] = (
            nearest_resistance if nearest_resistance > 0 else resistance_20d
        )

        if atr and atr > 0:
            result["suggested_stop"] = calculate_stop_loss(
                current_price, atr, multiplier=1.5
            )
        else:
            pct_to_support = (
                (current_price - result["support_level"]) / current_price
                if result["support_level"] > 0
                else 0.02
            )
            result["suggested_stop"] = current_price * (1 - max(pct_to_support, 0.02))

        result["reward_target"] = calculate_reward_target(
            current_price, result["resistance_level"]
        )

        if result["suggested_stop"] and result["reward_target"]:
            result["risk_reward_ratio"] = calculate_risk_reward_ratio(
                current_price, result["suggested_stop"], result["reward_target"]
            )
            result["risk_reward_score"] = calculate_risk_reward_score(
                result["risk_reward_ratio"]
            )

    except (KeyError, ValueError, RuntimeError) as e:
        logger.warning(
            "Failed to calculate support/resistance metrics for %s: %s", ticker, str(e)
        )

    return result
