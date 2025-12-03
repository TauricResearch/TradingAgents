import logging
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)


def calculate_rsi_score(rsi: float) -> float:
    if rsi <= 20:
        return 1.0
    elif rsi <= 30:
        return 0.8 + (30 - rsi) / 50
    elif rsi <= 35:
        return 0.7 + (35 - rsi) / 50
    elif rsi <= 50:
        return 0.6 + (50 - rsi) / 150
    elif rsi <= 65:
        return 0.5 + (65 - rsi) / 150
    elif rsi <= 70:
        return 0.4 + (70 - rsi) / 50
    elif rsi <= 80:
        return 0.2 + (80 - rsi) / 50
    else:
        return max(0.0, 0.2 - (rsi - 80) / 100)


def calculate_macd_score(macd: float, signal: float, histogram: float) -> float:
    score = 0.5

    if macd > signal:
        crossover_strength = min((macd - signal) / max(abs(signal), 0.01), 1.0)
        score += 0.25 * crossover_strength
    else:
        crossover_weakness = min((signal - macd) / max(abs(signal), 0.01), 1.0)
        score -= 0.25 * crossover_weakness

    if histogram > 0:
        histogram_bonus = min(histogram / max(abs(macd), 0.01), 1.0) * 0.25
        score += histogram_bonus
    else:
        histogram_penalty = min(abs(histogram) / max(abs(macd), 0.01), 1.0) * 0.25
        score -= histogram_penalty

    return max(0.0, min(1.0, score))


def calculate_sma_score(price: float, sma50: float, sma200: float) -> float:
    if sma50 == 0 or sma200 == 0:
        return 0.5

    score = 0.5

    pct_vs_sma50 = (price - sma50) / sma50
    pct_vs_sma200 = (price - sma200) / sma200

    if pct_vs_sma50 > 0:
        score += min(pct_vs_sma50 * 2, 0.25)
    else:
        score += max(pct_vs_sma50 * 2, -0.25)

    if pct_vs_sma200 > 0:
        score += min(pct_vs_sma200 * 2, 0.25)
    else:
        score += max(pct_vs_sma200 * 2, -0.25)

    if price > sma50 > sma200:
        score += 0.15

    return max(0.0, min(1.0, score))


def calculate_ema_direction(ema_values: list[float]) -> str:
    if len(ema_values) < 2:
        return "flat"

    first_half = ema_values[: len(ema_values) // 2]
    second_half = ema_values[len(ema_values) // 2 :]

    if not first_half or not second_half:
        return "flat"

    first_avg = sum(first_half) / len(first_half)
    second_avg = sum(second_half) / len(second_half)

    pct_change = (second_avg - first_avg) / first_avg if first_avg != 0 else 0

    if pct_change > 0.01:
        return "up"
    elif pct_change < -0.01:
        return "down"
    else:
        return "flat"


def _get_stock_stats_bulk(symbol: str, indicator: str, curr_date: str) -> dict:
    import os

    from stockstats import wrap

    from tradingagents.dataflows.config import get_config

    config = get_config()
    online = config["data_vendors"]["technical_indicators"] != "local"

    if not online:
        try:
            data = pd.read_csv(
                os.path.join(
                    config.get("data_cache_dir", "data"),
                    f"{symbol}-YFin-data-2015-01-01-2025-03-25.csv",
                )
            )
            df = wrap(data)
        except FileNotFoundError:
            raise Exception("Stockstats fail: Yahoo Finance data not fetched yet!")
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
            f"{symbol}-YFin-data-{start_date_str}-{end_date_str}.csv",
        )

        if os.path.exists(data_file):
            data = pd.read_csv(data_file)
            data["Date"] = pd.to_datetime(data["Date"])
        else:
            data = yf.download(
                symbol,
                start=start_date_str,
                end=end_date_str,
                multi_level_index=False,
                progress=False,
                auto_adjust=True,
            )
            data = data.reset_index()
            data.to_csv(data_file, index=False)

        df = wrap(data)
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

    df[indicator]

    indicator_series = df[indicator].apply(lambda x: "N/A" if pd.isna(x) else str(x))
    result_dict = dict(zip(df["Date"], indicator_series, strict=False))

    return result_dict


def _get_price_data(symbol: str, curr_date: str) -> dict:
    import os

    from tradingagents.dataflows.config import get_config

    config = get_config()
    online = config["data_vendors"]["technical_indicators"] != "local"

    if not online:
        try:
            data = pd.read_csv(
                os.path.join(
                    config.get("data_cache_dir", "data"),
                    f"{symbol}-YFin-data-2015-01-01-2025-03-25.csv",
                )
            )
        except FileNotFoundError:
            return {}
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
            f"{symbol}-YFin-data-{start_date_str}-{end_date_str}.csv",
        )

        if os.path.exists(data_file):
            data = pd.read_csv(data_file)
        else:
            data = yf.download(
                symbol,
                start=start_date_str,
                end=end_date_str,
                multi_level_index=False,
                progress=False,
                auto_adjust=True,
            )
            data = data.reset_index()
            data.to_csv(data_file, index=False)

    data["Date"] = pd.to_datetime(data["Date"]).dt.strftime("%Y-%m-%d")
    result_dict = {}
    for _, row in data.iterrows():
        result_dict[row["Date"]] = row["Close"]

    return result_dict


