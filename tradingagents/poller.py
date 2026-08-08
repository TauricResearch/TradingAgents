"""Media poller — accumulates social/news history for backtesting.

Polls each configured source (hourly by default), appending every new item to a
media store (local SQLite by default, or any database via ``MEDIA_DB_URL``),
deduped on the provider's stable id. See ``dataflows.media_sources`` (fetchers)
and ``dataflows.media_store`` (storage).

Designed to be cloud-hostable: every knob has an environment-variable form, so a
container can run with no CLI arguments. Env vars (CLI flags override them):

    MEDIA_POLLER_TICKERS   comma-separated; required only for ticker sources
    MEDIA_POLLER_SOURCES   subset of the sources; default = keyless (+x if token)
    MEDIA_POLLER_INTERVAL  seconds between broad-news cycles
    MEDIA_POLLER_X_INTERVAL seconds between X discovery cycles
    MEDIA_POLLER_X_TOPICS  max discovered topics per cycle           (default 3)
    MEDIA_POLLER_X_LIMIT   results per discovered X query            (default 10)
    MEDIA_POLLER_ONCE      "1"/"true" → poll once and exit (for cron/scheduler)
    MEDIA_COLLECTION_ENABLED explicit global-collector enable switch (default false)
    MEDIA_DB_URL           store location; default ~/.tradingagents/cache/media.db
    X_BEARER_TOKEN         enables the 'x' source (paid)
    TRUTHSOCIAL_TOKEN      enables Truth Social

Run modes:
    tradingagents-poller --tickers NVDA,AAPL          # hourly daemon
    tradingagents-poller --tickers NVDA --once        # one-shot (cron/scheduler)
    tradingagents-poller --stats                      # collection summary
    tradingagents-poller --global-only                # general news + bounded X
    tradingagents-poller --window NVDA --end 2026-06-28 --days 7
    python -m tradingagents.poller --tickers NVDA     # equivalent
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import math
import os
import re
import secrets
import signal
import time
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from tradingagents import global_research
from tradingagents.collector_contract import (
    COLLECTOR_POLICY as _GLOBAL_ONLY_COLLECTOR_POLICY,
    DISCOVERY_POLICY as _DISCOVERY_POLICY,
    discovery_policy_manifest,
)
from tradingagents.collector_health import (
    CollectorHealthState,
    start_collector_health_server,
)
from tradingagents.dataflows import media_store
from tradingagents.dataflows.media_sources import (
    FETCHERS,
    GLOBAL_X_ADAPTER_POLICY,
    KEYLESS_SOURCES,
    SELECTABLE_SOURCES,
    ProviderResponseError,
    ProviderTransientError,
    fetch_global_news,
    fetch_polymarket_odds,
    fetch_top_news_headlines,
    fetch_x_topic,
    fetch_x_trends,
    looks_company_authored,
)
from tradingagents.dataflows.media_store import open_store
from tradingagents.dataflows.trading_clock import TradingClock
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.global_research import (
    _evidence_id,
    _formal_query_slots,
    _raw_content_id,
    is_formally_eligible_evidence,
)
from tradingagents.logging_utils import safe_exception_type as _exception_kind
from tradingagents.operations import emit_alert, probe_alert_webhook
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_COLLECTION_PROTOCOL_ID,
    GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_ID,
    GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_MANIFEST,
    GLOBAL_EVENT_V2_COMPATIBLE_COLLECTOR_IDENTITIES,
    GLOBAL_EVENT_V2_CURRENT_COLLECTOR_IDENTITY,
    GLOBAL_EVENT_V2_PROTOCOL,
    build_identity,
    canonical_json,
    content_id,
    global_news_query_slot_label,
)
from tradingagents.x_cycle import x_cycle_structural_state

logger = logging.getLogger("media_poller")


_GLOBAL_ONLY_NEWS_INTERVAL_SECONDS = int(
    GLOBAL_EVENT_V2_PROTOCOL["evidence"]["query_cycle"]["collector_interval_seconds"]
)
_GLOBAL_ONLY_X_INTERVAL_SECONDS = int(
    GLOBAL_EVENT_V2_PROTOCOL["evidence"]["x_cycle_interval_seconds"]
)
_GLOBAL_X_TREND_LIMIT = int(GLOBAL_X_ADAPTER_POLICY["trends"]["result_limit"]["default"])
_GLOBAL_X_SEARCH_LIMIT = int(
    GLOBAL_X_ADAPTER_POLICY["recent_search"]["result_limit"]["default"]
)
_GLOBAL_X_TOPIC_LIMIT = int(
    GLOBAL_EVENT_V2_PROTOCOL["evidence"]["max_x_search_requests_per_utc_day"]
)
if int(
    GLOBAL_EVENT_V2_PROTOCOL["evidence"]["max_x_results_per_query"]
) != _GLOBAL_X_SEARCH_LIMIT:
    raise RuntimeError("formal X result limit differs from the adapter contract")
# Coverage alerts are operational state, separate from the immutable evidence
# ledger. Repeated identical incidents get one notification plus a daily reminder;
# a transition back to complete coverage emits one recovery notification.
_COVERAGE_ALERT_STATE_KEY = "poller:coverage_alert_unhealthy"
_COVERAGE_ALERT_LAST_UTC_KEY = "poller:coverage_alert_last_utc"
_COVERAGE_ALERT_DELIVERED_KEY = "poller:coverage_alert_incident_delivered"
_COVERAGE_ALERT_STARTED_UTC_KEY = "poller:coverage_alert_started_utc"
_COVERAGE_ALERT_SEQUENCE_KEY = "poller:coverage_alert_occurrence_sequence"
_COVERAGE_ALERT_INCIDENT_KEY = "poller:coverage_alert_incident_occurrence"
_COVERAGE_ALERT_REMINDER_KEY = "poller:coverage_alert_reminder_occurrence"
_COVERAGE_ALERT_RECOVERY_KEY = "poller:coverage_alert_recovery_occurrence"
_COVERAGE_ALERT_REMINDER_ORDINAL_KEY = "poller:coverage_alert_reminder_ordinal"
_COVERAGE_ALERT_PENDING_ORDINAL_KEY = "poller:coverage_alert_pending_reminder_ordinal"
_COVERAGE_ALERT_ACKED_REMINDER_KEY = "poller:coverage_alert_acked_reminder"
_COVERAGE_ALERT_X_CAUSE_KEY = "poller:coverage_alert_x_cause"
_COVERAGE_ALERT_REMINDER_SECONDS = 24 * 60 * 60

# Fatal runtime failures are retried in-process so Fly cannot turn a transient
# database or lease incident into an unbounded restart/webhook storm. Readiness
# recovers after any normally returned cycle; strict coverage health is separate.
_RUNTIME_RETRY_INITIAL_SECONDS = 5.0
_RUNTIME_RETRY_MAX_SECONDS = 300.0
_RUNTIME_ALERT_MIN_INTERVAL_SECONDS = 60 * 60
_RUNTIME_ALERT_REMINDER_SECONDS = 24 * 60 * 60
_RUNTIME_FAILURE_STAGES = frozenset(
    {
        "daemon_startup",
        "health_listener",
        "store_startup",
        "lease_acquisition",
        "lease_contended",
        "cycle",
        "lease_lost",
    }
)


_DISCOVERY_INPUTS = _DISCOVERY_POLICY["inputs"]
_DISCOVERY_NORMALIZATION = _DISCOVERY_POLICY["normalization"]
_DISCOVERY_STORY_GROUPING = _DISCOVERY_POLICY["story_grouping"]
_DISCOVERY_TREND_MATCHING = _DISCOVERY_POLICY["trend_matching"]
_DISCOVERY_QUERY = _DISCOVERY_POLICY["query"]
_DISCOVERY_RANKING = _DISCOVERY_POLICY["ranking"]
_DISCOVERY_ALLOCATION = _DISCOVERY_POLICY["allocation"]
_DISCOVERY_AUDIT = _DISCOVERY_POLICY["audit_record"]
_DISCOVERY_CATEGORIES = tuple(_DISCOVERY_INPUTS["categories"])
_QUERY_STOPWORDS = frozenset(_DISCOVERY_NORMALIZATION["stopwords"])
_GENERIC_CAPITALIZED = frozenset(_DISCOVERY_QUERY["generic_capitalized_terms"])
_LOW_INFORMATION_HEADLINE = re.compile(
    str(_DISCOVERY_INPUTS["low_information_pattern"]),
    int(_DISCOVERY_INPUTS["low_information_flags"]),
)

_GLOBALNEWS_RETRY_POLICY = GLOBAL_EVENT_V2_PROTOCOL["evidence"]["query_cycle"][
    "globalnews_exception_retry_policy"
]
_GLOBALNEWS_MAX_ATTEMPTS = int(_GLOBALNEWS_RETRY_POLICY["max_attempts_per_query_cycle"])
_GLOBALNEWS_RETRY_DELAYS = tuple(
    float(value) for value in _GLOBALNEWS_RETRY_POLICY["delays_seconds"]
)
_GLOBALNEWS_CIRCUIT_FAILURE_SLOTS = int(
    GLOBAL_EVENT_V2_PROTOCOL["evidence"]["query_cycle"]["globalnews_cycle_circuit_breaker"][
        "failed_query_slots_before_open"
    ]
)
_GLOBALNEWS_QUERY_SLOT_COUNT = sum(
    len(queries) for queries in GLOBAL_EVENT_V2_PROTOCOL["evidence"]["broad_news_queries"].values()
)
if (
    _GLOBALNEWS_MAX_ATTEMPTS < 1
    or len(_GLOBALNEWS_RETRY_DELAYS) != _GLOBALNEWS_MAX_ATTEMPTS - 1
    or any(not math.isfinite(value) or value < 0 for value in _GLOBALNEWS_RETRY_DELAYS)
    or sum(_GLOBALNEWS_RETRY_DELAYS) >= _GLOBAL_ONLY_NEWS_INTERVAL_SECONDS
    or _GLOBALNEWS_RETRY_POLICY.get("retry_on") != "provider_transient_exception_only"
    or _GLOBALNEWS_RETRY_POLICY.get("empty_response") != "terminal_observed_empty_without_retry"
):
    raise RuntimeError("formal globalnews retry policy is malformed")
if not 1 <= _GLOBALNEWS_CIRCUIT_FAILURE_SLOTS <= _GLOBALNEWS_QUERY_SLOT_COUNT:
    raise RuntimeError("formal globalnews circuit-breaker policy is malformed")


class _FetchBudgetExceeded(RuntimeError):
    """Raised before an HTTP request when its durable budget is exhausted."""


def _env_bool(name: str, env: Mapping[str, str] | None = None) -> bool:
    values = os.environ if env is None else env
    return (values.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def resolve_sources(
    explicit: list[str] | None, *, env: Mapping[str, str] | None = None
) -> list[str]:
    """Sources to poll: explicit list if given, else the keyless set plus 'x'
    when X_BEARER_TOKEN is present. Validates against the registry."""
    values = os.environ if env is None else env
    if explicit:
        sources = explicit
    else:
        sources = list(KEYLESS_SOURCES)
        if (values.get("X_BEARER_TOKEN") or "").strip():
            sources.append("x")
    unknown = [s for s in sources if s not in FETCHERS]
    if unknown:
        raise ValueError(
            f"unknown source(s): {','.join(unknown)}. Choose from: {','.join(SELECTABLE_SOURCES)}"
        )
    return sources


def _watermark_key(provider: str, query_key: str) -> str:
    suffix = hashlib.sha256(query_key.encode("utf-8")).hexdigest()[:16]
    return f"watermark:{provider}:{suffix}"


def _expected_query_slots(
    tickers: list[str],
    sources: list[str],
    macro_themes: dict,
    *,
    include_x_discovery: bool = False,
) -> list[tuple[str, str]]:
    """Return every exact provider/query slot configured for one cycle."""
    slots = [(source, ticker) for ticker in tickers for source in sources]
    for theme, spec in macro_themes.items():
        slots.extend(("globalnews", f"{theme}:{query}") for query in spec.get("queries", []))
        slots.extend(
            ("polymarket", f"{theme}:{topic}") for topic in spec.get("prediction_topics", [])
        )
    if include_x_discovery:
        slots.append(("trendnews", "ranked-global-discovery"))
    return list(dict.fromkeys(slots))


def _globalnews_query_slots(macro_themes: dict) -> list[tuple[str, str]]:
    """Return the exact configured broad-news query slots."""
    return [slot for slot in _expected_query_slots([], [], macro_themes) if slot[0] == "globalnews"]


def _global_only_news_themes() -> dict[str, dict[str, list[str]]]:
    """Return broad-news themes with every prediction-market query removed."""
    return {
        str(theme): {
            "queries": list(queries),
            "prediction_topics": [],
        }
        for theme, queries in GLOBAL_EVENT_V2_PROTOCOL["evidence"]["broad_news_queries"].items()
    }


def _query_slot_id(provider: str, query_key: str) -> str:
    material = f"{provider}\0{query_key}".encode()
    return hashlib.sha256(material).hexdigest()[:16]


def _safe_alert_provider(provider: object) -> str:
    """Keep ordinary adapter names useful without forwarding untrusted text."""
    if isinstance(provider, str) and re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", provider):
        return provider
    digest = hashlib.sha256(str(provider).encode("utf-8")).hexdigest()[:8]
    return f"unknown-{digest}"


def _runtime_failure_type(value: object) -> str:
    """Return only a bounded identifier supplied by trusted runtime machinery."""
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", value)
        else "Exception"
    )


class _CollectorRuntimeFailure(RuntimeError):
    """Sanitized handoff from a failed daemon session to its supervisor."""

    def __init__(self, stage: str, error_type: str):
        self.stage = stage if stage in _RUNTIME_FAILURE_STAGES else "cycle"
        self.error_type = _runtime_failure_type(error_type)
        message = (
            "collector singleton lease lost"
            if self.stage == "lease_lost"
            else f"collector cycle failed ({self.error_type})"
        )
        super().__init__(message)


def _collector_retry_delay(consecutive_failures: int) -> float:
    """Return deterministic bounded exponential daemon retry delay."""
    if (
        isinstance(consecutive_failures, bool)
        or not isinstance(consecutive_failures, int)
        or consecutive_failures < 1
    ):
        raise ValueError("collector retry count must be a positive integer")
    exponent = min(int(consecutive_failures) - 1, 30)
    return min(
        _RUNTIME_RETRY_MAX_SECONDS,
        _RUNTIME_RETRY_INITIAL_SECONDS * (2**exponent),
    )


class _CollectorRuntimeIncident:
    """Deduplicate one in-process unhealthy transition plus daily reminders."""

    def __init__(self, *, clock=None, alert=None):
        self._clock = time.monotonic if clock is None else clock
        self._alert = emit_alert if alert is None else alert
        self._active: tuple[str, str] | None = None
        self._incident_delivered = False
        self._last_attempt_monotonic: float | None = None
        self._occurrence_key: str | None = None
        self._pending_reminder_key: str | None = None
        self._reminder_number = 0
        self._pending_recovery: tuple[str, str, str] | None = None

    @property
    def active(self) -> bool:
        return self._active is not None

    def mark_failure(
        self,
        *,
        stage: str,
        error_type: str,
        retry_delay_seconds: float,
    ) -> bool:
        safe_stage = stage if stage in _RUNTIME_FAILURE_STAGES else "cycle"
        safe_error_type = _runtime_failure_type(error_type)
        observed = float(self._clock())
        next_incident = (safe_stage, safe_error_type)
        first_transition = self._active is None
        self._active = next_incident
        if first_transition:
            # A new outage supersedes an undelivered recovery from the prior one.
            self._pending_recovery = None
            self._incident_delivered = False
            self._last_attempt_monotonic = None
            self._occurrence_key = secrets.token_hex(16)
            self._pending_reminder_key = None
            self._reminder_number = 0
        since_last_attempt = (
            None
            if self._last_attempt_monotonic is None
            else observed - self._last_attempt_monotonic
        )
        if not self._incident_delivered:
            due = first_transition or (
                since_last_attempt is not None
                and since_last_attempt >= _RUNTIME_ALERT_MIN_INTERVAL_SECONDS
            )
            reminder = False
            dedupe_key = f"{self._occurrence_key}:incident"
        elif self._pending_reminder_key is not None:
            due = (
                since_last_attempt is not None
                and since_last_attempt >= _RUNTIME_ALERT_MIN_INTERVAL_SECONDS
            )
            reminder = True
            dedupe_key = self._pending_reminder_key
        else:
            due = (
                since_last_attempt is not None
                and since_last_attempt >= _RUNTIME_ALERT_REMINDER_SECONDS
            )
            reminder = due
            if due:
                self._reminder_number += 1
                self._pending_reminder_key = (
                    f"{self._occurrence_key}:reminder:{self._reminder_number}"
                )
            dedupe_key = self._pending_reminder_key
        if not due:
            return False
        self._last_attempt_monotonic = observed
        delivered = False
        try:
            delivered = bool(
                self._alert(
                    "collector",
                    "runtime_unhealthy",
                    severity="critical",
                    details={
                        "schema_version": 1,
                        "failure_stage": safe_stage,
                        "failure_type": safe_error_type,
                        "retry_delay_seconds": float(retry_delay_seconds),
                        "reminder": reminder,
                    },
                    dedupe_key=dedupe_key,
                )
            )
        except Exception as exc:  # noqa: BLE001 - supervision must survive alert bugs
            logger.error(
                "Collector runtime alert handler failed (%s)",
                _exception_kind(exc),
            )
        if delivered:
            if reminder:
                self._pending_reminder_key = None
            else:
                self._incident_delivered = True
        return True

    def mark_recovered(self) -> None:
        if self._active is not None:
            if self._incident_delivered:
                prior_stage, prior_error_type = self._active
                self._pending_recovery = (
                    prior_stage,
                    prior_error_type,
                    f"{self._occurrence_key}:recovery",
                )
            self._clear_active()
        if self._pending_recovery is None:
            return
        prior_stage, prior_error_type, dedupe_key = self._pending_recovery
        delivered = False
        try:
            delivered = bool(
                self._alert(
                    "collector",
                    "runtime_recovered",
                    severity="info",
                    details={
                        "schema_version": 1,
                        "prior_failure_stage": prior_stage,
                        "prior_failure_type": prior_error_type,
                    },
                    dedupe_key=dedupe_key,
                )
            )
        except Exception as exc:  # noqa: BLE001 - supervision must survive alert bugs
            logger.error(
                "Collector recovery alert handler failed (%s)",
                _exception_kind(exc),
            )
        if delivered:
            self._pending_recovery = None

    def _clear_active(self) -> None:
        self._active = None
        self._incident_delivered = False
        self._last_attempt_monotonic = None
        self._occurrence_key = None
        self._pending_reminder_key = None
        self._reminder_number = 0


def _sanitized_coverage_alert_details(coverage: dict) -> dict:
    """Summarize missing slots without query strings, errors, or response data."""
    missing = coverage.get("missing_query_slots") or []
    missing_periodic = coverage.get("missing_periodic_requirements") or []
    periodic = coverage.get("periodic_requirements") or {}
    x_daily_state = periodic.get("x_daily") if isinstance(periodic, dict) else None
    if x_daily_state not in {
        "complete", "incomplete", "invalid", "missing", "running", "scheduled"
    }:
        x_daily_state = None
    x_daily_missing = "x_daily" in missing_periodic
    periodic_x_providers = {"trendnews", "x", "xtrend"}
    fingerprint_missing = [
        slot
        for slot in missing
        if not (x_daily_missing and slot.get("provider") in periodic_x_providers)
    ]
    slots = []
    reason_counts: dict[str, int] = {}
    allowed_reasons = {
        "not_run",
        "empty",
        "failed",
        "running",
        "incomplete",
        "stale",
        "ineligible",
        "invalid_lineage",
        "invalid_receipt",
        "unbound_lineage",
        "collector_semantics_mismatch",
    }
    for slot in fingerprint_missing:
        provider = slot.get("provider")
        query_key = slot.get("query_key")
        reason = slot.get("reason")
        safe_reason = reason if reason in allowed_reasons else "unhealthy"
        reason_counts[safe_reason] = reason_counts.get(safe_reason, 0) + 1
        if len(slots) < 20:
            slots.append(
                {
                    "provider": _safe_alert_provider(provider),
                    "slot_id": _query_slot_id(str(provider), str(query_key)),
                    "reason": safe_reason,
                }
            )
    query_slots = coverage.get("query_slots") or []
    expected_count = sum(
        not (x_daily_missing and slot.get("provider") in periodic_x_providers)
        for slot in query_slots
    )
    return {
        "expected_query_slot_count": expected_count,
        "missing_query_slot_count": len(fingerprint_missing),
        "missing_periodic_requirement_count": len(missing_periodic),
        "missing_x_daily_requirement": x_daily_missing,
        "x_daily_state": x_daily_state,
        "missing_source_group_count": len(coverage.get("missing_source_groups") or []),
        "reason_counts": reason_counts,
        "slots": slots,
        "slots_truncated": max(0, len(fingerprint_missing) - len(slots)),
    }


def _update_coverage_alert_state(
    store,
    *,
    coverage: dict,
    observed_utc: float,
) -> None:
    """Notify once per unhealthy transition, daily while active, then on recovery."""
    if (
        isinstance(observed_utc, bool)
        or not isinstance(observed_utc, (int, float))
        or not math.isfinite(float(observed_utc))
        or float(observed_utc) <= 0
    ):
        raise ValueError("coverage alert observation time must be positive and finite")
    observed_utc = float(observed_utc)

    def valid_timestamp(value: object) -> bool:
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(float(value))
            and float(value) > 0
        )

    def valid_counter(value: object, *, positive: bool = False) -> bool:
        lower_bound = 1 if positive else 0
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(float(value))
            and float(value).is_integer()
            and lower_bound <= float(value) <= 2**53 - 1
        )

    def next_occurrence() -> float:
        candidates = [store.get_meta(_COVERAGE_ALERT_SEQUENCE_KEY)]
        candidates.extend(
            store.get_meta(key)
            for key in (
                _COVERAGE_ALERT_INCIDENT_KEY,
                _COVERAGE_ALERT_REMINDER_KEY,
                _COVERAGE_ALERT_RECOVERY_KEY,
            )
        )
        prior = max(
            (int(value) for value in candidates if valid_counter(value)),
            default=0,
        )
        occurrence = max(prior, int(observed_utc)) + 1
        if occurrence > 2**53 - 1:
            raise ValueError("coverage alert occurrence sequence is exhausted")
        store.set_meta(_COVERAGE_ALERT_SEQUENCE_KEY, float(occurrence))
        return float(occurrence)

    def dedupe_key(occurrence: object) -> str:
        if not valid_counter(occurrence, positive=True):
            raise ValueError("coverage alert occurrence identity is invalid")
        return f"coverage-v2:{int(occurrence)}"

    def clear_incident() -> None:
        store.set_meta(_COVERAGE_ALERT_DELIVERED_KEY, 0.0)
        store.set_meta(_COVERAGE_ALERT_STARTED_UTC_KEY, 0.0)
        store.set_meta(_COVERAGE_ALERT_LAST_UTC_KEY, 0.0)
        store.set_meta(_COVERAGE_ALERT_INCIDENT_KEY, 0.0)
        store.set_meta(_COVERAGE_ALERT_REMINDER_KEY, 0.0)
        store.set_meta(_COVERAGE_ALERT_RECOVERY_KEY, 0.0)
        store.set_meta(_COVERAGE_ALERT_REMINDER_ORDINAL_KEY, 0.0)
        store.set_meta(_COVERAGE_ALERT_PENDING_ORDINAL_KEY, 0.0)
        store.set_meta(_COVERAGE_ALERT_ACKED_REMINDER_KEY, 0.0)
        store.set_meta(_COVERAGE_ALERT_X_CAUSE_KEY, 0.0)

    previously_unhealthy = store.get_meta(_COVERAGE_ALERT_STATE_KEY) == 1.0
    periodic = coverage.get("periodic_requirements") or {}
    x_daily_state = periodic.get("x_daily") if isinstance(periodic, dict) else None
    x_failed = x_daily_state in {"incomplete", "invalid", "missing", "running"}
    x_caused_incident = store.get_meta(_COVERAGE_ALERT_X_CAUSE_KEY) == 1.0
    if previously_unhealthy and x_failed and not x_caused_incident:
        store.set_meta(_COVERAGE_ALERT_X_CAUSE_KEY, 1.0)
        x_caused_incident = True
    elif previously_unhealthy and x_daily_state == "complete" and x_caused_incident:
        # Clear the gate as soon as durable coverage proves a later X cycle
        # complete. If recovery delivery is interrupted, a scheduled cycle can
        # safely retry that already-earned recovery occurrence.
        store.set_meta(_COVERAGE_ALERT_X_CAUSE_KEY, 0.0)
        x_caused_incident = False
    if coverage.get("complete") is True:
        if not previously_unhealthy:
            return
        if x_caused_incident:
            # Before today's X window opens, ``scheduled`` is healthy for this
            # cycle but is not evidence that yesterday's X outage recovered.
            return
        delivered_incident = store.get_meta(_COVERAGE_ALERT_DELIVERED_KEY) == 1.0
        if delivered_incident:
            recovery_occurrence = store.get_meta(_COVERAGE_ALERT_RECOVERY_KEY)
            if not valid_counter(recovery_occurrence, positive=True):
                recovery_occurrence = next_occurrence()
                # Persist before delivery so transport and acknowledgement
                # ambiguity can only retry the same receiver identity.
                store.set_meta(_COVERAGE_ALERT_RECOVERY_KEY, recovery_occurrence)
            recovered = emit_alert(
                "collector",
                "query_slot_coverage_recovered",
                severity="info",
                details={
                    "expected_query_slot_count": len(coverage.get("query_slots") or []),
                    "missing_query_slot_count": 0,
                },
                dedupe_key=dedupe_key(recovery_occurrence),
            )
            if not recovered:
                return
        # This flag is the durable incident boundary. Clear it first so a
        # crash while cleaning auxiliary fields cannot merge a later outage
        # into the incident whose recovery was already acknowledged.
        store.set_meta(_COVERAGE_ALERT_STATE_KEY, 0.0)
        clear_incident()
        return

    incident_started_utc = store.get_meta(_COVERAGE_ALERT_STARTED_UTC_KEY)
    if not previously_unhealthy or not valid_timestamp(incident_started_utc):
        incident_started_utc = observed_utc
        clear_incident()
        store.set_meta(_COVERAGE_ALERT_STARTED_UTC_KEY, incident_started_utc)
        incident_occurrence = next_occurrence()
        store.set_meta(_COVERAGE_ALERT_INCIDENT_KEY, incident_occurrence)
        if x_failed:
            store.set_meta(_COVERAGE_ALERT_X_CAUSE_KEY, 1.0)
        # Commit the incident only after its complete identity is durable.
        store.set_meta(_COVERAGE_ALERT_STATE_KEY, 1.0)
    else:
        incident_occurrence = store.get_meta(_COVERAGE_ALERT_INCIDENT_KEY)
        if not valid_counter(incident_occurrence, positive=True):
            incident_occurrence = next_occurrence()
            store.set_meta(_COVERAGE_ALERT_INCIDENT_KEY, incident_occurrence)

    details = _sanitized_coverage_alert_details(coverage)
    delivered_incident = store.get_meta(_COVERAGE_ALERT_DELIVERED_KEY) == 1.0
    if not delivered_incident:
        delivered = emit_alert(
            "collector",
            "query_slot_coverage_incomplete",
            severity="warning",
            details=details,
            dedupe_key=dedupe_key(incident_occurrence),
        )
        if delivered:
            # Commit acknowledgement state before the next reminder can be
            # allocated. A crash before either write retries this occurrence.
            store.set_meta(_COVERAGE_ALERT_LAST_UTC_KEY, observed_utc)
            store.set_meta(_COVERAGE_ALERT_DELIVERED_KEY, 1.0)
        return

    last_alert_utc = store.get_meta(_COVERAGE_ALERT_LAST_UTC_KEY)
    reminder_due = not valid_timestamp(last_alert_utc) or (
        observed_utc - float(last_alert_utc) >= _COVERAGE_ALERT_REMINDER_SECONDS
    )
    reminder_occurrence = store.get_meta(_COVERAGE_ALERT_REMINDER_KEY)
    pending_ordinal = store.get_meta(_COVERAGE_ALERT_PENDING_ORDINAL_KEY)
    delivered_ordinal = store.get_meta(_COVERAGE_ALERT_REMINDER_ORDINAL_KEY)
    if not valid_counter(delivered_ordinal):
        delivered_ordinal = 0.0
        store.set_meta(_COVERAGE_ALERT_REMINDER_ORDINAL_KEY, delivered_ordinal)
    expected_ordinal = int(delivered_ordinal) + 1
    if expected_ordinal > 2**53 - 1:
        raise ValueError("coverage alert reminder sequence is exhausted")

    acked_reminder = store.get_meta(_COVERAGE_ALERT_ACKED_REMINDER_KEY)
    if valid_counter(acked_reminder, positive=True):
        same_pending = valid_counter(reminder_occurrence, positive=True) and int(
            acked_reminder
        ) == int(reminder_occurrence)
        if (
            same_pending
            and valid_counter(pending_ordinal, positive=True)
            and int(pending_ordinal) in {int(delivered_ordinal), expected_ordinal}
        ):
            if not valid_timestamp(last_alert_utc):
                store.set_meta(_COVERAGE_ALERT_LAST_UTC_KEY, observed_utc)
            store.set_meta(
                _COVERAGE_ALERT_REMINDER_ORDINAL_KEY,
                float(max(int(delivered_ordinal), int(pending_ordinal))),
            )
            store.set_meta(_COVERAGE_ALERT_REMINDER_KEY, 0.0)
            store.set_meta(_COVERAGE_ALERT_PENDING_ORDINAL_KEY, 0.0)
            store.set_meta(_COVERAGE_ALERT_ACKED_REMINDER_KEY, 0.0)
            return
        store.set_meta(_COVERAGE_ALERT_ACKED_REMINDER_KEY, 0.0)

    pending = valid_counter(reminder_occurrence, positive=True)
    if pending and (
        not valid_counter(pending_ordinal, positive=True)
        or int(pending_ordinal) != expected_ordinal
    ):
        pending_ordinal = float(expected_ordinal)
        store.set_meta(_COVERAGE_ALERT_PENDING_ORDINAL_KEY, pending_ordinal)
    elif (
        not pending
        and valid_counter(pending_ordinal, positive=True)
        and int(pending_ordinal) > int(delivered_ordinal)
    ):
        # Resume allocation if the process stopped between the two durable
        # writes that precede delivery.
        pending_ordinal = float(expected_ordinal)
        store.set_meta(_COVERAGE_ALERT_PENDING_ORDINAL_KEY, pending_ordinal)
        reminder_occurrence = next_occurrence()
        store.set_meta(_COVERAGE_ALERT_REMINDER_KEY, reminder_occurrence)
        pending = True
    elif not pending and reminder_due:
        pending_ordinal = float(expected_ordinal)
        store.set_meta(_COVERAGE_ALERT_PENDING_ORDINAL_KEY, pending_ordinal)
        reminder_occurrence = next_occurrence()
        store.set_meta(_COVERAGE_ALERT_REMINDER_KEY, reminder_occurrence)
        pending = True
    elif not pending and pending_ordinal not in (None, 0.0):
        store.set_meta(_COVERAGE_ALERT_PENDING_ORDINAL_KEY, 0.0)

    if not pending:
        return
    delivered = emit_alert(
        "collector",
        "query_slot_coverage_incomplete",
        severity="warning",
        details={**details, "reminder_ordinal": int(pending_ordinal)},
        dedupe_key=dedupe_key(reminder_occurrence),
    )
    if delivered:
        store.set_meta(_COVERAGE_ALERT_LAST_UTC_KEY, observed_utc)
        # This marker distinguishes a stale pending ordinal from a crash after
        # the receiver acknowledged this exact reminder.
        store.set_meta(_COVERAGE_ALERT_ACKED_REMINDER_KEY, reminder_occurrence)
        store.set_meta(_COVERAGE_ALERT_REMINDER_ORDINAL_KEY, pending_ordinal)
        store.set_meta(_COVERAGE_ALERT_REMINDER_KEY, 0.0)
        store.set_meta(_COVERAGE_ALERT_PENDING_ORDINAL_KEY, 0.0)
        # Clear the acknowledgement marker last. A crash before this point
        # resumes this commit instead of allocating another reminder.
        store.set_meta(_COVERAGE_ALERT_ACKED_REMINDER_KEY, 0.0)


def collector_semantics_manifest() -> dict:
    """Return the stable, declarative receipt and wire-format contract."""
    manifest = deepcopy(GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_MANIFEST)
    return {
        **manifest,
        "collector_semantics_id": content_id(manifest, prefix="collector_"),
    }


def _check_cycle_query_coverage(
    store,
    *,
    expected_query_slots: list[tuple[str, str]],
    cycle_started_utc: float,
    cycle_completed_utc: float,
    periodic_requirements: dict[str, str] | None = None,
) -> dict:
    """Persist a collector heartbeat and alert on partial per-query failures."""
    # These fetchers distinguish parsed empty responses from transport/auth
    # failures. Globalnews remains deliberately strict and is absent here.
    allowed_empty_providers = frozenset(
        GLOBAL_EVENT_V2_PROTOCOL["evidence"]["query_cycle"]["allowed_observed_empty_providers"]
    )
    allow_empty = [slot for slot in expected_query_slots if slot[0] in allowed_empty_providers]
    frozen_globalnews_slots = set(_globalnews_query_slots(_global_only_news_themes()))
    require_lineage = [
        slot
        for slot in expected_query_slots
        if slot in frozen_globalnews_slots or slot[0] == "trendnews"
    ]
    # This is an operational post-cycle observation, not a model's point-in-time
    # cutoff. Advance by one representable float so a receipt committed at the
    # same clock tick is included while research cutoffs remain strictly before.
    coverage = store.coverage_report(
        math.nextafter(cycle_completed_utc, math.inf),
        [],
        expected_query_slots=expected_query_slots,
        allow_empty_query_slots=allow_empty,
        require_lineage_query_slots=require_lineage,
        min_started_utc=cycle_started_utc,
    )
    periodic = dict(periodic_requirements or {})
    if any(
        not isinstance(name, str)
        or name not in {"x_daily"}
        or state not in {
            "complete", "incomplete", "invalid", "missing", "running", "scheduled"
        }
        for name, state in periodic.items()
    ):
        raise ValueError("collector periodic requirement state is invalid")
    missing_periodic = sorted(
        name for name, state in periodic.items()
        if state not in {"complete", "scheduled"}
    )
    coverage["periodic_requirements"] = periodic
    coverage["missing_periodic_requirements"] = missing_periodic
    coverage["complete"] = bool(coverage["complete"] and not missing_periodic)
    heartbeat = "poller:last_success_utc" if coverage["complete"] else "poller:last_failure_utc"
    store.set_meta(heartbeat, cycle_completed_utc)
    _update_coverage_alert_state(store, coverage=coverage, observed_utc=cycle_completed_utc)
    return coverage


def _collapse_identical_fetch_rows(rows: list[dict], provider: str) -> list[dict]:
    """Collapse repeated identities while retaining every label association.

    Ranked discovery can assign one exact headline to more than one topic. A
    fetch receipt has one lineage row per content identity, so exact duplicates
    become one item whose normalized labels include every topic/ticker. A
    reused identity with different content remains a hard failure.
    """
    collapsed: dict[tuple[object, object], dict] = {}
    fingerprints: dict[tuple[object, object], str] = {}
    associations: dict[tuple[object, object], set[str]] = {}
    tickers: dict[tuple[object, object], set[str]] = {}
    provider_vintages: dict[str, object] = {}
    for row in rows:
        identity = (row.get("source"), row.get("external_id"))
        metadata = row.get("metadata")
        provider_external_id = (
            metadata.get("provider_external_id") if isinstance(metadata, dict) else None
        )
        if (
            provider in {"globalnews", "trendnews"}
            and isinstance(provider_external_id, str)
            and provider_external_id
        ):
            prior_vintage = provider_vintages.setdefault(
                provider_external_id, row.get("external_id")
            )
            if prior_vintage != row.get("external_id"):
                raise ValueError(f"{provider} response contained ambiguous provider revisions")
        fingerprint = _raw_content_id(row)
        if identity in fingerprints and (
            fingerprints[identity] != fingerprint
            or media_store._media_rows_conflict(collapsed[identity], row)
        ):
            raise ValueError(f"{provider} fetcher returned conflicting duplicate provenance")
        fingerprints.setdefault(identity, fingerprint)
        collapsed.setdefault(identity, dict(row))
        label_values = row.get("labels") or []
        if not isinstance(label_values, (list, tuple, set)):
            raise ValueError(f"{provider} fetcher returned invalid media labels")
        ticker = row.get("ticker")
        if not isinstance(ticker, str) or not ticker.strip():
            raise ValueError(f"{provider} fetcher returned an invalid media ticker")
        normalized_ticker = ticker.strip().upper()
        tickers.setdefault(identity, set()).add(normalized_ticker)
        normalized_labels = associations.setdefault(identity, set())
        normalized_labels.add(normalized_ticker)
        for label in label_values:
            if not isinstance(label, str) or not label.strip():
                raise ValueError(f"{provider} fetcher returned invalid media labels")
            normalized_labels.add(label.strip().upper())
    normalized = []
    for identity, row in collapsed.items():
        row["ticker"] = min(tickers[identity])
        row["labels"] = sorted(associations[identity])
        metadata = row.get("metadata")
        row["metadata"] = {
            **(metadata if isinstance(metadata, dict) else {}),
            "receipt_labels": list(row["labels"]),
        }
        normalized.append(row)
    return normalized


def _assert_store_collector_lease(store) -> None:
    """Fail before external work when the production leader lease was lost."""
    lease = getattr(store, "_collector_lease_guard", None)
    if lease is not None:
        lease.assert_held()


def _run_fetch(
    store,
    *,
    provider: str,
    query_key: str,
    fetch_fn,
    labels: list[str] | None = None,
    odds: bool = False,
    cost_units: float = 0.0,
    store_result: bool = True,
    formal_eligibility_fn=None,
    budget_limits: dict[str, float] | None = None,
    budget_metadata: dict | None = None,
    collection_cycle_id: str | None = None,
) -> tuple[int, int, str]:
    """Fetch, receipt-stamp, store, and audit one independent query."""
    _assert_store_collector_lease(store)
    if provider in {"globalnews", "trendnews", "x"} and formal_eligibility_fn is None:

        def _default_formal_eligibility(row, cutoff):
            return is_formally_eligible_evidence(row, as_of_utc=cutoff)

        formal_eligibility_fn = _default_formal_eligibility
    watermark_key = _watermark_key(provider, query_key)
    cursor_before = store.get_meta(watermark_key)
    started = time.time()
    metadata = {
        "labels": labels or [],
        "kind": "odds" if odds else "media" if store_result else "request_receipt",
        "protocol_id": GLOBAL_EVENT_V2_COLLECTION_PROTOCOL_ID,
        "collector_semantics_id": GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_ID,
        **(budget_metadata or {}),
    }
    if cost_units > 0 and not budget_limits:
        raise ValueError("paid fetches require a durable atomic budget reservation")
    if budget_limits:
        fetch_run_id = store.start_budgeted_fetch(
            provider,
            query_key,
            started,
            cursor_before=cursor_before,
            metadata=metadata,
            budget_limits=budget_limits,
            collection_cycle_id=collection_cycle_id,
        )
        if fetch_run_id is None:
            raise _FetchBudgetExceeded(f"{provider} request budget exhausted")
    else:
        fetch_run_id = store.start_fetch(
            provider,
            query_key,
            started,
            cursor_before=cursor_before,
            metadata=metadata,
            collection_cycle_id=collection_cycle_id,
        )
    received = started
    terminal_committed = False
    try:
        _assert_store_collector_lease(store)
        rows = fetch_fn(started)
        received = time.time()
        _assert_store_collector_lease(store)
        if not isinstance(rows, list):
            raise TypeError(f"{provider} fetcher returned {type(rows).__name__}, expected list")
        if (
            store_result
            and not odds
            and any(not isinstance(row, dict) or row.get("source") != provider for row in rows)
        ):
            raise ValueError(f"{provider} fetcher returned mismatched source provenance")
        formal_eligible_item_count = None
        formal_eligible_evidence_ids = None
        if odds:
            rows = [{**row, "captured_utc": received} for row in rows]
        elif store_result:
            rows = [
                {**row, "fetched_utc": received, **({"labels": labels} if labels else {})}
                for row in rows
            ]
            rows = _collapse_identical_fetch_rows(rows, provider)
            if formal_eligibility_fn is not None:
                formal_eligible_evidence_ids = sorted(
                    {
                        _evidence_id(row)
                        for row in rows
                        if (provider != "globalnews" or query_key in _formal_query_slots(row))
                        # Decision cutoffs are strict. For this receipt's own
                        # content projection, admit the exact response timestamp.
                        and formal_eligibility_fn(row, math.nextafter(received, math.inf))
                    }
                )
                formal_eligible_item_count = len(formal_eligible_evidence_ids)
        status = "success" if rows else "empty"
        cursor_after = received if rows else None
        inserted = store.complete_fetch(
            fetch_run_id,
            rows=rows,
            status=status,
            received_utc=received,
            completed_utc=time.time(),
            cost_units=cost_units,
            cursor_after=cursor_after,
            formal_eligible_item_count=formal_eligible_item_count,
            formal_eligible_evidence_ids=formal_eligible_evidence_ids,
            kind="odds" if odds else "media" if store_result else "request_receipt",
        )
        terminal_committed = True
        # The terminal receipt is authoritative. A watermark is only an
        # incremental-fetch optimization; failure after commit must never cause
        # a duplicate external request or a second success receipt.
        if rows:
            try:
                store.set_meta(watermark_key, received)
            except Exception as exc:  # noqa: BLE001 - terminal receipt already committed
                logger.info(
                    "%s fetch watermark update deferred (%s)",
                    _safe_alert_provider(provider),
                    _exception_kind(exc),
                )
        return len(rows), inserted, status
    except Exception as exc:
        if terminal_committed:
            raise AssertionError("terminal fetch work escaped its commit boundary") from exc
        store.finish_fetch(
            fetch_run_id,
            status="failed",
            received_utc=received,
            completed_utc=time.time(),
            item_count=0,
            inserted_count=0,
            error=_exception_kind(exc),
            cost_units=cost_units,
            formal_eligible_item_count=None,
            formal_eligible_evidence_ids=None,
        )
        raise


def poll_once(store, tickers: list[str], sources: list[str]) -> None:
    for ticker in tickers:
        parts = []
        for src in sources:
            try:
                _, inserted, status = _run_fetch(
                    store,
                    provider=src,
                    query_key=ticker,
                    fetch_fn=lambda captured, source=src, symbol=ticker: FETCHERS[source](
                        symbol, captured
                    ),
                    labels=[ticker],
                )
                parts.append(f"{src} {status} +{inserted}")
            except Exception as exc:  # independent query state must survive peer failures
                logger.error(
                    "%s fetch slot %s failed (%s)",
                    _safe_alert_provider(src),
                    _query_slot_id(src, ticker),
                    _exception_kind(exc),
                )
                parts.append(f"{src} failed")
        logger.info("%s: %s", ticker, " · ".join(parts))
        time.sleep(1.0)  # be polite between tickers


def poll_macro_once(store, themes: dict) -> None:
    """Snapshot the macro layer: per theme, global/theme news (windowed like the
    social sources) and live Polymarket odds. Odds are always stored — each poll
    is a fresh point in the probability time series. FRED is omitted (it's fully
    historical and fetched live at backtest time)."""
    globalnews_failure_slots = 0
    globalnews_skipped_slots = 0
    for theme, spec in themes.items():
        news_new = 0
        for query in spec.get("queries", []):
            if globalnews_failure_slots >= _GLOBALNEWS_CIRCUIT_FAILURE_SLOTS:
                globalnews_skipped_slots += 1
                continue
            try:
                _, inserted, _ = _run_globalnews_query(store, theme, query)
                news_new += inserted
            except (ProviderTransientError, ProviderResponseError) as exc:
                globalnews_failure_slots += 1
                logger.info(
                    "globalnews fetch slot %s unavailable (%s)",
                    _query_slot_id("globalnews", f"{theme}:{query}"),
                    _exception_kind(exc),
                )
                if globalnews_failure_slots == _GLOBALNEWS_CIRCUIT_FAILURE_SLOTS:
                    logger.info(
                        "globalnews cycle circuit opened after %d unavailable slots",
                        globalnews_failure_slots,
                    )
            except Exception:
                # Persistence, programming, and invariant failures are not
                # provider outages. Let daemon health fail closed on them.
                raise
        odds_new = 0
        for topic in spec.get("prediction_topics", []):
            try:
                _, inserted, _ = _run_fetch(
                    store,
                    provider="polymarket",
                    query_key=f"{theme}:{topic}",
                    fetch_fn=lambda captured, p=topic, t=theme: fetch_polymarket_odds(
                        p, captured, t
                    ),
                    odds=True,
                )
                odds_new += inserted
            except Exception as exc:
                logger.error(
                    "polymarket fetch slot %s failed (%s)",
                    _query_slot_id("polymarket", f"{theme}:{topic}"),
                    _exception_kind(exc),
                )
        logger.info("macro[%s]: globalnews +%d · polymarket-odds +%d", theme, news_new, odds_new)
    if globalnews_skipped_slots:
        logger.info(
            "globalnews cycle circuit skipped %d remaining slots",
            globalnews_skipped_slots,
        )


def _run_globalnews_query(
    store,
    theme: str,
    query: str,
    *,
    sleep_fn=None,
    collection_cycle_id: str | None = None,
    max_attempts: int | None = None,
) -> tuple[int, int, str]:
    """Run one broad-news slot with bounded transient-transport retries.

    Every attempt calls ``_run_fetch`` and therefore owns a distinct immutable
    receipt. A structurally valid empty response is terminal for this cycle: it
    is not silently converted into success and is never retried as though it
    were a transport exception.
    """
    sleeper = time.sleep if sleep_fn is None else sleep_fn
    attempt_limit = _GLOBALNEWS_MAX_ATTEMPTS if max_attempts is None else max_attempts
    if (
        isinstance(attempt_limit, bool)
        or not isinstance(attempt_limit, int)
        or not 1 <= attempt_limit <= _GLOBALNEWS_MAX_ATTEMPTS
    ):
        raise ValueError("globalnews attempt limit is invalid")
    if collection_cycle_id is not None and attempt_limit != 1:
        # A collection-cycle slot intentionally owns one immutable child
        # receipt. The release rehearsal therefore fails on its first transport
        # exception; ordinary hourly collection retains the frozen three-attempt
        # policy and one append-only receipt per attempt.
        raise ValueError("collection-cycle globalnews slots require one exact attempt")
    query_key = f"{theme}:{query}"
    for attempt_ordinal in range(1, attempt_limit + 1):
        try:
            return _run_fetch(
                store,
                provider="globalnews",
                query_key=query_key,
                fetch_fn=lambda captured: fetch_global_news(
                    query,
                    captured,
                    theme,
                    limit=int(
                        GLOBAL_EVENT_V2_PROTOCOL["evidence"]["max_global_news_results_per_query"]
                    ),
                ),
                labels=[f"@{theme}", global_news_query_slot_label(theme, query)],
                formal_eligibility_fn=lambda row, cutoff: is_formally_eligible_evidence(
                    row, as_of_utc=cutoff
                ),
                budget_metadata={
                    "attempt_ordinal": attempt_ordinal,
                    "max_attempts": attempt_limit,
                    "retry_policy": "provider_transient_exception_only",
                },
                collection_cycle_id=collection_cycle_id,
            )
        except ProviderTransientError as exc:
            if attempt_ordinal >= attempt_limit:
                raise
            logger.info(
                "globalnews fetch slot %s attempt %d/%d failed (%s); retrying",
                _query_slot_id("globalnews", query_key),
                attempt_ordinal,
                attempt_limit,
                _exception_kind(exc),
            )
            sleeper(_GLOBALNEWS_RETRY_DELAYS[attempt_ordinal - 1])
    raise AssertionError("unreachable globalnews retry state")


def _headline_without_publisher(title: str) -> str:
    """Remove Google News' trailing `` - Publisher`` attribution."""
    return re.sub(str(_DISCOVERY_NORMALIZATION["publisher_suffix_pattern"]), "", title).strip()


