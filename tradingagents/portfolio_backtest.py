"""Cross-sectional portfolio accounting for historical TradingAgents signals."""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import asdict, dataclass

import pandas as pd

RATING_SCORES = {
    "buy": 1.0,
    "overweight": 0.5,
    "hold": 0.0,
    "underweight": -0.5,
    "sell": -1.0,
}


@dataclass(frozen=True)
class PortfolioMetrics:
    start_date: str
    end_date: str
    observations: int
    rebalances: int
    total_return: float
    benchmark_return: float
    excess_return: float
    annualized_return: float | None
    annualized_volatility: float | None
    sharpe: float | None
    max_drawdown: float
    total_turnover: float
    average_gross_exposure: float
    average_net_exposure: float
    estimated_trading_cost: float
    estimated_borrow_cost: float


@dataclass(frozen=True)
class PortfolioResult:
    metrics: PortfolioMetrics
    equity: list[dict]


def rating_score(action: str) -> float:
    try:
        return RATING_SCORES[action.strip().lower()]
    except KeyError as exc:
        raise ValueError(f"unsupported portfolio rating {action!r}") from exc


def aggregate_signal_records(records: list[dict], tickers: list[str]) -> dict[str, dict[str, float]]:
    """Average repeated LLM ratings into one score per ticker and decision date."""
    wanted = {ticker.upper() for ticker in tickers}
    grouped: dict[tuple[str, str], list[float]] = {}
    for record in records:
        ticker = record.get("ticker", "").upper()
        date = record.get("decision_date")
        action = record.get("action")
        if ticker not in wanted or not date or not action:
            continue
        grouped.setdefault((date, ticker), []).append(rating_score(action))
    by_date: dict[str, dict[str, float]] = {}
    for (date, ticker), scores in grouped.items():
        by_date.setdefault(date, {})[ticker] = statistics.fmean(scores)
    return by_date


def _allocate_capped(raw: dict[str, float], budget: float, cap: float) -> dict[str, float]:
    """Water-fill positive scores into a budget while respecting a hard cap."""
    active = {ticker: value for ticker, value in raw.items() if value > 0}
    weights = dict.fromkeys(raw, 0.0)
    remaining = max(0.0, budget)
    while active and remaining > 1e-12:
        total = sum(active.values())
        provisional = {
            ticker: remaining * value / total for ticker, value in active.items()
        }
        capped = [ticker for ticker, value in provisional.items() if value > cap]
        if not capped:
            weights.update(provisional)
            break
        for ticker in capped:
            weights[ticker] = cap
            remaining -= cap
            active.pop(ticker)
    return weights


def target_weights(
    scores: dict[str, float],
    *,
    mode: str = "long-only",
    gross_limit: float = 1.0,
    max_weight: float = 0.25,
) -> dict[str, float]:
    """Convert rating scores into constrained portfolio target weights."""
    if gross_limit <= 0:
        raise ValueError("gross_limit must be positive")
    if not 0 < max_weight <= gross_limit:
        raise ValueError("max_weight must be positive and no greater than gross_limit")
    if mode not in {"long-only", "long-short", "market-neutral"}:
        raise ValueError(f"unsupported portfolio mode {mode!r}")
    clean = {ticker.upper(): max(-1.0, min(1.0, float(value))) for ticker, value in scores.items()}
    if mode == "long-only":
        return _allocate_capped(
            {ticker: max(score, 0.0) for ticker, score in clean.items()},
            gross_limit,
            max_weight,
        )

    if mode == "market-neutral":
        mean = statistics.fmean(clean.values()) if clean else 0.0
        clean = {ticker: score - mean for ticker, score in clean.items()}
        long_budget = short_budget = gross_limit / 2.0
    else:
        positive_total = sum(max(score, 0.0) for score in clean.values())
        negative_total = sum(max(-score, 0.0) for score in clean.values())
        total = positive_total + negative_total
        if total == 0:
            return dict.fromkeys(clean, 0.0)
        long_budget = gross_limit * positive_total / total
        short_budget = gross_limit - long_budget

    longs = _allocate_capped(
        {ticker: max(score, 0.0) for ticker, score in clean.items()},
        long_budget,
        max_weight,
    )
    shorts = _allocate_capped(
        {ticker: max(-score, 0.0) for ticker, score in clean.items()},
        short_budget,
        max_weight,
    )
    if mode == "market-neutral":
        long_total = sum(longs.values())
        short_total = sum(shorts.values())
        matched = min(long_total, short_total)
        if matched <= 0:
            return dict.fromkeys(clean, 0.0)
        if long_total > matched:
            longs = {
                ticker: weight * matched / long_total for ticker, weight in longs.items()
            }
        if short_total > matched:
            shorts = {
                ticker: weight * matched / short_total for ticker, weight in shorts.items()
            }
    return {ticker: longs.get(ticker, 0.0) - shorts.get(ticker, 0.0) for ticker in clean}


