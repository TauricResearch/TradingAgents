"""Review a whole portfolio: risk metrics for the book, plus each holding's decision.

A single run analyzes one ticker, with the rest of the book reduced to one line
of context. This looks at the book itself. It prices every holding at the review
date, computes what only the combination shows (weights, concentration,
correlation, sector exposure, volatility, beta, value at risk, drawdown), runs
the full pipeline on each underlying, and hands both to a Portfolio Reviewer that
recommends what to do with each position in light of the others.

Options are looked through to their underlying: each contract counts as the
delta-equivalent shares it carries, so risk is measured per underlying across
shares and options together. A contract is valued at its broker mark when one
is given for the review date, with its delta taken at the mark's implied
volatility; otherwise it is modeled with Black-Scholes at the underlying's
realized volatility. Delta is a first-order view: it understates how a large
move changes an option book, which the reviewer is told.

Point in time like the rest of the system: every price is read as of the review
date, so a past date reviews the book as it stood then.

Scope: the metrics are historical, computed over a trailing window with today's
exposures held fixed. They describe the book; they do not forecast it, and
nothing here places or simulates an order. Prices are taken in each listing's
own currency with no conversion, so a mixed-currency book is flagged rather than
silently summed.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from tradingagents.agents.context import resolve_instrument_identity
from tradingagents.agents.managers.portfolio_reviewer import create_portfolio_reviewer
from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.date_window import get_current_date
from tradingagents.dataflows.symbols import safe_ticker_component
from tradingagents.dataflows.vendors.yahoo.ohlcv import load_ohlcv
from tradingagents.graph.settlement import resolve_benchmark
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.option_pricing import DAYS_PER_YEAR, black_scholes, implied_volatility
from tradingagents.portfolio import OptionPosition, PortfolioContext

logger = logging.getLogger(__name__)

TRADING_DAYS = 252
DEFAULT_LOOKBACK_DAYS = 252
DEFAULT_RISK_FREE_RATE = 0.04
# Pairs at or above this correlation are reported as moving together.
HIGH_CORRELATION = 0.8
# How much of each holding's final decision the reviewer reads.
DECISION_EXCERPT_CHARS = 2500


@dataclass
class HoldingMetrics:
    ticker: str
    quantity: float
    price: float
    market_value: float
    weight: float
    sector: str | None = None
    cost_basis: float | None = None
    unrealized_pnl: float | None = None
    unrealized_return: float | None = None
    period_return: float | None = None
    annual_volatility: float | None = None
    max_drawdown: float | None = None
    beta: float | None = None


@dataclass
class OptionMetrics:
    label: str
    underlying: str
    quantity: float
    multiplier: float
    spot: float
    price: float
    price_source: str
    volatility: float
    volatility_source: str
    days_to_expiry: int
    market_value: float
    weight: float
    delta: float
    delta_exposure: float
    theta_per_day: float
    cost_basis: float | None = None
    unrealized_pnl: float | None = None
    unrealized_return: float | None = None


@dataclass
class ExposureMetrics:
    """One underlying seen through shares and options together."""

    ticker: str
    share_value: float
    option_delta_value: float
    exposure: float
    weight: float
    sector: str | None = None


@dataclass
class PortfolioMetrics:
    as_of: str
    lookback_days: int
    benchmark: str
    currency: str | None
    cash: float | None
    total_value: float
    gross_exposure: float
    net_exposure: float
    holdings: list[HoldingMetrics]
    options: list[OptionMetrics] = field(default_factory=list)
    exposures: list[ExposureMetrics] = field(default_factory=list)
    option_value: float = 0.0
    option_theta_per_day: float = 0.0
    sector_weights: dict[str, float] = field(default_factory=dict)
    top_weight: float | None = None
    herfindahl: float | None = None
    effective_positions: float | None = None
    annual_volatility: float | None = None
    beta: float | None = None
    value_at_risk_95: float | None = None
    max_drawdown: float | None = None
    period_return: float | None = None
    benchmark_return: float | None = None
    observations: int = 0
    high_correlations: list[tuple[str, str, float]] = field(default_factory=list)
    unpriced: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def render(self) -> str:
        cur = f" {self.currency}" if self.currency else ""
        risk_basis = "delta-equivalent exposure" if self.options else "current weights"
        lines = [
            f"As of {self.as_of}, over the trailing {self.observations} trading days "
            f"(target {self.lookback_days}), benchmark {self.benchmark}.",
            "",
            f"- Total value: {self.total_value:,.2f}{cur}"
            + (f" (cash {self.cash:,.2f}, {_pct(self.cash / self.total_value)})"
               if self.cash is not None and self.total_value else " (cash not provided)"),
        ]
        if self.options:
            share = self.option_value / self.total_value if self.total_value else None
            lines.append(
                f"- Options: {self.option_value:,.2f}{cur} of value ({_pct(share)}), "
                f"time decay {self.option_theta_per_day:+,.0f}{cur} per day")
        lines += [
            f"- Gross exposure: {_pct(self.gross_exposure)} · net exposure: {_pct(self.net_exposure)}"
            + (" (options at delta)" if self.options else ""),
            f"- Largest exposure: {_pct(self.top_weight)} · effective number of positions: "
            f"{_num(self.effective_positions)} (HHI {_num(self.herfindahl, 3)})",
            f"- Annualized volatility: {_pct(self.annual_volatility)} · beta to {self.benchmark}: "
            f"{_num(self.beta)}",
            f"- 1-day historical VaR (95%): {_pct(self.value_at_risk_95)} of total value"
            + (f" (~{self.value_at_risk_95 * self.total_value:,.0f}{cur})"
               if self.value_at_risk_95 is not None else ""),
            f"- Max drawdown at {risk_basis}: {_pct(self.max_drawdown)}",
            f"- Return at {risk_basis}: {_pct(self.period_return)} vs {self.benchmark} "
            f"{_pct(self.benchmark_return)}",
        ]
        if self.holdings:
            lines += [
                "",
                "Shares:",
                "",
                "| Ticker | Sector | Qty | Price | Value | Weight | Unrealized | Return | Vol | Max DD | Beta |",
                "|---|---|---|---|---|---|---|---|---|---|---|",
            ]
            for h in self.holdings:
                lines.append(
                    f"| {h.ticker} | {h.sector or 'n/a'} | {h.quantity:,.4g} | {h.price:,.2f} "
                    f"| {h.market_value:,.0f} | {_pct(h.weight)} | {_unrealized(h)} "
                    f"| {_pct(h.period_return, signed=True)} | {_pct(h.annual_volatility)} "
                    f"| {_pct(h.max_drawdown)} | {_num(h.beta)} |"
                )
        if self.options:
            lines += [
                "",
                "Options:",
                "",
                "| Contract | Qty | Spot | Price | Value | Weight | Unrealized | Delta "
                "| Delta exposure | Vol | Days left | Theta/day |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|",
            ]
            for o in self.options:
                lines.append(
                    f"| {o.label} | {o.quantity:,.4g} | {o.spot:,.2f} "
                    f"| {o.price:,.2f} ({o.price_source}) | {o.market_value:,.0f} | {_pct(o.weight)} "
                    f"| {_unrealized(o)} | {o.delta:.2f} | {o.delta_exposure:,.0f} "
                    f"| {_pct(o.volatility)} ({o.volatility_source}) | {o.days_to_expiry} "
                    f"| {o.theta_per_day:+,.0f} |"
                )
            lines += [
                "",
                "Exposure by underlying (shares plus option delta):",
                "",
                "| Underlying | Sector | Shares | Option delta | Exposure | Weight |",
                "|---|---|---|---|---|---|",
            ]
            for e in self.exposures:
                lines.append(
                    f"| {e.ticker} | {e.sector or 'n/a'} | {e.share_value:,.0f} "
                    f"| {e.option_delta_value:,.0f} | {e.exposure:,.0f} | {_pct(e.weight)} |"
                )
        if self.sector_weights:
            lines += ["", "Sector weights: " + ", ".join(
                f"{sector} {_pct(w)}" for sector, w in self.sector_weights.items())]
        if self.high_correlations:
            lines += ["", f"Pairs correlated at {HIGH_CORRELATION} or more: " + ", ".join(
                f"{a}/{b} {rho:.2f}" for a, b, rho in self.high_correlations)]
        if self.unpriced:
            lines += ["", "Not priced, so left out of every figure above: " + "; ".join(
                f"{t} ({reason})" for t, reason in self.unpriced)]
        if self.warnings:
            lines += [""] + [f"Note: {w}" for w in self.warnings]
        return "\n".join(lines)


def _unrealized(item) -> str:
    if item.unrealized_pnl is None:
        return "n/a"
    return f"{item.unrealized_pnl:+,.0f} ({_pct(item.unrealized_return, signed=True)})"


def _pct(value: float | None, signed: bool = False) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"{value:+.1%}" if signed else f"{value:.1%}"


def _num(value: float | None, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"{value:.{digits}f}"


def _max_drawdown(returns: pd.Series) -> float | None:
    if returns.empty:
        return None
    wealth = (1 + returns).cumprod()
    return float((wealth / wealth.cummax() - 1).min())


def _beta(returns: pd.Series, benchmark: pd.Series | None) -> float | None:
    if benchmark is None:
        return None
    joined = pd.concat([returns, benchmark], axis=1, join="inner").dropna()
    if len(joined) < 2:
        return None
    variance = joined.iloc[:, 1].var()
    return float(joined.iloc[:, 0].cov(joined.iloc[:, 1]) / variance) if variance else None


def _realized_volatility(series: pd.Series) -> float | None:
    returns = series.pct_change().dropna()
    return float(returns.std() * math.sqrt(TRADING_DAYS)) if len(returns) > 1 else None


def price_option(option: OptionPosition, spot: float, as_of: str, realized_vol: float | None,
                 rate: float = DEFAULT_RISK_FREE_RATE) -> tuple[dict | None, str | None]:
    """Value and greeks of one contract as of ``as_of``, or ``(None, reason)``.

    A mark counts only for the day it was taken: marked on another day, or with
    no date, it is not a price for the review date and the contract is modeled.
    Returns the pricing and a note for the reader, when there is one.
    """
    as_of_date = date.fromisoformat(as_of)
    days = (option.expiry - as_of_date).days
    years = max(days, 0) / DAYS_PER_YEAR
    mark_applies = option.mark is not None and option.mark_date == as_of_date
    note = None
    if option.mark is not None and not mark_applies:
        note = (f"{option.label()}: mark is dated {option.mark_date or 'unknown'}, not the review "
                "date, so it was modeled instead")

    def result(price, price_source, vol, vol_source, greeks):
        return {"price": price, "price_source": price_source, "volatility": vol,
                "volatility_source": vol_source, "days": days, "greeks": greeks}

    if days <= 0:
        greeks = black_scholes(option.option_type, spot, option.strike, 0, rate, 0)
        return result(greeks.price, "expired", 0.0, "n/a", greeks), note

    if mark_applies:
        implied = implied_volatility(option.option_type, option.mark, spot, option.strike, years, rate)
        if implied is not None:
            greeks = black_scholes(option.option_type, spot, option.strike, years, rate, implied)
            return result(option.mark, "mark", implied, "implied", greeks), note
        if realized_vol is None:
            return None, "mark has no implied volatility and the underlying has no history"
        greeks = black_scholes(option.option_type, spot, option.strike, years, rate, realized_vol)
        note = f"{option.label()}: mark implies no volatility, so delta is at realized volatility"
        return result(option.mark, "mark", realized_vol, "realized", greeks), note

    if realized_vol is None:
        return None, "no mark for the review date and no underlying history to model it"
    greeks = black_scholes(option.option_type, spot, option.strike, years, rate, realized_vol)
    return result(greeks.price, "model", realized_vol, "realized", greeks), note


def compute_metrics(
    portfolio: PortfolioContext,
    closes: dict[str, pd.Series],
    as_of: str,
    benchmark: str = "SPY",
    benchmark_closes: pd.Series | None = None,
    sectors: dict[str, str] | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    unpriced: list[tuple[str, str]] | None = None,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
) -> PortfolioMetrics:
    """Portfolio metrics from daily closes already cut at ``as_of``.

    ``closes`` maps each underlying (upper case) to its close series; a holding
    whose underlying is missing from it is left out of every figure and should
    be listed in ``unpriced`` with the reason. Values are over total value
    (shares and options at their price plus cash), so cash dilutes risk the way
    it does in the account. Risk is measured on exposure per underlying, with
    options at delta, held fixed over the window.
    """
    sectors = sectors or {}
    unpriced = list(unpriced or [])
    unpriced_names = {t for t, _ in unpriced}
    warnings: list[str] = []
    series_of = {s: c.dropna().tail(lookback_days + 1) for s, c in closes.items()
                 if c is not None and not c.dropna().empty}

    def missing(name: str, reason: str = "no price data"):
        if name not in unpriced_names:
            unpriced.append((name, reason))
            unpriced_names.add(name)

    share_rows = []
    for position in portfolio.positions:
        symbol = position.ticker.strip().upper()
        if symbol not in series_of:
            missing(symbol)
            continue
        series = series_of[symbol]
        share_rows.append((symbol, position, series, position.quantity * float(series.iloc[-1])))

    option_rows = []
    for option in portfolio.options:
        underlying = option.underlying.strip().upper()
        if underlying not in series_of:
            missing(option.label(), f"underlying {underlying} has no price data")
            continue
        series = series_of[underlying]
        spot = float(series.iloc[-1])
        priced, note = price_option(option, spot, as_of, _realized_volatility(series), risk_free_rate)
        if priced is None:
            missing(option.label(), note or "could not be priced")
            continue
        if note:
            warnings.append(note)
        option_rows.append((underlying, option, spot, priced))

    cash = portfolio.cash
    share_value = sum(row[3] for row in share_rows)
    option_value = sum(o.quantity * o.multiplier * p["price"] for _, o, _, p in option_rows)
    total = share_value + option_value + (cash or 0.0)

    exposure: dict[str, list[float]] = {}  # underlying -> [share value, option delta value]
    for symbol, _, _, value in share_rows:
        exposure.setdefault(symbol, [0.0, 0.0])[0] += value
    for underlying, option, spot, p in option_rows:
        exposure.setdefault(underlying, [0.0, 0.0])[1] += (
            option.quantity * option.multiplier * p["greeks"].delta * spot)
    net = {u: s + o for u, (s, o) in exposure.items()}
    gross = sum(abs(v) for v in net.values())
    # A book that nets to nothing still has exposure; weigh it by gross instead.
    base = total if total > 0 else gross
    risk_weights = {u: (v / base if base else 0.0) for u, v in net.items()}

    returns = pd.DataFrame({u: series_of[u].pct_change() for u in net})
    bench_returns = (benchmark_closes.dropna().tail(lookback_days + 1).pct_change().dropna()
                     if benchmark_closes is not None else None)

    holdings = []
    for symbol, pos, series, value in share_rows:
        own = returns[symbol].dropna()
        cost = pos.quantity * pos.average_price if pos.average_price is not None else None
        pnl = value - cost if cost is not None else None
        holdings.append(HoldingMetrics(
            ticker=symbol,
            quantity=pos.quantity,
            price=float(series.iloc[-1]),
            market_value=value,
            weight=value / base if base else 0.0,
            sector=sectors.get(symbol),
            cost_basis=cost,
            unrealized_pnl=pnl,
            unrealized_return=(pnl / abs(cost)) if cost else None,
            period_return=float(series.iloc[-1] / series.iloc[0] - 1) if len(series) > 1 else None,
            annual_volatility=float(own.std() * math.sqrt(TRADING_DAYS)) if len(own) > 1 else None,
            max_drawdown=_max_drawdown(own),
            beta=_beta(own, bench_returns),
        ))
    holdings.sort(key=lambda h: abs(h.weight), reverse=True)

    options = []
    for underlying, option, spot, p in option_rows:
        contracts = option.quantity * option.multiplier
        value = contracts * p["price"]
        cost = contracts * option.average_price if option.average_price is not None else None
        pnl = value - cost if cost is not None else None
        options.append(OptionMetrics(
            label=option.label(),
            underlying=underlying,
            quantity=option.quantity,
            multiplier=option.multiplier,
            spot=spot,
            price=p["price"],
            price_source=p["price_source"],
            volatility=p["volatility"],
            volatility_source=p["volatility_source"],
            days_to_expiry=max(p["days"], 0),
            market_value=value,
            weight=value / base if base else 0.0,
            delta=p["greeks"].delta,
            delta_exposure=contracts * p["greeks"].delta * spot,
            theta_per_day=contracts * p["greeks"].theta_per_day,
            cost_basis=cost,
            unrealized_pnl=pnl,
            unrealized_return=(pnl / abs(cost)) if cost else None,
        ))
        if p["price_source"] == "expired":
            warnings.append(f"{option.label()} expired on or before the review date; "
                            "it is carried at intrinsic value with no delta")
    options.sort(key=lambda o: abs(o.market_value), reverse=True)

    exposures = sorted(
        (ExposureMetrics(ticker=u, share_value=s, option_delta_value=o, exposure=s + o,
                         weight=risk_weights[u], sector=sectors.get(u))
         for u, (s, o) in exposure.items()),
        key=lambda e: abs(e.weight), reverse=True,
    )

    metrics = PortfolioMetrics(
        as_of=as_of, lookback_days=lookback_days, benchmark=benchmark,
        currency=portfolio.currency, cash=cash, total_value=total,
        gross_exposure=gross / base if base else 0.0,
        net_exposure=sum(net.values()) / base if base else 0.0,
        holdings=holdings, options=options, exposures=exposures,
        option_value=option_value,
        option_theta_per_day=sum(o.theta_per_day for o in options),
        unpriced=unpriced, warnings=warnings,
    )
    if cash is None:
        metrics.warnings.append("cash was not provided, so weights are over positions only")
    if options:
        metrics.warnings.append(
            "option risk is measured at delta, a first-order view: a large move changes "
            "delta, so losses in a sharp fall and gains in a sharp rise differ from these figures")
    if not exposures:
        return metrics

    abs_weights = [abs(e.weight) for e in exposures]
    weight_total = sum(abs_weights)
    shares = [w / weight_total for w in abs_weights] if weight_total else []
    metrics.top_weight = max(abs_weights)
    if shares:
        metrics.herfindahl = sum(s * s for s in shares)
        metrics.effective_positions = 1 / metrics.herfindahl

    sector_weights: dict[str, float] = {}
    for e in exposures:
        key = e.sector or "Unknown"
        sector_weights[key] = sector_weights.get(key, 0.0) + e.weight
    metrics.sector_weights = dict(sorted(sector_weights.items(), key=lambda kv: -abs(kv[1])))

    # Days every underlying traded; a series that starts late shortens the window.
    aligned = returns.dropna()
    metrics.observations = len(aligned)
    if len(aligned) > 1:
        book = aligned.mul(pd.Series(risk_weights)).sum(axis=1)
        metrics.annual_volatility = float(book.std() * math.sqrt(TRADING_DAYS))
        metrics.value_at_risk_95 = float(max(-book.quantile(0.05), 0.0))
        metrics.max_drawdown = _max_drawdown(book)
        metrics.period_return = float((1 + book).prod() - 1)
        metrics.beta = _beta(book, bench_returns)
        if bench_returns is not None:
            window = bench_returns.loc[bench_returns.index.isin(aligned.index)]
            metrics.benchmark_return = float((1 + window).prod() - 1) if len(window) else None

        corr = aligned.corr()
        symbols = list(corr.columns)
        metrics.high_correlations = sorted(
            ((a, b, float(corr.loc[a, b]))
             for i, a in enumerate(symbols) for b in symbols[i + 1:]
             if corr.loc[a, b] >= HIGH_CORRELATION),
            key=lambda pair: -pair[2],
        )
    if metrics.observations < min(60, lookback_days):
        metrics.warnings.append(
            f"only {metrics.observations} overlapping trading days, so the risk figures are rough")
    return metrics


def _closes(symbol: str, as_of: str) -> pd.Series:
    """Daily closes up to and including ``as_of``, indexed by date."""
    data = load_ohlcv(symbol, as_of, fill_gaps=False)
    return data.set_index("Date")["Close"].astype(float)


def gather_metrics(
    portfolio: PortfolioContext,
    as_of: str,
    config: dict,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> PortfolioMetrics:
    """Price the book as of ``as_of`` and compute its metrics.

    A holding that cannot be priced is reported, not dropped silently, so the
    figures never pass for the whole book when they are not.
    """
    with run_config(config):
        closes, unpriced, sectors = {}, [], {}
        for symbol in portfolio.underlyings():
            try:
                closes[symbol] = _closes(symbol, as_of)
            except Exception as exc:  # one delisted holding must not end the review
                logger.warning("Could not price %s as of %s: %s", symbol, as_of, exc)
                unpriced.append((symbol, str(exc)))
                continue
            sector = resolve_instrument_identity(symbol).get("sector")
            if sector:
                sectors[symbol] = sector

        benchmarks = {resolve_benchmark(symbol, config) for symbol in closes}
        benchmark = config.get("benchmark_ticker") or "SPY"
        if closes and not config.get("benchmark_ticker"):
            benchmark = resolve_benchmark(next(iter(closes)), config)
        try:
            benchmark_closes = closes.get(benchmark)
            if benchmark_closes is None:
                benchmark_closes = _closes(benchmark, as_of)
        except Exception as exc:
            logger.warning("Could not price benchmark %s: %s", benchmark, exc)
            benchmark_closes = None

    metrics = compute_metrics(
        portfolio, closes, as_of, benchmark=benchmark, benchmark_closes=benchmark_closes,
        sectors=sectors, lookback_days=lookback_days, unpriced=unpriced,
        risk_free_rate=config.get("risk_free_rate", DEFAULT_RISK_FREE_RATE),
    )
    if benchmark_closes is None:
        metrics.warnings.append(f"benchmark {benchmark} could not be priced, so beta is not reported")
    if len(benchmarks) > 1 and not config.get("benchmark_ticker"):
        metrics.warnings.append(
            "holdings list on several markets (" + ", ".join(sorted(benchmarks)) + "); prices "
            "are in each listing's own currency and are not converted, so values and weights "
            "mix currencies")
    return metrics


@dataclass
class HoldingDecision:
    ticker: str
    rating: str | None = None
    decision: str = ""
    report_path: Path | None = None
    error: str | None = None


@dataclass
class PortfolioReview:
    as_of: str
    metrics: PortfolioMetrics
    decisions: list[HoldingDecision]
    assessment: str
    report_path: Path

    def render(self) -> str:
        return render_review(self.as_of, self.metrics, self.decisions, self.assessment)


def _decisions_report(decisions: list[HoldingDecision]) -> str:
    if not decisions:
        return "Single-ticker analysis was not run for this review; judge the book on its metrics."
    parts = []
    for d in decisions:
        if d.error:
            parts.append(f"### {d.ticker}\nNot analyzed: {d.error}")
        else:
            excerpt = d.decision[:DECISION_EXCERPT_CHARS]
            if len(d.decision) > DECISION_EXCERPT_CHARS:
                excerpt += " [...]"
            parts.append(f"### {d.ticker}: {d.rating}\n{excerpt}")
    return "\n\n".join(parts)


def render_review(as_of, metrics, decisions, assessment) -> str:
    parts = [f"# Portfolio Review, {as_of}", "", "## Portfolio Metrics", "", metrics.render()]
    if decisions:
        parts += ["", "## Single-Ticker Ratings", "", "| Ticker | Rating | Report |", "|---|---|---|"]
        parts += [
            f"| {d.ticker} | {d.rating or 'not analyzed'} | "
            f"{d.report_path if d.report_path else (d.error or '')} |"
            for d in decisions
        ]
    parts += ["", "## Assessment", "", assessment, "",
              "---", "Research output, not financial advice. Metrics are historical, "
              "computed with current exposures held fixed; they are not forecasts."]
    return "\n".join(parts)


def review_portfolio(
    portfolio: PortfolioContext,
    as_of: str,
    config: dict,
    selected_analysts=("market", "social", "news", "fundamentals"),
    analyze_holdings: bool = True,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    run_id: str | None = None,
) -> PortfolioReview:
    """Review the whole book as of ``as_of`` and write the review to disk.

    With ``analyze_holdings`` each underlying (a share holding, or the stock an
    option is written on) goes through the full pipeline with the book as its
    context, so its decision is logged like any other run. Without it, only the
    metrics and the reviewer's read of them are produced, which costs one LLM
    call instead of a full run per underlying.
    """
    try:
        valid = datetime.strptime(str(as_of), "%Y-%m-%d").strftime("%Y-%m-%d") == str(as_of)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(f"review date must be in YYYY-MM-DD format, got {as_of!r}")
    if as_of > get_current_date():
        raise ValueError(f"review date cannot be in the future: {as_of}")
    if not portfolio.positions and not portfolio.options:
        raise ValueError("the portfolio has no positions to review")

    run_id = safe_ticker_component(run_id or datetime.now().strftime("%Y%m%d_%H%M%S"))
    run_dir = Path(config["results_dir"]) / "portfolio_review" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    graph = TradingAgentsGraph(selected_analysts, config=config)
    metrics = gather_metrics(portfolio, as_of, config, lookback_days)

    decisions: list[HoldingDecision] = []
    if analyze_holdings:
        for symbol in portfolio.underlyings():
            try:
                state, rating = graph.propagate(symbol, as_of, portfolio=portfolio)
                path = graph.save_reports(state, symbol, run_dir / safe_ticker_component(symbol))
                decisions.append(HoldingDecision(symbol, rating, state["final_trade_decision"], path))
            except Exception as exc:  # one unreachable vendor must not end the review
                logger.warning("Analysis of %s failed: %s", symbol, exc)
                decisions.append(HoldingDecision(symbol, error=str(exc)))

    with run_config(config):
        reviewer = create_portfolio_reviewer(graph.deep_thinking_llm)
        assessment = reviewer(metrics.render(), _decisions_report(decisions))

    report_path = run_dir / "portfolio_review.md"
    review = PortfolioReview(as_of, metrics, decisions, assessment, report_path)
    report_path.write_text(review.render(), encoding="utf-8")
    return review
