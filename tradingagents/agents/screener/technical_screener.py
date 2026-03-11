"""Technical screening for swing trading candidates.

Pure computational screening (no LLM) - filters stocks by technical signals:
- Volume spikes (>2x 20-day average)
- MA crossovers (10 EMA crossing above 20/50 SMA)
- RSI oversold bounce (RSI was below 30, now rising)
- Bollinger Band breakout (price crossing above lower band)
- Price momentum patterns
"""

import logging
from datetime import datetime, timedelta

import pandas as pd

from tradingagents.dataflows.screening_data import (
    compute_screening_indicators,
    get_bulk_ohlcv,
)

logger = logging.getLogger(__name__)


def technical_screen(
    universe: pd.DataFrame,
    trade_date: str,
    market: str = "KRX",
    existing_positions: list[str] | None = None,
) -> list[dict]:
    """Screen stocks by technical indicators.

    Args:
        universe: DataFrame with Code, Name, Market columns
        trade_date: Current trading date (YYYY-MM-DD)
        market: "KRX" or "US"
        existing_positions: Tickers already held (skip screening)

    Returns:
        List of dicts with ticker, name, market, signals (list of trigger reasons),
        and indicator values
    """
    existing = set(existing_positions or [])
    tickers = [
        row["Code"]
        for _, row in universe.iterrows()
        if row["Code"] not in existing
    ]

    if not tickers:
        return []

    # Fetch OHLCV for last 60 trading days (enough for 50 SMA)
    end_date = trade_date
    start_dt = datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=120)
    start_date = start_dt.strftime("%Y-%m-%d")

    logger.info(f"Fetching OHLCV for {len(tickers)} tickers...")
    ohlcv_data = get_bulk_ohlcv(tickers, start_date, end_date, market=market)

    candidates = []
    ticker_names = dict(zip(universe["Code"], universe["Name"]))

    for ticker, df in ohlcv_data.items():
        indicators = compute_screening_indicators(df)
        if not indicators:
            continue

        signals = _check_swing_signals(indicators)

        if signals:
            candidates.append({
                "ticker": ticker,
                "name": ticker_names.get(ticker, ticker),
                "market": market,
                "signals": signals,
                "indicators": indicators,
                "signal_count": len(signals),
            })

    # Sort by number of signals (more signals = stronger candidate)
    candidates.sort(key=lambda x: x["signal_count"], reverse=True)
    logger.info(f"Technical screening found {len(candidates)} candidates")

    return candidates


def _check_swing_signals(ind: dict) -> list[str]:
    """Check for swing trading entry signals.

    Returns list of triggered signal descriptions.
    """
    signals = []
    price = ind.get("current_price")
    if price is None:
        return signals

    # 1. Volume spike: current volume > 2x 20-day average
    vol_ratio = ind.get("volume_ratio", 0)
    if vol_ratio >= 2.0:
        signals.append(f"거래량 급증 (평균 대비 {vol_ratio:.1f}배)")

    # 2. RSI oversold bounce: RSI was below 30 and is now rising
    rsi = ind.get("rsi")
    rsi_prev = ind.get("rsi_prev")
    if rsi is not None and rsi_prev is not None:
        if rsi_prev < 30 and rsi > rsi_prev:
            signals.append(f"RSI 과매도 반등 ({rsi_prev:.0f} → {rsi:.0f})")
        elif 30 <= rsi <= 40 and rsi > rsi_prev:
            signals.append(f"RSI 과매도권 탈출 중 ({rsi:.0f})")

    # 3. MA crossover: 10 EMA crosses above 20 SMA (golden cross short-term)
    ema10 = ind.get("ema_10")
    sma20 = ind.get("sma_20")
    if ema10 is not None and sma20 is not None:
        if ema10 > sma20 and price > ema10:
            signals.append(f"단기 골든크로스 (10 EMA > 20 SMA)")

    # 4. Bollinger Band lower touch and bounce
    boll_lower = ind.get("boll_lower")
    prev_close = ind.get("prev_close")
    if boll_lower is not None and prev_close is not None:
        if prev_close <= boll_lower and price > boll_lower:
            signals.append("볼린저 하단 반등")

    # 5. Price above key moving averages (trend confirmation)
    sma50 = ind.get("sma_50")
    if sma50 is not None and price > sma50 and ema10 is not None and ema10 > sma50:
        pct_above = (price / sma50 - 1) * 100
        if 0 < pct_above < 10:
            signals.append(f"50일 이평선 지지 (위 {pct_above:.1f}%)")

    # 6. Recent pullback in uptrend (mean reversion opportunity)
    pct_5d = ind.get("pct_change_5d")
    pct_20d = ind.get("pct_change_20d")
    if pct_5d is not None and pct_20d is not None:
        if pct_20d > 5 and -8 < pct_5d < -2:
            signals.append(f"상승 추세 내 조정 (20일 +{pct_20d:.1f}%, 5일 {pct_5d:.1f}%)")

    # 7. Volume + price breakout combo
    if vol_ratio >= 1.5:
        pct_1d = ind.get("pct_change_1d", 0)
        if pct_1d > 2:
            signals.append(f"거래량 동반 상승 돌파 (+{pct_1d:.1f}%, 거래량 {vol_ratio:.1f}배)")

    return signals