def _date_rows(frame: pd.DataFrame) -> dict[str, pd.Series]:
    return {pd.Timestamp(index).date().isoformat(): row for index, row in frame.iterrows()}


def _max_drawdown(values: list[float]) -> float:
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        worst = min(worst, value / peak - 1.0)
    return worst


def simulate_portfolio(
    *,
    signals: dict[str, dict[str, float]],
    prices: dict[str, pd.DataFrame],
    benchmark_prices: pd.DataFrame,
    mode: str = "long-only",
    gross_limit: float = 1.0,
    max_weight: float = 0.25,
    trading_cost_bps: float = 5.0,
    slippage_bps: float = 5.0,
    annual_borrow_bps: float = 300.0,
    tail_sessions: int = 5,
    require_complete_signals: bool = True,
) -> PortfolioResult:
    """Simulate synchronized next-open rebalancing with cash and drifting weights.

    Returns are marked open-to-open. A decision dated D becomes a target at the
    first benchmark session strictly after D, so D's closing bar and captured
    after-close media cannot trade at a price that preceded the decision.
    """
    if not signals:
        raise ValueError("at least one decision date is required")
    if tail_sessions < 1:
        raise ValueError("tail_sessions must be >= 1")
    if min(trading_cost_bps, slippage_bps, annual_borrow_bps) < 0:
        raise ValueError("cost, slippage, and borrow rates must be >= 0")
    universe = sorted(prices)
    if not universe:
        raise ValueError("at least one ticker price frame is required")
    benchmark = _date_rows(benchmark_prices)
    sessions = sorted(benchmark)
    price_rows = {ticker: _date_rows(frame) for ticker, frame in prices.items()}

    targets_by_entry: dict[str, dict[str, float]] = {}
    for decision_date, date_scores in sorted(signals.items()):
        missing = set(universe) - set(date_scores)
        if missing and require_complete_signals:
            raise ValueError(
                f"incomplete cross-section on {decision_date}: missing {', '.join(sorted(missing))}"
            )
        next_sessions = [date for date in sessions if date > decision_date]
        if not next_sessions:
            continue
        targets_by_entry[next_sessions[0]] = target_weights(
            {ticker: date_scores.get(ticker, 0.0) for ticker in universe},
            mode=mode,
            gross_limit=gross_limit,
            max_weight=max_weight,
        )
    if not targets_by_entry:
        raise ValueError("no decision has a later executable benchmark session")

    first_session = min(targets_by_entry)
    last_rebalance = max(targets_by_entry)
    first_index = sessions.index(first_session)
    final_index = min(sessions.index(last_rebalance) + tail_sessions, len(sessions) - 1)
    simulation_sessions = sessions[first_index:final_index + 1]
    for ticker, rows in price_rows.items():
        missing = [date for date in simulation_sessions if date not in rows]
        if missing:
            raise ValueError(
                f"{ticker} lacks open prices for portfolio session(s): {', '.join(missing[:3])}"
            )

    nav = 1.0
    benchmark_nav = 1.0
    weights = dict.fromkeys(universe, 0.0)
    equity = []
    total_turnover = 0.0
    total_trading_cost = 0.0
    total_borrow_cost = 0.0
    rebalances = 0
    previous_date = None
    interval_returns = []
    for date in simulation_sessions:
        interval_return = 0.0
        benchmark_return = 0.0
        borrow_cost = 0.0
        if previous_date is not None:
            asset_returns = {
                ticker: float(price_rows[ticker][date]["Open"])
                / float(price_rows[ticker][previous_date]["Open"]) - 1.0
                for ticker in universe
            }
            interval_return = sum(weights[ticker] * asset_returns[ticker] for ticker in universe)
            short_exposure = sum(abs(weight) for weight in weights.values() if weight < 0)
            borrow_cost = short_exposure * annual_borrow_bps / 10_000 / 252
            benchmark_return = float(benchmark[date]["Open"]) / \
                float(benchmark[previous_date]["Open"]) - 1.0
            nav *= 1.0 + interval_return - borrow_cost
            benchmark_nav *= 1.0 + benchmark_return
            denominator = 1.0 + interval_return - borrow_cost
            if denominator <= 0:
                raise ValueError("portfolio equity was exhausted")
            weights = {
                ticker: weights[ticker] * (1.0 + asset_returns[ticker]) / denominator
                for ticker in universe
            }
            total_borrow_cost += borrow_cost

        turnover = 0.0
        trading_cost = 0.0
        if date in targets_by_entry:
            target = targets_by_entry[date]
            turnover = sum(abs(target[ticker] - weights[ticker]) for ticker in universe)
            trading_cost = turnover * (trading_cost_bps + slippage_bps) / 10_000
            nav *= 1.0 - trading_cost
            weights = target
            total_turnover += turnover
            total_trading_cost += trading_cost
            rebalances += 1

        net_period_return = (1.0 + interval_return - borrow_cost) * (1.0 - trading_cost) - 1.0
        if previous_date is not None:
            interval_returns.append(net_period_return)
        equity.append({
            "date": date,
            "nav": nav,
            "benchmark_nav": benchmark_nav,
            "period_return": net_period_return,
            "benchmark_period_return": benchmark_return,
            "turnover": turnover,
            "trading_cost": trading_cost,
            "borrow_cost": borrow_cost,
            "gross_exposure": sum(abs(weight) for weight in weights.values()),
            "net_exposure": sum(weights.values()),
            "cash_weight": 1.0 - sum(weights.values()),
            "weights": dict(weights),
        })
        previous_date = date

    periods = max(0, len(simulation_sessions) - 1)
    annualized_return = nav ** (252 / periods) - 1.0 if periods and nav > 0 else None
    volatility = (
        statistics.stdev(interval_returns) * math.sqrt(252)
        if len(interval_returns) >= 2 else None
    )
    sharpe = (
        statistics.fmean(interval_returns) / statistics.stdev(interval_returns) * math.sqrt(252)
        if len(interval_returns) >= 2 and statistics.stdev(interval_returns) > 0 else None
    )
    metrics = PortfolioMetrics(
        start_date=simulation_sessions[0],
        end_date=simulation_sessions[-1],
        observations=len(simulation_sessions),
        rebalances=rebalances,
        total_return=nav - 1.0,
        benchmark_return=benchmark_nav - 1.0,
        excess_return=nav - benchmark_nav,
        annualized_return=annualized_return,
        annualized_volatility=volatility,
        sharpe=sharpe,
        max_drawdown=_max_drawdown([1.0, *[row["nav"] for row in equity]]),
        total_turnover=total_turnover,
        average_gross_exposure=statistics.fmean(row["gross_exposure"] for row in equity),
        average_net_exposure=statistics.fmean(row["net_exposure"] for row in equity),
        estimated_trading_cost=total_trading_cost,
        estimated_borrow_cost=total_borrow_cost,
    )
    return PortfolioResult(metrics=metrics, equity=equity)


