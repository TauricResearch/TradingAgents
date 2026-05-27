"""CLI delivery channel — writes the body to stdout.

Used by forge deepdive and the morning-digest --now command (when 'cli' is
in delivery.enabled_channels).
"""

from __future__ import annotations

import sys
from typing import Any, Dict

from tradingagents.delivery.base import DeliveryChannel


class CLIOutbound(DeliveryChannel):
    channel_name = "cli"

    def _send_impl(self, brief: Dict[str, Any], mode: str, body: str) -> tuple:
        sys.stdout.write(body)
        if not body.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()
        return ("cli", None)
