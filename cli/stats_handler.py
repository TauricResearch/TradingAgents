"""Backwards-compatible re-export of the LLM/tool usage callback handler.

The handler moved to :mod:`tradingagents.stats` so the package can use it
without importing from the CLI — the backtest runner records per-decision token
usage, and ``tradingagents`` must not depend on ``cli``. This shim keeps the old
import path working for anyone who was using it directly.
"""

from tradingagents.stats import StatsCallbackHandler

__all__ = ["StatsCallbackHandler"]