def _discovery_lower(text: str) -> str:
    if _DISCOVERY_NORMALIZATION["case"] != "lower":
        raise RuntimeError("discovery case-normalization policy is unsupported")
    return text.lower()


def _discovery_order_key(values: Mapping[str, object], order: object) -> tuple:
    if not isinstance(order, tuple) or any(name not in values for name in order):
        raise RuntimeError("discovery ordering policy is unsupported")
    return tuple(values[name] for name in order)


def _is_capitalized_anchor(token: str) -> bool:
    if _DISCOVERY_QUERY["capitalization"] != "initial-or-internal-uppercase-v1":
        raise RuntimeError("discovery capitalization policy is unsupported")
    return token[0].isupper() or any(char.isupper() for char in token[1:])


def _is_distinctive_anchor(token: str) -> bool:
    if (
        _DISCOVERY_QUERY["distinctive_token"]
        != "digit-or-internal-uppercase-or-single-uppercase-v1"
    ):
        raise RuntimeError("discovery distinctive-token policy is unsupported")
    return (
        any(char.isdigit() for char in token)
        or any(char.isupper() for char in token[1:])
        or (len(token) == 1 and token.isupper())
    )


def _topic_key(text: str) -> str:
    normalized = _discovery_lower(_headline_without_publisher(text))
    return " ".join(re.findall(str(_DISCOVERY_NORMALIZATION["word_pattern"]), normalized))