def portfolio_result_dict(result: PortfolioResult) -> dict:
    return {"metrics": asdict(result.metrics), "equity": result.equity}


def _rank(values: list[float]) -> list[float]:
    """Average ranks with ties, implemented locally to keep diagnostics portable."""
    ordered = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    position = 0
    while position < len(ordered):
        end = position + 1
        while end < len(ordered) and values[ordered[end]] == values[ordered[position]]:
            end += 1
        average = (position + 1 + end) / 2.0
        for index in ordered[position:end]:
            ranks[index] = average
        position = end
    return ranks


def _correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    left_var = sum((value - left_mean) ** 2 for value in left)
    right_var = sum((value - right_mean) ** 2 for value in right)
    if left_var <= 0 or right_var <= 0:
        return None
    covariance = sum(
        (lvalue - left_mean) * (rvalue - right_mean)
        for lvalue, rvalue in zip(left, right, strict=True)
    )
    return covariance / math.sqrt(left_var * right_var)


def beta_attribution(result: PortfolioResult) -> dict:
    """Decompose realized returns into benchmark beta and residual alpha."""
    portfolio_returns = [
        row["period_return"] for row in result.equity[1:]
        if row.get("period_return") is not None
    ]
    benchmark_returns = [
        row["benchmark_period_return"] for row in result.equity[1:]
        if row.get("benchmark_period_return") is not None
    ]
    if len(portfolio_returns) < 2 or len(portfolio_returns) != len(benchmark_returns):
        return {
            "observations": len(portfolio_returns),
            "beta": None,
            "annualized_residual_alpha": None,
            "correlation": None,
        }
    benchmark_mean = statistics.fmean(benchmark_returns)
    benchmark_variance = sum(
        (value - benchmark_mean) ** 2 for value in benchmark_returns
    )
    if benchmark_variance <= 0:
        beta = None
        alpha = None
    else:
        portfolio_mean = statistics.fmean(portfolio_returns)
        covariance = sum(
            (portfolio - portfolio_mean) * (benchmark - benchmark_mean)
            for portfolio, benchmark in zip(
                portfolio_returns, benchmark_returns, strict=True
            )
        )
        beta = covariance / benchmark_variance
        alpha = (portfolio_mean - beta * benchmark_mean) * 252
    return {
        "observations": len(portfolio_returns),
        "beta": beta,
        "annualized_residual_alpha": alpha,
        "correlation": _correlation(portfolio_returns, benchmark_returns),
    }


