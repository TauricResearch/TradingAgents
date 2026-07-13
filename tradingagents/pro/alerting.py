"""Operational alerting (OBS-02): push critical events to humans.

The dashboard's alert feed (ALERT-02) is pull — someone has to be looking
at it. This module is push: the service emits an Alert at each critical
event and the AlertManager fans it out to sinks. Sinks must never raise
into the trading loop; delivery failure is counted, logged, and dropped.

Severity levels mirror the dashboard feed: ``critical`` pages someone
(kill switch, breaker trip, reconciliation drift, quarantined injection),
``warning`` is reviewed daily (venue refusals, iteration errors), ``info``
is context (degraded feeds).
"""

from __future__ import annotations

import json
import logging
import urllib.request
from dataclasses import dataclass, field

from tradingagents.contracts import utc_now

logger = logging.getLogger(__name__)

SEVERITIES = ("critical", "warning", "info")


@dataclass(frozen=True)
class Alert:
    severity: str
    event: str            # stable machine key, e.g. "kill_switch_refusal"
    text: str             # human sentence
    labels: dict = field(default_factory=dict)
    time: str = field(default_factory=lambda: utc_now().isoformat())

    def __post_init__(self):
        if self.severity not in SEVERITIES:
            raise ValueError(f"severity must be one of {SEVERITIES}")

    def as_dict(self) -> dict:
        return {"severity": self.severity, "event": self.event,
                "text": self.text, "labels": dict(self.labels),
                "time": self.time}


class LogAlertSink:
    """One JSON log line per alert; works with configure_structured_logging."""

    def deliver(self, alert: Alert) -> None:
        level = logging.CRITICAL if alert.severity == "critical" else logging.WARNING
        logger.log(level, "ALERT %s: %s", alert.event, alert.text,
                   extra={"extra_fields": alert.as_dict()})


class MemoryAlertSink:
    """Keeps the last ``capacity`` alerts in memory (tests, dashboards)."""

    def __init__(self, capacity: int = 200):
        self.capacity = capacity
        self.alerts: list[Alert] = []

    def deliver(self, alert: Alert) -> None:
        self.alerts.append(alert)
        del self.alerts[:-self.capacity]


class WebhookAlertSink:
    """POSTs the alert as JSON — bridge to Slack/PagerDuty/ntfy relays.

    The URL comes from deployment secrets. Failures never propagate: the
    trading loop must not stall because the pager is down.
    """

    def __init__(self, url: str, timeout: float = 5.0,
                 min_severity: str = "warning"):
        if min_severity not in SEVERITIES:
            raise ValueError(f"min_severity must be one of {SEVERITIES}")
        self.url = url
        self.timeout = timeout
        self.min_severity = min_severity

    def deliver(self, alert: Alert) -> None:
        if SEVERITIES.index(alert.severity) > SEVERITIES.index(self.min_severity):
            return
        request = urllib.request.Request(
            self.url,
            data=json.dumps(alert.as_dict()).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(request, timeout=self.timeout).close()


class TelegramAlertSink:
    """Pushes alerts to a Telegram chat via the Bot API (go-live Phase 5).

    Bot token + chat id are secrets (read via the secrets layer at wiring
    time, never logged). Same fail-closed contract as every sink: the
    trading loop must not stall because the pager is down. Uses the stdlib
    ``urllib.request`` like ``WebhookAlertSink`` — no new dependency.
    """

    _SEVERITY_PREFIX = {"critical": "\U0001f6a8 CRITICAL",
                        "warning": "⚠️ WARNING", "info": "ℹ️ INFO"}

    def __init__(self, bot_token: str, chat_id: str, timeout: float = 5.0,
                 min_severity: str = "warning"):
        if min_severity not in SEVERITIES:
            raise ValueError(f"min_severity must be one of {SEVERITIES}")
        self._token = bot_token
        self.chat_id = chat_id
        self.timeout = timeout
        self.min_severity = min_severity

    def _redact(self, text: str) -> str:
        return text.replace(self._token, "***") if self._token else text

    def deliver(self, alert: Alert) -> None:
        if SEVERITIES.index(alert.severity) > SEVERITIES.index(self.min_severity):
            return
        prefix = self._SEVERITY_PREFIX.get(alert.severity, alert.severity)
        message = f"{prefix} · {alert.event}\n{alert.text}"
        payload = json.dumps({"chat_id": self.chat_id, "text": message}).encode()
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{self._token}/sendMessage",
            data=payload, headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=self.timeout).close()
        except Exception as exc:  # redact the token from any surfaced error
            raise RuntimeError(self._redact(str(exc))) from None


class AlertManager:
    """Fan-out with per-sink isolation and optional metric counting."""

    def __init__(self, sinks=None, metrics=None):
        self.sinks = list(sinks) if sinks is not None else [LogAlertSink()]
        self.metrics = metrics

    def emit(self, severity: str, event: str, text: str, **labels: str) -> Alert:
        alert = Alert(severity=severity, event=event, text=text, labels=labels)
        if self.metrics is not None:
            self.metrics.inc("alerts_total", severity=severity, event=event)
        for sink in self.sinks:
            try:
                sink.deliver(alert)
            except Exception:
                logger.exception("alert sink %s failed; alert dropped there",
                                 type(sink).__name__)
                if self.metrics is not None:
                    self.metrics.inc("alert_delivery_failures_total",
                                     sink=type(sink).__name__)
        return alert
