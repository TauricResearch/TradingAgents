"""Turn a stream of agent ratings into an equity curve.

This module is deliberately free of network and LLM calls: it takes decisions
(from :mod:`~tradingagents.backtest.store`) and a price frame, and returns what
a portfolio following those decisions would have done. That makes it cheap to
re-run — changing the weight map or the cost model re-scores a finished
backtest in milliseconds — and it makes every rule below testable against a
hand-built price series.

Two execution rules carry most of the credibility of the result:

* **Fills happen at the next bar's open, never the decision bar's close.** A
  decision dated D is produced from data through D, so filling it at D's close
  would be a look-ahead the rest of the framework works hard to prevent. The
  same rule handles a decision that lands on a market holiday: it fills at the
  next bar that actually trades.
* **Every rebalance pays commission and slippage** on the traded notional. An
  agent that flips between Buy and Sell every week should look expensive,
  because it is.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from tradingagents.agents.utils.rating import RATING_REVIEW

# Target portfolio weight per 5-tier rating. Sell/Underweight are negative so a
# long/short run can act on them; under the default long-only mode they clamp to
# flat (see ``PortfolioConfig.allow_short``).
DEFAULT_WEIGHTS: dict[str, float] = {
    "Buy": 1.0,
    "Overweight": 0.5,
    "Hold": 0.0,
    "Underweight": -0.5,
    "Sell": -1.0,
}

# Traded notional below this is treated as no trade, so floating-point dust does
# not generate an endless stream of ~zero-value rebalances (each of which would
# otherwise accrue commission).
_MIN_TRADE_NOTIONAL = 1e-6


@dataclass
class PortfolioConfig:
    """Execution and sizing rules for a simulation.

    ``hold_policy`` decides what a ``Hold`` rating does, and it is a real
    modelling choice rather than a detail. The Research Manager prompt defines
    Hold as "maintaining the current position", so the default ``"carry"``
    keeps the previous weight and a Hold after a Buy stays long. Setting it to
    ``"flat"`` instead reads Hold as a neutral target and uses the weight map's
    entry (0.0 by default), which exits to cash. Both are defensible; the
    scorecard records which one produced the numbers.

    ``REVIEW`` (#1170) is never tradeable under either policy — it means the
    decision had no parseable rating, so the position carries and the occurrence
    is counted separately in the scorecard.
    """

    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    hold_policy: str = "carry"
    allow_short: bool = False
    commission_bps: float = 1.0
    slippage_bps: float = 5.0
    initial_cash: float = 100_000.0

    def __post_init__(self):
        if self.hold_policy not in ("carry", "flat"):
            raise ValueError(
                f"hold_policy must be 'carry' or 'flat', got {self.hold_policy!r}"
            )
        if self.initial_cash <= 0:
            raise ValueError(f"initial_cash must be > 0, got {self.initial_cash}")
        if self.commission_bps < 0 or self.slippage_bps < 0:
            raise ValueError("commission_bps and slippage_bps must be >= 0")

    @property
    def cost_rate(self) -> float:
        """Round-trip-per-side cost as a fraction of traded notional."""
        return (self.commission_bps + self.slippage_bps) / 10_000.0


@dataclass
class SimulationResult:
    """Output of :func:`simulate`."""

    equity: pd.Series
    weights: pd.Series
    cash: pd.Series
    trades: list[dict]
    total_costs: float
    traded_notional: float

    @property
    def turnover(self) -> float:
        """Traded notional as a multiple of average equity over the run."""
        avg_equity = float(self.equity.mean()) if len(self.equity) else 0.0
        if avg_equity <= 0:
            return 0.0
        return self.traded_notional / avg_equity


def target_weight(
    rating: str | None, previous: float, config: PortfolioConfig
) -> float:
    """Resolve a rating to a target weight given the weight currently held.

    An unknown rating carries the previous weight rather than defaulting to
    flat: silently liquidating on a string the map does not recognise would be
    an invisible trading decision made by a typo.
    """
    if rating is None or rating == RATING_REVIEW:
        return previous
    if rating == "Hold" and config.hold_policy == "carry":
        return previous
    if rating not in config.weights:
        return previous

    weight = config.weights[rating]
    if not config.allow_short:
        weight = max(weight, 0.0)
    return weight


def _fill_bar_for(decision_date: str, index: pd.DatetimeIndex) -> int | None:
    """Position of the first bar strictly after ``decision_date``.

    Strictly after, because a decision dated D is built from data through D and
    can only be acted on at the next open. Returns ``None`` when no such bar
    exists, i.e. the decision falls after the end of the price history and is
    never filled.
    """
    position = index.searchsorted(pd.Timestamp(decision_date), side="right")
    return int(position) if position < len(index) else None


def simulate(
    decisions: list[tuple[str, str | None]],
    prices: pd.DataFrame,
    config: PortfolioConfig | None = None,
) -> SimulationResult:
    """Simulate a single-ticker sleeve following ``decisions``.

    Args:
        decisions: ``(date, rating)`` pairs for one ticker, in any order.
        prices: Daily bars with a ``DatetimeIndex`` and ``Open``/``Close``
            columns, covering the period to score.
        config: Execution rules; defaults to :class:`PortfolioConfig`.

    Returns:
        A :class:`SimulationResult` whose ``equity`` is marked to each bar's
        close, starting at ``config.initial_cash``.

    Raises:
        ValueError: If ``prices`` lacks the required columns or index type.
            Scoring against a malformed frame would produce a plausible-looking
            equity curve built on nothing, so this fails loudly.
    """
    config = config or PortfolioConfig()

    if not isinstance(prices.index, pd.DatetimeIndex):
        raise ValueError("prices must be indexed by a DatetimeIndex")
    missing = {"Open", "Close"} - set(prices.columns)
    if missing:
        raise ValueError(f"prices is missing required column(s): {sorted(missing)}")

    # Drop bars with no usable price rather than propagating NaN through the
    # equity curve, and work on a normalized (tz-naive, midnight) index so
    # comparisons against plain yyyy-mm-dd decision dates line up.
    prices = prices.dropna(subset=["Open", "Close"])
    index = pd.DatetimeIndex(prices.index).tz_localize(None).normalize()
    prices = prices.set_axis(index)

    if len(prices) == 0:
        empty = pd.Series(dtype="float64")
        return SimulationResult(empty, empty, empty, [], 0.0, 0.0)

    # Map each decision to the bar it fills on. When several decisions land on
    # the same fill bar (e.g. two dates across a weekend), the most recent one
    # wins — it saw strictly more information.
    # Sorted by date only: sorting whole tuples would compare ratings when two
    # decisions share a date, and a ``None`` rating (which this function
    # explicitly accepts) is not orderable against a string.
    fills: dict[int, tuple[str, str | None]] = {}
    for date, rating in sorted(decisions, key=lambda d: d[0]):
        bar = _fill_bar_for(date, index)
        if bar is not None:
            fills[bar] = (date, rating)

    cash = config.initial_cash
    shares = 0.0
    weight = 0.0
    total_costs = 0.0
    traded_notional = 0.0
    trades: list[dict] = []
    equity_points: list[float] = []
    weight_points: list[float] = []
    cash_points: list[float] = []

    opens = prices["Open"].to_numpy(dtype="float64")
    closes = prices["Close"].to_numpy(dtype="float64")

    for bar in range(len(prices)):
        open_price = opens[bar]

        if bar in fills and open_price > 0:
            date, rating = fills[bar]
            new_weight = target_weight(rating, weight, config)
            equity_at_open = cash + shares * open_price

            # Size against equity *net of* the trade's cost. Sizing against gross
            # equity would spend the whole balance on stock and then pay the
            # commission out of cash that is no longer there, leaving a
            # long-only sleeve holding slightly more than 100% on negative cash.
            # One refinement pass converges to well under a cent on a realistic
            # cost rate, so no iteration is needed.
            gross_delta = new_weight * equity_at_open - shares * open_price
            budget = equity_at_open - abs(gross_delta) * config.cost_rate
            delta_value = new_weight * budget - shares * open_price

            if abs(delta_value) > _MIN_TRADE_NOTIONAL:
                cost = abs(delta_value) * config.cost_rate
                cash -= delta_value + cost
                shares += delta_value / open_price
                total_costs += cost
                traded_notional += abs(delta_value)
                trades.append({
                    "decision_date": date,
                    "fill_date": index[bar].strftime("%Y-%m-%d"),
                    "rating": rating,
                    "from_weight": weight,
                    "to_weight": new_weight,
                    "fill_price": open_price,
                    "notional": abs(delta_value),
                    "cost": cost,
                })
            weight = new_weight

        equity_points.append(cash + shares * closes[bar])
        weight_points.append(weight)
        cash_points.append(cash)

    return SimulationResult(
        equity=pd.Series(equity_points, index=index, name="equity"),
        weights=pd.Series(weight_points, index=index, name="weight"),
        cash=pd.Series(cash_points, index=index, name="cash"),
        trades=trades,
        total_costs=total_costs,
        traded_notional=traded_notional,
    )


def simulate_multi(
    decisions_by_ticker: dict[str, list[tuple[str, str | None]]],
    prices_by_ticker: dict[str, pd.DataFrame],
    config: PortfolioConfig | None = None,
) -> tuple[SimulationResult, dict[str, SimulationResult]]:
    """Simulate several tickers as equal-capital sleeves and combine them.

    Capital is split evenly across tickers up front and each sleeve is run
    independently — there is no rebalancing between sleeves and no cross-ticker
    risk budgeting. That is a real simplification, and the honest one for a
    first harness: it keeps the reported alpha attributable to the agent's
    per-ticker calls rather than to an allocation scheme nobody asked for.

    Sleeve curves are combined on the union of their dates, forward-filling each
    sleeve over dates it has no bar for (a holiday on one exchange but not
    another), so the combined curve never dips just because one market was shut.

    Returns:
        ``(combined, per_ticker)``.
    """
    config = config or PortfolioConfig()
    tickers = sorted(t for t in decisions_by_ticker if t in prices_by_ticker)
    if not tickers:
        empty = pd.Series(dtype="float64")
        return SimulationResult(empty, empty, empty, [], 0.0, 0.0), {}

    sleeve_config = PortfolioConfig(
        weights=dict(config.weights),
        hold_policy=config.hold_policy,
        allow_short=config.allow_short,
        commission_bps=config.commission_bps,
        slippage_bps=config.slippage_bps,
        initial_cash=config.initial_cash / len(tickers),
    )

    per_ticker = {
        ticker: simulate(
            decisions_by_ticker[ticker], prices_by_ticker[ticker], sleeve_config
        )
        for ticker in tickers
    }

    curves = [r.equity for r in per_ticker.values() if len(r.equity)]
    if not curves:
        empty = pd.Series(dtype="float64")
        return SimulationResult(empty, empty, empty, [], 0.0, 0.0), per_ticker

    combined_index = curves[0].index
    for curve in curves[1:]:
        combined_index = combined_index.union(curve.index)

    # Forward-fill each sleeve across the union, then back-fill the leading gap
    # with that sleeve's starting capital so a ticker whose history begins late
    # contributes its idle cash rather than NaN.
    aligned = [
        curve.reindex(combined_index).ffill().fillna(sleeve_config.initial_cash)
        for curve in curves
    ]
    combined_equity = sum(aligned)

    # Weights combine as the capital-weighted average exposure across sleeves.
    weight_curves = [
        r.weights.reindex(combined_index).ffill().fillna(0.0)
        for r in per_ticker.values()
        if len(r.weights)
    ]
    combined_weights = sum(weight_curves) / len(weight_curves)

    cash_curves = [
        r.cash.reindex(combined_index).ffill().fillna(sleeve_config.initial_cash)
        for r in per_ticker.values()
        if len(r.cash)
    ]
    combined_cash = sum(cash_curves)

    combined = SimulationResult(
        equity=combined_equity.rename("equity"),
        weights=combined_weights.rename("weight"),
        cash=combined_cash.rename("cash"),
        trades=sorted(
            (t for r in per_ticker.values() for t in r.trades),
            key=lambda t: t["fill_date"],
        ),
        total_costs=sum(r.total_costs for r in per_ticker.values()),
        traded_notional=sum(r.traded_notional for r in per_ticker.values()),
    )
    return combined, per_ticker
