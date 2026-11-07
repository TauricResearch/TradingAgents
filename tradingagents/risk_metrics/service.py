"""The "Quantitative Risk Metrics" block: fetch a year of prices, compute, render text.

It is a computed graph step, not an LLM tool. ``risk_block`` never raises for a data
problem: a missing input becomes an UNAVAILABLE notice saying why, and nothing is estimated.
"""

from __future__ import annotations

import logging
from datetime import datetime
from statistics import NormalDist

from tradingagents.dataflows.benchmarks import benchmark_caveat
from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.errors import VendorError, VendorNotConfiguredError
from tradingagents.dataflows.vendors.fred import get_latest_observation
from tradingagents.dataflows.vendors.yahoo.market import get_final_bars, get_final_closes
from tradingagents.memory.settlement import resolve_benchmark
from tradingagents.risk_metrics import metrics as rm

logger = logging.getLogger(__name__)

TITLE = "Quantitative Risk Metrics"
# A last bar older than this many days before the run date is stale.
MAX_PRICE_AGE_DAYS = 10


def risk_free_rate(as_of: str, cfg: dict) -> tuple[float, str]:
    """(annual rate, provenance): the FRED series as published by ``as_of``, else the configured default."""
    reason = "disabled in config"
    series = cfg["risk_metrics_risk_free_series"]
    if cfg.get("risk_metrics_use_fred_risk_free", True):
        try:
            value, date = get_latest_observation(series, as_of)
            return value / 100, f"FRED {series} {value:.2f}% on {date}"
        except Exception as exc:  # noqa: BLE001 - no key, outage or no observation: use the default
            reason = ("FRED_API_KEY is not set" if isinstance(exc, VendorNotConfiguredError)
                      else f"{type(exc).__name__}: {exc}")
    rate = cfg["risk_metrics_risk_free_rate"]
    return rate, f"config default {rate:.2%} (FRED not used: {reason})"


def _pct(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value * 100:.{digits}f}%"


