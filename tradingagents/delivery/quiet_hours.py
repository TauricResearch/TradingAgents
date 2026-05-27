"""Quiet-hours predicate used by the delivery base to skip event_alert sends.

Per IIC-FORGE-08 D5: quiet hours apply to event_alert only — morning_digest
and deep_dive bypass. The bypass gate lives in base.send(), not here.
"""

from __future__ import annotations

from datetime import time


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def is_quiet_hours(*, local_time: time, config: dict) -> bool:
    if not config.get("enabled", False):
        return False
    start = _parse_hhmm(config["start"])
    end = _parse_hhmm(config["end"])
    if start <= end:
        return start <= local_time < end
    return local_time >= start or local_time < end