def calculate_momentum_score(ticker: str, curr_date: str) -> dict:
    result = {
        "rsi": None,
        "macd": None,
        "macd_signal": None,
        "macd_histogram": None,
        "price_vs_sma50": None,
        "price_vs_sma200": None,
        "ema10_direction": None,
        "momentum_score": 0.5,
    }

    try:
        rsi_data = _get_stock_stats_bulk(ticker, "rsi", curr_date)
        macd_data = _get_stock_stats_bulk(ticker, "macd", curr_date)
        macds_data = _get_stock_stats_bulk(ticker, "macds", curr_date)
        macdh_data = _get_stock_stats_bulk(ticker, "macdh", curr_date)
        sma50_data = _get_stock_stats_bulk(ticker, "close_50_sma", curr_date)
        sma200_data = _get_stock_stats_bulk(ticker, "close_200_sma", curr_date)
        ema10_data = _get_stock_stats_bulk(ticker, "close_10_ema", curr_date)
        price_data = _get_price_data(ticker, curr_date)

        rsi_value = None
        if curr_date in rsi_data and rsi_data[curr_date] != "N/A":
            try:
                rsi_value = float(rsi_data[curr_date])
                result["rsi"] = rsi_value
            except (ValueError, TypeError):
                pass

        macd_value = None
        macds_value = None
        macdh_value = None

        if curr_date in macd_data and macd_data[curr_date] != "N/A":
            try:
                macd_value = float(macd_data[curr_date])
                result["macd"] = macd_value
            except (ValueError, TypeError):
                pass

        if curr_date in macds_data and macds_data[curr_date] != "N/A":
            try:
                macds_value = float(macds_data[curr_date])
                result["macd_signal"] = macds_value
            except (ValueError, TypeError):
                pass

        if curr_date in macdh_data and macdh_data[curr_date] != "N/A":
            try:
                macdh_value = float(macdh_data[curr_date])
                result["macd_histogram"] = macdh_value
            except (ValueError, TypeError):
                pass

        current_price = None
        sma50_value = None
        sma200_value = None

        if curr_date in price_data:
            try:
                current_price = float(price_data[curr_date])
            except (ValueError, TypeError):
                pass

        if curr_date in sma50_data and sma50_data[curr_date] != "N/A":
            try:
                sma50_value = float(sma50_data[curr_date])
            except (ValueError, TypeError):
                pass

        if curr_date in sma200_data and sma200_data[curr_date] != "N/A":
            try:
                sma200_value = float(sma200_data[curr_date])
            except (ValueError, TypeError):
                pass

        if current_price and sma50_value:
            result["price_vs_sma50"] = (
                (current_price - sma50_value) / sma50_value
            ) * 100

        if current_price and sma200_value:
            result["price_vs_sma200"] = (
                (current_price - sma200_value) / sma200_value
            ) * 100

        ema_values = []
        sorted_dates = sorted(
            [d for d in ema10_data.keys() if d <= curr_date], reverse=True
        )[:10]
        for date in sorted_dates:
            if ema10_data[date] != "N/A":
                try:
                    ema_values.append(float(ema10_data[date]))
                except (ValueError, TypeError):
                    pass

        if ema_values:
            result["ema10_direction"] = calculate_ema_direction(ema_values[::-1])

        scores = []
        weights = []

        if rsi_value is not None:
            scores.append(calculate_rsi_score(rsi_value))
            weights.append(0.25)

        if (
            macd_value is not None
            and macds_value is not None
            and macdh_value is not None
        ):
            scores.append(calculate_macd_score(macd_value, macds_value, macdh_value))
            weights.append(0.35)

        if current_price and sma50_value and sma200_value:
            scores.append(calculate_sma_score(current_price, sma50_value, sma200_value))
            weights.append(0.40)

        if scores and weights:
            total_weight = sum(weights)
            result["momentum_score"] = (
                sum(s * w for s, w in zip(scores, weights, strict=False)) / total_weight
            )
        else:
            result["momentum_score"] = 0.5

    except (KeyError, ValueError, FileNotFoundError, RuntimeError) as e:
        logger.warning("Failed to calculate momentum score for %s: %s", ticker, str(e))
        result["momentum_score"] = 0.5

    return result