def _semantic_terms(text: str) -> set[str]:
    terms = set()
    normalized = _discovery_lower(_headline_without_publisher(text))
    for token in re.findall(str(_DISCOVERY_NORMALIZATION["word_pattern"]), normalized):
        if (
            len(token) < int(_DISCOVERY_NORMALIZATION["semantic_min_chars"])
            and token not in _DISCOVERY_NORMALIZATION["semantic_short_allowlist"]
        ) or token in _QUERY_STOPWORDS:
            continue
        # Lightweight normalization is deterministic and avoids a large NLP
        # dependency in the 256 MB collector.
        token = next(
            (
                replacement
                for prefix, replacement in _DISCOVERY_NORMALIZATION["semantic_prefix_aliases"]
                if token.startswith(prefix)
            ),
            token,
        )
        token = dict(_DISCOVERY_NORMALIZATION["semantic_exact_aliases"]).get(token, token)
        plural_suffix = str(_DISCOVERY_NORMALIZATION["plural_suffix"])
        if len(token) >= int(_DISCOVERY_NORMALIZATION["plural_min_chars"]) and token.endswith(
            plural_suffix
        ):
            token = token[: -len(plural_suffix)]
        terms.add(token)
    return terms


def _same_story(left: str, right: str) -> bool:
    a, b = _semantic_terms(left), _semantic_terms(right)
    if not a or not b:
        return False
    overlap = len(a & b)
    jaccard = overlap / len(a | b)
    return jaccard >= float(_DISCOVERY_STORY_GROUPING["primary_jaccard_min"]) or (
        overlap >= int(_DISCOVERY_STORY_GROUPING["secondary_overlap_min"])
        and jaccard >= float(_DISCOVERY_STORY_GROUPING["secondary_jaccard_min"])
    )


