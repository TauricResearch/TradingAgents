"""Offline replay orchestration for a run's event log (E2).

# Implements: FR-05, NFR-08

Thin wrapper over :func:`egta.contracts.evaluation.replay_events` (dedupe-first,
``(run_id, sequence)`` sort, chain verify + anchor) with optional run scoping.
Fully offline: reads only the event payloads; never calls a model or network.
"""

from __future__ import annotations

from egta.contracts.evaluation import ReplayState, replay_events
from egta.contracts.events import RunEvent


def replay_run(
    events: list[RunEvent], *, run_id: str | None = None, anchor: str | None = None
) -> ReplayState:
    """Reconstruct a run's state from its events (offline, deterministic).

    Args:
        events: the run's events, any order.
        run_id: if given, restrict to this run before replay.
        anchor: trusted external tip hash; a mismatch (tail truncation) raises
            ``ChainBroken``.
    """
    scoped = [e for e in events if e.run_id == run_id] if run_id is not None else events
    return replay_events(scoped, anchor=anchor)
