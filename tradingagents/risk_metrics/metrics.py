"""Quantitative risk metrics from daily prices: volatility, beta, drawdown, VaR, CVaR,
Sharpe, Sortino, ATR, an ATR stop and a volatility-scaled position size.

Pure functions over pandas series. No vendor calls and no LLM. Returns are simple daily
returns, ``close_t / close_{t-1} - 1``. Losses (VaR, CVaR, drawdown) are reported as
positive fractions of the position. Sample standard deviations use ``ddof=1``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

import pandas as pd

# Sessions per year used to annualise: equities trade ~252 days, crypto every day.
PERIODS_PER_YEAR = {"stock": 252, "crypto": 365}

MIN_RETURNS = 60        # about three months of sessions
MIN_SHARED_RETURNS = 30  # for a beta against the benchmark


class RiskMetricsError(ValueError):
    """Too little data to compute a figure; the message says why and is shown in the report."""


def daily_returns(closes: pd.Series) -> pd.Series:
    return closes.sort_index().pct_change().dropna()


def annualized_volatility(returns: pd.Series, periods: int) -> float:
    """sigma_daily * sqrt(periods)."""
    return float(returns.std(ddof=1) * math.sqrt(periods))


def beta(returns: pd.Series, benchmark_returns: pd.Series) -> tuple[float, int]:
    """(beta, shared observations): cov(stock, benchmark) / var(benchmark) on days both traded."""
    paired = pd.concat({"s": returns, "b": benchmark_returns}, axis=1).dropna()
    if len(paired) < MIN_SHARED_RETURNS:
        raise RiskMetricsError(f"only {len(paired)} days of returns are shared with the benchmark "
                               f"(need {MIN_SHARED_RETURNS})")
    variance = paired["b"].var()
    if not variance > 0:
        raise RiskMetricsError("the benchmark's returns do not vary")
    return float(paired["s"].cov(paired["b"]) / variance), len(paired)


def max_drawdown(closes: pd.Series) -> tuple[float, str, str]:
    """(depth, peak date, trough date): the largest fall from a running peak, as a positive fraction."""
    closes = closes.sort_index()
    peaks = closes.cummax()
    drawdown = closes / peaks - 1
    trough = drawdown.idxmin()
    peak = closes.loc[:trough].idxmax()
    return float(-drawdown.min()), f"{peak:%Y-%m-%d}", f"{trough:%Y-%m-%d}"


def var_historical(returns: pd.Series, confidence: float = 0.95) -> float:
    """1-day historical VaR: minus the (1 - confidence) quantile of daily returns."""
    return float(-returns.quantile(1 - confidence))


def var_parametric(returns: pd.Series, confidence: float = 0.95) -> float:
    """1-day normal VaR: -(mu + z sigma) with z = N^-1(1 - confidence), i.e. 1.645 sigma - mu at 95%."""
    z = NormalDist().inv_cdf(1 - confidence)
    return float(-(returns.mean() + z * returns.std(ddof=1)))


def cvar_historical(returns: pd.Series, confidence: float = 0.95) -> float:
    """Expected shortfall: minus the mean of the returns at or below the (1 - confidence) quantile."""
    cutoff = returns.quantile(1 - confidence)
    return float(-returns[returns <= cutoff].mean())


def cvar_parametric(returns: pd.Series, confidence: float = 0.95) -> float:
    """Normal expected shortfall: sigma * pdf(z) / (1 - confidence) - mu."""
    alpha = 1 - confidence
    dist = NormalDist()
    z = dist.inv_cdf(alpha)
    return float(returns.std(ddof=1) * dist.pdf(z) / alpha - returns.mean())


def sharpe_ratio(returns: pd.Series, risk_free_annual: float, periods: int) -> float:
    """sqrt(periods) x mean(excess) / std(excess), excess = daily return - rf / periods."""
    excess = returns - risk_free_annual / periods
    spread = excess.std(ddof=1)
    if not spread > 1e-12:     # a constant series has rounding noise, not zero, for a spread
        raise RiskMetricsError("returns do not vary, so the Sharpe ratio is undefined")
    return float(excess.mean() / spread * math.sqrt(periods))


def sortino_ratio(returns: pd.Series, risk_free_annual: float, periods: int) -> float:
    """sqrt(periods) x mean(excess) / downside deviation; the target is the risk-free rate.

    Downside deviation = sqrt(mean(min(excess, 0)^2)) over all observations.
    """
    excess = returns - risk_free_annual / periods
    downside = math.sqrt(float((excess.clip(upper=0) ** 2).mean()))
    if not downside > 1e-12:
        raise RiskMetricsError("no return fell below the risk-free rate, so the Sortino ratio is undefined")
    return float(excess.mean() / downside * math.sqrt(periods))


def true_range(bars: pd.DataFrame) -> pd.Series:
    """TR = max(High - Low, |High - previous Close|, |Low - previous Close|)."""
    previous = bars["Close"].shift(1)
    ranges = pd.concat([bars["High"] - bars["Low"], (bars["High"] - previous).abs(),
                        (bars["Low"] - previous).abs()], axis=1)
    return ranges.max(axis=1).iloc[1:]


def atr(bars: pd.DataFrame, window: int = 14) -> float:
    """Wilder's ATR: the mean of the first ``window`` true ranges, then ATR_t = (ATR_{t-1} (n-1) + TR_t) / n."""
    tr = true_range(bars.sort_index())
    if len(tr) < window:
        raise RiskMetricsError(f"{len(tr)} true ranges are available; ATR({window}) needs {window}")
    value = float(tr.iloc[:window].mean())
    for current in tr.iloc[window:]:
        value = (value * (window - 1) + float(current)) / window
    return value


