"""DeliveryChannel base class.

Every channel inherits from DeliveryChannel and implements ``_send_impl``.
The base ``send()`` handles:
  - quiet-hours gating (event_alert and event_alert_light)
  - writing the deliveries row on success / failure / skip
  - returning the delivery_id

A channel's ``_send_impl`` returns a tuple ``(channel_ref, error_msg)``:
  - on success: (channel_ref, None)
  - on failure: it should raise; the base catches and records the message
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, Optional

from tradingagents.delivery.quiet_hours import is_quiet_hours
from tradingagents.persistence import store


class DeliveryError(Exception):
    """Raised by a channel's ``_send_impl`` for a non-transient send failure
    (e.g. missing configuration). Caught by ``send()`` and recorded as a
    'failed' delivery row, so it never crashes the delivery loop."""


_QUIET_HOUR_MODES = {"event_alert", "event_alert_light"}


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
        if mode in _QUIET_HOUR_MODES and is_quiet_hours(
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
            delivery_id = store.insert_delivery(
                self._conn,
                brief_id=brief["brief_id"],
                channel=self.channel_name,
                status="sent",
                sent_ts=_utc_now_iso(),
                channel_ref=channel_ref,
                skip_reason=None,
            )
            # S-8: on event_alert delivery, create EXACTLY ONE pending
            # brief_action (matching the [Run Backtest]/[Dismiss] keyboard) so
            # an ignored alert can lapse to 'expired' organically (gate G5).
            # base.send() is per-channel, so guard on existing rows for this
            # brief_id — re-delivery or multiple channels create no duplicates.
            if mode == "event_alert":
                self._ensure_pending_action(brief["brief_id"])
            return delivery_id
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

    def _ensure_pending_action(self, brief_id: str) -> None:
        """Idempotently create one pending 'run_backtest' brief_action for an
        event_alert brief. No-op if any action already exists for this brief."""
        if store.count_brief_actions(self._conn, brief_id=brief_id) > 0:
            return
        ttl_hours = self._config.get("brief_action_ttl_hours", 24)
        expires_at = (
            datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
        ).isoformat()
        store.insert_brief_action(
            self._conn,
            brief_id=brief_id,
            action_type="run_backtest",
            action_params={},
            expires_at=expires_at,
        )
