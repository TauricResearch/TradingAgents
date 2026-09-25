"""Safe Binance executor wrapper.

By default this module never places real orders. Real execution requires
explicit ``dry_run=False`` and a separate human confirmation flag.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict


class BinanceExecutor:
    """Minimal executor with mandatory human confirmation."""

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run

    def execute(self, signal: Dict, human_confirmed: bool = False) -> Dict:
        if not human_confirmed:
            return {
                "status": "skipped",
                "reason": "human_confirmation_required",
                "signal": signal,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            }
        if self.dry_run:
            return {
                "status": "dry_run",
                "reason": "dry_run_enabled_no_order_sent",
                "signal": signal,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            }
        raise NotImplementedError("Live Binance order placement is intentionally not enabled yet.")