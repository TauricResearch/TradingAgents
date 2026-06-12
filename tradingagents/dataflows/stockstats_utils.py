import time
import logging

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError
from stockstats import wrap
from typing import Annotated
import os
from .config import get_config
from .utils import safe_ticker_component
from .symbol_utils import normalize_symbol, NoMarketDataError

logger = logging.getLogger(__name__)


def yf_retry(func, max_retries=3, base_delay=2.0):
    """Execute a yfinance call with exponential backoff on rate limits.

    yfinance raises YFRateLimitError on HTTP 429 responses but does not
    retry them internally. This wrapper adds retry logic specifically
    for rate limits. Other exceptions propagate immediately.
    """
    for attempt in range(max_retries + 1):
        try:
            return func()
        except YFRateLimitError:
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Yahoo Finance rate limited, retrying in {delay:.0f}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
            else:
                raise


def _ensure_date_column(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize the date column to ``Date``.

    Some yfinance builds leave the index unnamed (so ``reset_index()`` yields
    ``index``) or use ``Datetime`` for intraday data. Rename the first
    date-like column so indicators don't silently drop when it isn't ``Date``.
    """
    if "Date" in data.columns:
        return data
    for candidate in ("index", "Datetime", "date"):
        if candidate in data.columns:
            return data.rename(columns={candidate: "Date"})
    return data


def _clean_dataframe(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize a stock DataFrame for stockstats: parse dates, drop invalid rows, fill price gaps."""
    data = _ensure_date_column(data)
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data = data.dropna(subset=["Date"])

    price_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in data.columns]
    data[price_cols] = data[price_cols].apply(pd.to_numeric, errors="coerce")
    data = data.dropna(subset=["Close"])
    data[price_cols] = data[price_cols].ffill().bfill()

    return data


def load_ohlcv(symbol: str, curr_date: str) -> pd.DataFrame:
    """Fetch OHLCV data with caching, filtered to prevent look-ahead bias.

    Downloads 15 years of data up to today and caches per symbol. On
    subsequent calls the cache is reused. Rows after curr_date are
    filtered out so backtests never see future prices.
    """
    # Resolve broker/forex symbols (XAUUSD+ -> GC=F) to Yahoo's convention,
    # then reject values that would escape the cache directory when
    # interpolated into the cache filename (e.g. ``../../tmp/x``).
    canonical = normalize_symbol(symbol)
    safe_symbol = safe_ticker_component(canonical)

    config = get_config()
    curr_date_dt = pd.to_datetime(curr_date)

    # Cache uses a fixed window (15y to today) so one file per symbol
    today_date = pd.Timestamp.today()
    start_date = today_date - pd.DateOffset(years=5)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = today_date.strftime("%Y-%m-%d")

    os.makedirs(config["data_cache_dir"], exist_ok=True)
    data_file = os.path.join(
        config["data_cache_dir"],
        f"{safe_symbol}-YFin-data-{start_str}-{end_str}.csv",
    )

    # A cached file may be empty if a prior fetch failed (unknown symbol,
    # transient rate limit). Treat an empty/columnless cache as a miss and
    # re-fetch rather than serving the poisoned file forever.
    data = None
    if os.path.exists(data_file):
        cached = pd.read_csv(data_file, on_bad_lines="skip", encoding="utf-8")
        if not cached.empty and "Close" in cached.columns:
            data = cached

    if data is None:
        downloaded = yf_retry(lambda: yf.download(
            canonical,
            start=start_str,
            end=end_str,
            multi_level_index=False,
            progress=False,
            auto_adjust=True,
        ))
        downloaded = _ensure_date_column(downloaded.reset_index())
        # Only cache real data — never persist an empty frame.
        if downloaded.empty or "Close" not in downloaded.columns:
            raise NoMarketDataError(
                symbol, canonical, "Yahoo Finance returned no rows"
            )
        downloaded.to_csv(data_file, index=False, encoding="utf-8")
        data = downloaded

    data = _clean_dataframe(data)

    # Filter to curr_date to prevent look-ahead bias in backtesting
    data = data[data["Date"] <= curr_date_dt]

    return data


