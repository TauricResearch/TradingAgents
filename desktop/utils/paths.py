"""Shared path validation utilities.

Centralises the result-directory path traversal check used by
detail.py, compare.py, and database.py (SEC-01 fix).
"""

from __future__ import annotations

from pathlib import Path

_RESULTS_BASE = Path.home() / ".tradingagents" / "results"


def validated_result_dir(raw_path: str) -> Path | None:
    """Resolve and validate a result directory path.

    Returns the resolved ``Path`` if it falls under
    ``~/.tradingagents/results/``, or ``None`` otherwise.

    Uses ``Path.is_relative_to`` (Python 3.9+) instead of the
    fragile ``str.startswith`` approach that allowed prefix
    collisions like ``results_evil/`` (SEC-01 fix).
    """
    try:
        resolved = Path(raw_path).resolve()
        expected_base = _RESULTS_BASE.resolve()
        if resolved.is_relative_to(expected_base):
            return resolved
    except (ValueError, OSError):
        pass
    return None