def _trend_matches_headline(trend: str, headline: str) -> bool:
    word_pattern = str(_DISCOVERY_NORMALIZATION["word_pattern"])
    trend_words = set(
        re.findall(
            word_pattern,
            _discovery_lower(trend).lstrip(
                str(_DISCOVERY_TREND_MATCHING["leading_chars_to_strip"])
            ),
        )
    )
    headline_words = set(re.findall(word_pattern, _discovery_lower(headline)))
    meaningful = {
        word
        for word in trend_words
        if len(word) >= int(_DISCOVERY_TREND_MATCHING["meaningful_min_chars"])
        and word not in _QUERY_STOPWORDS
    }
    if not meaningful:
        return False
    needed = int(
        _DISCOVERY_TREND_MATCHING[
            "single_term_required_overlap"
            if len(meaningful) == 1
            else "multiple_term_required_overlap"
        ]
    )
    return len(meaningful & headline_words) >= needed


def _headline_query(title: str) -> str:
    """Turn a discovered headline into a compact X query without a watchlist.

    Named phrases are extracted from the headline itself and paired with one
    descriptive word. This is broad enough to capture public reaction while
    avoiding a brittle exact-headline search.
    """
    headline = _headline_without_publisher(title)
    tokens = re.findall(str(_DISCOVERY_QUERY["token_pattern"]), headline)
    capitalized_runs: list[list[str]] = []
    run: list[str] = []
    for token in tokens:
        is_capitalized = _is_capitalized_anchor(token)
        if is_capitalized and _discovery_lower(token) not in _QUERY_STOPWORDS:
            run.append(token)
        elif run:
            capitalized_runs.append(run)
            run = []
    if run:
        capitalized_runs.append(run)

    anchors = []
    for words in capitalized_runs:
        while words and words[0] in _GENERIC_CAPITALIZED:
            words = words[1:]
        if not words:
            continue
        distinctive = [word for word in words if _is_distinctive_anchor(word)]
        if len(words) >= int(_DISCOVERY_QUERY["long_run_min_words"]):
            cap = int(_DISCOVERY_QUERY["long_run_word_cap"])
            words = distinctive[:cap] or words[:cap]
        phrase = " ".join(words[: int(_DISCOVERY_QUERY["phrase_word_cap"])])
        if len(words) >= int(_DISCOVERY_QUERY["qualified_phrase_min_words"]) or distinctive:
            anchors.append((phrase, bool(distinctive)))
    anchors = sorted(
        set(anchors),
        key=lambda value: _discovery_order_key(
            {
                "distinctive-desc": value[1],
                "word-count-desc": len(value[0].split()),
                "character-count-desc": len(value[0]),
            },
            _DISCOVERY_QUERY["anchor_order"],
        ),
        reverse=True,
    )

    chosen = [phrase for phrase, _distinctive in anchors[: int(_DISCOVERY_QUERY["anchor_cap"])]]
    anchor_words = {_discovery_lower(word) for phrase in chosen for word in phrase.split()}
    signals = [
        token
        for token in tokens
        if len(token) >= int(_DISCOVERY_QUERY["signal_min_chars"])
        and _discovery_lower(token) not in _QUERY_STOPWORDS
        and _discovery_lower(token) not in anchor_words
        and token not in _GENERIC_CAPITALIZED
    ]

    quote = str(_DISCOVERY_QUERY["phrase_quote"])
    parts = [f"{quote}{phrase.replace(quote, '')}{quote}" for phrase in chosen]
    if parts and len(parts) < int(_DISCOVERY_QUERY["query_part_cap"]) and signals:
        parts.append(signals[0])
    if not parts:
        parts = signals[: int(_DISCOVERY_QUERY["fallback_signal_cap"])]
    return " ".join(parts)[: int(_DISCOVERY_QUERY["max_query_chars"])]


def _looks_company_authored(headline: dict) -> bool:
    """Reject press-release/newsroom items; discovery should measure reaction."""
    return looks_company_authored(headline.get("publisher"), headline.get("title"))


def discover_x_topics(
    max_topics: int,
    *,
    headlines: list[dict] | None = None,
    trends: list[dict] | None = None,
) -> list[dict]:
    """Select a small, diverse set of current high-information news topics.

    Ranked top-news feeds supply candidates. US and worldwide X trends can
    boost a matching headline, but cannot introduce an entertainment-only
    search on their own. One candidate per world/business/technology category
    maximizes coverage when the normal three-topic budget is used.
    """
    headlines = (
        fetch_top_news_headlines(limit_per_feed=int(_DISCOVERY_INPUTS["ranked_feed_limit"]))
        if headlines is None
        else headlines
    )
    if trends is None:
        trends = [
            trend
            for woeid in GLOBAL_EVENT_V2_PROTOCOL["evidence"]["x_trend_woeids"]
            for trend in fetch_x_trends(int(woeid), limit=_GLOBAL_X_TREND_LIMIT)
        ]
    trend_names = [trend["name"] for trend in trends if trend.get("name")]

    grouped: dict[str, dict] = {}
    if _DISCOVERY_STORY_GROUPING["resolution"] != "first-matching-input-group":
        raise RuntimeError("discovery story-group resolution policy is unsupported")
    if _DISCOVERY_ALLOCATION["representation_order"] != "configured-category-order":
        raise RuntimeError("discovery representation policy is unsupported")
    for headline in headlines:
        if (
            bool(_DISCOVERY_INPUTS["exclude_low_information"])
            and _LOW_INFORMATION_HEADLINE.search(headline.get("title", ""))
        ) or (
            bool(_DISCOVERY_INPUTS["exclude_company_authored"])
            and _looks_company_authored(headline)
        ):
            continue
        key = _topic_key(headline.get("title", ""))
        if not key:
            continue
        key = next(
            (
                existing
                for existing, candidate in grouped.items()
                if _same_story(candidate["title"], headline["title"])
            ),
            key,
        )
        candidate = grouped.setdefault(
            key,
            {
                **headline,
                "categories": set(),
                "regions": set(),
                "ranks": {},
                "lineage": [],
            },
        )
        category = headline.get("category", str(_DISCOVERY_RANKING["default_category"]))
        candidate["categories"].add(category)
        candidate["regions"].add(headline.get("region", str(_DISCOVERY_RANKING["default_region"])))
        candidate["lineage"].append(
            {key: headline.get(key) for key in _DISCOVERY_RANKING["lineage_fields"]}
        )
        missing_rank = int(_DISCOVERY_RANKING["missing_rank"])
        candidate["ranks"][category] = min(
            candidate["ranks"].get(category, missing_rank),
            headline.get("rank", missing_rank),
        )

    candidates = []
    for candidate in grouped.values():
        best_rank = min(candidate["ranks"].values())
        cross_feed_bonus = int(_DISCOVERY_RANKING["cross_feed_weight"]) * (
            len(candidate["categories"]) - int(_DISCOVERY_RANKING["cross_source_baseline_count"])
        )
        cross_region_bonus = int(_DISCOVERY_RANKING["cross_region_weight"]) * (
            len(candidate["regions"]) - int(_DISCOVERY_RANKING["cross_source_baseline_count"])
        )
        trend_bonus = (
            int(_DISCOVERY_RANKING["trend_match_weight"])
            if any(_trend_matches_headline(name, candidate["title"]) for name in trend_names)
            else 0
        )
        candidate["score"] = (
            int(_DISCOVERY_RANKING["score_base"])
            - min(best_rank, int(_DISCOVERY_RANKING["score_rank_cap"]))
            * int(_DISCOVERY_RANKING["score_rank_weight"])
            + cross_feed_bonus
            + cross_region_bonus
            + trend_bonus
        )
        candidate["query"] = _headline_query(candidate["title"])
        if candidate["query"]:
            candidates.append(candidate)

    chosen = []
    used_keys = set()
    for category in _DISCOVERY_CATEGORIES:
        eligible = [
            candidate
            for candidate in candidates
            if category in candidate["categories"]
            and _topic_key(candidate["title"]) not in used_keys
        ]
        if not eligible or len(chosen) >= max_topics:
            continue
        best = min(
            eligible,
            key=lambda candidate: _discovery_order_key(
                {
                    "category-adjusted-score-desc": -(
                        candidate["score"]
                        - candidate["ranks"].get(
                            category,
                            int(_DISCOVERY_RANKING["category_missing_rank"]),
                        )
                        * int(_DISCOVERY_RANKING["category_rank_weight"])
                    ),
                    "created-utc-desc": -(
                        candidate.get("created_utc")
                        or int(_DISCOVERY_RANKING["missing_created_utc"])
                    ),
                    "topic-key-asc": _topic_key(candidate["title"]),
                    "query-asc": candidate["query"],
                },
                _DISCOVERY_ALLOCATION["category_candidate_order"],
            ),
        )
        best = {
            **best,
            "topic": f"{_DISCOVERY_ALLOCATION['topic_prefix']}{category}",
            "category": category,
        }
        chosen.append(best)
        used_keys.add(_topic_key(best["title"]))

    if len(chosen) < max_topics:
        remaining = sorted(
            candidates,
            key=lambda candidate: _discovery_order_key(
                {
                    "score-desc": -candidate["score"],
                    "created-utc-desc": -(
                        candidate.get("created_utc")
                        or int(_DISCOVERY_RANKING["missing_created_utc"])
                    ),
                    "topic-key-asc": _topic_key(candidate["title"]),
                    "query-asc": candidate["query"],
                },
                _DISCOVERY_ALLOCATION["remaining_candidate_order"],
            ),
        )
        for candidate in remaining:
            key = _topic_key(candidate["title"])
            if key in used_keys:
                continue
            formal_categories = [
                category
                for category in _DISCOVERY_CATEGORIES
                if category in candidate["categories"]
            ]
            if not formal_categories:
                continue
            category = min(
                formal_categories,
                key=lambda value: _discovery_order_key(
                    {
                        "rank-asc": candidate["ranks"].get(
                            value, int(_DISCOVERY_RANKING["missing_rank"])
                        ),
                        "configured-category-order": (_DISCOVERY_CATEGORIES.index(value)),
                    },
                    _DISCOVERY_ALLOCATION["fallback_category_order"],
                ),
            )
            chosen.append(
                {
                    **candidate,
                    "topic": f"{_DISCOVERY_ALLOCATION['topic_prefix']}{category}",
                    "category": category,
                }
            )
            used_keys.add(key)
            if len(chosen) >= max_topics:
                break
    return chosen


