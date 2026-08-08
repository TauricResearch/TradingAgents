"""Dead-man's switch: prove the scheduler is alive, from outside the box.

Why an EXTERNAL monitor rather than a self-report
-------------------------------------------------
A process that has died cannot tell you it died. Self-reporting catches "the
app is confused" but never "the VM was reclaimed", "the host rebooted", or
"systemd gave up" — precisely the failures that matter on free-tier hosting.

So this inverts it: the scheduler pings an external service on every pass, and
that service alerts when the pings STOP. Silence becomes the alarm.

This is not hypothetical. The Ollama weekly cap was exhausted on 2026-08-06 and
errored 3 of 4 runs; the assistant then sat idle and the gap was only noticed
days later, by which point the experiment had lost a week of observations.

Free options for ``heartbeat_url`` (both have a free tier that covers one check):
  - healthchecks.io  — create a check, copy its ping URL
  - betteruptime / cronitor — same pattern

Set ``ASSISTANT_HEARTBEAT_URL`` and the pings start; leave it unset and this is
a no-op, so nothing here can break a local run.
"""

from __future__ import annotations

import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_consecutive_failures = 0
#: Tell the user via Telegram once the monitor itself looks unreachable, but
#: only after a few misses — a single network blip is not worth waking someone.
_ALERT_AFTER = 3


async def send_heartbeat() -> bool:
    """Ping the external monitor. Returns True when the ping was accepted.

    Never raises: a monitoring failure must not take down the scheduler it is
    supposed to be watching.
    """
    global _consecutive_failures

    settings = get_settings()
    url = (settings.assistant_heartbeat_url or "").strip()
    if not url:
        return False

    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
        response.raise_for_status()
    except Exception as exc:
        _consecutive_failures += 1
        logger.warning(
            "Heartbeat ping failed (%d in a row): %s", _consecutive_failures, exc
        )
        if _consecutive_failures == _ALERT_AFTER:
            # The heartbeat is how we learn the box is healthy. If IT is broken
            # we are flying blind, so say so through the channel that still works.
            try:
                from app.services.notifier import Notifier

                await Notifier(settings).send_telegram(
                    "⚠️ <b>Heartbeat monitor unreachable</b> — the assistant is "
                    f"running, but its dead-man's switch has failed {_ALERT_AFTER} "
                    "times. You would NOT be alerted if the machine stopped."
                )
            except Exception:
                logger.exception("Could not send heartbeat-failure alert")
        return False

    if _consecutive_failures:
        logger.info("Heartbeat recovered after %d failures", _consecutive_failures)
    _consecutive_failures = 0
    return True
