"""Utility to extract formatted strategy signals from agent state."""

from __future__ import annotations

from typing import Any


def get_signal_section(state: dict[str, Any], role: str) -> str:
    """Return a formatted strategy signals section for *role*, or empty string."""
    signals = state.get("strategy_signals")
    if not signals:
        return ""
    try:
        from tradingagents.strategies import format_signals_for_role
        section = format_signals_for_role(signals, role)
        return f"\n\n{section}" if section else ""
    except Exception:
        return ""
