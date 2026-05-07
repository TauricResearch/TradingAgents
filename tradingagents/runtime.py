"""Runtime configuration for TradingAgents.

This module is the official entry point for reading and writing the
runtime config.  It supersedes ``tradingagents.dataflows.config`` (which
still works as a thin compatibility wrapper).

Design:

* The runtime config is held in a ``ContextVar`` so different LangGraph
  threads / asyncio tasks see independent configs when needed.
* A module-level lock guards updates to the shared default so two
  concurrent ``set_runtime_config`` calls never corrupt the dict.
* ``get_runtime_config()`` returns a *copy* — callers cannot accidentally
  mutate shared state by writing back into the dict.

Why this exists:
The previous design lived inside ``dataflows/config.py`` and was a
plain module global.  Agents (a higher layer) reached into a "dataflows"
module to read it, and concurrent runs could race when one called
``set_config`` while another was mid-call.  This module fixes the
layering and the concurrency at once.
"""

from __future__ import annotations

import threading
from contextvars import ContextVar
from typing import Any, Dict, Optional

import tradingagents.default_config as default_config

# Process-wide default. New contexts inherit from this if no scope override
# has been set. Guarded by _DEFAULT_LOCK for write safety.
_DEFAULT_LOCK = threading.Lock()
_default_config: Dict[str, Any] = default_config.DEFAULT_CONFIG.copy()

# Per-context override. ``None`` means "use the default".
_context_config: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "tradingagents_config", default=None
)


def get_runtime_config() -> Dict[str, Any]:
    """Return the current effective config as a fresh copy.

    Resolution order: per-context override → process-wide default.
    """
    ctx = _context_config.get()
    if ctx is not None:
        return ctx.copy()
    with _DEFAULT_LOCK:
        return _default_config.copy()


def set_runtime_config(config: Dict[str, Any], *, scope: str = "default") -> None:
    """Update the runtime config.

    scope='default'  — merge into the process-wide default. Use this from
                       application bootstrap (e.g. CLI / TradingAgentsGraph init).
    scope='context' — merge into the current context only. Use this when a
                       single Python process runs multiple analyses with
                       different configs concurrently.
    """
    if scope not in ("default", "context"):
        raise ValueError(f"scope must be 'default' or 'context', got {scope!r}")

    if scope == "context":
        cur = _context_config.get()
        base = cur.copy() if cur is not None else get_runtime_config()
        base.update(config)
        _context_config.set(base)
        return

    with _DEFAULT_LOCK:
        _default_config.update(config)


def reset_context_config() -> None:
    """Drop any per-context override, falling back to the default."""
    _context_config.set(None)