def cross_sectional_rank_ic(
    signals: dict[str, dict[str, float]],
    prices: dict[str, pd.DataFrame],
    *,
    holding_sessions: int = 5,
) -> dict:
    """Mean per-date Spearman IC using next-open-to-horizon-close returns."""
    if holding_sessions < 1:
        raise ValueError("holding_sessions must be >= 1")
    price_rows = {ticker: _date_rows(frame) for ticker, frame in prices.items()}
    price_dates = {
        ticker: sorted(rows) for ticker, rows in price_rows.items()
    }
    per_date = []
    for decision_date, scores in sorted(signals.items()):
        score_values = []
        future_returns = []
        for ticker, score in sorted(scores.items()):
            dates = price_dates.get(ticker, [])
            later = [date for date in dates if date > decision_date]
            if len(later) < holding_sessions:
                continue
            entry_date = later[0]
            exit_date = later[holding_sessions - 1]
            entry = float(price_rows[ticker][entry_date]["Open"])
            exit_price = float(price_rows[ticker][exit_date]["Close"])
            score_values.append(float(score))
            future_returns.append(exit_price / entry - 1.0)
        # Two points always have |rho|=1 and are not a meaningful cross-section.
        if len(score_values) < 3:
            continue
        correlation = _correlation(_rank(score_values), _rank(future_returns))
        if correlation is not None:
            per_date.append({
                "date": decision_date,
                "rank_ic": correlation,
                "assets": len(score_values),
            })
    return {
        "mean_rank_ic": (
            statistics.fmean(row["rank_ic"] for row in per_date) if per_date else None
        ),
        "dates": len(per_date),
        "per_date": per_date,
    }


