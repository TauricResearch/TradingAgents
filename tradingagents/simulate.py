"""Turn a backtest's ratings into a simulated portfolio with vectorbt.

``tradingagents.backtest`` scores decisions and deliberately has no execution
model. This module is that execution model, kept apart from it: every
assumption a portfolio needs and the system does not supply is a parameter
here, so a reader sees what was assumed.

Assumptions, all overridable:

- A rating sets a target weight of the ticker's own cash (``DEFAULT_WEIGHTS``).
  Hold, and any rating not in the map, places no order: the position is kept.
- The order fills at the first close after the analysis date, the same entry
  ``fetch_returns`` uses when it settles a decision.
- Each ticker is its own portfolio with ``init_cash``; tickers share no cash.

Needs the optional extra: ``pip install "tradingagents[sim]"``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from tradingagents.agents.rating import RATING_REVIEW
from tradingagents.dataflows.vendors.yahoo.market import get_closes
from tradingagents.memory import TradingMemoryLog
from tradingagents.memory.settlement import _by_day

# Long-only by default. A negative weight shorts.
DEFAULT_WEIGHTS = {"Buy": 1.0, "Overweight": 0.75, "Underweight": 0.25, "Sell": 0.0}


def signals_from_log(log_path: str | Path) -> pd.DataFrame:
    """Ratings by analysis date (rows) and ticker (columns); unreadable ratings left out."""
    path = Path(log_path)
    if not path.is_file():
        raise FileNotFoundError(f"no memory log at {path}")
    entries = TradingMemoryLog({"memory_log_path": str(path)}).load_entries()
    rows = [(pd.Timestamp(e["date"]), e["ticker"], e["rating"])
            for e in entries if e["rating"] != RATING_REVIEW]
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows, columns=["date", "ticker", "rating"])
    # A cell logged twice keeps its later write, as the log reads it back.
    return frame.pivot_table(index="date", columns="ticker", values="rating", aggfunc="last").sort_index()


def target_weights(signals: pd.DataFrame, close: pd.DataFrame,
                   weights: dict[str, float] = DEFAULT_WEIGHTS) -> pd.DataFrame:
    """Target weights on ``close``'s bars: each rating lands on the first bar after its date.

    Bars with no new rating are NaN, which vectorbt reads as "no order".
    A rating with no bar after it has not traded yet and is dropped.
    """
    out = pd.DataFrame(float("nan"), index=close.index, columns=close.columns)
    for ticker in signals.columns.intersection(close.columns):
        bars = close[ticker].dropna().index
        for date, rating in signals[ticker].dropna().items():
            weight = weights.get(rating)
            at = bars.searchsorted(date, side="right")
            if weight is not None and at < len(bars):
                out.loc[bars[at], ticker] = weight
    return out


def fetch_closes(tickers, start: str) -> pd.DataFrame:
    """Daily closes from ``start`` to the last finished session, one column per ticker."""
    end = (pd.Timestamp.today() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    series = {t: _by_day(get_closes(t, start, end)) for t in tickers}
    close = pd.DataFrame(series)
    close.index = pd.DatetimeIndex(close.index).normalize()
    # Calendars differ (a coin trades weekends); carry a price over the other's gaps.
    return close.sort_index().ffill()


def simulate(log_path: str | Path, close: pd.DataFrame | None = None,
             weights: dict[str, float] = DEFAULT_WEIGHTS,
             init_cash: float = 10_000.0, fees: float = 0.001, slippage: float = 0.0):
    """A vectorbt ``Portfolio`` built from a backtest's memory log.

    ``close`` defaults to Yahoo closes from the first analysis date. Read the
    result with ``pf.stats()``, ``pf.total_return()`` or ``pf.plot()``.
    """
    try:
        import vectorbt as vbt
    except ImportError as exc:
        raise ImportError('simulate needs vectorbt: pip install "tradingagents[sim]"') from exc

    signals = signals_from_log(log_path)
    if signals.empty:
        raise ValueError(f"no rated decisions in {log_path}")
    if close is None:
        close = fetch_closes(list(signals.columns), signals.index[0].strftime("%Y-%m-%d"))
    size = target_weights(signals, close, weights)
    return vbt.Portfolio.from_orders(
        close, size=size, size_type="targetpercent", init_cash=init_cash,
        fees=fees, slippage=slippage, freq="1D",
    )