def _num(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def unavailable(ticker: str, as_of: str, reason: str) -> str:
    return (
        f"## {TITLE} for {ticker} as of {as_of}\n\n"
        f"UNAVAILABLE: {reason}\n\n"
        "No risk figure is estimated in its place. Size and place stops from the other reports and say "
        "that the computed risk metrics were unavailable."
    )


def risk_block(ticker: str, as_of: str, asset_type: str = "stock", cfg: dict | None = None) -> str:
    """The risk metrics block for ``ticker`` over the year ending ``as_of``."""
    cfg = cfg or get_config()
    try:
        return render(ticker, as_of, _compute(ticker, as_of, asset_type, cfg), cfg)
    except (rm.RiskMetricsError, VendorError) as exc:
        return unavailable(ticker, as_of, str(exc))
    except Exception as exc:  # noqa: BLE001 - a failure here must not end the run
        logger.warning("Risk metrics failed for %s: %s", ticker, exc)
        return unavailable(ticker, as_of, f"{type(exc).__name__}: {exc}")


def _compute(ticker: str, as_of: str, asset_type: str, cfg: dict):
    days = int(cfg["risk_metrics_window_days"])
    bars = get_final_bars(ticker, as_of, days)
    if bars.empty:
        raise rm.RiskMetricsError(f"no daily prices for {ticker} up to {as_of}")
    age =(datetime.strptime(as_of, "%Y-%m-%d") - bars.index[-1].to_pydatetime()).days
    if age > MAX_PRICE_AGE_DAYS:
        raise rm.RiskMetricsError(f"the latest bar for {ticker} is {bars.index[-1]:%Y-%m-%d}, {age} days before {as_of} (stale)")

    benchmark = resolve_benchmark(ticker, cfg)
    notes = [f"benchmark: {benchmark}"]
    caveat = benchmark_caveat(ticker, benchmark, cfg)
    if caveat:
        notes.append(f"caution: {caveat}")
    try:
        bench = get_final_closes(benchmark, as_of, days)
    except VendorError as exc:
        bench = None
        notes.append(f"benchmark prices unavailable ({exc})")
    rf, rf_note = risk_free_rate(as_of, cfg)
    notes.append(f"risk-free rate: {rf_note}")
    return rm.compute(
        bars, bench, risk_free=rf, periods=rm.PERIODS_PER_YEAR.get(asset_type, 252),
        confidence=cfg["risk_metrics_var_confidence"], atr_window=int(cfg["risk_metrics_atr_window"]),
        atr_multiple=cfg["risk_metrics_atr_multiple"], risk_per_position=cfg["risk_metrics_risk_per_position"],
        max_position=cfg["risk_metrics_max_position_pct"], notes=tuple(notes),
    )


def render(ticker: str, as_of: str, m: rm.RiskMetrics, cfg: dict) -> str:
    c = f"{m.confidence:.0%}"
    z = -NormalDist().inv_cdf(1 - m.confidence)
    s = m.sizing
    stop_long = f"{m.stop_long:,.2f}" if m.stop_long > 0 else "n/a (below zero)"
    rows = [
        ("Last close", f"{m.price:,.2f}", f"final close {m.end}"),
        ("Annualized volatility", _pct(m.volatility), f"std of daily returns x sqrt({m.periods_per_year})"),
        ("Beta vs benchmark", _num(m.beta), f"{m.beta_observations} shared daily returns"),
        ("Max drawdown", _pct(m.max_drawdown), f"peak {m.drawdown_peak} to trough {m.drawdown_trough}"),
        (f"1-day VaR {c}, historical", _pct(m.var_hist), f"a loss exceeded on {1 - m.confidence:.0%} of days"),
        (f"1-day VaR {c}, parametric", _pct(m.var_param), f"normal: {z:.3f} x sigma - mean"),
        (f"1-day CVaR {c}, historical", _pct(m.cvar_hist), "average loss on days beyond the VaR"),
        (f"1-day CVaR {c}, parametric", _pct(m.cvar_param), "normal expected shortfall"),
        ("Sharpe ratio", _num(m.sharpe), f"excess over risk-free {m.risk_free:.2%}, annualized"),
        ("Sortino ratio", _num(m.sortino), "excess over downside deviation, annualized"),
        (f"ATR({m.atr_window})", f"{m.atr:,.2f} ({m.atr / m.price:.2%} of price)", "Wilder's average true range"),
        (f"Stop, long ({m.atr_multiple:g} x ATR below)", stop_long, f"{s.stop_distance_pct:.2%} from the close"),
        (f"Stop, short ({m.atr_multiple:g} x ATR above)", f"{m.stop_short:,.2f}", f"{s.stop_distance_pct:.2%} from the close"),
        ("Risk per position", _pct(m.risk_per_position), "config risk_metrics_risk_per_position, % of the book"),
        ("Volatility-scaled position size", f"{s.size_pct:.1%} of the book",
         f"{_pct(m.risk_per_position)} / {s.stop_distance_pct:.2%} stop distance = {s.uncapped_pct:.1%}"
         + (f", capped at {cfg['risk_metrics_max_position_pct']:.0%}" if s.capped else "")),
        ("Book loss if the stop is hit", _pct(s.book_risk_pct), "size x stop distance"),
        ("1-day VaR of that position", _pct(s.size_pct * m.var_hist), "size x historical VaR, % of the book"),
    ]
    table = "| Metric | Value | Basis |\n|---|---|---|\n" + "\n".join(f"| {a} | {b} | {d} |" for a, b, d in rows)
    lines = [
        f"## {TITLE} for {ticker} as of {as_of} (computed in code)",
        f"Window {m.start} to {m.end}, {m.observations} daily returns; final closes only, nothing after {as_of}.",
        table,
    ]
    if m.notes:
        lines.append("Notes: " + "; ".join(m.notes) + ".")
    return "\n\n".join(lines)
