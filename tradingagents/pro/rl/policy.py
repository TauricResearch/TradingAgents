"""Policies over the discretized state space.

``QTablePolicy`` is the shipped implementation: tabular action-value
estimates with visit counts, JSON persistence, and an inspectable table.
``PolicyProtocol`` is the seam for PPO/SAC/DQN implementations later
(ADR-0025) — the advisor and trainer depend only on the protocol.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from tradingagents.pro.rl.env import ACTIONS
from tradingagents.pro.rl.features import RLState


class PolicyProtocol(Protocol):
    def q_values(self, state: RLState) -> dict[str, float]: ...

    def visits(self, state: RLState) -> int: ...


class QTablePolicy:
    def __init__(self, alpha: float = 0.1, gamma: float = 0.0):
        """``gamma=0`` is the honest default: with full-feedback offline
        rewards this is state-conditioned action-value estimation; raise
        gamma to bootstrap multi-step credit once evidence demands it."""
        if not 0 < alpha <= 1:
            raise ValueError("alpha must be in (0, 1]")
        if not 0 <= gamma < 1:
            raise ValueError("gamma must be in [0, 1)")
        self.alpha = alpha
        self.gamma = gamma
        self._q: dict[str, dict[str, float]] = {}
        self._visits: dict[str, int] = {}

    def _row(self, key: str) -> dict[str, float]:
        return self._q.setdefault(key, dict.fromkeys(ACTIONS, 0.0))

    def update(self, state: RLState, action: str, reward: float,
               next_state: RLState | None = None) -> None:
        if action not in ACTIONS:
            raise ValueError(f"unknown action {action!r}")
        row = self._row(state.key())
        target = reward
        if self.gamma > 0 and next_state is not None:
            target += self.gamma * max(self._row(next_state.key()).values())
        row[action] += self.alpha * (target - row[action])
        self._visits[state.key()] = self._visits.get(state.key(), 0) + 1

    def q_values(self, state: RLState) -> dict[str, float]:
        return dict(self._q.get(state.key(), dict.fromkeys(ACTIONS, 0.0)))

    def visits(self, state: RLState) -> int:
        return self._visits.get(state.key(), 0)

    def best(self, state: RLState) -> tuple[str, float]:
        """(best action, edge over the runner-up)."""
        values = self.q_values(state)
        ordered = sorted(values.items(), key=lambda kv: kv[1], reverse=True)
        return ordered[0][0], ordered[0][1] - ordered[1][1]

    @property
    def n_states(self) -> int:
        return len(self._q)

    # --- persistence ------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        payload = {
            "alpha": self.alpha,
            "gamma": self.gamma,
            "q": self._q,
            "visits": self._visits,
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> QTablePolicy:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        policy = cls(alpha=payload["alpha"], gamma=payload["gamma"])
        policy._q = {k: dict(v) for k, v in payload["q"].items()}
        policy._visits = dict(payload["visits"])
        return policy
