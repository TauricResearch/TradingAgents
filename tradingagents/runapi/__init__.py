"""Shared, prompt-free boundary for complete TradingAgents runs."""

from .context import ConsentState, FrozenSnapshot, InputMode, RunContext
from .result import CheckResult, Finding, InputError, RunResult

__all__ = [
    "CheckResult", "ConsentState", "Finding", "FrozenSnapshot", "InputError",
    "InputMode", "RunContext", "RunResult",
]
