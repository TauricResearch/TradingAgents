from __future__ import annotations

import io
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List

import pandas as pd
import requests
import yfinance as yf

from .broker import Portfolio
from .config import Aggressiveness, Config

logger = logging.getLogger(__name__)

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"

# Conservative Condition 1 (no existing positions): restrict to defensive sectors
# per strategy doc: utilities, consumer staples, healthcare, REITs
CONSERVATIVE_SECTORS = {"Utilities", "Consumer Defensive", "Healthcare", "Real Estate"}


def get_market_regime() -> dict:
    """Fetch S&P 500 and return current market regime.

    Regimes per strategy doc Universal Risk Management table:
        bull           — above both 50-day and 200-day SMA
        corrective     — above 200-day, below 50-day
        bear           — below 200-day SMA
        confirmed_bear — below 200-day AND death cross (50-day < 200-day)
        unknown        — insufficient data
    """
    try:
        spy = yf.download("SPY", period="1y", auto_adjust=True, progress=False, threads=False)
        if spy.empty or len(spy) < 50:
            return {"regime": "unknown"}

        close = spy["Close"].squeeze()
        current = float(close.iloc[-1])
        sma50 = float(close.rolling(50).mean().iloc[-1])
        sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

        above_sma50 = current > sma50
        above_sma200 = sma200 is not None and current > sma200
        death_cross = sma200 is not None and sma50 < sma200

        if above_sma50 and above_sma200:
            regime = "bull"
        elif above_sma200 and not above_sma50:
            regime = "corrective"
        elif sma200 is not None and not above_sma200:
            regime = "confirmed_bear" if death_cross else "bear"
        else:
            regime = "unknown"

        return {
            "regime": regime,
            "spy_price": round(current, 2),
            "sma50": round(sma50, 2),
            "sma200": round(sma200, 2) if sma200 is not None else None,
            "above_sma50": above_sma50,
            "above_sma200": above_sma200,
            "death_cross": death_cross,
        }
    except Exception as exc:
        logger.warning("Market regime check failed: %s", exc)
        return {"regime": "unknown"}


def _rsi(series: pd.Series, period: int = 14) -> float:
    """Compute RSI using exponential smoothing."""
    if len(series) < period + 1:
        return float("nan")
    delta = series.diff().dropna()
    gain = delta.clip(lower=0).ewm(com=period - 1, min_periods=period).mean()
    loss = (-delta).clip(lower=0).ewm(com=period - 1, min_periods=period).mean()
    rs = gain / loss.replace(0, float("nan"))
    return float((100 - 100 / (1 + rs)).iloc[-1])


def _macd_ok(series: pd.Series) -> bool:
    """True if MACD line > signal line AND both > 0 (strategy doc: Condition 1 Aggressive, Step 2)."""
    if len(series) < 35:
        return False
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    m = float(macd_line.iloc[-1])
    s = float(signal_line.iloc[-1])
    return m > s and m > 0 and s > 0


def fetch_nasdaq_tickers() -> List[str]:
    resp = requests.get(NASDAQ_LISTED_URL, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text), sep="|")
    df = df[df["Symbol"].str.match(r"^[A-Z]{1,5}$", na=False)]
    df = df[df["Test Issue"] == "N"]
    df = df[df["ETF"] == "N"]
    df = df[df["Financial Status"] == "N"]
    return df["Symbol"].tolist()