@dataclass(frozen=True)
class PositionSize:
    stop_distance_pct: float      # ATR multiple x ATR / price
    size_pct: float               # of the book, after the cap
    uncapped_pct: float
    capped: bool
    book_risk_pct: float          # the risk budget this sizing spends if the stop is hit


def position_size(price: float, atr_value: float, multiple: float, risk_per_position: float,
                  max_position: float) -> PositionSize:
    """Size so that hitting the ATR stop loses ``risk_per_position`` of the book.

    size = risk_per_position / (multiple x ATR / price), capped at ``max_position`` of the book
    (1.0 means no leverage). When capped, the loss at the stop is below the budget.
    """
    stop_distance = multiple * atr_value / price
    if not stop_distance > 0:
        raise RiskMetricsError("the ATR is zero, so no stop distance can size a position")
    uncapped = risk_per_position / stop_distance
    size = min(uncapped, max_position)
    return PositionSize(stop_distance, size, uncapped, uncapped > max_position, size * stop_distance)


@dataclass(frozen=True)
class RiskMetrics:
    start: str
    end: str
    observations: int
    price: float
    periods_per_year: int
    volatility: float
    max_drawdown: float
    drawdown_peak: str
    drawdown_trough: str
    var_hist: float
    var_param: float
    cvar_hist: float
    cvar_param: float
    confidence: float
    risk_free: float
    sharpe: float | None
    sortino: float | None
    beta: float | None
    beta_observations: int
    atr: float
    atr_window: int
    atr_multiple: float
    stop_long: float
    stop_short: float
    sizing: PositionSize
    risk_per_position: float
    notes: tuple[str, ...] = ()


def compute(bars: pd.DataFrame, benchmark_closes: pd.Series | None, *, risk_free: float, periods: int,
            confidence: float, atr_window: int, atr_multiple: float, risk_per_position: float,
            max_position: float, notes: tuple[str, ...] = ()) -> RiskMetrics:
    """Every metric from a window of daily bars (High, Low, Close) and optional benchmark closes."""
    bars = bars.sort_index()
    closes = bars["Close"]
    returns = daily_returns(closes)
    if len(returns) < MIN_RETURNS:
        raise RiskMetricsError(f"only {len(returns)} daily returns are available (need {MIN_RETURNS})")

    notes = list(notes)
    beta_value, beta_n = None, 0
    if benchmark_closes is None or benchmark_closes.empty:
        notes.append("beta unavailable: no benchmark prices")
    else:
        try:
            beta_value, beta_n = beta(returns, daily_returns(benchmark_closes))
        except RiskMetricsError as exc:
            notes.append(f"beta unavailable: {exc}")

    def optional(fn):
        try:
            return fn(returns, risk_free, periods)
        except RiskMetricsError as exc:
            notes.append(str(exc))
            return None

    mdd, peak, trough = max_drawdown(closes)
    price = float(closes.iloc[-1])
    atr_value = atr(bars, atr_window)
    return RiskMetrics(
        start=f"{closes.index[0]:%Y-%m-%d}", end=f"{closes.index[-1]:%Y-%m-%d}", observations=len(returns),
        price=price, periods_per_year=periods,
        volatility=annualized_volatility(returns, periods),
        max_drawdown=mdd, drawdown_peak=peak, drawdown_trough=trough,
        var_hist=var_historical(returns, confidence), var_param=var_parametric(returns, confidence),
        cvar_hist=cvar_historical(returns, confidence), cvar_param=cvar_parametric(returns, confidence),
        confidence=confidence, risk_free=risk_free,
        sharpe=optional(sharpe_ratio), sortino=optional(sortino_ratio),
        beta=beta_value, beta_observations=beta_n,
        atr=atr_value, atr_window=atr_window, atr_multiple=atr_multiple,
        stop_long=price - atr_multiple * atr_value, stop_short=price + atr_multiple * atr_value,
        sizing=position_size(price, atr_value, atr_multiple, risk_per_position, max_position),
        risk_per_position=risk_per_position, notes=tuple(notes),
    )
