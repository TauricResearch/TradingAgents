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
import inspect
import logging
import math
import os
import re
import signal
import time
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from tradingagents import global_research, operations
from tradingagents.collector_health import (
    CollectorHealthState,
    start_collector_health_server,
)
from tradingagents.dataflows import media_sources, media_store
from tradingagents.dataflows.media_sources import (
    FETCHERS,
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
from tradingagents.operations import emit_alert
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
    build_identity,
    canonical_json,
    content_id,
    global_news_query_slot_label,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("media_poller")


_GLOBAL_ONLY_COLLECTOR_POLICY_VERSION = 2
_GLOBAL_ONLY_COLLECTOR_POLICY = (
    f"global-only-editorial-and-trend-reaction-v{_GLOBAL_ONLY_COLLECTOR_POLICY_VERSION}"
)
_GLOBAL_ONLY_NEWS_INTERVAL_SECONDS = int(
    GLOBAL_EVENT_V2_PROTOCOL["evidence"]["query_cycle"]["collector_interval_seconds"]
)
_GLOBAL_ONLY_X_INTERVAL_SECONDS = int(
    GLOBAL_EVENT_V2_PROTOCOL["evidence"]["x_cycle_interval_seconds"]
)
# Filled with the content-derived value after the V2 surface was finalized.
# Any content-addressed helper change must deliberately update this ID; bump the
# policy version as well when the economic collection policy itself changes.
_EXPECTED_GLOBAL_ONLY_COLLECTOR_SEMANTICS_ID = "collector_5d8f7d2a7c92e52be419ad17"

# Coverage alerts are operational state, separate from the immutable evidence
# ledger. Repeated identical incidents get one notification plus a daily reminder;
# a transition back to complete coverage emits one recovery notification.
_COVERAGE_ALERT_STATE_KEY = "poller:coverage_alert_unhealthy"
_COVERAGE_ALERT_LAST_UTC_KEY = "poller:coverage_alert_last_utc"
_COVERAGE_ALERT_FINGERPRINT_KEY = "poller:coverage_alert_fingerprint"
_COVERAGE_ALERT_REMINDER_SECONDS = 24 * 60 * 60

# Fatal runtime failures are retried in-process so Fly cannot turn a transient
# database or lease incident into an unbounded restart/webhook storm. The health
# endpoint remains fail-closed until a complete cycle succeeds.
_RUNTIME_RETRY_INITIAL_SECONDS = 5.0
_RUNTIME_RETRY_MAX_SECONDS = 300.0
_RUNTIME_ALERT_MIN_INTERVAL_SECONDS = 60 * 60
_RUNTIME_ALERT_REMINDER_SECONDS = 24 * 60 * 60
_RUNTIME_FAILURE_STAGES = frozenset({
    "daemon_startup",
    "health_listener",
    "store_startup",
    "lease_acquisition",
    "lease_contended",
    "cycle",
    "lease_lost",
})


# Topic discovery is deliberately entity-agnostic. It starts from ranked news
# feeds and live trends instead of a watchlist of companies, politicians, or
# products, then spends at most three recent-search calls on the day's strongest
# cross-source stories.
_DISCOVERY_CATEGORIES = ("world", "business", "technology")
_QUERY_STOPWORDS = {
    "a", "about", "according", "after", "against", "all", "amid", "an", "and", "are", "as",
    "at", "be", "before", "but", "by", "can", "confirms", "could", "for", "from", "has",
    "have", "how", "in", "into", "is", "it", "its", "may", "more", "new", "not",
    "of", "on", "or", "over", "report", "reports", "says", "than", "that", "the", "their", "this",
    "to", "up", "was", "what", "when", "where", "which", "who", "why", "will",
    "with", "would",
}
_GENERIC_CAPITALIZED = {
    "Analysis", "Breaking", "Exclusive", "Explainer", "Here", "How", "Live",
    "My", "New", "Opinion", "The", "This", "Update", "What", "When", "Why",
}
_LOW_INFORMATION_HEADLINE = re.compile(
    r"\b(best|deal|discount|guide|hands[- ]on|how to|review|rumor|versus|vs\.?|wishlist)\b",
    re.IGNORECASE,
)

_GLOBALNEWS_RETRY_POLICY = GLOBAL_EVENT_V2_PROTOCOL["evidence"]["query_cycle"][
    "globalnews_exception_retry_policy"
]
_GLOBALNEWS_MAX_ATTEMPTS = int(
    _GLOBALNEWS_RETRY_POLICY["max_attempts_per_query_cycle"]
)
_GLOBALNEWS_RETRY_DELAYS = tuple(
    float(value) for value in _GLOBALNEWS_RETRY_POLICY["delays_seconds"]
)
_GLOBALNEWS_CIRCUIT_FAILURE_SLOTS = int(
    GLOBAL_EVENT_V2_PROTOCOL["evidence"]["query_cycle"][
        "globalnews_cycle_circuit_breaker"
    ]["failed_query_slots_before_open"]
)
if _GLOBALNEWS_MAX_ATTEMPTS != 3 \
        or len(_GLOBALNEWS_RETRY_DELAYS) != _GLOBALNEWS_MAX_ATTEMPTS - 1 \
        or any(value < 0 or value > 10 for value in _GLOBALNEWS_RETRY_DELAYS) \
        or _GLOBALNEWS_RETRY_POLICY.get("retry_on") \
            != "provider_transient_exception_only" \
        or _GLOBALNEWS_RETRY_POLICY.get("empty_response") \
            != "terminal_observed_empty_without_retry":
    raise RuntimeError("formal globalnews retry policy is malformed")
if _GLOBALNEWS_CIRCUIT_FAILURE_SLOTS != 2:
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
        raise ValueError(f"unknown source(s): {','.join(unknown)}. "
                         f"Choose from: {','.join(SELECTABLE_SOURCES)}")
    return sources


def _within(rows: list[dict], since: float | None) -> list[dict]:
    """Return every discovered item; storage dedup makes polling incremental.

    ``since`` is retained for API compatibility only. Filtering on publication
    time discarded older stories first discovered after a cursor advanced.
    Point-in-time consumers already constrain both publication and receipt time.
    """
    return rows


def _watermark_key(provider: str, query_key: str) -> str:
    suffix = hashlib.sha256(query_key.encode("utf-8")).hexdigest()[:16]
    return f"watermark:{provider}:{suffix}"


def _expected_query_slots(
    tickers: list[str], sources: list[str], macro_themes: dict,
    *, include_x_discovery: bool = False,
) -> list[tuple[str, str]]:
    """Return every exact provider/query slot configured for one cycle."""
    slots = [(source, ticker) for ticker in tickers for source in sources]
    for theme, spec in macro_themes.items():
        slots.extend(
            ("globalnews", f"{theme}:{query}") for query in spec.get("queries", [])
        )
        slots.extend(
            ("polymarket", f"{theme}:{topic}")
            for topic in spec.get("prediction_topics", [])
        )
    if include_x_discovery:
        slots.append(("trendnews", "ranked-global-discovery"))
    return list(dict.fromkeys(slots))


def _globalnews_query_slots(macro_themes: dict) -> list[tuple[str, str]]:
    """Return the exact configured broad-news query slots."""
    return [
        slot for slot in _expected_query_slots([], [], macro_themes)
        if slot[0] == "globalnews"
    ]


def _global_only_news_themes() -> dict[str, dict[str, list[str]]]:
    """Return broad-news themes with every prediction-market query removed."""
    return {
        str(theme): {
            "queries": list(queries),
            "prediction_topics": [],
        }
        for theme, queries in GLOBAL_EVENT_V2_PROTOCOL["evidence"][
            "broad_news_queries"
        ].items()
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


def _exception_kind(exc: BaseException) -> str:
    """Return a bounded class label; exception messages can contain credentials."""
    name = type(exc).__name__
    return name if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name) else "Exception"


def _runtime_failure_type(value: object) -> str:
    """Return only a bounded identifier supplied by trusted runtime machinery."""
    return (
        value
        if isinstance(value, str)
        and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", value)
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
        _RUNTIME_RETRY_INITIAL_SECONDS * (2 ** exponent),
    )


class _CollectorRuntimeIncident:
    """Deduplicate one in-process unhealthy transition plus daily reminders."""

    def __init__(self, *, clock=None, alert=None):
        self._clock = time.monotonic if clock is None else clock
        self._alert = emit_alert if alert is None else alert
        self._active: tuple[str, str] | None = None
        self._last_alerted: tuple[str, str] | None = None
        self._last_alert_monotonic: float | None = None

    @property
    def active(self) -> bool:
        return self._active is not None

    def mark_failure(
        self, *, stage: str, error_type: str, retry_delay_seconds: float,
    ) -> bool:
        safe_stage = stage if stage in _RUNTIME_FAILURE_STAGES else "cycle"
        safe_error_type = _runtime_failure_type(error_type)
        observed = float(self._clock())
        next_incident = (safe_stage, safe_error_type)
        first_transition = self._active is None
        self._active = next_incident
        since_last_alert = (
            None
            if self._last_alert_monotonic is None
            else observed - self._last_alert_monotonic
        )
        reminder_due = (
            self._last_alerted == next_incident
            and since_last_alert is not None
            and since_last_alert >= _RUNTIME_ALERT_REMINDER_SECONDS
        )
        changed_transition_due = (
            self._last_alerted != next_incident
            and since_last_alert is not None
            and since_last_alert >= _RUNTIME_ALERT_MIN_INTERVAL_SECONDS
        )
        if not first_transition and not changed_transition_due and not reminder_due:
            return False
        try:
            self._alert(
                "collector",
                "runtime_unhealthy",
                severity="critical",
                details={
                    "schema_version": 1,
                    "failure_stage": safe_stage,
                    "failure_type": safe_error_type,
                    "retry_delay_seconds": float(retry_delay_seconds),
                    "reminder": reminder_due,
                },
            )
        except Exception as exc:  # noqa: BLE001 - supervision must survive alert bugs
            logger.error(
                "Collector runtime alert handler failed (%s)",
                _exception_kind(exc),
            )
        # Bound attempts even while the webhook is unavailable. Retrying on
        # every exponential-backoff turn would recreate the alert storm this
        # supervisor exists to prevent.
        self._last_alerted = next_incident
        self._last_alert_monotonic = observed
        return True

    def mark_recovered(self) -> None:
        if self._active is None:
            return
        prior_stage, prior_error_type = self._active
        self._active = None
        self._last_alerted = None
        self._last_alert_monotonic = None
        try:
            self._alert(
                "collector",
                "runtime_recovered",
                severity="info",
                details={
                    "schema_version": 1,
                    "prior_failure_stage": prior_stage,
                    "prior_failure_type": prior_error_type,
                },
            )
        except Exception as exc:  # noqa: BLE001 - supervision must survive alert bugs
            logger.error(
                "Collector recovery alert handler failed (%s)",
                _exception_kind(exc),
            )


def _sanitized_coverage_alert_details(coverage: dict) -> dict:
    """Summarize missing slots without query strings, errors, or response data."""
    missing = coverage.get("missing_query_slots") or []
    missing_periodic = coverage.get("missing_periodic_requirements") or []
    periodic = coverage.get("periodic_requirements") or {}
    x_daily_state = periodic.get("x_daily") if isinstance(periodic, dict) else None
    if x_daily_state not in {"complete", "incomplete", "invalid", "missing", "running"}:
        x_daily_state = None
    x_daily_missing = "x_daily" in missing_periodic
    periodic_x_providers = {"trendnews", "x", "xtrend"}
    fingerprint_missing = [
        slot for slot in missing
        if not (x_daily_missing and slot.get("provider") in periodic_x_providers)
    ]
    slots = []
    reason_counts: dict[str, int] = {}
    allowed_reasons = {
        "not_run", "empty", "failed", "running", "incomplete", "stale", "ineligible",
        "invalid_lineage", "invalid_receipt", "unbound_lineage",
        "collector_semantics_mismatch",
    }
    for slot in fingerprint_missing:
        provider = slot.get("provider")
        query_key = slot.get("query_key")
        reason = slot.get("reason")
        safe_reason = reason if reason in allowed_reasons else "unhealthy"
        reason_counts[safe_reason] = reason_counts.get(safe_reason, 0) + 1
        if len(slots) < 20:
            slots.append({
                "provider": _safe_alert_provider(provider),
                "slot_id": _query_slot_id(str(provider), str(query_key)),
                "reason": safe_reason,
            })
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


def _coverage_alert_fingerprint(details: dict) -> float:
    """Encode a stable incident identity in the store's numeric metadata type."""
    digest = hashlib.sha256(canonical_json(details).encode("utf-8")).hexdigest()
    # Twelve hex characters fit exactly in an IEEE-754 double, which is the
    # common representation used by both poll-state backends.
    return float(int(digest[:12], 16))


def _update_coverage_alert_state(
    store, *, coverage: dict, observed_utc: float,
) -> None:
    """Notify on coverage transitions, changed incidents, and daily reminders."""
    previously_unhealthy = store.get_meta(_COVERAGE_ALERT_STATE_KEY) == 1.0
    if coverage["complete"]:
        delivered_incident = store.get_meta(_COVERAGE_ALERT_FINGERPRINT_KEY)
        if previously_unhealthy and delivered_incident not in {None, 0.0}:
            recovered = emit_alert(
                "collector",
                "query_slot_coverage_recovered",
                severity="info",
                details={
                    "expected_query_slot_count": len(coverage.get("query_slots") or []),
                    "missing_query_slot_count": 0,
                },
            )
            if not recovered:
                return
        store.set_meta(_COVERAGE_ALERT_STATE_KEY, 0.0)
        store.set_meta(_COVERAGE_ALERT_FINGERPRINT_KEY, 0.0)
        return

    details = _sanitized_coverage_alert_details(coverage)
    fingerprint = _coverage_alert_fingerprint(details)
    prior_fingerprint = store.get_meta(_COVERAGE_ALERT_FINGERPRINT_KEY)
    last_alert_utc = store.get_meta(_COVERAGE_ALERT_LAST_UTC_KEY)
    reminder_due = last_alert_utc is None or (
        observed_utc - float(last_alert_utc) >= _COVERAGE_ALERT_REMINDER_SECONDS
    )
    if not previously_unhealthy or prior_fingerprint != fingerprint or reminder_due:
        delivered = emit_alert(
            "collector",
            "query_slot_coverage_incomplete",
            severity="warning",
            details=details,
        )
        # A failed webhook delivery must be retried on the next collection cycle
        # instead of being suppressed for a full reminder interval.
        if delivered:
            store.set_meta(_COVERAGE_ALERT_LAST_UTC_KEY, observed_utc)
            store.set_meta(_COVERAGE_ALERT_FINGERPRINT_KEY, fingerprint)
    store.set_meta(_COVERAGE_ALERT_STATE_KEY, 1.0)


@lru_cache(maxsize=1)
def collector_semantics_manifest() -> dict:
    """Content-address every helper that can alter a global-only fetch receipt."""
    components = {
        "provider_response_error": media_sources.ProviderResponseError,
        "provider_transient_error": media_sources.ProviderTransientError,
        "provider_http_retry_classification": media_sources._is_transient_http_error,
        "normalize_public_url": media_sources.normalize_public_url,
        "publisher_domain": media_sources.publisher_domain,
        "html_normalization": media_sources._strip_html,
        "meaningful_text_contract": media_sources._has_meaningful_text,
        "provider_metric_contract": media_sources._has_nonnegative_metrics,
        "provider_bounded_read": media_sources._read_bounded,
        "provider_json_request": media_sources._get_json,
        "rss_response_contract": media_sources._parse_rss_response,
        "rss_item_structure_contract": media_sources._rss_channel_items,
        "x_response_contract": media_sources._x_response_items,
        "iso_timestamp_parser": media_sources._iso_to_epoch,
        "rfc822_timestamp_parser": media_sources._rfc822_to_epoch,
        "google_news_provenance": media_sources._google_news_provenance,
        "google_news_content_vintage": media_sources._google_news_content_vintage,
        "google_news_item_contract": media_sources._google_news_item,
        "media_row_projection": media_sources._row,
        "company_authorship_classifier": media_sources.looks_company_authored,
        "automation_risk": media_sources._automation_risk,
        "x_search": media_sources._fetch_x_search,
        "x_topic_fetch": media_sources.fetch_x_topic,
        "x_trends_fetch": media_sources.fetch_x_trends,
        "x_trend_response_normalization": _x_trend_media_rows,
        "top_news_fetch": media_sources.fetch_top_news_headlines,
        "global_news_fetch": media_sources.fetch_global_news,
        "topic_key": _topic_key,
        "semantic_terms": _semantic_terms,
        "story_clustering": _same_story,
        "trend_headline_match": _trend_matches_headline,
        "headline_query": _headline_query,
        "discovery_company_boundary": _looks_company_authored,
        "topic_discovery": discover_x_topics,
        "discovery_news_projection": _discovery_news_row,
        "formal_discovery_grounding": _formally_grounded_discovery_topics,
        "evidence_identity": _evidence_id,
        "raw_content_identity": _raw_content_id,
        "stable_bucket_assignment": global_research._stable_bucket_assignment,
        "exact_query_slots": _formal_query_slots,
        "assigned_query_slot": global_research._formal_query_slot,
        "formal_company_boundary": global_research.is_company_authored_evidence,
        "formal_publisher_normalization": global_research._publisher_key,
        "formal_editorial_boundary": global_research.is_independent_editorial_evidence,
        "formal_ineligibility": global_research.formal_evidence_ineligibility_reason,
        "formal_eligibility": is_formally_eligible_evidence,
        "identical_fetch_item_collapse": _collapse_identical_fetch_rows,
        "collector_lease_guard": _assert_store_collector_lease,
        "fetch_receipt_pipeline": _run_fetch,
        "globalnews_retry_orchestration": _run_globalnews_query,
        "globalnews_cycle_orchestration": poll_macro_once,
        "cycle_coverage_contract": _check_cycle_query_coverage,
        "collector_cycle_orchestration": run_cycle,
        "collector_daemon_sleep": _sleep,
        "collector_signal_handlers": _install_collector_signal_handlers,
        "collector_runtime_failure": _CollectorRuntimeFailure,
        "collector_runtime_failure_type": _runtime_failure_type,
        "collector_retry_delay": _collector_retry_delay,
        "collector_runtime_incident": _CollectorRuntimeIncident,
        "collector_daemon_loop": poll_forever,
        "collection_cycle_spec": media_store.collection_cycle_spec,
        "collection_cycle_manifest": media_store._collection_cycle_manifest,
        "collection_cycle_item_replay": media_store._verified_cycle_item_rows,
        "sqlite_x_cycle_identity_inventory": (
            media_store.SqliteMediaStore.collection_cycle_identity_pairs
        ),
        "sqlalchemy_x_cycle_identity_inventory": (
            media_store.SqlAlchemyMediaStore.collection_cycle_identity_pairs
        ),
        "x_collection_cycle_identity_spec": (
            _x_collection_cycle_spec_for_identity
        ),
        "x_collection_cycle_spec": _x_collection_cycle_spec,
        "x_compatible_collection_cycle_specs": (
            _x_compatible_collection_cycle_specs
        ),
        "x_collection_cycle_validation": _x_collection_cycle_state,
        "x_daily_cycle_resolution": _x_daily_cycle_resolution,
        "x_collection_cycle_manifest_slots": _x_manifest_slots,
        "x_paid_request_budget": _x_request_budget_limits,
        "x_paid_cycle_children": _poll_x_cycle_children,
        "x_collection_cycle_orchestration": poll_x_topics_once,
        "x_collection_cycle_due": _x_poll_due,
        "x_daily_requirement_state": _x_daily_requirement_state,
        "headline_publisher_normalization": _headline_without_publisher,
        "formal_evidence_id_encoding": media_store._encoded_formal_evidence_ids,
        "formal_content_lineage_encoding": media_store._encoded_formal_lineage,
        "fetch_item_lineage": media_store._build_fetch_item_lineage,
        "fetch_completion_validation": media_store._validate_fetch_completion,
        "terminal_receipt_validation": media_store._terminal_receipt_reason,
        "media_identity_coherence": media_store._media_rows_conflict,
        "batch_media_coherence": media_store._validate_batch_media_coherence,
        "sqlite_media_store": media_store.SqliteMediaStore.store,
        "sqlite_atomic_media_store": media_store.SqliteMediaStore._store_in_transaction,
        "sqlite_fetch_start": media_store.SqliteMediaStore.start_fetch,
        "sqlite_budgeted_fetch_start": media_store.SqliteMediaStore.start_budgeted_fetch,
        "sqlite_fetch_finish": media_store.SqliteMediaStore.finish_fetch,
        "sqlite_terminal_transition": (
            media_store.SqliteMediaStore._finish_fetch_in_transaction
        ),
        "sqlite_fetch_complete": media_store.SqliteMediaStore.complete_fetch,
        "sqlite_fetch_read": media_store.SqliteMediaStore.fetch_runs,
        "sqlite_cycle_start": media_store.SqliteMediaStore.start_collection_cycle,
        "sqlite_cycle_declare": (
            media_store.SqliteMediaStore.declare_collection_cycle_slots
        ),
        "sqlite_cycle_finish": media_store.SqliteMediaStore.finish_collection_cycle,
        "sqlite_cycle_recover": media_store.SqliteMediaStore.recover_collection_cycle,
        "sqlite_cycle_read": media_store.SqliteMediaStore.collection_cycle,
        "sqlite_server_clock": media_store.SqliteMediaStore.server_observed_utc,
        "postgres_collector_lease": media_store._PostgresCollectorLease,
        "postgres_advisory_lock_held": (
            media_store._advisory_lock_is_held_statement
        ),
        "postgres_store_initialization": media_store.SqlAlchemyMediaStore.__init__,
        "postgres_column_type_family": (
            media_store._collector_postgres_type_family
        ),
        "postgres_column_contract_authentication": (
            media_store._collector_postgres_column_contract_valid
        ),
        "postgres_connect_args": media_store._postgres_connect_args,
        "postgres_transaction_hook_install": (
            media_store._install_postgres_transaction_settings
        ),
        "postgres_transaction_hook_apply": (
            media_store._set_postgres_transaction_settings
        ),
        "postgres_collector_direct_url": (
            media_store.SqlAlchemyMediaStore._collector_direct_database_url
        ),
        "postgres_collector_direct_engine": (
            media_store.SqlAlchemyMediaStore._collector_direct_engine
        ),
        "postgres_session_affine_connection": (
            media_store.SqlAlchemyMediaStore._session_affine_connection
        ),
        "postgres_acquire_collector_lease": (
            media_store.SqlAlchemyMediaStore.acquire_collector_lease
        ),
        "postgres_collector_runtime_preflight": (
            media_store.SqlAlchemyMediaStore.collector_runtime_preflight
        ),
        "postgres_media_store": media_store.SqlAlchemyMediaStore.store,
        "postgres_atomic_media_store": (
            media_store.SqlAlchemyMediaStore._store_in_transaction
        ),
        "postgres_fetch_start": media_store.SqlAlchemyMediaStore.start_fetch,
        "postgres_budgeted_fetch_start": (
            media_store.SqlAlchemyMediaStore.start_budgeted_fetch
        ),
        "postgres_fetch_finish": media_store.SqlAlchemyMediaStore.finish_fetch,
        "postgres_terminal_transition": (
            media_store.SqlAlchemyMediaStore._finish_fetch_in_transaction
        ),
        "postgres_fetch_complete": media_store.SqlAlchemyMediaStore.complete_fetch,
        "postgres_fetch_read": media_store.SqlAlchemyMediaStore.fetch_runs,
        "postgres_cycle_start": media_store.SqlAlchemyMediaStore.start_collection_cycle,
        "postgres_cycle_declare": (
            media_store.SqlAlchemyMediaStore.declare_collection_cycle_slots
        ),
        "postgres_cycle_finish": (
            media_store.SqlAlchemyMediaStore.finish_collection_cycle
        ),
        "postgres_cycle_recover": (
            media_store.SqlAlchemyMediaStore.recover_collection_cycle
        ),
        "postgres_cycle_read": media_store.SqlAlchemyMediaStore.collection_cycle,
        "postgres_server_clock": media_store.SqlAlchemyMediaStore.server_observed_utc,
        "collector_attempt_cleanup": _close_collector_attempt,
        "collector_daemon_supervisor": _run_supervised_daemon,
        "collector_preflight": _run_preflight,
        "collector_main": main,
        "collector_executable_boundary": _main_entrypoint,
        "operations_alert_text_redaction": operations._redact_text,
        "operations_alert_structure_redaction": operations.redact_sensitive,
        "operations_alert_delivery": operations.emit_alert,
    }
    sources = {
        name: hashlib.sha256(inspect.getsource(component).encode("utf-8")).hexdigest()
        for name, component in components.items()
    }
    evidence = GLOBAL_EVENT_V2_PROTOCOL["evidence"]
    manifest = {
        "schema_version": 6,
        "policy": _GLOBAL_ONLY_COLLECTOR_POLICY,
        "components": sources,
        "semantic_values": {
            "collection_scope": {
                "ticker_watchlist": False,
                "ticker_sources": [],
                "polymarket": False,
                "broad_editorial_news": True,
                "trend_derived_x_reaction": True,
                "news_interval_seconds": _GLOBAL_ONLY_NEWS_INTERVAL_SECONDS,
                "x_interval_seconds": _GLOBAL_ONLY_X_INTERVAL_SECONDS,
            },
            "broad_news_queries": evidence["broad_news_queries"],
            "formal_allowed_sources": evidence["allowed_sources"],
            "trendnews_role": evidence["trendnews_role"],
            "independent_editorial_policy": evidence["independent_editorial_policy"],
            "x_formal_policy": evidence["x_formal_policy"],
            "fetch_receipt_evidence_lineage": evidence[
                "fetch_receipt_evidence_lineage"
            ],
            "x_trend_woeids": evidence["x_trend_woeids"],
            "x_daily_request_limits": {
                "trends": evidence["max_x_trend_requests_per_utc_day"],
                "search": evidence["max_x_search_requests_per_utc_day"],
                "results_per_search": evidence["max_x_results_per_query"],
            },
            "x_cycle_recovery_stale_seconds": evidence[
                "x_cycle_recovery_stale_seconds"
            ],
            "compatible_collector_identities": evidence[
                "compatible_collector_identities"
            ],
            "allowed_observed_empty_providers": evidence["query_cycle"][
                "allowed_observed_empty_providers"
            ],
            "globalnews_exception_retry_policy": evidence["query_cycle"][
                "globalnews_exception_retry_policy"
            ],
            "globalnews_cycle_circuit_breaker": evidence["query_cycle"][
                "globalnews_cycle_circuit_breaker"
            ],
            "provider_response_validation": evidence["query_cycle"][
                "provider_response_validation"
            ],
            "provider_response_contract": {
                "maximum_response_bytes": media_sources._MAX_PROVIDER_RESPONSE_BYTES,
                "user_agent": media_sources._UA,
                "x_recent_search_endpoint": media_sources._X_SEARCH,
                "x_trends_endpoint": media_sources._X_TRENDS,
                "x_required_post_metrics": media_sources._X_REQUIRED_POST_METRICS,
                "x_required_user_metrics": media_sources._X_REQUIRED_USER_METRICS,
                "global_news_endpoint": media_sources._GLOBAL_NEWS_RSS,
                "top_news_feeds": media_sources._GOOGLE_TOP_NEWS_RSS,
            },
            "postgres_connection_contract": {
                "prepare_threshold": media_store._postgres_connect_args()[
                    "prepare_threshold"
                ],
                "transaction_settings": list(
                    media_store._POSTGRES_TRANSACTION_SETTINGS
                ),
                "pool_recycle_seconds": media_store._POSTGRES_POOL_RECYCLE_SECONDS,
                "collector_lease_heartbeat_seconds": (
                    media_store._COLLECTOR_LEASE_HEARTBEAT_SECONDS
                ),
                "collector_advisory_lock_id": (
                    media_store._COLLECTOR_ADVISORY_LOCK_ID
                ),
                "fly_mpg_pool_host_pattern": media_store._FLY_MPG_POOL_HOST.pattern,
                "fly_mpg_direct_host_pattern": (
                    media_store._FLY_MPG_DIRECT_HOST.pattern
                ),
                "local_postgres_hosts": sorted(media_store._LOCAL_POSTGRES_HOSTS),
            },
            "postgres_schema_contract": {
                "check_constraint_definition_hashes": {
                    f"{table}.{constraint}": sorted(hashes)
                    for (table, constraint), hashes in sorted(
                        media_store._COLLECTOR_CHECK_CONSTRAINT_HASHES.items()
                    )
                },
                "column_type_families": {
                    family: [
                        {"type_oid": oid, "type_modifier": modifier}
                        for oid, modifier in sorted(members)
                    ]
                    for family, members in sorted(
                        media_store._COLLECTOR_POSTGRES_TYPE_FAMILIES.items()
                    )
                },
                "column_metadata": {
                    "nullability": "exact-model-match",
                    "server_defaults": "forbidden",
                    "collation": "built-in-type-default",
                    "identity": "forbidden",
                    "generated": "forbidden",
                },
            },
            "runtime_supervision": {
                "retry_initial_seconds": _RUNTIME_RETRY_INITIAL_SECONDS,
                "retry_max_seconds": _RUNTIME_RETRY_MAX_SECONDS,
                "alert_min_interval_seconds": (
                    _RUNTIME_ALERT_MIN_INTERVAL_SECONDS
                ),
                "alert_reminder_seconds": _RUNTIME_ALERT_REMINDER_SECONDS,
                "failure_stages": sorted(_RUNTIME_FAILURE_STAGES),
                "retry_scope": "daemon-only",
                "teardown_before_retry": True,
                "recovery_boundary": "completed-cycle",
            },
            "release_preflight_alert_probe": {
                "required_when_webhook_required": True,
                "event": "release_preflight_probe",
                "schema_version": 1,
            },
            "release_preflight_x_identity_history": {
                "cycle_kind": "x-daily",
                "accepted_pairs": "current-or-explicitly-compatible",
                "scope": "all-observed-history",
                "provider_calls": False,
            },
            "operations_alert_redaction_policy": {
                "sensitive_key_parts": list(operations._SENSITIVE_KEY_PARTS),
                "url_pattern": operations._URL.pattern,
                "url_pattern_flags": int(operations._URL.flags),
                "bearer_pattern": operations._BEARER.pattern,
                "bearer_pattern_flags": int(operations._BEARER.flags),
                "api_key_pattern": operations._API_KEY.pattern,
                "api_key_pattern_flags": int(operations._API_KEY.flags),
            },
            "discovery_categories": list(_DISCOVERY_CATEGORIES),
            "query_stopwords": sorted(_QUERY_STOPWORDS),
            "generic_capitalized_terms": sorted(_GENERIC_CAPITALIZED),
            "corporate_source_markers": list(media_sources._CORPORATE_SOURCE_MARKERS),
            "editorial_source_markers": list(media_sources._EDITORIAL_SOURCE_MARKERS),
            "first_party_headline_pattern": media_sources._FIRST_PARTY_HEADLINE.pattern,
            "low_information_pattern": _LOW_INFORMATION_HEADLINE.pattern,
        },
    }
    semantics_id = content_id(manifest, prefix="collector_")
    if semantics_id != _EXPECTED_GLOBAL_ONLY_COLLECTOR_SEMANTICS_ID:
        raise RuntimeError(
            "global-only collector semantics changed without a policy version bump"
        )
    return {**manifest, "collector_semantics_id": semantics_id}


def _check_cycle_query_coverage(
    store, *, expected_query_slots: list[tuple[str, str]],
    cycle_started_utc: float, cycle_completed_utc: float,
    periodic_requirements: dict[str, str] | None = None,
) -> dict:
    """Persist a collector heartbeat and alert on partial per-query failures."""
    # These fetchers distinguish parsed empty responses from transport/auth
    # failures. Globalnews remains deliberately strict and is absent here.
    allowed_empty_providers = frozenset(
        GLOBAL_EVENT_V2_PROTOCOL["evidence"]["query_cycle"][
            "allowed_observed_empty_providers"
        ]
    )
    allow_empty = [
        slot for slot in expected_query_slots if slot[0] in allowed_empty_providers
    ]
    frozen_globalnews_slots = set(_globalnews_query_slots(_global_only_news_themes()))
    require_lineage = [
        slot for slot in expected_query_slots
        if slot in frozen_globalnews_slots or slot[0] == "trendnews"
    ]
    coverage = store.coverage_report(
        cycle_completed_utc,
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
        or state not in {"complete", "incomplete", "invalid", "missing", "running"}
        for name, state in periodic.items()
    ):
        raise ValueError("collector periodic requirement state is invalid")
    missing_periodic = sorted(
        name for name, state in periodic.items() if state != "complete"
    )
    coverage["periodic_requirements"] = periodic
    coverage["missing_periodic_requirements"] = missing_periodic
    coverage["complete"] = bool(coverage["complete"] and not missing_periodic)
    heartbeat = "poller:last_success_utc" if coverage["complete"] else "poller:last_failure_utc"
    store.set_meta(heartbeat, cycle_completed_utc)
    _update_coverage_alert_state(
        store, coverage=coverage, observed_utc=cycle_completed_utc
    )
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
            metadata.get("provider_external_id")
            if isinstance(metadata, dict) else None
        )
        if provider in {"globalnews", "trendnews"} and isinstance(
            provider_external_id, str
        ) and provider_external_id:
            prior_vintage = provider_vintages.setdefault(
                provider_external_id, row.get("external_id")
            )
            if prior_vintage != row.get("external_id"):
                raise ValueError(
                    f"{provider} response contained ambiguous provider revisions"
                )
        fingerprint = _raw_content_id(row)
        if identity in fingerprints and (
            fingerprints[identity] != fingerprint
            or media_store._media_rows_conflict(collapsed[identity], row)
        ):
            raise ValueError(
                f"{provider} fetcher returned conflicting duplicate provenance"
            )
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
    store, *, provider: str, query_key: str, fetch_fn,
    labels: list[str] | None = None, odds: bool = False, cost_units: float = 0.0,
    store_result: bool = True, formal_eligibility_fn=None,
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
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "collector_semantics_id": collector_semantics_manifest()[
            "collector_semantics_id"
        ],
        **(budget_metadata or {}),
    }
    if cost_units > 0 and not budget_limits:
        raise ValueError("paid fetches require a durable atomic budget reservation")
    if budget_limits:
        fetch_run_id = store.start_budgeted_fetch(
            provider, query_key, started, cursor_before=cursor_before,
            metadata=metadata, budget_limits=budget_limits,
            collection_cycle_id=collection_cycle_id,
        )
        if fetch_run_id is None:
            raise _FetchBudgetExceeded(f"{provider} request budget exhausted")
    else:
        fetch_run_id = store.start_fetch(
            provider, query_key, started, cursor_before=cursor_before, metadata=metadata,
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
        if store_result and not odds and any(
            not isinstance(row, dict) or row.get("source") != provider for row in rows
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
                formal_eligible_evidence_ids = sorted({
                    _evidence_id(row)
                    for row in rows
                    if (
                        provider != "globalnews"
                        or query_key in _formal_query_slots(row)
                    )
                    # Decision cutoffs are strict. For this receipt's own
                    # content projection, admit the exact response timestamp.
                    and formal_eligibility_fn(
                        row, math.nextafter(received, math.inf)
                    )
                })
                formal_eligible_item_count = len(formal_eligible_evidence_ids)
        status = "success" if rows else "empty"
        cursor_after = received if rows else None
        inserted = store.complete_fetch(
            fetch_run_id, rows=rows, status=status, received_utc=received,
            completed_utc=time.time(), cost_units=cost_units,
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
            fetch_run_id, status="failed", received_utc=received,
            completed_utc=time.time(), item_count=0, inserted_count=0,
            error=_exception_kind(exc), cost_units=cost_units,
            formal_eligible_item_count=None,
            formal_eligible_evidence_ids=None,
        )
        raise


def poll_once(store, tickers: list[str], sources: list[str],
              now: float, since: float | None) -> None:
    for ticker in tickers:
        parts = []
        for src in sources:
            try:
                _, inserted, status = _run_fetch(
                    store, provider=src, query_key=ticker,
                    fetch_fn=lambda captured, source=src, symbol=ticker: FETCHERS[source](
                        symbol, captured
                    ),
                    labels=[ticker],
                )
                parts.append(f"{src} {status} +{inserted}")
            except Exception as exc:  # independent query state must survive peer failures
                logger.error(
                    "%s fetch slot %s failed (%s)",
                    _safe_alert_provider(src), _query_slot_id(src, ticker), _exception_kind(exc),
                )
                parts.append(f"{src} failed")
        logger.info("%s: %s", ticker, " · ".join(parts))
        time.sleep(1.0)  # be polite between tickers


def poll_macro_once(store, themes: dict, now: float, since: float | None) -> None:
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
                    _query_slot_id("globalnews", f"{theme}:{query}"), _exception_kind(exc),
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
                    store, provider="polymarket", query_key=f"{theme}:{topic}",
                    fetch_fn=lambda captured, p=topic, t=theme: fetch_polymarket_odds(
                        p, captured, t
                    ),
                    odds=True,
                )
                odds_new += inserted
            except Exception as exc:
                logger.error(
                    "polymarket fetch slot %s failed (%s)",
                    _query_slot_id("polymarket", f"{theme}:{topic}"), _exception_kind(exc),
                )
        logger.info("macro[%s]: globalnews +%d · polymarket-odds +%d",
                    theme, news_new, odds_new)
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
                    limit=int(GLOBAL_EVENT_V2_PROTOCOL["evidence"][
                        "max_global_news_results_per_query"
                    ]),
                ),
                labels=[f"@{theme}", global_news_query_slot_label(theme, query)],
                formal_eligibility_fn=lambda row, cutoff: (
                    is_formally_eligible_evidence(row, as_of_utc=cutoff)
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
    return re.sub(r"\s+-\s+[^-]{2,80}$", "", title).strip()


def _topic_key(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", _headline_without_publisher(text).lower()))


def _semantic_terms(text: str) -> set[str]:
    terms = set()
    for token in re.findall(r"[a-z0-9]+", _headline_without_publisher(text).lower()):
        if (len(token) < 3 and token not in {"ai", "us", "uk"}) or token in _QUERY_STOPWORDS:
            continue
        # Lightweight normalization is deterministic and avoids a large NLP
        # dependency in the 256 MB collector.
        if token.startswith("launch"):
            token = "launch"
        elif token == "worldwide":
            token = "world"
        terms.add(token[:-1] if len(token) > 4 and token.endswith("s") else token)
    return terms


def _same_story(left: str, right: str) -> bool:
    a, b = _semantic_terms(left), _semantic_terms(right)
    if not a or not b:
        return False
    overlap = len(a & b)
    jaccard = overlap / len(a | b)
    return jaccard >= 0.58 or (overlap >= 3 and jaccard >= 0.38)


def _trend_matches_headline(trend: str, headline: str) -> bool:
    trend_words = set(re.findall(r"[a-z0-9]+", trend.lower().lstrip("#")))
    headline_words = set(re.findall(r"[a-z0-9]+", headline.lower()))
    meaningful = {word for word in trend_words if len(word) >= 4 and word not in _QUERY_STOPWORDS}
    if not meaningful:
        return False
    needed = 1 if len(meaningful) == 1 else 2
    return len(meaningful & headline_words) >= needed


def _headline_query(title: str) -> str:
    """Turn a discovered headline into a compact X query without a watchlist.

    Named phrases are extracted from the headline itself and paired with one
    descriptive word. This is broad enough to capture public reaction while
    avoiding a brittle exact-headline search.
    """
    headline = _headline_without_publisher(title)
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9&.'’+-]*", headline)
    capitalized_runs: list[list[str]] = []
    run: list[str] = []
    for token in tokens:
        is_capitalized = token[0].isupper() or any(char.isupper() for char in token[1:])
        if is_capitalized and token.lower() not in _QUERY_STOPWORDS:
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
        distinctive = [
            word for word in words
            if any(c.isdigit() for c in word)
            or any(c.isupper() for c in word[1:])
            or (len(word) == 1 and word.isupper())
        ]
        if len(words) > 3:
            words = distinctive[:2] or words[:2]
        phrase = " ".join(words[:3])
        if len(words) > 1 or distinctive:
            anchors.append((phrase, bool(distinctive)))
    anchors = sorted(
        set(anchors),
        key=lambda value: (value[1], len(value[0].split()), len(value[0])),
        reverse=True,
    )

    chosen = [anchors[0][0]] if anchors else []
    anchor_words = {word.lower() for phrase in chosen for word in phrase.split()}
    signals = [
        token for token in tokens
        if len(token) >= 4
        and token.lower() not in _QUERY_STOPWORDS
        and token.lower() not in anchor_words
        and token not in _GENERIC_CAPITALIZED
    ]

    parts = [f'"{phrase.replace(chr(34), "")}"' for phrase in chosen]
    if parts and len(parts) < 2 and signals:
        parts.append(signals[0])
    if not parts:
        parts = signals[:3]
    return " ".join(parts)[:400]


def _looks_company_authored(headline: dict) -> bool:
    """Reject press-release/newsroom items; discovery should measure reaction."""
    return looks_company_authored(headline.get("publisher"), headline.get("title"))


def discover_x_topics(
    max_topics: int = 3, *, headlines: list[dict] | None = None,
    trends: list[dict] | None = None,
) -> list[dict]:
    """Select a small, diverse set of current high-information news topics.

    Ranked top-news feeds supply candidates. US and worldwide X trends can
    boost a matching headline, but cannot introduce an entertainment-only
    search on their own. One candidate per world/business/technology category
    maximizes coverage when the normal three-topic budget is used.
    """
    headlines = fetch_top_news_headlines() if headlines is None else headlines
    if trends is None:
        trends = [
            trend
            for woeid in GLOBAL_EVENT_V2_PROTOCOL["evidence"]["x_trend_woeids"]
            for trend in fetch_x_trends(int(woeid))
        ]
    trend_names = [trend["name"] for trend in trends if trend.get("name")]

    grouped: dict[str, dict] = {}
    for headline in headlines:
        if _LOW_INFORMATION_HEADLINE.search(headline.get("title", "")) or \
                _looks_company_authored(headline):
            continue
        key = _topic_key(headline.get("title", ""))
        if not key:
            continue
        key = next(
            (existing for existing, candidate in grouped.items()
             if _same_story(candidate["title"], headline["title"])),
            key,
        )
        candidate = grouped.setdefault(key, {
            **headline,
            "categories": set(),
            "regions": set(),
            "ranks": {},
            "lineage": [],
        })
        category = headline.get("category", "general")
        candidate["categories"].add(category)
        candidate["regions"].add(headline.get("region", "unknown"))
        candidate["lineage"].append({
            key: headline.get(key) for key in (
                "external_id", "title", "body", "created_utc", "publisher",
                "metadata", "category", "region", "rank",
            )
        })
        candidate["ranks"][category] = min(
            candidate["ranks"].get(category, 10_000), headline.get("rank", 10_000)
        )

    candidates = []
    for candidate in grouped.values():
        best_rank = min(candidate["ranks"].values())
        cross_feed_bonus = 18 * (len(candidate["categories"]) - 1)
        cross_region_bonus = 12 * (len(candidate["regions"]) - 1)
        trend_bonus = 30 if any(
            _trend_matches_headline(name, candidate["title"]) for name in trend_names
        ) else 0
        candidate["score"] = (
            100 - min(best_rank, 20) * 4 + cross_feed_bonus + cross_region_bonus + trend_bonus
        )
        candidate["query"] = _headline_query(candidate["title"])
        if candidate["query"]:
            candidates.append(candidate)

    chosen = []
    used_keys = set()
    for category in _DISCOVERY_CATEGORIES:
        eligible = [
            candidate for candidate in candidates
            if category in candidate["categories"] and _topic_key(candidate["title"]) not in used_keys
        ]
        if not eligible or len(chosen) >= max_topics:
            continue
        best = min(eligible, key=lambda candidate: (
            -(candidate["score"] - candidate["ranks"].get(category, 20) * 2),
            -(candidate.get("created_utc") or 0),
            _topic_key(candidate["title"]),
            candidate["query"],
        ))
        best = {**best, "topic": f"trend_{category}", "category": category}
        chosen.append(best)
        used_keys.add(_topic_key(best["title"]))

    if len(chosen) < max_topics:
        remaining = sorted(candidates, key=lambda candidate: (
            -candidate["score"],
            -(candidate.get("created_utc") or 0),
            _topic_key(candidate["title"]),
            candidate["query"],
        ))
        for candidate in remaining:
            key = _topic_key(candidate["title"])
            if key in used_keys:
                continue
            formal_categories = [
                category for category in _DISCOVERY_CATEGORIES
                if category in candidate["categories"]
            ]
            if not formal_categories:
                continue
            category = min(
                formal_categories,
                key=lambda value: (
                    candidate["ranks"].get(value, 10_000),
                    _DISCOVERY_CATEGORIES.index(value),
                ),
            )
            chosen.append({**candidate, "topic": f"trend_{category}", "category": category})
            used_keys.add(key)
            if len(chosen) >= max_topics:
                break
    return chosen


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


def _formally_grounded_discovery_topics(
    topics: list[dict], captured_utc: float
) -> list[dict]:
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
    if isinstance(captured_utc, bool) or not isinstance(captured_utc, (int, float)) \
            or not math.isfinite(float(captured_utc)):
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
        limit = int(
            GLOBAL_EVENT_V2_PROTOCOL["evidence"]["max_x_trend_requests_per_utc_day"]
        )
    elif category == "search":
        limit = int(
            GLOBAL_EVENT_V2_PROTOCOL["evidence"]["max_x_search_requests_per_utc_day"]
        )
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
    trends: list[dict], *, woeid: int, captured_utc: float,
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
        rows.append({
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
        })
    return rows


def _x_collection_cycle_spec_for_identity(
    now: float,
    max_topics: int,
    *,
    protocol_id: str,
    collector_semantics_id: str,
) -> dict:
    """Rebuild one exact daily X identity before any provider request starts."""
    if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now):
        raise ValueError("X collection cycle time must be finite")
    period_key = datetime.fromtimestamp(float(now), timezone.utc).strftime("%Y-%m-%d")
    static_slots = [
        ("xtrend", f"woeid:{int(woeid)}")
        for woeid in GLOBAL_EVENT_V2_PROTOCOL["evidence"]["x_trend_woeids"]
    ] + [("trendnews", "ranked-global-discovery")]
    return media_store.collection_cycle_spec(
        cycle_kind="x-daily",
        period_key=period_key,
        protocol_id=protocol_id,
        collector_semantics_id=collector_semantics_id,
        expected_static_slots=static_slots,
        max_dynamic_slots=max_topics,
    )


def _x_collection_cycle_spec(now: float, max_topics: int) -> dict:
    """Return the current daily X identity before any provider request starts."""
    return _x_collection_cycle_spec_for_identity(
        now,
        max_topics,
        protocol_id=GLOBAL_EVENT_V2_PROTOCOL_ID,
        collector_semantics_id=collector_semantics_manifest()[
            "collector_semantics_id"
        ],
    )


def _x_compatible_collection_cycle_specs(
    now: float, max_topics: int
) -> list[dict]:
    """Rebuild only the protocol's explicitly allowlisted prior X identities."""
    identities = GLOBAL_EVENT_V2_PROTOCOL["evidence"].get(
        "compatible_collector_identities"
    )
    if not isinstance(identities, list):
        raise ValueError("compatible collector identities must be a list")
    current_pair = (
        GLOBAL_EVENT_V2_PROTOCOL_ID,
        collector_semantics_manifest()["collector_semantics_id"],
    )
    seen: set[tuple[str, str]] = set()
    specs = []
    for entry in identities:
        if not isinstance(entry, Mapping) or set(entry) != {
            "protocol_id", "collector_semantics_id", "reason",
        }:
            raise ValueError("compatible collector identity has an invalid shape")
        protocol_id = entry.get("protocol_id")
        semantics_id = entry.get("collector_semantics_id")
        reason = entry.get("reason")
        if not isinstance(protocol_id, str) or re.fullmatch(
            r"protocol_[0-9a-f]{24}", protocol_id
        ) is None:
            raise ValueError("compatible collector protocol ID is invalid")
        if not isinstance(semantics_id, str) or re.fullmatch(
            r"collector_[0-9a-f]{24}", semantics_id
        ) is None:
            raise ValueError("compatible collector semantics ID is invalid")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("compatible collector identity requires a reason")
        pair = (protocol_id, semantics_id)
        if pair == current_pair or pair in seen:
            raise ValueError("compatible collector identities must be prior and unique")
        seen.add(pair)
        specs.append(_x_collection_cycle_spec_for_identity(
            now,
            max_topics,
            protocol_id=protocol_id,
            collector_semantics_id=semantics_id,
        ))
    return specs


def _x_collection_cycle_state(spec: dict, cycle: Mapping | None) -> str:
    """Validate one exact X cycle and its required paid-trend receipts."""
    if cycle is None:
        return "missing"
    if (
        cycle.get("identity_valid") is not True
        or cycle.get("identity") != spec["identity"]
    ):
        return "invalid"
    status = cycle.get("status")
    if status == "running":
        return "running"
    if status not in {"complete", "incomplete"}:
        return "invalid"
    manifest = cycle.get("manifest")
    if cycle.get("manifest_valid") is not True or not isinstance(manifest, Mapping):
        return "invalid"
    identity = spec["identity"]
    expected_manifest_values = {
        "collection_cycle_id": spec["collection_cycle_id"],
        "cycle_kind": identity["cycle_kind"],
        "period_key": identity["period_key"],
        "protocol_id": identity["protocol_id"],
        "collector_semantics_id": identity["collector_semantics_id"],
        "status": status,
        "expected_static_slots": identity["expected_static_slots"],
    }
    if any(manifest.get(key) != value for key, value in expected_manifest_values.items()):
        return "invalid"
    dynamic_slots = manifest.get("expected_dynamic_slots")
    receipts = manifest.get("slot_receipts")
    if not isinstance(dynamic_slots, list) or not isinstance(receipts, list):
        return "invalid"
    if len(dynamic_slots) > int(identity["max_dynamic_slots"]) or any(
        not isinstance(slot, Mapping)
        or set(slot) != {"provider", "query_key"}
        or not isinstance(slot.get("provider"), str)
        or not isinstance(slot.get("query_key"), str)
        for slot in dynamic_slots
    ):
        return "invalid"
    expected_slots = [
        (slot["provider"], slot["query_key"])
        for slot in identity["expected_static_slots"] + dynamic_slots
    ]
    receipt_slots: list[tuple[str, str]] = []
    for receipt in receipts:
        if not isinstance(receipt, Mapping):
            return "invalid"
        provider = receipt.get("provider")
        query_key = receipt.get("query_key")
        receipt_status = receipt.get("status")
        if (
            not isinstance(provider, str)
            or not isinstance(query_key, str)
            or receipt_status not in {"success", "empty", "failed", "missing"}
        ):
            return "invalid"
        receipt_slots.append((provider, query_key))
    if (
        len(expected_slots) != len(set(expected_slots))
        or len(receipt_slots) != len(set(receipt_slots))
        or set(receipt_slots) != set(expected_slots)
    ):
        return "invalid"
    if status == "complete" and any(
        receipt.get("status") not in {"success", "empty"}
        for receipt in receipts
    ):
        return "invalid"
    required_trend_slots = {
        ("xtrend", f"woeid:{int(woeid)}")
        for woeid in GLOBAL_EVENT_V2_PROTOCOL["evidence"]["x_trend_woeids"]
    }
    trend_receipts = [
        receipt for receipt in receipts if receipt.get("provider") == "xtrend"
    ]
    successful_trend_slots = {
        (receipt.get("provider"), receipt.get("query_key"))
        for receipt in trend_receipts
        if receipt.get("status") == "success"
        and isinstance(receipt.get("fetch_run_id"), str)
    }
    if (
        len(trend_receipts) != len(required_trend_slots)
        or successful_trend_slots != required_trend_slots
    ):
        return "incomplete"
    return str(status)


def _x_daily_cycle_resolution(store, now: float, max_topics: int) -> dict:
    """Resolve one same-day attempt, preferring current over prior identities.

    Any exact allowlisted prior attempt blocks creation of a fresh paid identity.
    When more than one prior identity exists, select the first present cycle in
    the frozen compatibility registry.  This is the same precedence rule used
    by the research projection and never depends on terminal status or content.
    """
    current_spec = _x_collection_cycle_spec(now, max_topics)
    compatible_specs = _x_compatible_collection_cycle_specs(now, max_topics)

    try:
        current_cycle = store.collection_cycle(current_spec["collection_cycle_id"])
    except ValueError:
        return {
            "origin": "current", "spec": current_spec, "cycle": None,
            "state": "invalid", "blocks_new_paid_cycle": True,
        }
    if current_cycle is not None:
        return {
            "origin": "current", "spec": current_spec, "cycle": current_cycle,
            "state": _x_collection_cycle_state(current_spec, current_cycle),
            "blocks_new_paid_cycle": True,
        }

    for spec in compatible_specs:
        try:
            cycle = store.collection_cycle(spec["collection_cycle_id"])
        except ValueError:
            return {
                "origin": "compatible", "spec": spec, "cycle": None,
                "state": "invalid", "blocks_new_paid_cycle": True,
            }
        if cycle is not None:
            return {
                "origin": "compatible", "spec": spec, "cycle": cycle,
                "state": _x_collection_cycle_state(spec, cycle),
                "blocks_new_paid_cycle": True,
            }
    return {
        "origin": None, "spec": current_spec, "cycle": None,
        "state": "missing", "blocks_new_paid_cycle": False,
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
    store, *, now: float, limit: int, max_topics: int,
    collection_cycle_id: str, expected_slots: list[tuple[str, str]],
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
                result["raw"] = fetch_x_trends(location)
                return _x_trend_media_rows(
                    result["raw"], woeid=location, captured_utc=captured
                )

            _run_fetch(
                store, provider="xtrend", query_key=query_key, fetch_fn=fetch_trends,
                labels=[f"@X_TREND_{woeid}"], cost_units=1.0,
                budget_limits=_x_request_budget_limits("trend", now, query_key),
                budget_metadata={"budget_category": "trend"},
                collection_cycle_id=collection_cycle_id,
            )
            trends.extend(trend_box.get("raw", []))
        except _FetchBudgetExceeded:
            logger.warning("X trend request budget already reserved; skipping %s", query_key)
        except (ProviderTransientError, ProviderResponseError) as exc:
            logger.info(
                "xtrend slot %s unavailable (%s); stopping paid cycle",
                _query_slot_id("xtrend", query_key), _exception_kind(exc),
            )
            return expected_slots
        except Exception:
            raise

    topics_box: dict[str, list[dict]] = {}

    def discover(captured):
        topics_box["topics"] = _formally_grounded_discovery_topics(
            discover_x_topics(
                max_topics=max_topics,
                headlines=discovery_headlines,
                trends=trends,
            ),
            captured,
        )
        return [
            _discovery_news_row(topic, captured, headline)
            for topic in topics_box["topics"]
            for headline in (topic.get("lineage") or [topic])
        ]

    try:
        _, _, discovery_status = _run_fetch(
            store, provider="trendnews", query_key="ranked-global-discovery",
            fetch_fn=discover,
            formal_eligibility_fn=lambda row, cutoff: (
                is_formally_eligible_evidence(row, as_of_utc=cutoff)
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
    topics = topics_box.get("topics", [])
    if discovery_status != "success":
        logger.warning("X discovery returned no eligible global topics; daily cursor unchanged")
        return expected_slots

    dynamic_slots = list(dict.fromkeys(("x", topic["query"]) for topic in topics))
    store.declare_collection_cycle_slots(
        collection_cycle_id, dynamic_slots, declared_utc=time.time()
    )
    expected_slots.extend(dynamic_slots)
    for topic in topics:
        inserted = 0
        status = "failed"
        try:
            _, inserted, status = _run_fetch(
                store, provider="x", query_key=topic["query"],
                fetch_fn=lambda captured, item=topic: fetch_x_topic(
                    item["topic"], item["query"], captured, limit=limit
                ),
                labels=[f"@{topic['topic']}"], cost_units=1.0,
                budget_limits=_x_request_budget_limits(
                    "search", now, topic["query"]
                ),
                budget_metadata={"budget_category": "search"},
                collection_cycle_id=collection_cycle_id,
            )
        except _FetchBudgetExceeded:
            logger.warning("X daily search budget exhausted; skipping remaining topics")
            emit_alert(
                "collector", "x_daily_budget_exhausted", severity="warning",
                details={
                    "limit": int(GLOBAL_EVENT_V2_PROTOCOL["evidence"][
                        "max_x_search_requests_per_utc_day"
                    ])
                },
            )
            break
        except (ProviderTransientError, ProviderResponseError) as exc:
            logger.info(
                "x discovery slot %s unavailable (%s); stopping paid cycle",
                _query_slot_id("x", topic["query"]), _exception_kind(exc),
            )
            break
        except Exception:
            raise
        logger.info(
            "x-discovery[%s]: %s · slot=%s · x %s +%d",
            topic["category"], _headline_without_publisher(topic["title"]),
            _query_slot_id("x", topic["query"]), status, inserted,
        )
    return expected_slots


def poll_x_topics_once(store, now: float, limit: int = 10,
                       max_topics: int = 3) -> list[tuple[str, str]]:
    """Discover today's broad stories and capture bounded public X discussion."""
    evidence_policy = GLOBAL_EVENT_V2_PROTOCOL["evidence"]
    if max_topics != int(evidence_policy["max_x_search_requests_per_utc_day"]):
        raise ValueError("X search count must exactly match the frozen protocol")
    if limit != int(evidence_policy["max_x_results_per_query"]):
        raise ValueError("X result count must exactly match the frozen protocol")
    resolution = _x_daily_cycle_resolution(store, now, max_topics)
    if resolution["origin"] == "compatible":
        if resolution["state"] != "complete" or resolution["cycle"] is None:
            raise ValueError(
                "same-day compatible X collection cycle is not uniquely complete"
            )
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
            if isinstance(server_started, bool) or not isinstance(
                server_started, (int, float)
            ) or not math.isfinite(float(server_started)):
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
                "complete", "incomplete",
            }:
                raise ValueError("recovered X collection cycle manifest is invalid")
        elif resolution["state"] not in {"complete", "incomplete"}:
            raise ValueError("existing X collection cycle manifest is invalid")
        store.set_meta("last_x_poll_utc", now)
        return _x_manifest_slots(existing)

    # Validate the complete free discovery snapshot before creating the
    # once-per-day parent or spending a paid X request.  A free-feed outage can
    # therefore be retried on the next ordinary cycle without either biasing a
    # terminal daily manifest or wasting the paid budget.
    try:
        discovery_headlines = fetch_top_news_headlines()
    except (ProviderTransientError, ProviderResponseError) as exc:
        logger.info(
            "top-news precheck unavailable (%s); paid X cycle not started",
            _exception_kind(exc),
        )
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
        (slot["provider"], slot["query_key"])
        for slot in spec["identity"]["expected_static_slots"]
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
        cycle = store.finish_collection_cycle(
            collection_cycle_id, completed_utc=time.time()
        )
        # Terminal complete and incomplete cycles are both once-per-day attempts.
        # Retrying an incomplete paid cycle would bias availability and could
        # duplicate billed reads; the exact incomplete manifest remains visible.
        store.set_meta("last_x_poll_utc", now)
        logger.info(
            "x-cycle %s: %s · manifest=%s",
            collection_cycle_id, cycle["status"], cycle["manifest_id"],
        )


def _x_poll_due(store, now: float, interval: int) -> bool:
    expected_interval = int(
        GLOBAL_EVENT_V2_PROTOCOL["evidence"]["x_cycle_interval_seconds"]
    )
    if interval != expected_interval:
        raise ValueError("X cycle interval must exactly match the frozen protocol")
    max_topics = int(
        GLOBAL_EVENT_V2_PROTOCOL["evidence"]["max_x_search_requests_per_utc_day"]
    )
    resolution = _x_daily_cycle_resolution(store, now, max_topics)
    # Only a missing attempt or the current identity's running parent can do
    # work. Any prior compatible attempt is observed but never reissued.
    return resolution["origin"] is None or (
        resolution["origin"] == "current"
        and resolution["state"] == "running"
    )


def _x_daily_requirement_state(store, now: float, max_topics: int) -> str:
    """Return the fail-closed state of today's exact, frozen X collection cycle."""
    return str(_x_daily_cycle_resolution(store, now, max_topics)["state"])


def run_cycle(store, tickers: list[str], sources: list[str], macro_themes: dict,
              x_enabled: bool = False, x_interval: int = 86400,
              x_limit: int = 10, x_topic_limit: int = 3,
              force_x: bool = False) -> dict:
    """One cycle with independent provider/query receipts and watermarks."""
    since = None
    cycle_started = store.server_observed_utc()
    now = cycle_started
    if x_enabled and x_interval != int(
        GLOBAL_EVENT_V2_PROTOCOL["evidence"]["x_cycle_interval_seconds"]
    ):
        raise ValueError("X cycle interval must exactly match the frozen protocol")
    x_resolution = (
        _x_daily_cycle_resolution(store, now, x_topic_limit)
        if x_enabled else None
    )
    x_due = bool(x_enabled and (
        (
            force_x
            and x_resolution["origin"] != "compatible"
        )
        or (
            not force_x
            and (
                x_resolution["origin"] is None
                or (
                    x_resolution["origin"] == "current"
                    and x_resolution["state"] == "running"
                )
            )
        )
    ))
    expected_slots = _expected_query_slots(
        tickers,
        sources,
        macro_themes,
        include_x_discovery=bool(x_due and x_resolution["origin"] is None),
    )
    if sources:
        poll_once(store, tickers, sources, now, since)
    if macro_themes:
        poll_macro_once(store, macro_themes, now, since)
    if x_due:
        x_slots = poll_x_topics_once(
            store, now, limit=x_limit, max_topics=x_topic_limit
        ) or []
        if x_resolution["origin"] is None:
            expected_slots.extend(x_slots)
    cycle_completed = store.server_observed_utc()
    periodic_requirements = (
        {"x_daily": _x_daily_requirement_state(store, now, x_topic_limit)}
        if x_enabled
        else {}
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


def poll_forever(store, tickers: list[str], sources: list[str], interval: int,
                 macro_themes: dict, clock: TradingClock | None = None,
                 x_enabled: bool = False, x_interval: int = 86400,
                 x_limit: int = 10, x_topic_limit: int = 3,
                 *, health_state: CollectorHealthState | None = None,
                 lease_guard=None, stop: dict | None = None,
                 on_cycle_success=None) -> None:
    if stop is None:
        stop = {"flag": False}
        _install_collector_signal_handlers(stop)

    x_label = (f" + X discovery (up to {x_topic_limit} topics) every {x_interval}s"
               if x_enabled else "")
    logger.info("Polling %s [%s]%s%s every %ds%s. Ctrl-C / SIGTERM to stop.",
                ",".join(tickers), ",".join(sources),
                " + macro" if macro_themes else "", x_label, interval,
                " during extended trading hours" if clock else "")
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
            if coverage.get("complete") is True and on_cycle_success is not None:
                on_cycle_success()
            _sleep(interval, stop, lease_guard=lease_guard)
        except Exception as exc:  # noqa: BLE001 - sanitize before terminating
            error_kind = _exception_kind(exc)
            lease_lost = bool(
                lease_guard is not None
                and not bool(getattr(lease_guard, "is_held", False))
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
            lo_s = datetime.fromtimestamp(lo, timezone.utc).strftime("%Y-%m-%d %H:%M") if lo else "?"
            hi_s = datetime.fromtimestamp(hi, timezone.utc).strftime("%Y-%m-%d %H:%M") if hi else "?"
            print(f"{theme:<14} {n_markets:>7} {n_snap:>9}  {lo_s} → {hi_s}")


def print_window(store, ticker: str, end: str, days: int) -> None:
    rows = store.window(ticker, end, days)
    print(f"{ticker.upper()} — {len(rows)} items in the {days}d window ending {end}:")
    for r in rows:
        ts = (datetime.fromtimestamp(r["created_utc"], timezone.utc).strftime("%Y-%m-%d %H:%M")
              if r.get("created_utc") else "?")
        tag = r.get("sentiment") or (f"r/{r['subreddit']}" if r.get("subreddit") else "")
        text = (r.get("title") or r.get("body") or "").replace("\n", " ")[:120]
        print(f"  [{ts} · {r['source']:<10} {tag:<10}] {text}")


def _x_cycle_audit_projection(store, period_date) -> dict:
    midnight = datetime.combine(
        period_date, datetime.min.time(), tzinfo=timezone.utc
    ).timestamp()
    resolution = _x_daily_cycle_resolution(
        store,
        midnight,
        int(GLOBAL_EVENT_V2_PROTOCOL["evidence"][
            "max_x_search_requests_per_utc_day"
        ]),
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
            for row in receipts if isinstance(row, dict)
        ),
        "search_requests": sum(
            row.get("provider") == "x" and row.get("fetch_run_id") is not None
            for row in receipts if isinstance(row, dict)
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
    print(f"collector_coverage_complete={str(coverage['complete']).lower()}")
    print(f"collector_expected_query_slots={len(coverage['query_slots'])}")
    print(f"collector_missing_query_slots={len(coverage['missing_query_slots'])}")
    today = datetime.fromtimestamp(now, timezone.utc).date()
    for label, period in (("current", today), ("prior", today - timedelta(days=1))):
        x_cycle = _x_cycle_audit_projection(store, period)
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
        query_cycle["collector_interval_seconds"]
        + query_cycle["cycle_start_grace_seconds"]
    )


def _build_parser(env: Mapping[str, str] | None = None) -> argparse.ArgumentParser:
    values = os.environ if env is None else env
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tickers", default=values.get("MEDIA_POLLER_TICKERS"),
                   help="Comma-separated tickers (env: MEDIA_POLLER_TICKERS)")
    p.add_argument("--sources", default=values.get("MEDIA_POLLER_SOURCES"),
                   help="Comma-separated subset of: " + ",".join(SELECTABLE_SOURCES)
                        + " (env: MEDIA_POLLER_SOURCES). Default: keyless + 'x' if token set.")
    p.add_argument("--db", default=values.get("MEDIA_DB_URL"),
                   help="Store URL/path (env: MEDIA_DB_URL). Default: local SQLite.")
    p.add_argument("--interval", type=int,
                   default=_configured_integer(values, "MEDIA_POLLER_INTERVAL"),
                   help="Seconds between news cycles (env: MEDIA_POLLER_INTERVAL)")
    p.add_argument("--x-interval", type=int,
                   default=_configured_integer(values, "MEDIA_POLLER_X_INTERVAL"),
                   help="Seconds between X discovery cycles (env: MEDIA_POLLER_X_INTERVAL)")
    p.add_argument("--x-topics", type=int,
                   default=int(values.get("MEDIA_POLLER_X_TOPICS", "3")),
                   help="Maximum discovered topics per X cycle (default 3)")
    p.add_argument("--x-limit", type=int,
                   default=int(values.get("MEDIA_POLLER_X_LIMIT", "10")),
                   help="Results per broad X query (X API minimum/default: 10)")
    p.add_argument("--once", action="store_true", default=_env_bool("MEDIA_POLLER_ONCE", values),
                   help="Poll once and exit (env: MEDIA_POLLER_ONCE)")
    p.add_argument("--no-macro", dest="macro", action="store_false", default=True,
                   help="Skip the macro snapshot (Polymarket odds + theme news). "
                        "Macro is on by default; it captures unrecoverable data.")
    trading_default = (values.get("MEDIA_POLLER_TRADING_HOURS", "true").strip().lower()
                       not in ("0", "false", "no", "off"))
    p.add_argument("--no-trading-hours", dest="trading_hours", action="store_false",
                   default=trading_default,
                   help="Poll around the clock instead of gating to market hours. "
                        "By default the daemon polls only during the extended US session "
                        "(04:00–20:00 ET) on NYSE trading days (env: MEDIA_POLLER_TRADING_HOURS).")
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
        parser.error("collector alert webhook test was not delivered")
    print(canonical_json({"component": "collector", "delivered": True}))


def _run_preflight(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    env: Mapping[str, str],
) -> None:
    """Run the database-read-only release gate and optional webhook probe."""
    if (env.get("MEDIA_AUTO_MIGRATE") or "").strip().lower() not in {
        "0", "false", "no", "off",
    }:
        parser.error("collector preflight requires MEDIA_AUTO_MIGRATE=false")
    webhook_required_raw = (env.get("MEDIA_REQUIRE_ALERT_WEBHOOK") or "").strip().lower()
    if webhook_required_raw and webhook_required_raw not in {
        "1", "true", "yes", "on", "0", "false", "no", "off",
    }:
        parser.error("MEDIA_REQUIRE_ALERT_WEBHOOK must be an explicit boolean")
    webhook_required = webhook_required_raw in {"1", "true", "yes", "on"}
    if webhook_required and not (
        env.get("TRADINGAGENTS_ALERT_WEBHOOK_URL") or ""
    ).strip():
        parser.error("collector preflight requires the configured alert webhook")
    if args.health_port is None or not 1 <= args.health_port <= 65535:
        parser.error("collector preflight requires a valid MEDIA_HEALTH_PORT")

    configured_db = args.db or env.get("DATABASE_URL")
    if not (configured_db or "").strip():
        parser.error("collector preflight requires a configured PostgreSQL database")
    store = None
    try:
        semantics_id = collector_semantics_manifest()["collector_semantics_id"]
        expected_id = GLOBAL_EVENT_V2_PROTOCOL["evidence"][
            "expected_collector_semantics_id"
        ]
        if semantics_id != expected_id:
            raise RuntimeError("collector semantics do not match the frozen protocol")
        store = open_store(configured_db, auto_migrate=False)
        preflight = store.collector_runtime_preflight(
            direct_url=(env.get("MEDIA_DB_DIRECT_URL") or "").strip() or None
        )
        if preflight.get("ready") is not True:
            logger.error(
                "Collector database preflight rejected the release: %s",
                canonical_json(preflight),
            )
            raise RuntimeError("collector database contract is not ready")
        max_topics = int(GLOBAL_EVENT_V2_PROTOCOL["evidence"][
            "max_x_search_requests_per_utc_day"
        ])
        accepted_specs = [
            _x_collection_cycle_spec(0.0, max_topics),
            *_x_compatible_collection_cycle_specs(0.0, max_topics),
        ]
        accepted_pairs = {
            (
                spec["identity"]["protocol_id"],
                spec["identity"]["collector_semantics_id"],
            )
            for spec in accepted_specs
        }
        observed_pairs = store.collection_cycle_identity_pairs("x-daily")
        if (
            not isinstance(observed_pairs, list)
            or any(
                not isinstance(pair, (list, tuple))
                or len(pair) != 2
                or not all(isinstance(value, str) for value in pair)
                for pair in observed_pairs
            )
            or len(observed_pairs) != len({tuple(pair) for pair in observed_pairs})
            or any(tuple(pair) not in accepted_pairs for pair in observed_pairs)
        ):
            raise RuntimeError("collector X identity history is not compatible")
        x_identity_pair_count = len(observed_pairs)
        collector_build_id = build_identity()
        alert_probe_delivered = False
        if webhook_required:
            alert_probe_delivered = bool(emit_alert(
                "collector",
                "release_preflight_probe",
                severity="info",
                details={
                    "schema_version": 1,
                    "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
                    "collector_semantics_id": semantics_id,
                    "collector_build_id": collector_build_id,
                    "database_contract_ready": True,
                    "x_identity_history_compatible": True,
                    "x_identity_pair_count": x_identity_pair_count,
                },
            ))
            if not alert_probe_delivered:
                raise RuntimeError("collector alert preflight probe was not delivered")
        print(canonical_json({
            "schema_version": 2,
            "status": "ok",
            "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
            "collector_semantics_id": semantics_id,
            "collector_build_id": collector_build_id,
            "database_contract": preflight,
            "x_identity_history_compatible": True,
            "x_identity_pair_count": x_identity_pair_count,
            "health_port": args.health_port,
            "alert_webhook_required": webhook_required,
            "alert_probe_delivered": alert_probe_delivered,
        }))
    except Exception as exc:  # noqa: BLE001 - never render a DSN or DB error string
        parser.error(f"collector preflight failed ({_exception_kind(exc)})")
    finally:
        if store is not None:
            store.close()


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
                    health_server = start_collector_health_server(
                        health_state, port=health_port
                    )
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

                def _on_cycle_success() -> None:
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
                    on_cycle_success=_on_cycle_success,
                )
            except _CollectorRuntimeFailure as exc:
                failure = exc
            except Exception as exc:  # noqa: BLE001 - sanitize and retry daemon only
                failure = _CollectorRuntimeFailure(
                    failure_stage, _exception_kind(exc)
                )
            finally:
                _close_collector_attempt(store, collector_lease)

            if stop["flag"]:
                break
            if failure is None:
                failure = _CollectorRuntimeFailure(
                    "cycle", "UnexpectedDaemonReturn"
                )
            consecutive_failures += 1
            retry_delay = _collector_retry_delay(consecutive_failures)
            if health_state is not None:
                health_state.mark_failure(failure.error_type)
            transition_or_reminder = incident.mark_failure(
                stage=failure.stage,
                error_type=failure.error_type,
                retry_delay_seconds=retry_delay,
            )
            log = logger.error if transition_or_reminder else logger.info
            log(
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
            p.error(
                "--global-only requires explicit --interval and --x-interval cadence"
            )
        if args.interval != _GLOBAL_ONLY_NEWS_INTERVAL_SECONDS:
            p.error(
                "--global-only news interval must match the versioned collector policy"
            )
        if args.x_interval != _GLOBAL_ONLY_X_INTERVAL_SECONDS:
            p.error(
                "--global-only X interval must match the versioned collector policy"
            )
        expected_topics = int(
            GLOBAL_EVENT_V2_PROTOCOL["evidence"][
                "max_x_search_requests_per_utc_day"
            ]
        )
        expected_limit = int(
            GLOBAL_EVENT_V2_PROTOCOL["evidence"]["max_x_results_per_query"]
        )
        if args.x_topics != expected_topics or args.x_limit != expected_limit:
            p.error("--global-only X request bounds must match the collector policy")
        if not args.once:
            try:
                collection_enabled = _collection_enabled(env)
            except ValueError as exc:
                p.error(str(exc))
            if not collection_enabled:
                p.error(
                    "global collection is paused; set MEDIA_COLLECTION_ENABLED=true"
                )
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
        p.error(
            "--tickers (or MEDIA_POLLER_TICKERS) is required for ticker-specific sources"
        )

    x_token_configured = bool((env.get("X_BEARER_TOKEN") or "").strip())
    if x_selected and not x_token_configured:
        p.error("X_BEARER_TOKEN is required when source 'x' is configured")
    x_enabled = bool(x_selected and x_token_configured)
    if "truthsocial" in sources and not env.get("TRUTHSOCIAL_TOKEN"):
        logger.warning("source 'truthsocial' selected but TRUTHSOCIAL_TOKEN is unset — "
                       "Cloudflare will likely block it.")
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

                def _on_one_shot_lease_loss(failure_type: str) -> None:
                    emit_alert(
                        "collector",
                        "singleton_lease_lost",
                        severity="critical",
                        details={
                            "singleton_enforced": True,
                            "failure_type": _runtime_failure_type(failure_type),
                        },
                    )

                collector_lease = store.acquire_collector_lease(
                    direct_url=direct_url,
                    on_loss=_on_one_shot_lease_loss,
                )
                if collector_lease is None:
                    raise RuntimeError(
                        "another global collector owns the singleton lease"
                    )
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
        static_query_slots = _expected_query_slots(
            tickers, ticker_sources, macro_themes
        )
        health_state = CollectorHealthState(
            max_age_seconds=_collector_max_age_seconds(),
            expected_query_slot_ids={
                _query_slot_id(provider, query_key)
                for provider, query_key in static_query_slots
            },
            build_revision=(env.get("GIT_REVISION") or "").strip() or None,
            machine_id=(env.get("FLY_MACHINE_ID") or "").strip() or None,
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
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - sanitize the executable boundary
        logger.critical("Collector exited (%s)", _exception_kind(exc))
        raise SystemExit(1) from None


if __name__ == "__main__":
    _main_entrypoint()
