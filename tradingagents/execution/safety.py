"""Safety primitives for the execution layer.

Two layers of guarding sit between a MarketDecision and a real order:

1. ``paper_mode`` (config flag, default True) — the runner still records
   the intended trade in the ledger but never calls Kalshi's order API.
2. ``TRADINGAGENTS_LIVE_DISABLED=1`` (env var, kill switch) — overrides
   the config flag and forces paper mode. Set this in the environment
   when on-call has paged you about a flapping pipeline; toggling it
   does not require a code change or restart.

Going live also requires explicit ``--live`` opt-in from the CLI / runner
caller. Three concurrent gates (config, env, CLI flag) make accidental
real-money execution a non-trivial mistake to make.
"""

from __future__ import annotations

import os


KILL_SWITCH_ENV = "TRADINGAGENTS_LIVE_DISABLED"


def is_kill_switch_set() -> bool:
    """Return True when the kill-switch env var is set to a truthy value."""
    raw = os.environ.get(KILL_SWITCH_ENV, "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def resolve_mode(*, requested_live: bool, config: dict) -> str:
    """Resolve effective execution mode based on layered guards.

    Args:
        requested_live: Whether the caller asked for live mode (e.g. CLI ``--live``).
        config: Pipeline config (typically ``DEFAULT_CONFIG`` merged with overrides).

    Returns:
        ``"live"`` only when ALL of:
          - ``requested_live`` is True
          - ``config['kalshi']['paper_mode']`` is False
          - the kill-switch env var is unset
        Otherwise returns ``"paper"``.
    """
    if not requested_live:
        return "paper"

    if is_kill_switch_set():
        return "paper"

    paper_mode = config.get("kalshi", {}).get("paper_mode", True)
    if paper_mode:
        return "paper"

    return "live"
