"""Offline environment: historical bars -> (state, action-rewards) transitions.

Full-feedback construction: because forward returns are known offline, the
reward of *every* action at each step is computable — BUY earns the
cost-adjusted forward return, SELL its negation (also paying costs), HOLD
earns zero. No lookahead leaks into the state: the state at step ``i`` is
built from bars <= i; only the *reward* peeks ahead, which is the entire
point of offline evaluation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from tradingagents.contracts import OHLCVBar
from tradingagents.pro.rl.features import MIN_BARS, RLState, state_from_bars

ACTIONS = ("BUY", "SELL", "HOLD")


@dataclass(frozen=True)
class Transition:
    state: RLState
    rewards: dict[str, float]  # action -> reward (full feedback)
    next_state: RLState


def build_transitions(
    bars: Sequence[OHLCVBar],
    horizon: int = 5,
    window: int = 120,
    cost_bps: float = 4.0,  # round-trip cost estimate
) -> list[Transition]:
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    if window < MIN_BARS:
        raise ValueError(f"window must be >= {MIN_BARS}")
    bars = list(bars)
    transitions = []
    cost = cost_bps / 10_000
    for i in range(window - 1, len(bars) - horizon):
        visible = bars[max(0, i + 1 - window) : i + 1]
        state = state_from_bars(visible)
        forward = (bars[i + horizon].close - bars[i].close) / bars[i].close
        next_visible = bars[max(0, i + 1 + horizon - window) : i + 1 + horizon]
        transitions.append(Transition(
            state=state,
            rewards={"BUY": forward - cost, "SELL": -forward - cost, "HOLD": 0.0},
            next_state=state_from_bars(next_visible),
        ))
    if not transitions:
        raise ValueError("bar series too short for the given window/horizon")
    return transitions