def permutation_placebo(
    *,
    signals: dict[str, dict[str, float]],
    prices: dict[str, pd.DataFrame],
    benchmark_prices: pd.DataFrame,
    observed_return: float,
    trials: int = 100,
    seed: int = 1729,
    simulation_kwargs: dict | None = None,
) -> dict:
    """Shuffle ticker assignments within each date as a stock-selection placebo."""
    if trials < 0:
        raise ValueError("trials must be >= 0")
    if trials == 0:
        return {"trials": 0, "seed": seed, "returns": [], "empirical_p_value": None}
    rng = random.Random(seed)
    returns = []
    for _ in range(trials):
        permuted = {}
        for date, date_scores in signals.items():
            tickers = sorted(date_scores)
            values = [date_scores[ticker] for ticker in tickers]
            rng.shuffle(values)
            permuted[date] = dict(zip(tickers, values, strict=True))
        result = simulate_portfolio(
            signals=permuted,
            prices=prices,
            benchmark_prices=benchmark_prices,
            **(simulation_kwargs or {}),
        )
        returns.append(result.metrics.total_return)
    # One-sided: how often arbitrary ticker assignment matches or beats us.
    p_value = (1 + sum(value >= observed_return for value in returns)) / (trials + 1)
    ordered = sorted(returns)
    return {
        "trials": trials,
        "seed": seed,
        "mean_total_return": statistics.fmean(returns),
        "p95_total_return": ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))],
        "empirical_p_value": p_value,
    }


def baseline_portfolios(
    *,
    signals: dict[str, dict[str, float]],
    prices: dict[str, pd.DataFrame],
    benchmark_prices: pd.DataFrame,
    observed_return: float,
    momentum_lookback_sessions: int = 20,
    simulation_kwargs: dict | None = None,
) -> dict:
    """Evaluate equal-weight and price-momentum baselines on identical dates/costs."""
    if momentum_lookback_sessions < 1:
        raise ValueError("momentum_lookback_sessions must be >= 1")
    dates = sorted(signals)
    universe = sorted(prices)
    equal_weight = {date: dict.fromkeys(universe, 1.0) for date in dates}
    rows = {ticker: _date_rows(frame) for ticker, frame in prices.items()}
    momentum = {}
    for decision_date in dates:
        scores = {}
        for ticker in universe:
            eligible = [date for date in sorted(rows[ticker]) if date <= decision_date]
            if len(eligible) <= momentum_lookback_sessions:
                scores[ticker] = 0.0
                continue
            current = float(rows[ticker][eligible[-1]]["Close"])
            prior = float(rows[ticker][eligible[-1 - momentum_lookback_sessions]]["Close"])
            scores[ticker] = current / prior - 1.0
        momentum[decision_date] = scores

    payload = {}
    for name, baseline_signals in (
        ("equal_weight", equal_weight),
        (f"price_momentum_{momentum_lookback_sessions}s", momentum),
    ):
        result = simulate_portfolio(
            signals=baseline_signals,
            prices=prices,
            benchmark_prices=benchmark_prices,
            **(simulation_kwargs or {}),
        )
        payload[name] = {
            "total_return": result.metrics.total_return,
            "max_drawdown": result.metrics.max_drawdown,
            "total_turnover": result.metrics.total_turnover,
            "observed_minus_baseline_return": observed_return - result.metrics.total_return,
        }
    return payload


def portfolio_diagnostics(
    *,
    result: PortfolioResult,
    signals: dict[str, dict[str, float]],
    prices: dict[str, pd.DataFrame],
    benchmark_prices: pd.DataFrame,
    holding_sessions: int,
    placebo_trials: int = 100,
    simulation_kwargs: dict | None = None,
) -> dict:
    """Leakage-resistant diagnostics kept alongside every portfolio result."""
    return {
        "beta_attribution": beta_attribution(result),
        "baselines": baseline_portfolios(
            signals=signals,
            prices=prices,
            benchmark_prices=benchmark_prices,
            observed_return=result.metrics.total_return,
            simulation_kwargs=simulation_kwargs,
        ),
        "cross_sectional_rank_ic": cross_sectional_rank_ic(
            signals, prices, holding_sessions=holding_sessions
        ),
        "ticker_permutation_placebo": permutation_placebo(
            signals=signals,
            prices=prices,
            benchmark_prices=benchmark_prices,
            observed_return=result.metrics.total_return,
            trials=placebo_trials,
            simulation_kwargs=simulation_kwargs,
        ),
    }