def _group_x_search_topics(topics: list[dict]) -> list[dict]:
    """Collapse identical derived queries before declaring or issuing requests."""
    if _DISCOVERY_ALLOCATION["search_request_grouping"] != (
        "exact-query-with-sorted-label-union-v1"
    ) or _DISCOVERY_ALLOCATION["search_request_order"] != "query-asc":
        raise RuntimeError("discovery request-grouping policy is unsupported")
    grouped: dict[str, dict] = {}
    for topic in topics:
        query = topic.get("query")
        topic_name = topic.get("topic")
        category = topic.get("category")
        external_id = topic.get("external_id")
        if not all(
            isinstance(value, str) and value
            for value in (query, topic_name, category, external_id)
        ):
            raise ValueError("selected X topics require complete request provenance")
        group = grouped.setdefault(
            query,
            {
                "query_key": query,
                "topic": topic_name,
                "labels": set(),
                "categories": set(),
                "selected_external_ids": set(),
            },
        )
        group["topic"] = min(group["topic"], topic_name)
        group["labels"].add(f"@{topic_name}".upper())
        group["categories"].add(category)
        group["selected_external_ids"].add(external_id)
    return [
        {
            **group,
            "labels": sorted(group["labels"]),
            "categories": sorted(group["categories"]),
            "selected_external_ids": sorted(group["selected_external_ids"]),
        }
        for _query, group in sorted(grouped.items())
    ]


def _discovery_topic_decision(topic: dict) -> dict:
    return {
        key: deepcopy(topic.get(key))
        for key in _DISCOVERY_AUDIT["selected_topic_fields"]
    }


def _discovery_input_headline(headline: dict) -> dict:
    metadata = headline.get("metadata")
    return {
        **{
            key: deepcopy(headline.get(key))
            for key in _DISCOVERY_AUDIT["headline_fields"]
        },
        "metadata": {
            key: deepcopy(metadata.get(key)) if isinstance(metadata, dict) else None
            for key in _DISCOVERY_AUDIT["headline_metadata_fields"]
        },
    }


def _x_discovery_decision_manifest(
    *,
    collection_cycle_id: str,
    captured_utc: float,
    max_topics: int,
    headlines: list[dict],
    trends: list[dict],
    topics: list[dict],
    search_requests: list[dict],
) -> dict:
    if (
        not isinstance(collection_cycle_id, str)
        or re.fullmatch(r"cycle_[0-9a-f]{24}", collection_cycle_id) is None
        or isinstance(captured_utc, bool)
        or not isinstance(captured_utc, (int, float))
        or not math.isfinite(float(captured_utc))
        or isinstance(max_topics, bool)
        or not isinstance(max_topics, int)
        or max_topics
        != int(GLOBAL_EVENT_V2_PROTOCOL["evidence"]["max_x_search_requests_per_utc_day"])
        or any(not isinstance(item, dict) for item in headlines)
        or any(not isinstance(item, dict) for item in trends)
    ):
        raise ValueError("X discovery decision parameters are invalid")
    payload = {
        "schema_version": 1,
        "collection_cycle_id": collection_cycle_id,
        "collection_protocol_id": GLOBAL_EVENT_V2_COLLECTION_PROTOCOL_ID,
        "collector_semantics_id": GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_ID,
        "discovery_policy_id": content_id(
            discovery_policy_manifest(), prefix="discovery_policy_"
        ),
        "captured_utc": float(captured_utc),
        "max_topics": max_topics,
        "discovery_input": {
            "headlines": [
                _discovery_input_headline(headline) for headline in headlines
            ],
            "trends": [
                {key: deepcopy(trend.get(key)) for key in _DISCOVERY_AUDIT["trend_fields"]}
                for trend in trends
            ],
        },
        "selected_topics": [_discovery_topic_decision(topic) for topic in topics],
        "search_requests": deepcopy(search_requests),
    }
    return {
        "discovery_decision_id": content_id(payload, prefix="xdiscovery_"),
        **payload,
    }


def validate_x_discovery_decision(manifest: dict) -> None:
    """Replay a stored query-free input and require its exact selection decision."""
    if not isinstance(manifest, dict):
        raise ValueError("X discovery decision must be a mapping")
    payload = {
        key: value for key, value in manifest.items()
        if key != "discovery_decision_id"
    }
    if manifest.get("discovery_decision_id") != content_id(
        payload, prefix="xdiscovery_"
    ):
        raise ValueError("X discovery decision identity is invalid")
    inputs = manifest.get("discovery_input")
    headlines = inputs.get("headlines") if isinstance(inputs, dict) else None
    trends = inputs.get("trends") if isinstance(inputs, dict) else None
    captured = manifest.get("captured_utc")
    max_topics = manifest.get("max_topics")
    if not isinstance(headlines, list) or not isinstance(trends, list):
        raise ValueError("X discovery decision input is malformed")
    topics = _formally_grounded_discovery_topics(
        discover_x_topics(
            max_topics=max_topics,
            headlines=deepcopy(headlines),
            trends=deepcopy(trends),
        ),
        captured,
    )
    expected = _x_discovery_decision_manifest(
        collection_cycle_id=manifest.get("collection_cycle_id"),
        captured_utc=captured,
        max_topics=max_topics,
        headlines=headlines,
        trends=trends,
        topics=topics,
        search_requests=_group_x_search_topics(topics),
    )
    if manifest != expected:
        raise ValueError("X discovery decision does not replay from its immutable input")


def x_discovery_decision_row(manifest: dict) -> dict:
    validate_x_discovery_decision(manifest)
    captured = manifest["captured_utc"]
    decision_id = manifest["discovery_decision_id"]
    return {
        "source": "trendnews",
        "external_id": decision_id,
        "ticker": "@X_DISCOVERY_AUDIT",
        "subreddit": None,
        "author": None,
        "sentiment": None,
        "created_utc": captured,
        "title": "Query-free X discovery decision",
        "body": canonical_json(manifest),
        "fetched_utc": captured,
        "metadata": {
            "evidence_role": "query_free_discovery_decision",
            "discovery_decision_id": decision_id,
        },
    }


def _discovery_news_row(topic: dict, now: float, headline: dict | None = None) -> dict:
    headline = headline or topic
    return {
        "source": "trendnews",
        "external_id": headline["external_id"],
        "ticker": f"@{topic['topic']}".upper(),
        "subreddit": None,
        "author": headline.get("publisher"),
        "sentiment": None,
        "created_utc": headline.get("created_utc"),
        "title": headline.get("title"),
        "body": headline.get("body", ""),
        "fetched_utc": now,
        "metadata": headline.get("metadata") or {},
    }


def _formally_grounded_discovery_topics(topics: list[dict], captured_utc: float) -> list[dict]:
    """Keep topics grounded in recent, independent editorial discovery lineage.

    Discovery rows are deliberately stored as ``trendnews`` provenance, which
    is not formal forecast evidence.  Reusing the formal evidence predicate
    here would therefore reject every discovery row.  Apply the narrower
    discovery boundary directly: an exact frozen publisher/domain pair, no
    company-authored material, a stable provider ID, and a publication time in
    the same frozen lookback window.  The resulting topic may drive a paid X
    search, but the discovery headline itself never crosses the forecast
    boundary.
    """
    if (
        isinstance(captured_utc, bool)
        or not isinstance(captured_utc, (int, float))
        or not math.isfinite(float(captured_utc))
    ):
        raise ValueError("discovery capture time must be finite")
    captured = float(captured_utc)
    lookback = float(GLOBAL_EVENT_V2_PROTOCOL["evidence"]["lookback_days"] * 86400)

    def eligible_lineage(headline: dict, topic: dict) -> bool:
        try:
            row = _discovery_news_row(topic, captured, headline)
        except (KeyError, TypeError):
            return False
        external_id = row.get("external_id")
        published = row.get("created_utc")
        return (
            isinstance(external_id, str)
            and bool(external_id)
            and not isinstance(published, bool)
            and isinstance(published, (int, float))
            and math.isfinite(float(published))
            and captured - lookback <= float(published) <= captured
            and global_research.is_independent_editorial_evidence(row)
            and not global_research.is_company_authored_evidence(row)
        )

    grounded = []
    for topic in topics:
        lineage = topic.get("lineage") if isinstance(topic.get("lineage"), list) else []
        headlines = lineage or [topic]
        if any(
            eligible_lineage(headline, topic)
            for headline in headlines
            if isinstance(headline, dict)
        ):
            grounded.append(topic)
    return grounded


def _x_request_budget_limits(category: str, now: float, request_key: str) -> dict[str, float]:
    """Return aggregate and idempotency counters for one paid X request."""
    if category == "trend":
        limit = int(GLOBAL_EVENT_V2_PROTOCOL["evidence"]["max_x_trend_requests_per_utc_day"])
    elif category == "search":
        limit = int(GLOBAL_EVENT_V2_PROTOCOL["evidence"]["max_x_search_requests_per_utc_day"])
    else:
        raise ValueError("unknown X budget category")
    day = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")
    request_id = hashlib.sha256(request_key.encode("utf-8")).hexdigest()[:16]
    prefix = f"x-budget:{category}:{day}"
    return {
        f"{prefix}:total": float(limit),
        f"{prefix}:request:{request_id}": 1.0,
    }


def _x_trend_media_rows(
    trends: list[dict],
    *,
    woeid: int,
    captured_utc: float,
) -> list[dict]:
    """Persist every ranked trend response item as discovery-only provenance."""
    if not isinstance(trends, list):
        raise TypeError("X trend response must be a list")
    captured = float(captured_utc)
    if not math.isfinite(captured):
        raise ValueError("X trend capture time must be finite")
    rows = []
    for rank, trend in enumerate(trends):
        if not isinstance(trend, dict):
            raise TypeError("X trend entries must be mappings")
        name = trend.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("X trend entries require a non-empty name")
        name = name.strip()
        count = trend.get("tweet_count")
        if count is not None and (
            isinstance(count, bool) or not isinstance(count, int) or count < 0
        ):
            raise ValueError("X trend tweet counts must be non-negative integers or null")
        snapshot = {
            "woeid": int(woeid),
            "rank": rank,
            "trend_name": name,
            "tweet_count": count,
            "captured_utc": captured,
        }
        rows.append(
            {
                "source": "xtrend",
                "external_id": content_id(snapshot, prefix="xtrend_"),
                "ticker": f"@X_TREND_{int(woeid)}",
                "subreddit": None,
                "author": None,
                "sentiment": None,
                "created_utc": captured,
                "title": name,
                "body": canonical_json(snapshot),
                "fetched_utc": captured,
                "metadata": {
                    "evidence_role": "discovery_only",
                    "woeid": int(woeid),
                    "rank": rank,
                    "tweet_count": count,
                },
            }
        )
    return rows


def _x_collection_cycle_spec_for_identity(
    now: float,
    identity: Mapping,
) -> dict:
    """Rebuild one exact daily X identity before any provider request starts."""
    if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now):
        raise ValueError("X collection cycle time must be finite")
    period_key = datetime.fromtimestamp(float(now), timezone.utc).strftime("%Y-%m-%d")
    return media_store.collection_cycle_spec(
        cycle_kind="x-daily",
        period_key=period_key,
        protocol_id=identity["protocol_id"],
        collector_semantics_id=identity["collector_semantics_id"],
        expected_static_slots=identity["x_daily_static_slots"],
        max_dynamic_slots=identity["x_daily_max_dynamic_slots"],
    )


def _x_start_window_open(now: float) -> bool:
    return _x_start_window_state(now) == "open"


def _x_start_window_state(now: float) -> str:
    if (
        isinstance(now, bool)
        or not isinstance(now, (int, float))
        or not math.isfinite(float(now))
    ):
        raise ValueError("X collection cycle time must be finite")
    value = float(now)
    day = datetime.fromtimestamp(value, timezone.utc)
    start = datetime.combine(
        day.date(), datetime.min.time(), tzinfo=timezone.utc
    ).timestamp()
    next_day = datetime.combine(
        day.date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
    ).timestamp()
    earliest = float(
        GLOBAL_EVENT_V2_PROTOCOL["evidence"][
            "x_cycle_start_earliest_utc_seconds"
        ]
    )
    minimum = float(
        GLOBAL_EVENT_V2_PROTOCOL["evidence"][
            "x_cycle_start_minimum_remaining_utc_seconds"
        ]
    )
    if (
        not math.isfinite(earliest)
        or not math.isfinite(minimum)
        or earliest < 0
        or minimum <= 0
        or earliest >= 86400 - minimum
    ):
        raise ValueError("X cycle start-window policy is invalid")
    if value - start < earliest:
        return "scheduled"
    return "open" if next_day - value >= minimum else "closed"


def _x_collection_cycle_spec(now: float, max_topics: int) -> dict:
    """Return the current daily X identity before any provider request starts."""
    if max_topics != GLOBAL_EVENT_V2_CURRENT_COLLECTOR_IDENTITY["x_daily_max_dynamic_slots"]:
        raise ValueError("X topic limit does not match the current collector identity")
    return _x_collection_cycle_spec_for_identity(now, GLOBAL_EVENT_V2_CURRENT_COLLECTOR_IDENTITY)


def _x_compatible_collection_cycle_specs(now: float) -> list[dict]:
    """Rebuild only the protocol's explicitly allowlisted prior X identities."""
    specs = []
    for identity in GLOBAL_EVENT_V2_COMPATIBLE_COLLECTOR_IDENTITIES:
        specs.append(_x_collection_cycle_spec_for_identity(now, identity))
    return specs


def _x_collection_cycle_state(spec: dict, cycle: Mapping | None) -> str:
    """Return the shared operational/formal structural state."""
    return x_cycle_structural_state(spec, cycle)


def _x_daily_cycle_resolution(store, now: float, max_topics: int) -> dict:
    """Resolve one same-day attempt, preferring current over prior identities.

    Any exact allowlisted prior attempt blocks creation of a fresh paid identity.
    When more than one prior identity exists, select the newest present
    compatible cycle. This is the same precedence rule used by the research
    projection and never depends on terminal status or content.
    """
    current_spec = _x_collection_cycle_spec(now, max_topics)
    compatible_specs = _x_compatible_collection_cycle_specs(now)

    try:
        current_cycle = store.collection_cycle(current_spec["collection_cycle_id"])
    except ValueError:
        return {
            "origin": "current",
            "spec": current_spec,
            "cycle": None,
            "state": "invalid",
            "blocks_new_paid_cycle": True,
        }
    if current_cycle is not None:
        return {
            "origin": "current",
            "spec": current_spec,
            "cycle": current_cycle,
            "state": _x_collection_cycle_state(current_spec, current_cycle),
            "blocks_new_paid_cycle": True,
        }

    for spec in compatible_specs:
        try:
            cycle = store.collection_cycle(spec["collection_cycle_id"])
        except ValueError:
            return {
                "origin": "compatible",
                "spec": spec,
                "cycle": None,
                "state": "invalid",
                "blocks_new_paid_cycle": True,
            }
        if cycle is not None:
            return {
                "origin": "compatible",
                "spec": spec,
                "cycle": cycle,
                "state": _x_collection_cycle_state(spec, cycle),
                "blocks_new_paid_cycle": True,
            }
    period_key = current_spec["identity"]["period_key"]
    try:
        observed_cycles = store.collection_cycle_identities("x-daily", period_key=period_key)
    except (AttributeError, TypeError, ValueError):
        observed_cycles = None
    if not isinstance(observed_cycles, list) or observed_cycles:
        # An unrecognized or unreadable same-day identity is never admissible,
        # but it still blocks another paid attempt until an operator resolves it.
        return {
            "origin": "unknown",
            "spec": current_spec,
            "cycle": None,
            "state": "invalid",
            "blocks_new_paid_cycle": True,
        }
    return {
        "origin": None,
        "spec": current_spec,
        "cycle": None,
        "state": "missing",
        "blocks_new_paid_cycle": False,
    }


