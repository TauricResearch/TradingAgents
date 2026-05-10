import json
from datetime import datetime
from dateutil.relativedelta import relativedelta

from .twelve_data_common import _make_api_request, _calc_start_date

# Cache for multi-value indicators (MACD, BBands) to avoid redundant API calls
_indicator_cache = {}


def get_indicator(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int,
    interval: str = "1day",
    time_period: int = 14,
    series_type: str = "close",
) -> str:
    """Returns Twelve Data technical indicator values over a time window."""

    indicator_descriptions = {
        "close_50_sma": "50 SMA: A medium-term trend indicator. Usage: Identify trend direction and serve as dynamic support/resistance. Tips: It lags price; combine with faster indicators for timely signals.",
        "close_200_sma": "200 SMA: A long-term trend benchmark. Usage: Confirm overall market trend and identify golden/death cross setups. Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries.",
        "close_10_ema": "10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum and potential entry points. Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals.",
        "macd": "MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers and divergence as signals of trend changes. Tips: Confirm with other indicators in low-volatility or sideways markets.",
        "macds": "MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers with the MACD line to trigger trades. Tips: Should be part of a broader strategy to avoid false positives.",
        "macdh": "MACD Histogram: Shows the gap between the MACD line and its signal. Usage: Visualize momentum strength and spot divergence early. Tips: Can be volatile; complement with additional filters in fast-moving markets.",
        "rsi": "RSI: Measures momentum to flag overbought/oversold conditions. Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis.",
        "boll": "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. Usage: Acts as a dynamic benchmark for price movement. Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals.",
        "boll_ub": "Bollinger Upper Band: Typically 2 standard deviations above the middle line. Usage: Signals potential overbought conditions and breakout zones. Tips: Confirm signals with other tools; prices may ride the band in strong trends.",
        "boll_lb": "Bollinger Lower Band: Typically 2 standard deviations below the middle line. Usage: Indicates potential oversold conditions. Tips: Use additional analysis to avoid false reversal signals.",
        "atr": "ATR: Averages true range to measure volatility. Usage: Set stop-loss levels and adjust position sizes based on current market volatility. Tips: It's a reactive measure, so use it as part of a broader risk management strategy.",
        "vwma": "VWMA: A moving average weighted by volume. Usage: Confirm trends by integrating price action with volume data. Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses.",
        "mfi": "MFI: Money Flow Index. Usage: Identify overbought/oversold conditions using price and volume. Tips: Similar to RSI but incorporates volume; divergences are powerful signals.",
    }

    # Map internal indicator names to Twelve Data API parameters
    indicator_config = {
        "close_50_sma": {"type": "sma", "time_period": 50},
        "close_200_sma": {"type": "sma", "time_period": 200},
        "close_10_ema": {"type": "ema", "time_period": 10},
        "macd": {"type": "macd", "key": "macd"},
        "macds": {"type": "macd", "key": "macd_signal"},
        "macdh": {"type": "macd", "key": "macd_hist"},
        "rsi": {"type": "rsi", "time_period": 14},
        "boll": {"type": "bbands", "key": "mid"},
        "boll_ub": {"type": "bbands", "key": "upper"},
        "boll_lb": {"type": "bbands", "key": "lower"},
        "atr": {"type": "atr", "time_period": 14},
        "vwma": {"type": "vwma", "time_period": 20},
        "mfi": {"type": "mfi", "time_period": 14},
    }

    if indicator not in indicator_config:
        raise ValueError(
            f"Indicator {indicator} is not supported. Please choose from: {list(indicator_config.keys())}"
        )

    config = indicator_config[indicator]
    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_date_dt - relativedelta(days=look_back_days)

    try:
        api_type = config["type"]
        cache_key = f"{symbol}_{api_type}_{interval}"

        # Check cache for multi-value indicators
        if cache_key in _indicator_cache:
            data = _indicator_cache[cache_key]
        else:
            params = {
                "symbol": symbol,
                "interval": interval,
                "start_date": _calc_start_date(curr_date, look_back_days),
                "end_date": curr_date,
                "outputsize": look_back_days + 50,
            }
            if "time_period" in config:
                params["time_period"] = config["time_period"]

            data = _make_api_request(api_type, params)

            # Cache multi-value indicator responses
            if "key" in config:
                _indicator_cache[cache_key] = data

        # Extract values from response
        values = data.get("values", [])
        if not values:
            return f"Error: No data returned for {indicator}"

        # Determine which key to extract
        value_key = config.get("key")
        if value_key is None:
            # Single-value indicator: the response has a single value per timestamp
            # Find the value key (not 'datetime')
            if values:
                keys = [k for k in values[0].keys() if k != "datetime"]
                value_key = keys[0] if keys else None

        result_data = []
        for entry in values:
            dt_str = entry.get("datetime", "")
            try:
                dt = datetime.strptime(dt_str, "%Y-%m-%d")
            except ValueError:
                continue
            if start_dt <= dt <= curr_date_dt:
                val = entry.get(value_key, "") if value_key else ""
                if val:
                    result_data.append((dt, val))

        result_data.sort(key=lambda x: x[0])

        ind_string = ""
        for dt, val in result_data:
            ind_string += f"{dt.strftime('%Y-%m-%d')}: {val}\n"

        if not ind_string:
            ind_string = "No data available for the specified date range.\n"

        return (
            f"## {indicator.upper()} values from {start_dt.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
            + ind_string
            + "\n\n"
            + indicator_descriptions.get(indicator, "No description available.")
        )

    except Exception as e:
        print(f"Error getting Twelve Data indicator data for {indicator}: {e}")
        raise  # Re-raise to trigger fallback
