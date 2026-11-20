"""Fixtures for the offline FR-04 risk-gate specification.

The implementation package is imported lazily inside ``gate_factory``. This keeps
collection working while ``src/egta/risk_gate`` is absent, so every behavioural case
fails red individually with a clear missing-module error instead of one collection
abort. There is intentionally no ``xfail``/``skip`` for missing implementation.
"""

from __future__ import annotations

import itertools
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fakes import NOW, FixedClock, base_policy, base_portfolio

_SRC = Path(__file__).resolve().parents[3] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_UNSET = object()


@dataclass
class GateHarness:
    gate: Any
    db_path: Path
    policy: Any
    clock: Any


@pytest.fixture(autouse=True)
def _forbid_network(monkeypatch):
    def _deny(*args, **kwargs):
        raise AssertionError("network access is forbidden in offline risk_gate tests")

    monkeypatch.setattr(socket.socket, "connect", _deny)
    monkeypatch.setattr(socket, "create_connection", _deny)


@pytest.fixture
def gate_factory(tmp_path):
    counter = itertools.count()

    def _make(
        *,
        policy: Any = _UNSET,
        initial_portfolio: Any = _UNSET,
        clock: Any = None,
        db_path: str | Path | None = None,
        **kwargs: Any,
    ) -> GateHarness:
        from egta.risk_gate import RiskGate

        if policy is _UNSET:
            policy = base_policy()
        if initial_portfolio is _UNSET:
            initial_portfolio = base_portfolio()
        if clock is None:
            clock = FixedClock(NOW)
        path = Path(db_path) if db_path is not None else tmp_path / f"risk-{next(counter)}.db"
        gate = RiskGate(db_path=path, policy=policy, clock=clock, **kwargs)
        if initial_portfolio is not None:
            gate.ensure_initialized(initial_portfolio)
        return GateHarness(gate=gate, db_path=path, policy=policy, clock=clock)

    return _make
