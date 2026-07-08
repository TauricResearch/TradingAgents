"""RLAdvisor: trained policy -> advisory MetricReadings.

The advisory path is structural (ADR-0025): the advisor's output enters the
pipeline as pre-computed metrics consumed by the roster's
``reinforcement_learning`` evidence agent — one voice among 59, subject to
the same debate, gates, and votes. There is no route from a policy output
to execution that does not pass the full chain.

An undertrained state (below ``min_visits``) yields no advice at all: the
agent abstains rather than whisper noise.
"""

from __future__ import annotations

from collections.abc import Sequence

from tradingagents.contracts import MetricReading, OHLCVBar
from tradingagents.pro.rl.features import MIN_BARS, state_from_bars
from tradingagents.pro.rl.policy import PolicyProtocol

RL_SOURCE = "rl_advisor"


class RLAdvisor:
    def __init__(self, policy: PolicyProtocol, min_visits: int = 10):
        if min_visits < 1:
            raise ValueError("min_visits must be >= 1")
        self.policy = policy
        self.min_visits = min_visits

    def advise(self, bars: Sequence[OHLCVBar]) -> dict[str, MetricReading]:
        """Advisory readings for the current state; {} when undertrained."""
        if len(bars) < MIN_BARS:
            return {}
        state = state_from_bars(bars)
        visits = self.policy.visits(state)
        if visits < self.min_visits:
            return {}
        q = self.policy.q_values(state)
        ordered = sorted(q.values(), reverse=True)
        readings = {
            f"RL_Q_{action}": MetricReading(
                name=f"RL_Q_{action}", value=value, unit="reward", source=RL_SOURCE
            )
            for action, value in q.items()
        }
        readings["RL_POLICY_EDGE"] = MetricReading(
            name="RL_POLICY_EDGE", value=ordered[0] - ordered[1], unit="reward",
            source=RL_SOURCE,
        )
        readings["RL_STATE_VISITS"] = MetricReading(
            name="RL_STATE_VISITS", value=float(visits), unit="count", source=RL_SOURCE
        )
        return readings
