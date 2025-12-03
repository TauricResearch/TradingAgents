import logging

logger = logging.getLogger(__name__)


def determine_signal_from_indicators(
    rsi: float | None,
    macd: float | None,
    macd_signal: float | None,
    price_vs_sma: float | None,
    ema_direction: str | None,
) -> str:
    bullish_signals = 0
    bearish_signals = 0
    total_signals = 0

    if rsi is not None:
        total_signals += 1
        if rsi < 40:
            bullish_signals += 1
        elif rsi > 60:
            bearish_signals += 1

    if macd is not None and macd_signal is not None:
        total_signals += 1
        if macd > macd_signal:
            bullish_signals += 1
        else:
            bearish_signals += 1

    if price_vs_sma is not None:
        total_signals += 1
        if price_vs_sma > 0:
            bullish_signals += 1
        elif price_vs_sma < 0:
            bearish_signals += 1

    if ema_direction is not None:
        total_signals += 1
        if ema_direction == "up":
            bullish_signals += 1
        elif ema_direction == "down":
            bearish_signals += 1

    if total_signals == 0:
        return "neutral"

    bullish_ratio = bullish_signals / total_signals
    bearish_ratio = bearish_signals / total_signals

    if bullish_ratio >= 0.6:
        return "bullish"
    elif bearish_ratio >= 0.6:
        return "bearish"
    else:
        return "neutral"


def calculate_timeframe_signals(
    momentum_data: dict,
    relative_strength_data: dict,
) -> dict:
    result = {
        "short_term_signal": "neutral",
        "medium_term_signal": "neutral",
        "long_term_signal": "neutral",
        "timeframe_alignment": "neutral",
        "signal_strength": 0.5,
    }

    try:
        rsi = momentum_data.get("rsi")
        macd = momentum_data.get("macd")
        macd_signal = momentum_data.get("macd_signal")
        ema_direction = momentum_data.get("ema10_direction")
        price_vs_sma50 = momentum_data.get("price_vs_sma50")
        price_vs_sma200 = momentum_data.get("price_vs_sma200")

        rs_5d = relative_strength_data.get("rs_vs_spy_5d")
        rs_20d = relative_strength_data.get("rs_vs_spy_20d")
        rs_60d = relative_strength_data.get("rs_vs_spy_60d")

        short_bullish = 0
        short_bearish = 0
        short_total = 0

        if rsi is not None:
            short_total += 1
            if rsi < 35:
                short_bullish += 1
            elif rsi > 65:
                short_bearish += 1

        if ema_direction == "up":
            short_total += 1
            short_bullish += 1
        elif ema_direction == "down":
            short_total += 1
            short_bearish += 1

        if rs_5d is not None:
            short_total += 1
            if rs_5d > 0:
                short_bullish += 1
            elif rs_5d < 0:
                short_bearish += 1

        if short_total > 0:
            if short_bullish / short_total >= 0.6:
                result["short_term_signal"] = "bullish"
            elif short_bearish / short_total >= 0.6:
                result["short_term_signal"] = "bearish"

        med_bullish = 0
        med_bearish = 0
        med_total = 0

        if macd is not None and macd_signal is not None:
            med_total += 1
            if macd > macd_signal:
                med_bullish += 1
            else:
                med_bearish += 1

        if price_vs_sma50 is not None:
            med_total += 1
            if price_vs_sma50 > 0:
                med_bullish += 1
            elif price_vs_sma50 < -2:
                med_bearish += 1

        if rs_20d is not None:
            med_total += 1
            if rs_20d > 0:
                med_bullish += 1
            elif rs_20d < 0:
                med_bearish += 1

        if med_total > 0:
            if med_bullish / med_total >= 0.6:
                result["medium_term_signal"] = "bullish"
            elif med_bearish / med_total >= 0.6:
                result["medium_term_signal"] = "bearish"

        long_bullish = 0
        long_bearish = 0
        long_total = 0

        if price_vs_sma200 is not None:
            long_total += 1
            if price_vs_sma200 > 0:
                long_bullish += 1
            elif price_vs_sma200 < -5:
                long_bearish += 1

        if rs_60d is not None:
            long_total += 1
            if rs_60d > 0:
                long_bullish += 1
            elif rs_60d < 0:
                long_bearish += 1

        if price_vs_sma50 is not None and price_vs_sma200 is not None:
            long_total += 1
            if price_vs_sma50 > 0 and price_vs_sma200 > 0:
                long_bullish += 1
            elif price_vs_sma50 < 0 and price_vs_sma200 < 0:
                long_bearish += 1

        if long_total > 0:
            if long_bullish / long_total >= 0.6:
                result["long_term_signal"] = "bullish"
            elif long_bearish / long_total >= 0.6:
                result["long_term_signal"] = "bearish"

        signals = [
            result["short_term_signal"],
            result["medium_term_signal"],
            result["long_term_signal"],
        ]
        bullish_count = signals.count("bullish")
        bearish_count = signals.count("bearish")

        if bullish_count == 3:
            result["timeframe_alignment"] = "aligned_bullish"
            result["signal_strength"] = 1.0
        elif bearish_count == 3:
            result["timeframe_alignment"] = "aligned_bearish"
            result["signal_strength"] = 0.0
        elif bullish_count >= 2:
            result["timeframe_alignment"] = "mixed"
            result["signal_strength"] = 0.7
        elif bearish_count >= 2:
            result["timeframe_alignment"] = "mixed"
            result["signal_strength"] = 0.3
        else:
            result["timeframe_alignment"] = "neutral"
            result["signal_strength"] = 0.5

    except (KeyError, TypeError, ValueError) as e:
        logger.warning("Failed to calculate timeframe signals: %s", str(e))

    return result