def filter_financials_by_date(data: pd.DataFrame, curr_date: str) -> pd.DataFrame:
    """Drop financial statement columns (fiscal period timestamps) after curr_date.

    yfinance financial statements use fiscal period end dates as columns.
    Columns after curr_date represent future data and are removed to
    prevent look-ahead bias.
    """
    if not curr_date or data.empty:
        return data
    cutoff = pd.Timestamp(curr_date)
    mask = pd.to_datetime(data.columns, errors="coerce") <= cutoff
    return data.loc[:, mask]


def compute_td_setup(close: "pd.Series") -> "pd.Series":
    """TD Sequential *Setup* running count, signed by direction.

    For each bar, compare Close to the Close 4 bars earlier:
      * Close < Close[-4]  -> buy setup  (count climbs +1, +2, ...)
      * Close > Close[-4]  -> sell setup (count falls  -1, -2, ...)
      * equal, a flip, or no 4-bar lookback resets the run.
    The magnitude is clamped at 9 (a completed setup); the Countdown phase and
    TDST levels are intentionally out of scope (see plan P1). The *last* value
    is the current running count — the live signal, not just a completed 9.
    """
    values = pd.to_numeric(pd.Series(close).reset_index(drop=True), errors="coerce")
    counts = [0] * len(values)
    run = 0
    for i in range(len(values)):
        if i < 4 or pd.isna(values.iloc[i]) or pd.isna(values.iloc[i - 4]):
            run = 0
        elif values.iloc[i] < values.iloc[i - 4]:
            run = run + 1 if run > 0 else 1
        elif values.iloc[i] > values.iloc[i - 4]:
            run = run - 1 if run < 0 else -1
        else:
            run = 0
        run = max(-9, min(9, run))
        counts[i] = run
    return pd.Series(counts, index=pd.Series(close).index)


def td_setup_by_timeframe(data: "pd.DataFrame", curr_date: str = None) -> dict:
    """Current TD Setup count on weekly / monthly / daily bars.

    Weekly and monthly are resampled (last close per period) from the same daily
    frame, so no extra fetch is needed. When ``curr_date`` is given, rows after
    it are dropped first to preserve the no-look-ahead guarantee. Returns signed
    ints keyed ``weekly``/``monthly``/``daily`` (the plan's tier 1/2/3).
    """
    df = _ensure_date_column(pd.DataFrame(data)).copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).sort_values("Date")
    if curr_date:
        df = df[df["Date"] <= pd.Timestamp(curr_date)]

    close = pd.to_numeric(df["Close"], errors="coerce")
    close.index = pd.DatetimeIndex(df["Date"])
    close = close.dropna()

    def _last(series: "pd.Series") -> int:
        return int(compute_td_setup(series).iloc[-1]) if len(series) else 0

    return {
        "weekly": _last(close.resample("W").last().dropna()),
        "monthly": _last(close.resample("ME").last().dropna()),
        "daily": _last(close),
    }


def _td_phrase(n: int) -> str:
    if n == 0:
        return "(no active setup)"
    side = "buy" if n > 0 else "sell"
    if abs(n) == 9:
        return f"({side}-setup COMPLETE 9 of 9 — reversal watch)"
    return f"({side}-setup, {abs(n)} of 9)"


def format_td_setup_block(counts: dict) -> str:
    """Render the tiered TD-9 report block (weekly > monthly > daily)."""
    tiers = [
        ("Tier 1", "Weekly", counts.get("weekly", 0)),
        ("Tier 2", "Monthly", counts.get("monthly", 0)),
        ("Tier 3", "Daily", counts.get("daily", 0)),
    ]
    lines = [
        "## TD-9 (TD Sequential Setup) — current running count by timeframe "
        "(higher tier wins):"
    ]
    for tier, name, n in tiers:
        lines.append(f"- {tier} {name}: {n:+d}  {_td_phrase(n)}")
    return "\n".join(lines)


