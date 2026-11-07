"""The contract between the hourly job and the signal module."""

from __future__ import annotations

from dataclasses import dataclass

SIGNALS = ("Long", "Short", "Flat")


@dataclass(frozen=True)
class SignalResult:
    """One hourly decision for one coin.

    ``signal`` is None when the call failed or the answer had no usable signal;
    the job then leaves the position as it is. ``cost_usd`` is None when the
    model has no price or a call reported no usage.
    """

    signal: str | None      # "Long" | "Short" | "Flat" | None
    conviction: int | None  # 1 (weak) .. 3 (strong); None when unknown
    reason: str             # the model's reasoning, "" when none
    error: str | None       # the exception, truncated, when the call failed
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float | None = None