def _x_manifest_slots(cycle: Mapping) -> list[tuple[str, str]]:
    manifest = cycle.get("manifest")
    if not isinstance(manifest, Mapping):
        return []
    return [
        (slot["provider"], slot["query_key"])
        for slot in (
            list(manifest.get("expected_static_slots") or [])
            + list(manifest.get("expected_dynamic_slots") or [])
        )
    ]


def _poll_x_cycle_children(
    store,
    *,
    now: float,
    limit: int,
    max_topics: int,
    collection_cycle_id: str,
    expected_slots: list[tuple[str, str]],
    discovery_headlines: list[dict],
) -> list[tuple[str, str]]:
    """Execute one cycle's children after its immutable parent is durable.

    The query-free news dependency is fetched before the cycle is created and
    before any paid X request is reserved.  Reusing that exact snapshot here
    prevents a free-feed outage from consuming the day's paid allowance.
    """
    trends: list[dict] = []
    for raw_woeid in GLOBAL_EVENT_V2_PROTOCOL["evidence"]["x_trend_woeids"]:
        woeid = int(raw_woeid)
        query_key = f"woeid:{woeid}"
        try:
            trend_box: dict[str, list[dict]] = {}

            def fetch_trends(captured, *, location=woeid, result=trend_box):
                result["raw"] = fetch_x_trends(location, limit=_GLOBAL_X_TREND_LIMIT)
                return _x_trend_media_rows(result["raw"], woeid=location, captured_utc=captured)

            _run_fetch(
                store,
                provider="xtrend",
                query_key=query_key,
                fetch_fn=fetch_trends,
                labels=[f"@X_TREND_{woeid}"],
                cost_units=1.0,
                budget_limits=_x_request_budget_limits("trend", now, query_key),
                budget_metadata={"budget_category": "trend"},
                collection_cycle_id=collection_cycle_id,
            )
            trends.extend(trend_box.get("raw", []))
        except _FetchBudgetExceeded:
            logger.info("X trend request budget already reserved; skipping %s", query_key)
        except (ProviderTransientError, ProviderResponseError) as exc:
            logger.info(
                "xtrend slot %s unavailable (%s); stopping paid cycle",
                _query_slot_id("xtrend", query_key),
                _exception_kind(exc),
            )
            return expected_slots
        except Exception:
            raise

    discovery_box: dict[str, list[dict]] = {}

    def discover(captured):
        topics = _formally_grounded_discovery_topics(
            discover_x_topics(
                max_topics=max_topics,
                headlines=discovery_headlines,
                trends=trends,
            ),
            captured,
        )
        search_requests = _group_x_search_topics(topics)
        decision = _x_discovery_decision_manifest(
            collection_cycle_id=collection_cycle_id,
            captured_utc=captured,
            max_topics=max_topics,
            headlines=discovery_headlines,
            trends=trends,
            topics=topics,
            search_requests=search_requests,
        )
        discovery_box["topics"] = topics
        discovery_box["search_requests"] = search_requests
        return [
            _discovery_news_row(topic, captured, headline)
            for topic in topics
            for headline in (topic.get("lineage") or [topic])
        ] + [x_discovery_decision_row(decision)]

    try:
        _, _, discovery_status = _run_fetch(
            store,
            provider="trendnews",
            query_key="ranked-global-discovery",
            fetch_fn=discover,
            formal_eligibility_fn=lambda row, cutoff: is_formally_eligible_evidence(
                row, as_of_utc=cutoff
            ),
            collection_cycle_id=collection_cycle_id,
        )
    except (ProviderTransientError, ProviderResponseError) as exc:
        logger.info(
            "trendnews discovery slot %s unavailable (%s)",
            _query_slot_id("trendnews", "ranked-global-discovery"),
            _exception_kind(exc),
        )
        return expected_slots
    except Exception:
        raise
    topics = discovery_box.get("topics", [])
    search_requests = discovery_box.get("search_requests", [])
    if discovery_status != "success" or not topics:
        logger.info("X discovery returned no eligible global topics; daily cursor unchanged")
        return expected_slots

    dynamic_slots = [("x", request["query_key"]) for request in search_requests]
    store.declare_collection_cycle_slots(
        collection_cycle_id, dynamic_slots, declared_utc=time.time()
    )
    expected_slots.extend(dynamic_slots)
    for request in search_requests:
        inserted = 0
        status = "failed"
        try:
            _, inserted, status = _run_fetch(
                store,
                provider="x",
                query_key=request["query_key"],
                fetch_fn=lambda captured, item=request: fetch_x_topic(
                    item["topic"], item["query_key"], captured, limit=limit
                ),
                labels=request["labels"],
                cost_units=1.0,
                budget_limits=_x_request_budget_limits(
                    "search", now, request["query_key"]
                ),
                budget_metadata={"budget_category": "search"},
                collection_cycle_id=collection_cycle_id,
            )
        except _FetchBudgetExceeded:
            logger.info("X daily search budget reached; stopping paid cycle")
            break
        except (ProviderTransientError, ProviderResponseError) as exc:
            logger.info(
                "x discovery slot %s unavailable (%s); stopping paid cycle",
                _query_slot_id("x", request["query_key"]),
                _exception_kind(exc),
            )
            break
        except Exception:
            raise
        logger.info(
            "x-discovery[%s]: %s · slot=%s · x %s +%d",
            ",".join(request["categories"]),
            ",".join(request["selected_external_ids"]),
            _query_slot_id("x", request["query_key"]),
            status,
            inserted,
        )
    return expected_slots


def poll_x_topics_once(
    store,
    now: float,
    limit: int = _GLOBAL_X_SEARCH_LIMIT,
    max_topics: int = _GLOBAL_X_TOPIC_LIMIT,
) -> list[tuple[str, str]]:
    """Discover today's broad stories and capture bounded public X discussion."""
    evidence_policy = GLOBAL_EVENT_V2_PROTOCOL["evidence"]
    if max_topics != int(evidence_policy["max_x_search_requests_per_utc_day"]):
        raise ValueError("X search count must exactly match the frozen protocol")
    if limit != int(evidence_policy["max_x_results_per_query"]):
        raise ValueError("X result count must exactly match the frozen protocol")
    resolution = _x_daily_cycle_resolution(store, now, max_topics)
    if resolution["origin"] == "unknown":
        raise ValueError("same-day X collection identity is not recognized")
    if resolution["origin"] == "compatible":
        if resolution["state"] != "complete" or resolution["cycle"] is None:
            raise ValueError("same-day compatible X collection cycle is not uniquely complete")
        store.set_meta("last_x_poll_utc", now)
        return _x_manifest_slots(resolution["cycle"])
    if resolution["origin"] == "current" and resolution["cycle"] is None:
        raise ValueError("existing X collection cycle is invalid")
    spec = resolution["spec"]
    collection_cycle_id = spec["collection_cycle_id"]
    existing = resolution["cycle"]
    if existing is not None:
        if resolution["state"] == "invalid":
            raise ValueError("existing X collection cycle identity is invalid")
        if existing["status"] == "running":
            observed_utc = store.server_observed_utc()
            stale_seconds = float(evidence_policy["x_cycle_recovery_stale_seconds"])
            server_started = existing.get("server_started_utc")
            if (
                isinstance(server_started, bool)
                or not isinstance(server_started, (int, float))
                or not math.isfinite(float(server_started))
            ):
                raise ValueError("running X cycle lacks a server start observation")
            if observed_utc - float(server_started) < stale_seconds:
                # Another worker may still own this exact daily attempt. A
                # contender neither spends nor terminalizes plausibly live work.
                return [
                    (slot["provider"], slot["query_key"])
                    for slot in store.collection_cycle_slots(collection_cycle_id)
                ]
            existing = store.recover_collection_cycle(
                collection_cycle_id,
                recovered_utc=observed_utc,
                minimum_age_seconds=stale_seconds,
            )
            if _x_collection_cycle_state(spec, existing) not in {
                "complete",
                "incomplete",
            }:
                raise ValueError("recovered X collection cycle manifest is invalid")
        elif resolution["state"] not in {"complete", "incomplete"}:
            raise ValueError("existing X collection cycle manifest is invalid")
        store.set_meta("last_x_poll_utc", now)
        return _x_manifest_slots(existing)

    if not _x_start_window_open(now):
        return [
            (slot["provider"], slot["query_key"])
            for slot in spec["identity"]["expected_static_slots"]
        ]

    # Validate the complete free discovery snapshot before creating the
    # once-per-day parent or spending a paid X request.  A free-feed outage can
    # therefore be retried on the next ordinary cycle without either biasing a
    # terminal daily manifest or wasting the paid budget.
    try:
        discovery_headlines = fetch_top_news_headlines(
            limit_per_feed=int(_DISCOVERY_INPUTS["ranked_feed_limit"])
        )
    except (ProviderTransientError, ProviderResponseError) as exc:
        logger.info(
            "top-news precheck unavailable (%s); paid X cycle not started",
            _exception_kind(exc),
        )
        return [
            (slot["provider"], slot["query_key"])
            for slot in spec["identity"]["expected_static_slots"]
        ]
    observed_now = store.server_observed_utc()
    if (
        _x_collection_cycle_spec(observed_now, max_topics)["collection_cycle_id"]
        != collection_cycle_id
        or not _x_start_window_open(observed_now)
    ):
        return [
            (slot["provider"], slot["query_key"])
            for slot in spec["identity"]["expected_static_slots"]
        ]
    try:
        store.start_collection_cycle(spec, started_utc=time.time())
    except ValueError:
        # Close the insert race without ever allocating a second daily identity
        # or issuing a request before its exact parent is known.
        existing = store.collection_cycle(collection_cycle_id)
        if existing is None:
            raise
        return poll_x_topics_once(store, now=now, limit=limit, max_topics=max_topics)
    expected_slots = [
        (slot["provider"], slot["query_key"]) for slot in spec["identity"]["expected_static_slots"]
    ]
    try:
        return _poll_x_cycle_children(
            store,
            now=now,
            limit=limit,
            max_topics=max_topics,
            collection_cycle_id=collection_cycle_id,
            expected_slots=expected_slots,
            discovery_headlines=discovery_headlines,
        )
    finally:
        cycle = store.finish_collection_cycle(collection_cycle_id, completed_utc=time.time())
        # Terminal complete and incomplete cycles are both once-per-day attempts.
        # Retrying an incomplete paid cycle would bias availability and could
        # duplicate billed reads; the exact incomplete manifest remains visible.
        store.set_meta("last_x_poll_utc", now)
        logger.info(
            "x-cycle %s: %s · manifest=%s",
            collection_cycle_id,
            cycle["status"],
            cycle["manifest_id"],
        )


def _x_daily_requirement_state(store, now: float, max_topics: int) -> str:
    """Return the fail-closed state of today's exact, frozen X collection cycle."""
    resolution = _x_daily_cycle_resolution(store, now, max_topics)
    if resolution["state"] == "missing" and _x_start_window_state(now) == "scheduled":
        return "scheduled"
    return str(resolution["state"])


def run_cycle(
    store,
    tickers: list[str],
    sources: list[str],
    macro_themes: dict,
    x_enabled: bool = False,
    x_interval: int = _GLOBAL_ONLY_X_INTERVAL_SECONDS,
    x_limit: int = _GLOBAL_X_SEARCH_LIMIT,
    x_topic_limit: int = _GLOBAL_X_TOPIC_LIMIT,
    force_x: bool = False,
) -> dict:
    """One cycle with independent provider/query receipts and watermarks."""
    cycle_started = store.server_observed_utc()
    now = cycle_started
    if x_enabled and x_interval != int(
        GLOBAL_EVENT_V2_PROTOCOL["evidence"]["x_cycle_interval_seconds"]
    ):
        raise ValueError("X cycle interval must exactly match the frozen protocol")
    x_resolution = _x_daily_cycle_resolution(store, now, x_topic_limit) if x_enabled else None
    x_due = bool(
        x_enabled
        and _x_start_window_open(now)
        and (
            (force_x and x_resolution["origin"] in {None, "current"})
            or (
                not force_x
                and (
                    x_resolution["origin"] is None
                    or (x_resolution["origin"] == "current" and x_resolution["state"] == "running")
                )
            )
        )
    )
    expected_slots = _expected_query_slots(
        tickers,
        sources,
        macro_themes,
        include_x_discovery=bool(x_due and x_resolution["origin"] is None),
    )
    if sources:
        poll_once(store, tickers, sources)
    if macro_themes:
        poll_macro_once(store, macro_themes)
    if x_due:
        x_slots = poll_x_topics_once(store, now, limit=x_limit, max_topics=x_topic_limit) or []
        if x_resolution["origin"] is None:
            expected_slots.extend(x_slots)
    cycle_completed = store.server_observed_utc()
    periodic_requirements = {}
    if x_enabled:
        periodic_requirements["x_daily"] = _x_daily_requirement_state(
            store, now, x_topic_limit
        )
    coverage = _check_cycle_query_coverage(
        store,
        expected_query_slots=list(dict.fromkeys(expected_slots)),
        cycle_started_utc=cycle_started,
        cycle_completed_utc=cycle_completed,
        periodic_requirements=periodic_requirements,
    )
    store.set_meta("poller:last_cycle_utc", cycle_completed)
    return coverage


def _sleep(seconds: float, stop: dict, *, lease_guard=None) -> None:
    """Sleep in short slices so a stop signal is honoured promptly."""
    slept = 0.0
    while slept < seconds and not stop["flag"]:
        if lease_guard is not None:
            lease_guard.assert_held()
        duration = min(5.0, seconds - slept)
        time.sleep(duration)
        slept += duration


def _install_collector_signal_handlers(stop: dict) -> None:
    """Install one signal-responsive stop flag shared by every retry attempt."""

    def _handle(signum, _frame):
        logger.info("Received signal %s — finishing current cycle then exiting.", signum)
        stop["flag"] = True

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)


