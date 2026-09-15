"""Performance statistics and baselines for a simulated equity curve.

The baselines matter as much as the statistics. An agent that rates everything
Buy in a rising market produces a fine-looking equity curve while contributing
nothing, so every scorecard is reported against three references:

* **Buy-and-hold** the traded ticker — did the agent beat simply owning it?
* **Buy-and-hold the benchmark** — the alpha baseline the decision log already
  uses (SPY for US listings, resolved per-market elsewhere).
* **A random-rating monkey** drawn from the agent's *own* rating distribution
  and run through the identical execution model. This is the reference that
  separates skill from directional bias: if the agent is 80% Buy in a bull
  market, so is the monkey, and only the timing differs.

All functions here are pure — they take an equity curve or a price frame and
return numbers — so the whole scorecard can be recomputed from a stored
backtest without re-running a single agent.
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass

import pandas as pd

from tradingagents.backtest.portfolio import (
    PortfolioConfig,
    SimulationResult,
    simulate,
)

TRADING_DAYS_PER_YEAR = 252

# Ratings that express a direction, used for hit rate. Hold and REVIEW are
# excluded rather than scored as misses: neither claims the price will move.
_LONG_RATINGS = frozenset({"Buy", "Overweight"})
_SHORT_RATINGS = frozenset({"Underweight", "Sell"})


@dataclass
class Metrics:
    """Risk and return statistics for one equity curve."""

    total_return: float
    annualized_return: float
    volatility: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float
    n_days: int

    def as_dict(self) -> dict:
        return asdict(self)


def compute_metrics(equity: pd.Series) -> Metrics:
    """Summarise an equity curve.

    A curve with fewer than two points yields all-zero statistics rather than
    NaN, so a backtest whose window was too short to trade produces a readable
    scorecard instead of a wall of nulls.
    """
    equity = equity.dropna()
    if len(equity) < 2 or float(equity.iloc[0]) <= 0:
        return Metrics(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, len(equity))

    start, end = float(equity.iloc[0]), float(equity.iloc[-1])
    total_return = end / start - 1.0

    span_days = (equity.index[-1] - equity.index[0]).days
    years = span_days / 365.25
    if years > 0 and total_return > -1.0:
        annualized = (1.0 + total_return) ** (1.0 / years) - 1.0
    else:
        annualized = 0.0

    returns = equity.pct_change().dropna()
    if len(returns) < 2:
        return Metrics(total_return, annualized, 0.0, 0.0, 0.0, 0.0, 0.0, len(equity))

    scale = math.sqrt(TRADING_DAYS_PER_YEAR)
    mean_daily = float(returns.mean())
    std_daily = float(returns.std(ddof=1))
    volatility = std_daily * scale
    sharpe = (mean_daily / std_daily) * scale if std_daily > 0 else 0.0

    downside = returns.clip(upper=0.0)
    downside_dev = float((downside**2).mean()) ** 0.5
    sortino = (mean_daily / downside_dev) * scale if downside_dev > 0 else 0.0

    drawdown = equity / equity.cummax() - 1.0
    max_drawdown = float(drawdown.min())
    calmar = annualized / abs(max_drawdown) if max_drawdown < 0 else 0.0

    return Metrics(
        total_return=total_return,
        annualized_return=annualized,
        volatility=volatility,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_drawdown,
        calmar=calmar,
        n_days=len(equity),
    )


def buy_and_hold(prices: pd.DataFrame, initial_cash: float = 100_000.0) -> pd.Series:
    """Equity curve for buying at the first open and holding to the last close.

    Bought at the *open* to match the execution model in
    :func:`~tradingagents.backtest.portfolio.simulate`, so the comparison is not
    quietly tilted by a different entry convention.
    """
    prices = prices.dropna(subset=["Open", "Close"])
    if len(prices) == 0:
        return pd.Series(dtype="float64")

    index = pd.DatetimeIndex(prices.index).tz_localize(None).normalize()
    entry = float(prices["Open"].iloc[0])
    if entry <= 0:
        return pd.Series(dtype="float64")

    shares = initial_cash / entry
    return pd.Series(
        prices["Close"].to_numpy(dtype="float64") * shares,
        index=index,
        name="equity",
    )


def hit_rate(
    decisions: list[tuple[str, str | None]],
    prices: pd.DataFrame,
    horizon_days: int = 5,
) -> tuple[float, int]:
    """Fraction of directional calls whose forward return went the right way.

    Measured from the fill bar's open over ``horizon_days`` trading bars, which
    is the same 5-day window the decision log uses to resolve outcomes. Hold and
    REVIEW are not counted either way.

    Returns:
        ``(rate, n_scored)``. ``n_scored`` is 0 when no directional call had a
        full forward window, in which case ``rate`` is 0.0 and the scorecard
        reports the call count rather than a meaningless percentage.
    """
    prices = prices.dropna(subset=["Open", "Close"])
    if len(prices) == 0:
        return 0.0, 0

    index = pd.DatetimeIndex(prices.index).tz_localize(None).normalize()
    opens = prices["Open"].to_numpy(dtype="float64")

    hits = 0
    scored = 0
    for date, rating in decisions:
        if rating in _LONG_RATINGS:
            direction = 1.0
        elif rating in _SHORT_RATINGS:
            direction = -1.0
        else:
            continue

        entry_bar = int(index.searchsorted(pd.Timestamp(date), side="right"))
        exit_bar = entry_bar + horizon_days
        if exit_bar >= len(index) or opens[entry_bar] <= 0:
            continue

        forward = opens[exit_bar] / opens[entry_bar] - 1.0
        scored += 1
        if forward * direction > 0:
            hits += 1

    return (hits / scored if scored else 0.0), scored


@dataclass
class BaselineComparison:
    """Where the agent's return falls against random sequences of its own ratings."""

    n_trials: int
    mean_return: float
    median_return: float
    p05_return: float
    p95_return: float
    agent_percentile: float

    def as_dict(self) -> dict:
        return asdict(self)