def compute_zscore(close: "pd.Series", window: int = 20) -> "pd.Series":
    """Rolling z-score of close: (close - rolling mean) / rolling std.

    Measures how many standard deviations the latest close sits from its
    ``window``-period mean — a mean-reversion / stretch gauge. Positive means
    extended above the mean (overbought), negative below (oversold); magnitude
    >= 2 flags a statistically stretched price. Bars without a full window or a
    zero/NaN std yield 0 (no signal). The *last* value is the current reading.
    """
    values = pd.to_numeric(pd.Series(close).reset_index(drop=True), errors="coerce")
    mean = values.rolling(window).mean()
    std = values.rolling(window).std()
    z = (values - mean) / std
    z = z.where(std > 0)  # guard divide-by-zero (a flat window)
    return pd.Series(z.fillna(0.0).to_numpy(), index=pd.Series(close).index)


def zscore_by_timeframe(
    data: "pd.DataFrame", curr_date: str = None, window: int = 20
) -> dict:
    """Current close z-score on weekly / monthly / daily bars.

    Weekly and monthly are resampled (last close per period) from the same daily
    frame, so no extra fetch is needed. When ``curr_date`` is given, rows after
    it are dropped first to preserve the no-look-ahead guarantee. Returns floats
    keyed ``weekly``/``monthly``/``daily`` (tier 1/2/3), mirroring TD-9.
    """
    df = _ensure_date_column(pd.DataFrame(data)).copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).sort_values("Date")
    if curr_date:
        df = df[df["Date"] <= pd.Timestamp(curr_date)]

    close = pd.to_numeric(df["Close"], errors="coerce")
    close.index = pd.DatetimeIndex(df["Date"])
    close = close.dropna()

    def _last(series: "pd.Series") -> float:
        return float(compute_zscore(series, window).iloc[-1]) if len(series) else 0.0

    return {
        "weekly": _last(close.resample("W").last().dropna()),
        "monthly": _last(close.resample("ME").last().dropna()),
        "daily": _last(close),
    }


def _zscore_phrase(z: float) -> str:
    if abs(z) < 1:
        return "(near the mean)"
    side = "above" if z > 0 else "below"
    if abs(z) >= 2:
        stretch = "overbought" if z > 0 else "oversold"
        return f"(stretched {side} mean — {stretch})"
    return f"({side} the mean)"


def format_zscore_block(zscores: dict, window: int = 20) -> str:
    """Render the tiered z-score report block (weekly > monthly > daily)."""
    tiers = [
        ("Tier 1", "Weekly", zscores.get("weekly", 0.0)),
        ("Tier 2", "Monthly", zscores.get("monthly", 0.0)),
        ("Tier 3", "Daily", zscores.get("daily", 0.0)),
    ]
    lines = [
        f"## Z-Score ({window}-period close z-score) — current reading by timeframe "
        "(higher tier wins):"
    ]
    for tier, name, z in tiers:
        lines.append(f"- {tier} {name}: {z:+.2f}  {_zscore_phrase(z)}")
    return "\n".join(lines)


def compute_obv(data: "pd.DataFrame") -> "pd.Series":
    """On-Balance Volume: cumulative volume signed by the close-to-close move.

    Volume is added on up days, subtracted on down days and ignored on
    unchanged days. The absolute level is meaningless — the signal is the
    slope and divergences against price over the lookback window. Returned as
    a date-indexed daily series (OBV has no tiered timeframe payload).
    """
    df = _ensure_date_column(pd.DataFrame(data)).copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).sort_values("Date")

    close = pd.to_numeric(df["Close"], errors="coerce")
    volume = pd.to_numeric(df["Volume"], errors="coerce").fillna(0.0)
    move = close.diff()
    direction = move.mask(move > 0, 1.0).mask(move < 0, -1.0).fillna(0.0)
    obv = (volume * direction).cumsum()
    obv.index = pd.DatetimeIndex(df["Date"])
    return obv