def poll_forever(
    store,
    tickers: list[str],
    sources: list[str],
    interval: int,
    macro_themes: dict,
    clock: TradingClock | None = None,
    x_enabled: bool = False,
    x_interval: int = _GLOBAL_ONLY_X_INTERVAL_SECONDS,
    x_limit: int = _GLOBAL_X_SEARCH_LIMIT,
    x_topic_limit: int = _GLOBAL_X_TOPIC_LIMIT,
    *,
    health_state: CollectorHealthState | None = None,
    lease_guard=None,
    stop: dict | None = None,
    on_cycle_terminal=None,
) -> None:
    if stop is None:
        stop = {"flag": False}
        _install_collector_signal_handlers(stop)

    x_label = (
        f" + X discovery (up to {x_topic_limit} topics) every {x_interval}s" if x_enabled else ""
    )
    logger.info(
        "Polling %s [%s]%s%s every %ds%s. Ctrl-C / SIGTERM to stop.",
        ",".join(tickers),
        ",".join(sources),
        " + macro" if macro_themes else "",
        x_label,
        interval,
        " during extended trading hours" if clock else "",
    )
    while not stop["flag"]:
        try:
            if clock is not None and not clock.is_polling_time():
                wake = clock.next_open()
                wait = max(
                    60.0,
                    (wake - datetime.now(timezone.utc)).total_seconds(),
                )
                logger.info(
                    "Outside trading hours — sleeping until %s",
                    wake.strftime("%Y-%m-%d %H:%M UTC"),
                )
                _sleep(wait, stop, lease_guard=lease_guard)
                continue
            if lease_guard is not None:
                lease_guard.assert_held()
            coverage = run_cycle(
                store,
                tickers,
                sources,
                macro_themes,
                x_enabled,
                x_interval=x_interval,
                x_limit=x_limit,
                x_topic_limit=x_topic_limit,
            )
            if lease_guard is not None:
                lease_guard.assert_held()
            if health_state is not None:
                health_state.mark_cycle(coverage, completed_utc=time.time())
            if on_cycle_terminal is not None:
                on_cycle_terminal()
            _sleep(interval, stop, lease_guard=lease_guard)
        except Exception as exc:  # noqa: BLE001 - sanitize before terminating
            error_kind = _exception_kind(exc)
            lease_lost = bool(
                lease_guard is not None and not bool(getattr(lease_guard, "is_held", False))
            )
            failure_type = "CollectorLeaseLost" if lease_lost else error_kind
            if health_state is not None:
                health_state.mark_failure(failure_type)
            if not lease_lost:
                try:
                    store.set_meta(
                        "poller:last_failure_utc",
                        datetime.now(timezone.utc).timestamp(),
                    )
                except Exception as heartbeat_exc:  # noqa: BLE001
                    logger.info(
                        "Poller failure heartbeat unavailable (%s)",
                        _exception_kind(heartbeat_exc),
                    )
            raise _CollectorRuntimeFailure(
                "lease_lost" if lease_lost else "cycle",
                failure_type,
            ) from None
    logger.info("Stopped.")


def print_stats(store) -> None:
    rows = store.stats()
    if not rows:
        print("No data collected yet.")
        return
    print(f"{'TICKER':<8} {'SOURCE':<11} {'ROWS':>7}  EARLIEST → LATEST (post time, UTC)")
    for ticker, source, n, lo, hi in rows:
        lo_s = datetime.fromtimestamp(lo, timezone.utc).strftime("%Y-%m-%d %H:%M") if lo else "?"
        hi_s = datetime.fromtimestamp(hi, timezone.utc).strftime("%Y-%m-%d %H:%M") if hi else "?"
        print(f"{ticker:<8} {source:<11} {n:>7}  {lo_s} → {hi_s}")

    odds = store.odds_stats()
    if odds:
        print(f"\n{'THEME':<14} {'MARKETS':>7} {'SNAPSHOTS':>9}  EARLIEST → LATEST (capture, UTC)")
        for theme, n_markets, n_snap, lo, hi in odds:
            lo_s = (
                datetime.fromtimestamp(lo, timezone.utc).strftime("%Y-%m-%d %H:%M") if lo else "?"
            )
            hi_s = (
                datetime.fromtimestamp(hi, timezone.utc).strftime("%Y-%m-%d %H:%M") if hi else "?"
            )
            print(f"{theme:<14} {n_markets:>7} {n_snap:>9}  {lo_s} → {hi_s}")


def print_window(store, ticker: str, end: str, days: int) -> None:
    rows = store.window(ticker, end, days)
    print(f"{ticker.upper()} — {len(rows)} items in the {days}d window ending {end}:")
    for r in rows:
        ts = (
            datetime.fromtimestamp(r["created_utc"], timezone.utc).strftime("%Y-%m-%d %H:%M")
            if r.get("created_utc")
            else "?"
        )
        tag = r.get("sentiment") or (f"r/{r['subreddit']}" if r.get("subreddit") else "")
        text = (r.get("title") or r.get("body") or "").replace("\n", " ")[:120]
        print(f"  [{ts} · {r['source']:<10} {tag:<10}] {text}")


def _x_cycle_audit_projection(store, period_date) -> dict:
    midnight = datetime.combine(period_date, datetime.min.time(), tzinfo=timezone.utc).timestamp()
    resolution = _x_daily_cycle_resolution(
        store,
        midnight,
        int(GLOBAL_EVENT_V2_PROTOCOL["evidence"]["max_x_search_requests_per_utc_day"]),
    )
    cycle = resolution["cycle"]
    if resolution["origin"] is None:
        return {
            "period": period_date.isoformat(),
            "state": "missing",
            "terminal_utc": None,
            "trend_requests": 0,
            "search_requests": 0,
            "posts_returned": 0,
        }
    state = resolution["state"]
    manifest = cycle.get("manifest") if isinstance(cycle, Mapping) else None
    receipts = []
    terminal = None
    if state in {"complete", "incomplete"} and isinstance(manifest, Mapping):
        receipts = manifest.get("slot_receipts")
        if not isinstance(receipts, list):
            state = "invalid"
            receipts = []
        value = cycle.get("server_terminal_utc")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            terminal = datetime.fromtimestamp(float(value), timezone.utc).isoformat()
        else:
            state = "invalid"
    return {
        "period": period_date.isoformat(),
        "state": state,
        "terminal_utc": terminal,
        "trend_requests": sum(
            row.get("provider") == "xtrend" and row.get("fetch_run_id") is not None
            for row in receipts
            if isinstance(row, dict)
        ),
        "search_requests": sum(
            row.get("provider") == "x" and row.get("fetch_run_id") is not None
            for row in receipts
            if isinstance(row, dict)
        ),
        "posts_returned": sum(
            int(row.get("item_count") or 0)
            for row in receipts
            if isinstance(row, dict) and row.get("provider") == "x"
        ),
    }


def print_audit(store, *, include_history: bool = False) -> None:
    """Print current collector health and, when requested, immutable history."""
    now = store.server_observed_utc()
    expected_slots = _globalnews_query_slots(_global_only_news_themes())
    max_age_seconds = _collector_max_age_seconds()
    coverage = store.coverage_report(
        now,
        GLOBAL_EVENT_V2_PROTOCOL["evidence"]["required_source_groups"],
        max_age_seconds=max_age_seconds,
        expected_query_slots=expected_slots,
        require_lineage_query_slots=expected_slots,
    )
    current_x_state = _x_daily_requirement_state(
        store, now, _GLOBAL_X_TOPIC_LIMIT
    )
    overall_complete = bool(
        coverage["complete"] and current_x_state in {"complete", "scheduled"}
    )
    print(f"collector_coverage_complete={str(overall_complete).lower()}")
    print(f"collector_expected_query_slots={len(coverage['query_slots'])}")
    print(f"collector_missing_query_slots={len(coverage['missing_query_slots'])}")
    today = datetime.fromtimestamp(now, timezone.utc).date()
    for label, period in (("current", today), ("prior", today - timedelta(days=1))):
        x_cycle = _x_cycle_audit_projection(store, period)
        if label == "current":
            x_cycle["state"] = current_x_state
        print(f"collector_x_{label}_period={x_cycle['period']}")
        print(f"collector_x_{label}_state={x_cycle['state']}")
        print(f"collector_x_{label}_terminal_utc={x_cycle['terminal_utc'] or 'none'}")
        print(f"collector_x_{label}_trend_requests={x_cycle['trend_requests']}")
        print(f"collector_x_{label}_search_requests={x_cycle['search_requests']}")
        print(f"collector_x_{label}_posts_returned={x_cycle['posts_returned']}")
    if include_history:
        print("collector_immutable_receipt_history_begin")
        print(
            "collector_immutable_receipt_history_note="
            "historical_receipts_do_not_override_current_health"
        )
        for run in store.fetch_runs(limit=25):
            when = datetime.fromtimestamp(run["started_utc"], timezone.utc).isoformat()
            print(
                f"{when} {run['provider']} {run['status']} items={run['item_count']} "
                f"inserted={run['inserted_count']} cost_units={run['cost_units']} "
                f"query={run['query_key']}"
            )
        print("collector_immutable_receipt_history_end")


def _store_log_label(configured_url: str | None) -> str:
    """Describe the store without ever rendering credentials or URL parameters."""
    if not configured_url:
        return "local SQLite (default)"
    if "://" not in configured_url:
        return "configured local database"
    scheme = configured_url.split("://", 1)[0].split("+", 1)[0].lower()
    if scheme in {"postgres", "postgresql"}:
        return "configured PostgreSQL database"
    if scheme == "sqlite":
        return "configured SQLite database"
    return "configured database"


def _configured_integer(values: Mapping[str, str], name: str) -> int | None:
    raw = values.get(name)
    if raw is None or not raw.strip():
        return None
    return int(raw)


def _collector_max_age_seconds() -> float:
    query_cycle = GLOBAL_EVENT_V2_PROTOCOL["evidence"]["query_cycle"]
    return float(
        query_cycle["collector_interval_seconds"] + query_cycle["cycle_start_grace_seconds"]
    )


def _build_parser(env: Mapping[str, str] | None = None) -> argparse.ArgumentParser:
    values = os.environ if env is None else env
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--tickers",
        default=values.get("MEDIA_POLLER_TICKERS"),
        help="Comma-separated tickers (env: MEDIA_POLLER_TICKERS)",
    )
    p.add_argument(
        "--sources",
        default=values.get("MEDIA_POLLER_SOURCES"),
        help="Comma-separated subset of: "
        + ",".join(SELECTABLE_SOURCES)
        + " (env: MEDIA_POLLER_SOURCES). Default: keyless + 'x' if token set.",
    )
    p.add_argument(
        "--db",
        default=values.get("MEDIA_DB_URL"),
        help="Store URL/path (env: MEDIA_DB_URL). Default: local SQLite.",
    )
    p.add_argument(
        "--interval",
        type=int,
        default=_configured_integer(values, "MEDIA_POLLER_INTERVAL"),
        help="Seconds between news cycles (env: MEDIA_POLLER_INTERVAL)",
    )
    p.add_argument(
        "--x-interval",
        type=int,
        default=_configured_integer(values, "MEDIA_POLLER_X_INTERVAL"),
        help="Seconds between X discovery cycles (env: MEDIA_POLLER_X_INTERVAL)",
    )
    p.add_argument(
        "--x-topics",
        type=int,
        default=int(values.get("MEDIA_POLLER_X_TOPICS", str(_GLOBAL_X_TOPIC_LIMIT))),
        help=f"Maximum discovered topics per X cycle (default {_GLOBAL_X_TOPIC_LIMIT})",
    )
    p.add_argument(
        "--x-limit",
        type=int,
        default=int(values.get("MEDIA_POLLER_X_LIMIT", str(_GLOBAL_X_SEARCH_LIMIT))),
        help=(
            "Results per broad X query "
            f"(X API configured default: {_GLOBAL_X_SEARCH_LIMIT})"
        ),
    )
    p.add_argument(
        "--once",
        action="store_true",
        default=_env_bool("MEDIA_POLLER_ONCE", values),
        help="Poll once and exit (env: MEDIA_POLLER_ONCE)",
    )
    p.add_argument(
        "--no-macro",
        dest="macro",
        action="store_false",
        default=True,
        help="Skip the macro snapshot (Polymarket odds + theme news). "
        "Macro is on by default; it captures unrecoverable data.",
    )
    trading_default = values.get("MEDIA_POLLER_TRADING_HOURS", "true").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    p.add_argument(
        "--no-trading-hours",
        dest="trading_hours",
        action="store_false",
        default=trading_default,
        help="Poll around the clock instead of gating to market hours. "
        "By default the daemon polls only during the extended US session "
        "(04:00–20:00 ET) on NYSE trading days (env: MEDIA_POLLER_TRADING_HOURS).",
    )
    p.add_argument("--stats", action="store_true", help="Print collection stats and exit")
    p.add_argument("--audit", action="store_true", help="Print current collector health and exit")
    p.add_argument(
        "--audit-history",
        action="store_true",
        help="Print current health plus clearly delimited immutable recent receipts and exit",
    )
    p.add_argument(
        "--test-alert",
        action="store_true",
        help="Send one sanitized collector webhook test without DB/provider access",
    )
    p.add_argument(
        "--preflight",
        action="store_true",
        help=(
            "Validate production configuration, schema, and least-privilege DB access "
            "without provider calls or database writes; when required, send one "
            "sanitized webhook delivery probe"
        ),
    )
    p.add_argument(
        "--health-port",
        type=int,
        default=_configured_integer(values, "MEDIA_HEALTH_PORT"),
        help="Private daemon health-listener port (env: MEDIA_HEALTH_PORT)",
    )
    p.add_argument("--window", metavar="TICKER", help="Print the backtest window and exit")
    p.add_argument("--end", help="Window end date YYYY-MM-DD (default: today)")
    p.add_argument("--days", type=int, default=7, help="Window length in days (default: 7)")
    p.add_argument(
        "--global-only",
        action="store_true",
        help=(
            "Collect broad editorial news plus bounded trend-derived X reaction; "
            "ticker inputs and prediction markets are forbidden"
        ),
    )
    return p


def _comma_separated(value: str | None, *, lowercase: bool = False) -> list[str]:
    if not value:
        return []
    items = [item.strip() for item in value.split(",") if item.strip()]
    return [item.lower() for item in items] if lowercase else items


def _collection_enabled(env: Mapping[str, str]) -> bool:
    raw = (env.get("MEDIA_COLLECTION_ENABLED") or "").strip().lower()
    if not raw:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError("MEDIA_COLLECTION_ENABLED must be an explicit boolean")


def _inspection_command(args) -> bool:
    return bool(args.stats or args.audit or args.audit_history or args.window)


def _run_inspection(args) -> None:
    store = open_store(args.db)
    try:
        if args.stats:
            print_stats(store)
        elif args.audit or args.audit_history:
            print_audit(store, include_history=args.audit_history)
        else:
            end = args.end or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            print_window(store, args.window, end, args.days)
    finally:
        store.close()


def _run_alert_test(parser: argparse.ArgumentParser) -> None:
    delivered = emit_alert(
        "collector",
        "delivery_test",
        severity="info",
        details={
            "schema_version": 1,
            "collector_policy": _GLOBAL_ONLY_COLLECTOR_POLICY,
        },
    )
    if not delivered:
        parser.exit(2, "collector alert test failed\n")
    print(canonical_json({"component": "collector", "delivered": True}))


def _preflight_x_cycle_is_known(spec: Mapping, cycle: object) -> bool:
    """Admit an authenticated older terminal shape so a repair can deploy."""
    if not isinstance(cycle, Mapping):
        return False
    identity = spec.get("identity")
    if (
        not isinstance(identity, Mapping)
        or cycle.get("identity_valid") is not True
        or cycle.get("identity") != identity
        or cycle.get("collection_cycle_id") != spec.get("collection_cycle_id")
        or any(
            cycle.get(key) != identity.get(key)
            for key in (
                "cycle_kind",
                "period_key",
                "protocol_id",
                "collector_semantics_id",
            )
        )
    ):
        return False
    state = x_cycle_structural_state(spec, cycle)
    if state in {"running", "complete", "incomplete"}:
        return True
    if state != "invalid" or cycle.get("status") not in {"complete", "incomplete"}:
        return False
    manifest = cycle.get("manifest")
    return bool(
        isinstance(manifest, Mapping)
        and manifest.get("collection_cycle_id") == cycle.get("collection_cycle_id")
        and manifest.get("status") == cycle.get("status")
        and cycle.get("manifest_id")
        == media_store._content_addressed_json_id("cycle_manifest_", manifest)
    )


