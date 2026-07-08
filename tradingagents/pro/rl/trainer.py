"""Training and evaluation for the tabular policy.

Training consumes offline transitions (full feedback: every action's
reward is applied per state). Evaluation follows the greedy policy over a
held-out bar range and scores it with the Phase 7 performance metrics —
the objectives the spec names (Sharpe, Sortino, profit factor, max
drawdown, win rate, expectancy).
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from tradingagents.contracts import OHLCVBar
from tradingagents.pro.backtest.metrics import PerformanceReport, performance_report
from tradingagents.pro.rl.env import ACTIONS, build_transitions
from tradingagents.pro.rl.features import state_from_bars
from tradingagents.pro.rl.policy import QTablePolicy


@dataclass(frozen=True)
class TrainingReport:
    transitions: int
    epochs: int
    states_seen: int
    eval_report: PerformanceReport | None
    baseline_hold_return: float | None


def train_q_policy(
    bars: Sequence[OHLCVBar],
    horizon: int = 5,
    window: int = 120,
    cost_bps: float = 4.0,
    epochs: int = 3,
    alpha: float = 0.1,
    gamma: float = 0.0,
    eval_fraction: float = 0.25,
    seed: int = 7,
) -> tuple[QTablePolicy, TrainingReport]:
    """Train on the leading (1 - eval_fraction) of bars, evaluate greedily
    on the held-out tail. Shuffling is seeded; results are reproducible."""
    if not 0 <= eval_fraction < 1:
        raise ValueError("eval_fraction must be in [0, 1)")
    bars = list(bars)
    split = len(bars) if eval_fraction == 0 else int(len(bars) * (1 - eval_fraction))
    train_bars, eval_bars = bars[:split], bars[split - window :]

    transitions = build_transitions(train_bars, horizon, window, cost_bps)
    policy = QTablePolicy(alpha=alpha, gamma=gamma)
    rng = random.Random(seed)
    for _ in range(max(1, epochs)):
        order = list(transitions)
        rng.shuffle(order)
        for t in order:
            for action in ACTIONS:
                policy.update(t.state, action, t.rewards[action], t.next_state)

    eval_report = None
    baseline = None
    if eval_fraction > 0 and len(eval_bars) >= window + horizon:
        eval_report = evaluate_policy(policy, eval_bars, horizon, window, cost_bps)
        baseline = (eval_bars[-1].close - eval_bars[window - 1].close) / eval_bars[
            window - 1
        ].close
    return policy, TrainingReport(
        transitions=len(transitions),
        epochs=max(1, epochs),
        states_seen=policy.n_states,
        eval_report=eval_report,
        baseline_hold_return=baseline,
    )


def evaluate_policy(
    policy: QTablePolicy,
    bars: Sequence[OHLCVBar],
    horizon: int = 5,
    window: int = 120,
    cost_bps: float = 4.0,
    initial_equity: float = 100_000.0,
) -> PerformanceReport:
    """Follow the greedy policy over non-overlapping horizon steps."""
    bars = list(bars)
    equity = initial_equity
    curve = [equity]
    cost = cost_bps / 10_000
    i = window - 1
    while i < len(bars) - horizon:
        state = state_from_bars(bars[max(0, i + 1 - window) : i + 1])
        action, _ = policy.best(state)
        forward = (bars[i + horizon].close - bars[i].close) / bars[i].close
        if action == "BUY":
            equity *= 1 + forward - cost
        elif action == "SELL":
            equity *= 1 - forward - cost
        curve.append(equity)
        i += horizon
    return performance_report(curve, [], periods_per_year=252 // max(1, horizon))