def random_rating_baseline(
    decisions: list[tuple[str, str | None]],
    prices: pd.DataFrame,
    agent_total_return: float,
    config: PortfolioConfig | None = None,
    n_trials: int = 200,
    seed: int = 0,
) -> BaselineComparison | None:
    """Score random re-orderings of the agent's own ratings.

    Each trial keeps the decision *dates* and the empirical rating *mix* fixed
    and re-draws which rating landed on which date. Everything else — execution,
    costs, weight map — is identical, so the only thing being tested is whether
    the agent put the right rating on the right date.

    ``agent_percentile`` is the share of trials the agent beat: 0.5 means the
    agent performed like a coin flip with its own bias, and a number near 1.0 is
    the claim worth making.

    Returns ``None`` when there are too few decisions to shuffle meaningfully.
    """
    config = config or PortfolioConfig()
    dates = [d for d, _ in decisions]
    ratings = [r for _, r in decisions]
    # n_trials < 1 is how the CLI disables the baseline; it must return None
    # rather than reaching the empty-list average below.
    if n_trials < 1 or len(dates) < 2 or len(set(ratings)) < 2:
        return None

    rng = random.Random(seed)
    totals: list[float] = []
    for _ in range(n_trials):
        shuffled = ratings[:]
        rng.shuffle(shuffled)
        result = simulate(list(zip(dates, shuffled, strict=True)), prices, config)
        metrics = compute_metrics(result.equity)
        totals.append(metrics.total_return)

    totals.sort()
    beaten = sum(1 for t in totals if agent_total_return > t)
    return BaselineComparison(
        n_trials=n_trials,
        mean_return=sum(totals) / len(totals),
        median_return=_percentile(totals, 0.50),
        p05_return=_percentile(totals, 0.05),
        p95_return=_percentile(totals, 0.95),
        agent_percentile=beaten / len(totals),
    )


def _percentile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolated quantile of an already-sorted list."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = q * (len(sorted_values) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return sorted_values[low]
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def cost_per_alpha_point(alpha: float | None, cost_usd: float | None) -> float | None:
    """Dollars of LLM spend per percentage point of alpha earned.

    The metric that makes an agent framework's cost legible: two configurations
    with the same alpha are not equally good if one costs ten times more to
    produce it.

    Deliberately expressed this way round rather than as "alpha per $1,000
    spent". The latter reads as a rate and invites multiplying up — a $10 run
    that earned 27% alpha would be reported as 2,658% per $1,000, which is not
    a thing that would happen. Cost per point makes the same comparison without
    implying the result scales with spend.

    Returns ``None`` when spend is unknown (an unpriced model), zero, or when
    alpha is not positive — there is no meaningful price for alpha that was
    never earned.
    """
    if alpha is None or alpha <= 0:
        return None
    if not cost_usd or cost_usd <= 0:
        return None
    return cost_usd / (alpha * 100.0)


def summarize(
    result: SimulationResult,
    benchmark_equity: pd.Series | None = None,
) -> dict:
    """Bundle a simulation's metrics with alpha against a benchmark curve."""
    metrics = compute_metrics(result.equity)
    payload = metrics.as_dict()
    payload["turnover"] = result.turnover
    payload["total_costs"] = result.total_costs
    payload["n_trades"] = len(result.trades)

    if benchmark_equity is not None and len(benchmark_equity) >= 2:
        bench = compute_metrics(benchmark_equity)
        payload["benchmark_total_return"] = bench.total_return
        payload["alpha"] = metrics.total_return - bench.total_return
    else:
        payload["benchmark_total_return"] = None
        payload["alpha"] = None

    return payload