def _run_preflight(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    env: Mapping[str, str],
) -> None:
    """Run the database-read-only release gate and silent webhook probe."""
    store = None
    try:
        if (env.get("MEDIA_AUTO_MIGRATE") or "").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }:
            raise ValueError("automatic migration must be disabled")
        webhook_setting = (env.get("MEDIA_REQUIRE_ALERT_WEBHOOK") or "").strip().lower()
        if webhook_setting not in {
            "",
            "1",
            "true",
            "yes",
            "on",
            "0",
            "false",
            "no",
            "off",
        }:
            raise ValueError("alert webhook requirement must be boolean")
        webhook_required = webhook_setting in {"1", "true", "yes", "on"}
        if webhook_required and not (env.get("TRADINGAGENTS_ALERT_WEBHOOK_URL") or "").strip():
            raise ValueError("required alert webhook is not configured")
        if args.health_port is None or not 1 <= args.health_port <= 65535:
            raise ValueError("health port is invalid")
        configured_db = args.db or env.get("DATABASE_URL")
        if not (configured_db or "").strip():
            raise ValueError("PostgreSQL database is not configured")

        semantics_id = collector_semantics_manifest()["collector_semantics_id"]
        if semantics_id != GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_ID:
            raise RuntimeError("collector semantics do not match the protocol")
        store = open_store(configured_db, auto_migrate=False)
        database_contract = store.collector_runtime_preflight(
            direct_url=(env.get("MEDIA_DB_DIRECT_URL") or "").strip() or None
        )
        if database_contract.get("ready") is not True:
            raise RuntimeError("collector database contract is not ready")

        server_now = store.server_observed_utc()
        if (
            isinstance(server_now, bool)
            or not isinstance(server_now, (int, float))
            or not math.isfinite(float(server_now))
        ):
            raise RuntimeError("collector database clock is invalid")
        period_key = datetime.fromtimestamp(float(server_now), timezone.utc).date().isoformat()
        expected_specs = [
            _x_collection_cycle_spec(
                float(server_now),
                int(GLOBAL_EVENT_V2_CURRENT_COLLECTOR_IDENTITY["x_daily_max_dynamic_slots"]),
            ),
            *_x_compatible_collection_cycle_specs(float(server_now)),
        ]
        expected_by_id = {spec["collection_cycle_id"]: spec for spec in expected_specs}
        if len(expected_by_id) != len(expected_specs):
            raise RuntimeError("X collection compatibility identities are duplicated")
        observed_cycles = store.collection_cycle_identities("x-daily", period_key=period_key)
        if (
            not isinstance(observed_cycles, list)
            or any(
                not isinstance(item, dict)
                or set(item)
                != {
                    "collection_cycle_id",
                    "protocol_id",
                    "collector_semantics_id",
                }
                or not all(isinstance(value, str) for value in item.values())
                for item in observed_cycles
            )
            or len(observed_cycles)
            != len({item["collection_cycle_id"] for item in observed_cycles})
        ):
            raise RuntimeError("today's X collection identity inventory is invalid")
        repair_compatible_cycle_count = 0
        for observed in observed_cycles:
            spec = expected_by_id.get(observed["collection_cycle_id"])
            if spec is None or (observed["protocol_id"], observed["collector_semantics_id"]) != (
                spec["identity"]["protocol_id"],
                spec["identity"]["collector_semantics_id"],
            ):
                raise RuntimeError("today's X collection identity is not compatible")
            cycle = store.collection_cycle(observed["collection_cycle_id"])
            if not _preflight_x_cycle_is_known(spec, cycle):
                raise RuntimeError("today's X collection cycle is structurally invalid")
            if x_cycle_structural_state(spec, cycle) == "invalid":
                repair_compatible_cycle_count += 1

        alert_probe_delivered = False
        if webhook_required:
            alert_probe_delivered = bool(probe_alert_webhook())
            if not alert_probe_delivered:
                raise RuntimeError("collector alert receiver contract is not ready")
        print(
            canonical_json(
                {
                    "schema_version": 4,
                    "status": "ok",
                    "collection_protocol_id": GLOBAL_EVENT_V2_COLLECTION_PROTOCOL_ID,
                    "collector_semantics_id": semantics_id,
                    "collector_build_id": build_identity(),
                    "database_contract": database_contract,
                    "x_identity_period": period_key,
                    "x_identity_inventory_valid": True,
                    "x_identity_cycle_count": len(observed_cycles),
                    "x_repair_compatible_cycle_count": repair_compatible_cycle_count,
                    "x_evidence_health_validated": False,
                    "health_port": args.health_port,
                    "alert_webhook_required": webhook_required,
                    "alert_probe_delivered": alert_probe_delivered,
                }
            )
        )
    except Exception as exc:  # noqa: BLE001 - never render configuration or DB text
        parser.exit(2, f"collector preflight failed ({_exception_kind(exc)})\n")
    finally:
        if store is not None:
            try:
                store.close()
            except Exception as exc:  # noqa: BLE001 - keep diagnostics sanitized
                logger.error("Collector preflight cleanup failed (%s)", _exception_kind(exc))


def _close_collector_attempt(store, lease_guard) -> None:
    """Best-effort cleanup before a supervised store/lease reacquisition."""
    if store is not None and hasattr(store, "_collector_lease_guard"):
        del store._collector_lease_guard
    if lease_guard is not None:
        try:
            lease_guard.close()
        except Exception as exc:  # noqa: BLE001 - keep the supervisor alive
            logger.info("Collector lease cleanup failed (%s)", _exception_kind(exc))
    if store is not None:
        try:
            store.close()
        except Exception as exc:  # noqa: BLE001 - keep the supervisor alive
            logger.info("Collector store cleanup failed (%s)", _exception_kind(exc))


def _run_supervised_daemon(
    *,
    db_url: str | None,
    direct_url: str | None,
    tickers: list[str],
    sources: list[str],
    interval: int,
    macro_themes: dict,
    global_only: bool,
    trading_hours: bool,
    x_enabled: bool,
    x_interval: int,
    x_limit: int,
    x_topic_limit: int,
    health_state: CollectorHealthState | None,
    health_port: int | None,
) -> None:
    """Supervise daemon attempts without restarting or duplicating collection."""
    stop = {"flag": False}
    _install_collector_signal_handlers(stop)
    incident = _CollectorRuntimeIncident()
    consecutive_failures = 0
    health_server = None
    clock = None
    try:
        while not stop["flag"]:
            store = None
            collector_lease = None
            failure = None
            failure_stage = "health_listener"
            try:
                if health_state is not None and health_server is None:
                    if health_port is None:
                        raise RuntimeError("health listener port is unavailable")
                    health_server = start_collector_health_server(health_state, port=health_port)
                    logger.info(
                        "Private collector health listener started on port %d",
                        health_port,
                    )

                failure_stage = "daemon_startup"
                if trading_hours and clock is None:
                    clock = TradingClock()

                failure_stage = "store_startup"
                store = open_store(db_url)

                if global_only and getattr(store, "dialect", None) == "postgresql":
                    failure_stage = "lease_acquisition"

                    def _on_collector_lease_loss(_failure_type: str) -> None:
                        if health_state is not None:
                            health_state.mark_failure("CollectorLeaseLost")

                    collector_lease = store.acquire_collector_lease(
                        direct_url=direct_url,
                        on_loss=_on_collector_lease_loss,
                    )
                    if collector_lease is None:
                        raise _CollectorRuntimeFailure(
                            "lease_contended", "DuplicateCollectorWorker"
                        )
                    store._collector_lease_guard = collector_lease
                    logger.info("PostgreSQL singleton collector lease acquired")

                store_label = _store_log_label(db_url)
                logger.info(
                    "Store: %s · news themes: %d · news cadence: %ds · X cadence: %ds",
                    store_label,
                    len(macro_themes),
                    interval,
                    x_interval,
                )

                def _on_cycle_terminal() -> None:
                    nonlocal consecutive_failures
                    consecutive_failures = 0
                    incident.mark_recovered()

                failure_stage = "cycle"
                poll_forever(
                    store,
                    tickers,
                    sources,
                    interval,
                    macro_themes,
                    clock,
                    x_enabled=x_enabled,
                    x_interval=x_interval,
                    x_limit=x_limit,
                    x_topic_limit=x_topic_limit,
                    health_state=health_state,
                    lease_guard=collector_lease,
                    stop=stop,
                    on_cycle_terminal=_on_cycle_terminal,
                )
            except _CollectorRuntimeFailure as exc:
                failure = exc
            except Exception as exc:  # noqa: BLE001 - sanitize and retry daemon only
                failure = _CollectorRuntimeFailure(failure_stage, _exception_kind(exc))
            finally:
                _close_collector_attempt(store, collector_lease)

            if stop["flag"]:
                break
            if failure is None:
                failure = _CollectorRuntimeFailure("cycle", "UnexpectedDaemonReturn")
            consecutive_failures += 1
            retry_delay = _collector_retry_delay(consecutive_failures)
            if health_state is not None:
                health_state.mark_failure(failure.error_type)
            incident.mark_failure(
                stage=failure.stage,
                error_type=failure.error_type,
                retry_delay_seconds=retry_delay,
            )
            logger.info(
                "Collector runtime unhealthy at %s (%s); retrying in %.0fs",
                failure.stage,
                failure.error_type,
                retry_delay,
            )
            _sleep(retry_delay, stop)
    finally:
        if health_server is not None:
            try:
                health_server.close()
            except Exception as exc:  # noqa: BLE001 - sanitize shutdown failures
                logger.info(
                    "Collector health listener cleanup failed (%s)",
                    _exception_kind(exc),
                )


def main(argv: list[str] | None = None) -> None:
    env = os.environ
    p = _build_parser(env)
    args = p.parse_args(argv)

    if args.preflight and not args.global_only:
        p.error("--preflight requires --global-only")

    if args.test_alert:
        _run_alert_test(p)
        return
    if _inspection_command(args):
        _run_inspection(args)
        return

    tickers = [ticker.upper() for ticker in _comma_separated(args.tickers)]
    explicit = _comma_separated(args.sources, lowercase=True) or None
    try:
        sources = resolve_sources(explicit, env=env)
    except ValueError as exc:
        p.error(str(exc))

    if args.global_only:
        if tickers:
            p.error("--global-only rejects ticker inputs and MEDIA_POLLER_TICKERS")
        if sources != ["x"] or explicit != ["x"]:
            p.error("--global-only requires the sole explicit source '--sources x'")
        if not args.macro:
            p.error("--global-only requires its broad editorial-news queries")
        if args.trading_hours:
            p.error("--global-only requires --no-trading-hours for global coverage")
        if args.interval is None or args.x_interval is None:
            p.error("--global-only requires explicit --interval and --x-interval cadence")
        if args.interval != _GLOBAL_ONLY_NEWS_INTERVAL_SECONDS:
            p.error("--global-only news interval must match the versioned collector policy")
        if args.x_interval != _GLOBAL_ONLY_X_INTERVAL_SECONDS:
            p.error("--global-only X interval must match the versioned collector policy")
        expected_topics = int(
            GLOBAL_EVENT_V2_PROTOCOL["evidence"]["max_x_search_requests_per_utc_day"]
        )
        expected_limit = int(GLOBAL_EVENT_V2_PROTOCOL["evidence"]["max_x_results_per_query"])
        if args.x_topics != expected_topics or args.x_limit != expected_limit:
            p.error("--global-only X request bounds must match the collector policy")
        if not args.once:
            try:
                collection_enabled = _collection_enabled(env)
            except ValueError as exc:
                p.error(str(exc))
            if not collection_enabled:
                p.error("global collection is paused; set MEDIA_COLLECTION_ENABLED=true")
        macro_themes = _global_only_news_themes()
    else:
        if args.interval is None:
            args.interval = _GLOBAL_ONLY_NEWS_INTERVAL_SECONDS
        if args.x_interval is None:
            args.x_interval = _GLOBAL_ONLY_X_INTERVAL_SECONDS
        macro_themes = DEFAULT_CONFIG.get("macro_themes", {}) if args.macro else {}

    x_selected = "x" in sources
    ticker_sources = [source for source in sources if source != "x"]
    if ticker_sources and not tickers:
        p.error("--tickers (or MEDIA_POLLER_TICKERS) is required for ticker-specific sources")

    x_token_configured = bool((env.get("X_BEARER_TOKEN") or "").strip())
    if x_selected and not x_token_configured:
        p.error("X_BEARER_TOKEN is required when source 'x' is configured")
    x_enabled = bool(x_selected and x_token_configured)
    if "truthsocial" in sources and not env.get("TRUTHSOCIAL_TOKEN"):
        logger.warning(
            "source 'truthsocial' selected but TRUTHSOCIAL_TOKEN is unset — "
            "Cloudflare will likely block it."
        )
    if not ticker_sources and not macro_themes and not x_enabled:
        p.error("no enabled ticker, macro, or X collection source")

    if args.preflight:
        _run_preflight(p, args, env)
        return

    direct_url = (env.get("MEDIA_DB_DIRECT_URL") or "").strip() or None
    if args.once:
        # One-shot (cron/manual) remains fail-fast. A scheduler can decide when
        # to invoke it again; hiding its failure in a daemon loop would make the
        # command's exit status dishonest.
        store = open_store(args.db)
        collector_lease = None
        try:
            if args.global_only and getattr(store, "dialect", None) == "postgresql":
                collector_lease = store.acquire_collector_lease(
                    direct_url=direct_url,
                )
                if collector_lease is None:
                    raise RuntimeError("another global collector owns the singleton lease")
                store._collector_lease_guard = collector_lease
            logger.info(
                "Store: %s · news themes: %d · news cadence: %ds · X cadence: %ds",
                _store_log_label(args.db),
                len(macro_themes),
                args.interval,
                args.x_interval,
            )
            run_cycle(
                store,
                tickers,
                ticker_sources,
                macro_themes,
                x_enabled,
                x_interval=args.x_interval,
                x_limit=args.x_limit,
                x_topic_limit=args.x_topics,
                force_x=True,
            )
        finally:
            _close_collector_attempt(store, collector_lease)
        return

    health_state = None
    if args.health_port is not None:
        if not 1 <= args.health_port <= 65535:
            p.error("--health-port must be between 1 and 65535")
        static_query_slots = _expected_query_slots(tickers, ticker_sources, macro_themes)
        health_state = CollectorHealthState(
            max_age_seconds=_collector_max_age_seconds(),
            expected_query_slot_ids={
                _query_slot_id(provider, query_key) for provider, query_key in static_query_slots
            },
            build_revision=(env.get("GIT_REVISION") or "").strip() or None,
            machine_id=(env.get("FLY_MACHINE_ID") or "").strip() or None,
            deployment_nonce=((env.get("COLLECTOR_DEPLOYMENT_NONCE") or "").strip() or None),
        )
    _run_supervised_daemon(
        db_url=args.db,
        direct_url=direct_url,
        tickers=tickers,
        sources=ticker_sources,
        interval=args.interval,
        macro_themes=macro_themes,
        global_only=args.global_only,
        trading_hours=args.trading_hours,
        x_enabled=x_enabled,
        x_interval=args.x_interval,
        x_limit=args.x_limit,
        x_topic_limit=args.x_topics,
        health_state=health_state,
        health_port=args.health_port,
    )


def _main_entrypoint() -> None:
    """Exit nonzero without printing credential-bearing exception details."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - sanitize the executable boundary
        logger.critical("Collector exited (%s)", _exception_kind(exc))
        raise SystemExit(1) from None


if __name__ == "__main__":
    _main_entrypoint()
