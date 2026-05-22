"""Hermes tool wrappers for the autonomous trading system.

Each module exposes one or more callable functions that Hermes registers
in its tool registry via scripts/register_tools.py.
"""

from hermes_tools.tradingagents_tool import tradingagents_analyze
from hermes_tools.ib_executor_tool import (
    ib_place_bracket,
    ib_cancel_order,
    ib_get_positions,
    ib_get_account_value,
)
from hermes_tools.telegram_tool import send_approval_card, send_notification

__all__ = [
    "tradingagents_analyze",
    "ib_place_bracket",
    "ib_cancel_order",
    "ib_get_positions",
    "ib_get_account_value",
    "send_approval_card",
    "send_notification",
]