def screen_candidates(
    portfolio: Portfolio,
    cfg: Config,
    cash: float = 0.0,
    on_progress=None,
) -> List[str]:
    owned = {p.ticker for p in portfolio.positions}
    prices = [p.current_price for p in portfolio.positions]

    # Build price bounds — use owned positions if available, else fall back to cash
    if prices:
        price_min = min(prices) * (1 - cfg.price_range_pct)
        price_max = max(prices) * (1 + cfg.price_range_pct)
    elif cash >= cfg.cash_threshold:
        # Condition 1 (cash, no positions): any stock affordable with available cash
        price_min = 1.0
        price_max = cash
    else:
        logger.info("No positions and no meaningful cash — skipping screener")
        return []

    logger.info("Fetching NASDAQ ticker list")
    all_tickers = [t for t in fetch_nasdaq_tickers() if t not in owned]
    logger.info("%d NASDAQ tickers after removing owned", len(all_tickers))

    # Aggressive mode needs more history for RSI(14) and MACD(12,26,9)
    lookback = 70 if cfg.aggressiveness == Aggressiveness.AGGRESSIVE else cfg.momentum_days + 25
    period = f"{lookback}d"

    passed: List[dict] = []
    batch_size = 200
    total_batches = max(1, (len(all_tickers) + batch_size - 1) // batch_size)

    for i in range(0, len(all_tickers), batch_size):
        batch = all_tickers[i : i + batch_size]
        batch_num = i // batch_size + 1
        if on_progress:
            on_progress(batch_num / total_batches, f"Batch {batch_num}/{total_batches}")
        try:
            data = yf.download(
                batch,
                period=period,
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            if data.empty:
                continue

            if isinstance(data.columns, pd.MultiIndex):
                close = data["Close"]
                volume = data["Volume"]
            else:
                close = data[["Close"]].rename(columns={"Close": batch[0]})
                volume = data[["Volume"]].rename(columns={"Volume": batch[0]})

            for ticker in batch:
                if ticker not in close.columns:
                    continue
                ps = close[ticker].dropna()
                vs = volume[ticker].dropna()
                if len(ps) < cfg.momentum_days + 2:
                    continue

                current = float(ps.iloc[-1])
                avg_vol = float(vs.tail(20).mean())
                recent_vol = float(vs.iloc[-1])
                momentum = float(ps.iloc[-1] - ps.iloc[-(cfg.momentum_days + 1)])

                # Universal base filters
                if not (price_min <= current <= price_max):
                    continue
                if avg_vol < cfg.min_avg_volume:
                    continue
                if momentum <= 0:
                    continue

                # Aggressive technical filters (strategy doc: Condition 1 Aggressive, Step 2)
                if cfg.aggressiveness == Aggressiveness.AGGRESSIVE:
                    # Volume confirmation: breakout day >= 150% of 20-day average
                    if recent_vol < avg_vol * 1.5:
                        continue
                    # RSI between 55 and 75 (trending bullish, not yet overbought)
                    rsi_val = _rsi(ps)
                    if not (cfg.min_rsi <= rsi_val <= cfg.max_rsi):
                        continue
                    # MACD: line above signal line, both above zero
                    if not _macd_ok(ps):
                        continue

                passed.append({"ticker": ticker, "momentum": momentum, "price": current})

        except Exception as exc:
            logger.warning("Batch %d–%d failed: %s", i, i + batch_size, exc)

    logger.info("%d tickers passed base filter", len(passed))

    # Sector filters
    if cfg.aggressiveness == Aggressiveness.CONSERVATIVE:
        if prices:
            # Condition 2 conservative: match sectors already held in portfolio
            owned_sectors = {
                p.sector for p in portfolio.positions
                if p.sector not in ("Unknown", None, "")
            }
            if owned_sectors:
                passed = _filter_by_sector(passed, owned_sectors)
                logger.info("%d after owned-sector filter", len(passed))
        else:
            # Condition 1 conservative: defensive sectors only
            passed = _filter_by_sector(passed, CONSERVATIVE_SECTORS)
            logger.info("%d after conservative-sector filter", len(passed))

    # Aggressive: minimum market cap $2B (strategy doc: Condition 1 Aggressive, Step 2, criterion 5)
    if cfg.aggressiveness == Aggressiveness.AGGRESSIVE and cfg.min_market_cap_b > 0:
        passed = _filter_by_market_cap(passed, cfg.min_market_cap_b)
        logger.info("%d after market cap filter", len(passed))

    passed.sort(key=lambda x: x["momentum"], reverse=True)
    return [item["ticker"] for item in passed[: cfg.max_candidates]]


def _filter_by_sector(candidates: List[dict], target_sectors: set) -> List[dict]:
    def _fetch(ticker: str) -> tuple[str, str]:
        try:
            return ticker, yf.Ticker(ticker).info.get("sector", "Unknown")
        except Exception:
            return ticker, "Unknown"

    ticker_sector: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        for ticker, sector in pool.map(_fetch, [c["ticker"] for c in candidates]):
            ticker_sector[ticker] = sector

    return [c for c in candidates if ticker_sector.get(c["ticker"]) in target_sectors]


def _filter_by_market_cap(candidates: List[dict], min_cap_b: float) -> List[dict]:
    min_cap = min_cap_b * 1_000_000_000

    def _fetch(ticker: str) -> tuple[str, float]:
        try:
            cap = yf.Ticker(ticker).fast_info.market_cap or 0
            return ticker, float(cap)
        except Exception:
            return ticker, 0.0

    ticker_cap: dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        for ticker, cap in pool.map(_fetch, [c["ticker"] for c in candidates]):
            ticker_cap[ticker] = cap

    return [c for c in candidates if ticker_cap.get(c["ticker"], 0) >= min_cap]