def _resample_ohlcv(df: "pd.DataFrame", rule: str) -> "pd.DataFrame":
    """Resample a date-indexed daily OHLCV frame to weekly/monthly bars."""
    agg = df.resample(rule).agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    )
    return agg.dropna(subset=["Close"])


def supertrend_by_timeframe(
    data: "pd.DataFrame", curr_date: str = None, window: int = 14
) -> dict:
    """Current SuperTrend state on weekly / monthly / daily bars.

    stockstats computes the SuperTrend line itself (``window``-period ATR,
    3x multiplier); the custom part is only the weekly/monthly OHLC resample —
    mirroring ``td_setup_by_timeframe``. When ``curr_date`` is given, rows
    after it are dropped first to preserve the no-look-ahead guarantee.
    Returns per tier (``weekly``/``monthly``/``daily``) either None
    (insufficient history) or a dict with:

    * ``direction`` — "up" (close at/above the line) or "down"
    * ``level`` — the SuperTrend line, i.e. the current trailing stop
    * ``distance_pct`` — signed % distance from the line to the close
    """
    df = _ensure_date_column(pd.DataFrame(data)).copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).sort_values("Date")
    if curr_date:
        df = df[df["Date"] <= pd.Timestamp(curr_date)]

    column = f"supertrend_{window}"

    def _last(frame: "pd.DataFrame"):
        if len(frame) < 2:
            return None
        stock_df = wrap(frame.copy())
        level = stock_df[column].iloc[-1]
        close = pd.to_numeric(frame["Close"], errors="coerce").iloc[-1]
        if pd.isna(level) or level <= 0 or pd.isna(close):
            return None
        level = float(level)
        close = float(close)
        return {
            "direction": "up" if close >= level else "down",
            "level": level,
            "distance_pct": (close - level) / level * 100.0,
        }

    if df.empty:
        return {"weekly": None, "monthly": None, "daily": None}

    daily = df.set_index(pd.DatetimeIndex(df["Date"]))[
        ["Open", "High", "Low", "Close", "Volume"]
    ]
    return {
        "weekly": _last(_resample_ohlcv(daily, "W")),
        "monthly": _last(_resample_ohlcv(daily, "ME")),
        "daily": _last(daily),
    }


def format_supertrend_block(snapshots: dict, window: int = 14) -> str:
    """Render the tiered SuperTrend report block (weekly > monthly > daily)."""
    tiers = [
        ("Tier 1", "Weekly", snapshots.get("weekly")),
        ("Tier 2", "Monthly", snapshots.get("monthly")),
        ("Tier 3", "Daily", snapshots.get("daily")),
    ]
    lines = [
        f"## SuperTrend ({window}-period, 3x ATR) — trend direction and "
        "trailing stop by timeframe (higher tier wins):"
    ]
    for tier, name, snap in tiers:
        if snap is None:
            lines.append(f"- {tier} {name}: n/a (insufficient history)")
        else:
            direction = snap["direction"].upper()
            lines.append(
                f"- {tier} {name}: {direction} — trailing stop {snap['level']:.2f} "
                f"(close {snap['distance_pct']:+.2f}% from stop)"
            )
    return "\n".join(lines)


class StockstatsUtils:
    @staticmethod
    def get_stock_stats(
        symbol: Annotated[str, "ticker symbol for the company"],
        indicator: Annotated[
            str, "quantitative indicators based off of the stock data for the company"
        ],
        curr_date: Annotated[
            str, "curr date for retrieving stock price data, YYYY-mm-dd"
        ],
    ):
        data = load_ohlcv(symbol, curr_date)
        df = wrap(data)
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
        curr_date_str = pd.to_datetime(curr_date).strftime("%Y-%m-%d")

        df[indicator]  # trigger stockstats to calculate the indicator
        matching_rows = df[df["Date"].str.startswith(curr_date_str)]

        if not matching_rows.empty:
            indicator_value = matching_rows[indicator].values[0]
            return indicator_value
        else:
            return "N/A: Not a trading day (weekend or holiday)"
