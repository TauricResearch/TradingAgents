"""DeliveryChannel base class.

Every channel inherits from DeliveryChannel and implements ``_send_impl``.
The base ``send()`` handles:
  - quiet-hours gating (event_alert only)
  - writing the deliveries row on success / failure / skip
  - returning the delivery_id

A channel's ``_send_impl`` returns a tuple ``(channel_ref, error_msg)``:
  - on success: (channel_ref, None)
  - on failure: it should raise; the base catches and records the message
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, time, timezone
from typing import Any, Dict, Optional

from tradingagents.delivery.quiet_hours import is_quiet_hours
from tradingagents.persistence import store


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _local_now() -> time:
    """Local-time *time* (no date) used for quiet-hours comparison.

    Pulled out so tests can patch it. Local TZ comes from the OS — for the
    F5 single-machine use case this is correct."""
    return datetime.now().time()


class DeliveryChannel(ABC):
    channel_name: str = "abstract"

    def __init__(self, *, conn: sqlite3.Connection, config: Dict[str, Any]) -> None:
        self._conn = conn
        self._config = config

    @abstractmethod
    def _send_impl(self, brief: Dict[str, Any], mode: str, body: str) -> tuple:
        """Return (channel_ref, error_msg). Raise on failure."""

    def send(self, *, brief: Dict[str, Any], mode: str, body: str) -> int:
        if mode == "event_alert" and is_quiet_hours(
            local_time=_local_now(),
            config=self._config["delivery"]["quiet_hours"],
        ):
            return store.insert_delivery(
                self._conn,
                brief_id=brief["brief_id"],
                channel=self.channel_name,
                status="skipped",
                sent_ts=None,
                channel_ref=None,
                skip_reason="quiet_hours",
            )

        try:
            channel_ref, _err = self._send_impl(brief, mode, body)
            return store.insert_delivery(
                self._conn,
                brief_id=brief["brief_id"],
                channel=self.channel_name,
                status="sent",
                sent_ts=_utc_now_iso(),
                channel_ref=channel_ref,
                skip_reason=None,
            )
        except Exception as exc:  # noqa: BLE001
            return store.insert_delivery(
                self._conn,
                brief_id=brief["brief_id"],
                channel=self.channel_name,
                status="failed",
                sent_ts=None,
                channel_ref=str(exc)[:500],
                skip_reason=None,
            )
