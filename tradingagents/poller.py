"""Media poller — accumulates social/news history for backtesting.

Polls each configured source (hourly by default), appending every new item to a
media store (local SQLite by default, or any database via ``MEDIA_DB_URL``),
deduped on the provider's stable id. See ``dataflows.media_sources`` (fetchers)
and ``dataflows.media_store`` (storage).

Designed to be cloud-hostable: every knob has an environment-variable form, so a
container can run with no CLI arguments. Env vars (CLI flags override them):

    MEDIA_POLLER_TICKERS   comma-separated; required only for ticker sources
    MEDIA_POLLER_SOURCES   subset of the sources; default = keyless (+x if token)
    MEDIA_POLLER_INTERVAL  seconds between polls in daemon mode      (default 3600)
    MEDIA_POLLER_X_INTERVAL seconds between X discovery cycles       (default 86400)
    MEDIA_POLLER_X_TOPICS  max discovered topics per cycle           (default 3)
    MEDIA_POLLER_X_LIMIT   results per discovered X query            (default 10)
    MEDIA_POLLER_ONCE      "1"/"true" → poll once and exit (for cron/scheduler)
    MEDIA_COLLECTION_ENABLED explicit formal-collector pause switch (default false)
    MEDIA_DB_URL           store location; default ~/.tradingagents/cache/media.db
    X_BEARER_TOKEN         enables the 'x' source (paid)
    TRUTHSOCIAL_TOKEN      enables Truth Social

Run modes:
    tradingagents-poller --tickers NVDA,AAPL          # hourly daemon
    tradingagents-poller --tickers NVDA --once        # one-shot (cron/scheduler)
    tradingagents-poller --stats                      # collection summary
    tradingagents-poller --formal-collector           # frozen global-news mode
    tradingagents-poller --formal-collector --release-material
    tradingagents-poller --formal-collector --release-rehearsal
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
from datetime import datetime, timezone
from functools import lru_cache

from tradingagents import global_research
from tradingagents.dataflows import media_sources, media_store
from tradingagents.dataflows.media_sources import (
    FETCHERS,
    KEYLESS_SOURCES,
    SELECTABLE_SOURCES,
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
    canonical_json,
    content_id,
    global_news_query_slot_label,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("media_poller")


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
if _GLOBALNEWS_MAX_ATTEMPTS != 3 \
        or len(_GLOBALNEWS_RETRY_DELAYS) != _GLOBALNEWS_MAX_ATTEMPTS - 1 \
        or any(value < 0 or value > 10 for value in _GLOBALNEWS_RETRY_DELAYS) \
        or _GLOBALNEWS_RETRY_POLICY.get("retry_on") != "exception_only" \
        or _GLOBALNEWS_RETRY_POLICY.get("empty_response") \
            != "terminal_observed_empty_without_retry":
    raise RuntimeError("formal globalnews retry policy is malformed")


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
    """Exact broad-news slots used by the formal evidence activation gate."""
    return [
        slot for slot in _expected_query_slots([], [], macro_themes)
        if slot[0] == "globalnews"
    ]


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


def _sanitized_coverage_alert_details(coverage: dict) -> dict:
    """Summarize missing slots without query strings, errors, or response data."""
    missing = coverage.get("missing_query_slots") or []
    slots = []
    reason_counts: dict[str, int] = {}
    allowed_reasons = {
        "not_run", "empty", "failed", "running", "incomplete", "stale", "ineligible",
        "invalid_lineage", "invalid_receipt", "unbound_lineage",
        "collector_semantics_mismatch",
    }
    for slot in missing:
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
    expected_count = len(coverage.get("query_slots") or [])
    return {
        "expected_query_slot_count": expected_count,
        "missing_query_slot_count": len(missing),
        "missing_source_group_count": len(coverage.get("missing_source_groups") or []),
        "reason_counts": reason_counts,
        "slots": slots,
        "slots_truncated": max(0, len(missing) - len(slots)),
    }


@lru_cache(maxsize=1)
def collector_semantics_manifest() -> dict:
    """Content-address every helper that can alter a formal fetch receipt."""
    components = {
        "normalize_public_url": media_sources.normalize_public_url,
        "publisher_domain": media_sources.publisher_domain,
        "google_news_provenance": media_sources._google_news_provenance,
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
        "fetch_receipt_pipeline": _run_fetch,
        "globalnews_retry_orchestration": _run_globalnews_query,
        "collection_cycle_spec": media_store.collection_cycle_spec,
        "collection_cycle_manifest": media_store._collection_cycle_manifest,
        "collection_cycle_item_replay": media_store._verified_cycle_item_rows,
        "x_collection_cycle_spec": _x_collection_cycle_spec,
        "x_collection_cycle_orchestration": poll_x_topics_once,
        "formal_release_cycle_spec": _formal_release_collection_cycle_spec,
        "formal_release_cycle_orchestration": (
            run_formal_collector_release_rehearsal
        ),
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
    }
    sources = {
        name: hashlib.sha256(inspect.getsource(component).encode("utf-8")).hexdigest()
        for name, component in components.items()
    }
    evidence = GLOBAL_EVENT_V2_PROTOCOL["evidence"]
    manifest = {
        "schema_version": 2,
        "policy": "formal-collector-atomic-source-content-v2",
        "components": sources,
        "semantic_values": {
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
            "allowed_observed_empty_providers": evidence["query_cycle"][
                "allowed_observed_empty_providers"
            ],
            "globalnews_exception_retry_policy": evidence["query_cycle"][
                "globalnews_exception_retry_policy"
            ],
            "discovery_categories": list(_DISCOVERY_CATEGORIES),
            "corporate_source_markers": list(media_sources._CORPORATE_SOURCE_MARKERS),
            "editorial_source_markers": list(media_sources._EDITORIAL_SOURCE_MARKERS),
            "first_party_headline_pattern": media_sources._FIRST_PARTY_HEADLINE.pattern,
            "low_information_pattern": _LOW_INFORMATION_HEADLINE.pattern,
        },
    }
    return {**manifest, "collector_semantics_id": content_id(
        manifest, prefix="collector_"
    )}


def _check_cycle_query_coverage(
    store, *, expected_query_slots: list[tuple[str, str]],
    cycle_started_utc: float, cycle_completed_utc: float,
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
    frozen_globalnews_slots = set(_globalnews_query_slots(DEFAULT_CONFIG["macro_themes"]))
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
    heartbeat = "poller:last_success_utc" if coverage["complete"] else "poller:last_failure_utc"
    store.set_meta(heartbeat, cycle_completed_utc)
    if not coverage["complete"]:
        emit_alert(
            "collector",
            "query_slot_coverage_incomplete",
            details=_sanitized_coverage_alert_details(coverage),
        )
    return coverage


def _run_fetch(
    store, *, provider: str, query_key: str, fetch_fn,
    labels: list[str] | None = None, odds: bool = False, cost_units: float = 0.0,
    store_result: bool = True, formal_eligibility_fn=None,
    budget_limits: dict[str, float] | None = None,
    budget_metadata: dict | None = None,
    collection_cycle_id: str | None = None,
) -> tuple[int, int, str]:
    """Fetch, receipt-stamp, store, and audit one independent query."""
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
        rows = fetch_fn(started)
        received = time.time()
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
            fingerprints: dict[tuple[object, object], str] = {}
            for row in rows:
                identity = (row.get("source"), row.get("external_id"))
                fingerprint = _raw_content_id(row)
                if identity in fingerprints and fingerprints[identity] != fingerprint:
                    raise ValueError(
                        f"{provider} fetcher returned conflicting duplicate provenance"
                    )
                fingerprints.setdefault(identity, fingerprint)
            if formal_eligibility_fn is not None:
                formal_eligible_evidence_ids = sorted({
                    _evidence_id(row)
                    for row in rows
                    if (
                        provider != "globalnews"
                        or query_key in _formal_query_slots(row)
                    )
                    and formal_eligibility_fn(row, received)
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
        # Empty results are deliberately retried: they can mean a transient API
        # or auth problem and cannot prove coverage.
        if rows:
            store.set_meta(watermark_key, received)
        return len(rows), inserted, status
    except Exception as exc:
        if terminal_committed:
            # The durable success receipt is authoritative. A later best-effort
            # watermark failure must not attempt to rewrite it as failed; the
            # next cycle will safely refetch and deduplicate instead.
            raise
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
    for theme, spec in themes.items():
        news_new = 0
        for query in spec.get("queries", []):
            try:
                _, inserted, _ = _run_globalnews_query(store, theme, query)
                news_new += inserted
            except Exception as exc:
                logger.error(
                    "globalnews fetch slot %s failed (%s)",
                    _query_slot_id("globalnews", f"{theme}:{query}"), _exception_kind(exc),
                )
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


def _run_globalnews_query(
    store,
    theme: str,
    query: str,
    *,
    sleep_fn=None,
    collection_cycle_id: str | None = None,
    max_attempts: int | None = None,
) -> tuple[int, int, str]:
    """Run one broad-news slot with bounded exception-only retries.

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
                    "retry_policy": "exception_only",
                },
                collection_cycle_id=collection_cycle_id,
            )
        except Exception as exc:
            if attempt_ordinal >= attempt_limit:
                raise
            logger.warning(
                "globalnews fetch slot %s attempt %d/%d failed (%s); retrying",
                _query_slot_id("globalnews", query_key),
                attempt_ordinal,
                attempt_limit,
                _exception_kind(exc),
            )
            sleeper(_GLOBALNEWS_RETRY_DELAYS[attempt_ordinal - 1])
    raise AssertionError("unreachable globalnews retry state")


def _formal_release_collection_cycle_spec(now: float) -> dict:
    """Return the one-shot exact broad-news/X release-rehearsal identity."""

    if (
        isinstance(now, bool)
        or not isinstance(now, (int, float))
        or not math.isfinite(float(now))
    ):
        raise ValueError("collector release rehearsal time must be finite")
    observed = datetime.fromtimestamp(float(now), timezone.utc)
    period_key = observed.strftime("release-%Y%m%dT%H%M%S.") + f"{observed.microsecond:06d}Z"
    evidence = GLOBAL_EVENT_V2_PROTOCOL["evidence"]
    static_slots = [
        ("globalnews", f"{theme}:{query}")
        for theme, queries in evidence["broad_news_queries"].items()
        for query in queries
    ] + [
        ("xtrend", f"woeid:{int(woeid)}")
        for woeid in evidence["x_trend_woeids"]
    ] + [("trendnews", "ranked-global-discovery")]
    return media_store.collection_cycle_spec(
        cycle_kind="formal-release-rehearsal-v1",
        period_key=period_key,
        protocol_id=GLOBAL_EVENT_V2_PROTOCOL_ID,
        collector_semantics_id=collector_semantics_manifest()[
            "collector_semantics_id"
        ],
        expected_static_slots=static_slots,
        max_dynamic_slots=int(evidence["max_x_search_requests_per_utc_day"]),
    )


def run_formal_collector_release_rehearsal(
    store,
    *,
    now: float,
    component_configuration_id: str,
    collector_build_id: str,
) -> dict:
    """Run real frozen collector children and emit only a durable exact proof.

    This is an explicitly requested one-shot operation while the daemon switch
    remains paused. It performs the ten broad editorial-news fetches and the
    same bounded X discovery/search children used by normal collection. Any
    missing or empty broad-news slot fails closed in the terminal manifest.
    """

    from tradingagents.formal_activation import build_collector_rehearsal_payload

    spec = _formal_release_collection_cycle_spec(now)
    cycle_id = store.start_collection_cycle(spec, started_utc=time.time())
    expected_slots = [
        (slot["provider"], slot["query_key"])
        for slot in spec["identity"]["expected_static_slots"]
    ]
    try:
        for theme, queries in GLOBAL_EVENT_V2_PROTOCOL["evidence"][
            "broad_news_queries"
        ].items():
            for query in queries:
                try:
                    _run_globalnews_query(
                        store,
                        theme,
                        query,
                        collection_cycle_id=cycle_id,
                        max_attempts=1,
                    )
                except Exception as exc:
                    logger.error(
                        "release globalnews slot %s failed (%s)",
                        _query_slot_id("globalnews", f"{theme}:{query}"),
                        _exception_kind(exc),
                    )
        _poll_x_cycle_children(
            store,
            now=now,
            limit=int(
                GLOBAL_EVENT_V2_PROTOCOL["evidence"]["max_x_results_per_query"]
            ),
            max_topics=int(
                GLOBAL_EVENT_V2_PROTOCOL["evidence"][
                    "max_x_search_requests_per_utc_day"
                ]
            ),
            collection_cycle_id=cycle_id,
            expected_slots=expected_slots,
        )
    finally:
        cycle = store.finish_collection_cycle(cycle_id, completed_utc=time.time())
    if cycle.get("status") != "complete" or cycle.get("manifest_valid") is not True:
        raise ValueError("collector release rehearsal did not complete every exact slot")
    manifest = cycle.get("manifest")
    if not isinstance(manifest, Mapping):
        raise ValueError("collector release rehearsal lacks its durable manifest")
    if manifest.get("collector_build_id") != collector_build_id:
        raise ValueError("collector release rehearsal used a different runtime build")
    return build_collector_rehearsal_payload(
        final_collection_cycle_manifest=manifest,
        component_configuration_id=component_configuration_id,
    )


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


def _x_collection_cycle_spec(now: float, max_topics: int) -> dict:
    """Return the daily X cycle identity before any free or paid request starts."""
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
        protocol_id=GLOBAL_EVENT_V2_PROTOCOL_ID,
        collector_semantics_id=collector_semantics_manifest()["collector_semantics_id"],
        expected_static_slots=static_slots,
        max_dynamic_slots=max_topics,
    )


def _poll_x_cycle_children(
    store, *, now: float, limit: int, max_topics: int,
    collection_cycle_id: str, expected_slots: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Execute one cycle's children after its immutable parent is durable."""
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
        except Exception as exc:
            logger.error(
                "xtrend slot %s failed (%s)",
                _query_slot_id("xtrend", query_key), _exception_kind(exc),
            )

    topics_box: dict[str, list[dict]] = {}

    def discover(captured):
        headlines = fetch_top_news_headlines()
        topics_box["topics"] = _formally_grounded_discovery_topics(
            discover_x_topics(
                max_topics=max_topics, headlines=headlines, trends=trends
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
    except Exception as exc:
        logger.error(
            "trendnews discovery slot %s failed (%s)",
            _query_slot_id("trendnews", "ranked-global-discovery"),
            _exception_kind(exc),
        )
        return expected_slots
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
        except Exception as exc:
            logger.error(
                "x discovery slot %s failed (%s)",
                _query_slot_id("x", topic["query"]), _exception_kind(exc),
            )
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
    spec = _x_collection_cycle_spec(now, max_topics)
    collection_cycle_id = spec["collection_cycle_id"]
    existing = store.collection_cycle(collection_cycle_id)
    if existing is not None:
        if not existing.get("identity_valid") or existing.get("identity") != spec["identity"]:
            raise ValueError("existing X collection cycle identity is invalid")
        if existing["status"] == "running":
            observed_utc = time.time()
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
        elif not existing.get("manifest_valid"):
            raise ValueError("existing X collection cycle manifest is invalid")
        store.set_meta("last_x_poll_utc", now)
        manifest = existing.get("manifest") or {}
        return [
            (slot["provider"], slot["query_key"])
            for slot in (
                (manifest.get("expected_static_slots") or [])
                + (manifest.get("expected_dynamic_slots") or [])
            )
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
    spec = _x_collection_cycle_spec(now, max_topics)
    cycle = store.collection_cycle(spec["collection_cycle_id"])
    if cycle is None:
        return True
    # A running same-day parent needs recovery, not another external attempt.
    if cycle["status"] == "running":
        return True
    return not cycle.get("identity_valid") or not cycle.get("manifest_valid")


def run_cycle(store, tickers: list[str], sources: list[str], macro_themes: dict,
              x_enabled: bool = False, x_interval: int = 86400,
              x_limit: int = 10, x_topic_limit: int = 3,
              force_x: bool = False) -> None:
    """One cycle with independent provider/query receipts and watermarks."""
    since = None
    cycle_started = time.time()
    now = cycle_started
    if x_enabled and x_interval != int(
        GLOBAL_EVENT_V2_PROTOCOL["evidence"]["x_cycle_interval_seconds"]
    ):
        raise ValueError("X cycle interval must exactly match the frozen protocol")
    x_due = bool(x_enabled and (force_x or _x_poll_due(store, now, x_interval)))
    existing_x_cycle = None
    if x_due:
        existing_x_cycle = store.collection_cycle(
            _x_collection_cycle_spec(now, x_topic_limit)["collection_cycle_id"]
        )
    expected_slots = _expected_query_slots(
        tickers,
        sources,
        macro_themes,
        include_x_discovery=bool(x_due and existing_x_cycle is None),
    )
    if sources:
        poll_once(store, tickers, sources, now, since)
    if macro_themes:
        poll_macro_once(store, macro_themes, now, since)
    if x_due:
        x_slots = poll_x_topics_once(
            store, now, limit=x_limit, max_topics=x_topic_limit
        ) or []
        if existing_x_cycle is None:
            expected_slots.extend(x_slots)
    cycle_completed = time.time()
    _check_cycle_query_coverage(
        store,
        expected_query_slots=list(dict.fromkeys(expected_slots)),
        cycle_started_utc=cycle_started,
        cycle_completed_utc=cycle_completed,
    )
    store.set_meta("poller:last_cycle_utc", cycle_completed)


def check_paper_heartbeat(store, now: float, max_age: float) -> bool:
    """Independent watchdog for the paper worker's database heartbeat."""
    success = store.get_meta("paper:last_success_utc")
    failure = store.get_meta("paper:last_failure_utc")
    healthy = bool(success and now - success <= max_age and (not failure or success >= failure))
    if success is None:
        logger.warning("Paper watchdog: no success heartbeat recorded yet")
    elif now - success > max_age:
        logger.error("Paper watchdog: success heartbeat is %.1f hours stale", (now - success) / 3600)
    elif failure and failure > success:
        logger.error("Paper watchdog: latest paper heartbeat is a failure")
    if not healthy:
        emit_alert(
            "paper-watchdog", "unhealthy_heartbeat",
            details={"success_utc": success, "failure_utc": failure, "max_age": max_age},
        )
    return healthy


_FORMAL_COLLECTOR_RELEASE_PROJECTION_SQL = """
SELECT authorized, collector_configuration_id
FROM public.formal_collector_release_projection(
    :protocol_id, :collector_build_id
)
""".strip()
_FORMAL_HEALTH_ROW_FIELDS = frozenset({
    "runtime_component",
    "event_type",
    "observed_utc",
    "latest_success_utc",
    "latest_failure_utc",
    "latest_paused_utc",
})


def _formal_runtime_health_projection(
    store,
    *,
    protocol_id: str,
    collector_build_id: str,
) -> tuple[dict, list[dict]]:
    """Read only migration-013's outcome-free collector projections."""
    from sqlalchemy import text

    from tradingagents.formal_roles import RUNTIME_HEALTH_PROJECTION_SQL

    engine = getattr(store, "engine", None)
    if engine is None:
        raise RuntimeError("formal collector health requires PostgreSQL projections")
    parameters = {
        "protocol_id": protocol_id,
        "collector_build_id": collector_build_id,
    }
    with engine.connect() as connection:
        release = connection.execute(
            text(_FORMAL_COLLECTOR_RELEASE_PROJECTION_SQL), parameters
        ).mappings().one()
        health = connection.execute(
            text(RUNTIME_HEALTH_PROJECTION_SQL), parameters
        ).mappings().all()
    return dict(release), [dict(row) for row in health]


def _validated_formal_runtime_health_projection(
    release: object, rows: object
) -> tuple[dict, list[dict]]:
    if not isinstance(release, Mapping) or set(release) != {
        "authorized",
        "collector_configuration_id",
    }:
        raise ValueError("formal collector release projection has a wrong schema")
    authorized = release["authorized"]
    configuration_id = release["collector_configuration_id"]
    if not isinstance(authorized, bool):
        raise ValueError("formal collector release projection has invalid authority")
    if authorized:
        if not isinstance(configuration_id, str) or re.fullmatch(
            r"config_[0-9a-f]{24}", configuration_id
        ) is None:
            raise ValueError("formal collector release projection has an invalid config")
    elif configuration_id is not None:
        raise ValueError("unauthorized collector projection exposed a configuration")
    if not isinstance(rows, list):
        raise ValueError("formal runtime health projection must be a list")

    normalized_rows = []
    seen_components: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != _FORMAL_HEALTH_ROW_FIELDS:
            raise ValueError("formal runtime health projection row has a wrong schema")
        component = row["runtime_component"]
        event_type = row["event_type"]
        if component not in {"decision", "marker"} or component in seen_components:
            raise ValueError("formal runtime health projection component is invalid")
        if event_type not in {"success", "failure", "paused"}:
            raise ValueError("formal runtime health projection event is invalid")
        for field in (
            "observed_utc",
            "latest_success_utc",
            "latest_failure_utc",
            "latest_paused_utc",
        ):
            value = row[field]
            if value is None and field != "observed_utc":
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(float(value)):
                raise ValueError("formal runtime health projection time is invalid")
        latest_field = f"latest_{event_type}_utc"
        if row[latest_field] != row["observed_utc"]:
            raise ValueError("formal runtime health projection latest event is inconsistent")
        if any(
            isinstance(row[field], (int, float))
            and float(row[field]) > float(row["observed_utc"])
            for field in (
                "latest_success_utc",
                "latest_failure_utc",
                "latest_paused_utc",
            )
        ):
            raise ValueError("formal runtime health projection chronology is invalid")
        seen_components.add(component)
        normalized_rows.append(dict(row))
    if not authorized and normalized_rows:
        raise ValueError("unauthorized collector projection exposed runtime health")
    return dict(release), normalized_rows


def check_formal_runtime_health(
    store,
    now: float,
    max_age: float,
    *,
    protocol_id: str,
    collector_build_id: str,
    collector_configuration_id: str,
) -> dict:
    """Watch split paper workers without reading their protected ledgers.

    Trial authorization gates paper activity, not preregistration evidence
    collection. An unmatched collector image therefore reports
    ``not-yet-authorized`` and leaves collection running.
    """
    if (
        isinstance(now, bool)
        or not isinstance(now, (int, float))
        or not math.isfinite(float(now))
        or isinstance(max_age, bool)
        or not isinstance(max_age, (int, float))
        or not math.isfinite(float(max_age))
        or float(max_age) <= 0
    ):
        raise ValueError("formal runtime health clock settings are invalid")
    try:
        release, rows = _formal_runtime_health_projection(
            store,
            protocol_id=protocol_id,
            collector_build_id=collector_build_id,
        )
    except Exception as exc:  # noqa: BLE001 - keep collection independent of paper health
        error_kind = _exception_kind(exc)
        logger.error("Formal paper health projection failed (%s)", error_kind)
        emit_alert(
            "paper-watchdog",
            "health_projection_unavailable",
            details={"error_type": error_kind},
        )
        return {
            "status": "unavailable",
            "healthy": False,
            "authorized": False,
            "runtime_components": [],
        }

    try:
        release, rows = _validated_formal_runtime_health_projection(release, rows)
    except ValueError:
        logger.error("Formal paper health projection returned an invalid contract")
        emit_alert(
            "paper-watchdog",
            "health_projection_invalid",
            details={"contract": "migration-013-runtime-health"},
        )
        return {
            "status": "invalid",
            "healthy": False,
            "authorized": False,
            "runtime_components": [],
        }

    if release.get("authorized") is not True:
        logger.info(
            "Formal paper health: collector build is not yet trial-authorized; "
            "evidence collection remains enabled"
        )
        return {
            "status": "not-yet-authorized",
            "healthy": True,
            "authorized": False,
            "runtime_components": [],
        }
    if release.get("collector_configuration_id") != collector_configuration_id:
        logger.error("Formal paper health: authorized collector configuration differs")
        emit_alert(
            "paper-watchdog",
            "collector_configuration_mismatch",
            details={"build_id": collector_build_id},
        )
        return {
            "status": "configuration-mismatch",
            "healthy": False,
            "authorized": True,
            "runtime_components": [],
        }

    by_component = {row.get("runtime_component"): row for row in rows}
    components = []
    for name in ("decision", "marker"):
        row = by_component.get(name)
        if row is None:
            status = "missing"
        elif float(row["observed_utc"]) > float(now) + 300.0:
            status = "future"
        elif row["event_type"] == "paused":
            paused = row["latest_paused_utc"]
            success = row["latest_success_utc"]
            failure = row["latest_failure_utc"]
            unresolved_failure = isinstance(failure, (int, float)) and (
                not isinstance(success, (int, float)) or float(failure) >= float(success)
            )
            if unresolved_failure:
                status = "failure"
            elif not isinstance(paused, (int, float)) or now - float(paused) > max_age:
                status = "stale"
            else:
                status = "paused"
        elif row["event_type"] == "failure":
            status = "failure"
        else:
            success = row["latest_success_utc"]
            status = (
                "healthy"
                if isinstance(success, (int, float)) and now - float(success) <= max_age
                else "stale"
            )
        components.append({"runtime_component": name, "status": status})

    unhealthy = [
        component
        for component in components
        if component["status"] in {"failure", "future", "missing", "stale"}
    ]
    if unhealthy:
        logger.error("Formal paper health: one or more split workers are unhealthy")
        emit_alert(
            "paper-watchdog",
            "unhealthy_formal_runtime",
            details={"components": unhealthy, "max_age": max_age},
        )
        status = "unhealthy"
    elif all(component["status"] == "healthy" for component in components):
        status = "healthy"
    else:
        status = "paused"
    return {
        "status": status,
        "healthy": not unhealthy,
        "authorized": True,
        "runtime_components": components,
    }


def _sleep(seconds: float, stop: dict) -> None:
    """Sleep in short slices so a stop signal is honoured promptly."""
    slept = 0.0
    while slept < seconds and not stop["flag"]:
        time.sleep(min(5.0, seconds - slept))
        slept += 5.0


def poll_forever(store, tickers: list[str], sources: list[str], interval: int,
                 macro_themes: dict, clock: TradingClock | None = None,
                 x_enabled: bool = False, x_interval: int = 86400,
                 x_limit: int = 10, x_topic_limit: int = 3,
                 paper_heartbeat_max_age: float | None = None,
                 formal_runtime_identity: Mapping[str, str] | None = None) -> None:
    stop = {"flag": False}

    def _handle(signum, _frame):
        logger.info("Received signal %s — finishing current cycle then exiting.", signum)
        stop["flag"] = True

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    x_label = (f" + X discovery (up to {x_topic_limit} topics) every {x_interval}s"
               if x_enabled else "")
    logger.info("Polling %s [%s]%s%s every %ds%s. Ctrl-C / SIGTERM to stop.",
                ",".join(tickers), ",".join(sources),
                " + macro" if macro_themes else "", x_label, interval,
                " during extended trading hours" if clock else "")
    while not stop["flag"]:
        if clock is not None and not clock.is_polling_time():
            wake = clock.next_open()
            wait = max(60.0, (wake - datetime.now(timezone.utc)).total_seconds())
            logger.info("Outside trading hours — sleeping until %s",
                        wake.strftime("%Y-%m-%d %H:%M UTC"))
            _sleep(wait, stop)
            continue
        try:
            run_cycle(store, tickers, sources, macro_themes, x_enabled,
                      x_interval=x_interval, x_limit=x_limit, x_topic_limit=x_topic_limit)
            if paper_heartbeat_max_age and formal_runtime_identity is not None:
                check_formal_runtime_health(
                    store,
                    datetime.now(timezone.utc).timestamp(),
                    paper_heartbeat_max_age,
                    **formal_runtime_identity,
                )
            elif paper_heartbeat_max_age:
                check_paper_heartbeat(
                    store, datetime.now(timezone.utc).timestamp(), paper_heartbeat_max_age
                )
        except Exception as exc:  # noqa: BLE001 — daemon must survive transient providers/DBs
            error_kind = _exception_kind(exc)
            logger.error(
                "Poll cycle failed (%s); incomplete slots retry next cycle", error_kind
            )
            emit_alert("collector", "cycle_failed", details={"error_type": error_kind})
            try:
                store.set_meta("poller:last_failure_utc", datetime.now(timezone.utc).timestamp())
            except Exception as heartbeat_exc:  # noqa: BLE001
                logger.error(
                    "Could not record poller failure heartbeat (%s)",
                    _exception_kind(heartbeat_exc),
                )
        _sleep(interval, stop)
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


def print_audit(store) -> None:
    now = datetime.now(timezone.utc).timestamp()
    expected_slots = _globalnews_query_slots(DEFAULT_CONFIG.get("macro_themes", {}))
    coverage = store.coverage_report(
        now,
        GLOBAL_EVENT_V2_PROTOCOL["evidence"]["required_source_groups"],
        expected_query_slots=expected_slots,
        require_lineage_query_slots=expected_slots,
    )
    print(f"formal_coverage_complete={str(coverage['complete']).lower()}")
    print(f"formal_expected_query_slots={len(coverage['query_slots'])}")
    print(f"formal_missing_query_slots={len(coverage['missing_query_slots'])}")
    for run in store.fetch_runs(limit=25):
        when = datetime.fromtimestamp(run["started_utc"], timezone.utc).isoformat()
        print(
            f"{when} {run['provider']} {run['status']} items={run['item_count']} "
            f"inserted={run['inserted_count']} cost_units={run['cost_units']} "
            f"query={run['query_key']}"
        )


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
                   default=int(values.get("MEDIA_POLLER_INTERVAL", "3600")),
                   help="Seconds between polls in daemon mode (env: MEDIA_POLLER_INTERVAL)")
    p.add_argument("--x-interval", type=int,
                   default=int(values.get("MEDIA_POLLER_X_INTERVAL", "86400")),
                   help="Seconds between X discovery cycles (default 86400 / 1 day)")
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
    p.add_argument("--audit", action="store_true", help="Print fetch receipts/coverage and exit")
    p.add_argument("--window", metavar="TICKER", help="Print the backtest window and exit")
    p.add_argument("--end", help="Window end date YYYY-MM-DD (default: today)")
    p.add_argument("--days", type=int, default=7, help="Window length in days (default: 7)")
    p.add_argument(
        "--formal-collector",
        action="store_true",
        help="Run the exact frozen global-event collector without a ticker watchlist",
    )
    p.add_argument(
        "--release-material",
        action="store_true",
        help="Emit in-image collector configuration/preflight JSON and exit",
    )
    p.add_argument(
        "--release-rehearsal",
        action="store_true",
        help=(
            "Run one exact broad-news/X collector rehearsal while the daemon "
            "switch remains paused, emit content-addressed JSON, and exit"
        ),
    )
    return p


def _comma_separated(value: str | None, *, lowercase: bool = False) -> list[str]:
    if not value:
        return []
    items = [item.strip() for item in value.split(",") if item.strip()]
    return [item.lower() for item in items] if lowercase else items


def _formal_collection_enabled(env: Mapping[str, str]) -> bool:
    raw = (env.get("MEDIA_COLLECTION_ENABLED") or "").strip().lower()
    if not raw:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError("MEDIA_COLLECTION_ENABLED must be an explicit boolean")


def _require_formal_collection_paused(env: Mapping[str, str]) -> None:
    raw = env.get("MEDIA_COLLECTION_ENABLED")
    if not isinstance(raw, str) or raw.strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }:
        raise ValueError(
            "MEDIA_COLLECTION_ENABLED must be explicitly false for release evidence"
        )


def _hold_paused_formal_collector() -> None:
    """Keep the paused image reachable without touching DBs or providers.

    Fly's ``on-failure`` restart policy deliberately does not restart a process
    that exits successfully. A paused deployment therefore remains alive so an
    operator can SSH into that exact Machine for release evidence and the
    controlled one-shot rehearsal.
    """

    while True:
        time.sleep(3600.0)


def _formal_collector_runtime_material(
    args,
    *,
    sources: list[str],
    macro_themes: Mapping[str, object],
    env: Mapping[str, str],
    require_release_environment: bool = False,
) -> dict:
    """Resolve exact collector material without opening a DB or provider."""
    from tradingagents.formal_runtime import collector_component_configuration

    return collector_component_configuration(
        args,
        enabled_sources=sources,
        macro_themes=macro_themes,
        collector_semantics_id=collector_semantics_manifest()[
            "collector_semantics_id"
        ],
        env=env,
        require_release_environment=require_release_environment,
    )


def _inspection_command(args) -> bool:
    return bool(args.stats or args.audit or args.window)


def _run_inspection(args) -> None:
    store = open_store(args.db)
    try:
        if args.stats:
            print_stats(store)
        elif args.audit:
            print_audit(store)
        else:
            end = args.end or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            print_window(store, args.window, end, args.days)
    finally:
        store.close()


def main(argv: list[str] | None = None) -> None:
    env = os.environ
    p = _build_parser(env)
    args = p.parse_args(argv)

    if (args.release_material or args.release_rehearsal) and not args.formal_collector:
        p.error("release evidence commands require --formal-collector")
    if args.release_material and args.release_rehearsal:
        p.error("--release-material and --release-rehearsal are mutually exclusive")
    if _inspection_command(args):
        _run_inspection(args)
        return

    tickers = [ticker.upper() for ticker in _comma_separated(args.tickers)]
    explicit = _comma_separated(args.sources, lowercase=True) or None
    try:
        sources = resolve_sources(explicit, env=env)
    except ValueError as exc:
        p.error(str(exc))

    x_selected = "x" in sources
    ticker_sources = [source for source in sources if source != "x"]
    if ticker_sources and not tickers:
        p.error(
            "--tickers (or MEDIA_POLLER_TICKERS) is required for ticker-specific sources"
        )
    macro_themes = DEFAULT_CONFIG.get("macro_themes", {}) if args.macro else {}

    component = None
    formal_runtime_identity = None
    if args.formal_collector:
        collection_enabled = False
        if args.release_material or args.release_rehearsal:
            try:
                _require_formal_collection_paused(env)
            except ValueError as exc:
                p.error(str(exc))
        else:
            try:
                collection_enabled = _formal_collection_enabled(env)
            except ValueError as exc:
                p.error(str(exc))
        try:
            component = _formal_collector_runtime_material(
                args,
                sources=sources,
                macro_themes=macro_themes,
                env=env,
                require_release_environment=(
                    args.release_material or args.release_rehearsal or collection_enabled
                ),
            )
        except ValueError as exc:
            p.error(str(exc))
        from tradingagents.formal_runtime import in_image_preflight_identity

        if args.release_material:
            try:
                material = in_image_preflight_identity(component, env=env)
            except ValueError as exc:
                p.error(str(exc))
            print(canonical_json(material))
            return
        if not collection_enabled and not args.release_rehearsal:
            print(
                canonical_json(
                    {
                        "schema_version": 1,
                        "status": "paused",
                        "role": "collector",
                        "protocol_id": component["protocol_id"],
                        "component_configuration_id": component[
                            "configuration_id"
                        ],
                    }
                ),
                flush=True,
            )
            _hold_paused_formal_collector()
            return
        try:
            runtime_material = in_image_preflight_identity(component, env=env)
        except ValueError as exc:
            p.error(str(exc))
        preflight = runtime_material["preflight_payload"]
        formal_runtime_identity = {
            "protocol_id": component["protocol_id"],
            "collector_build_id": preflight["build_id"],
            "collector_configuration_id": component["configuration_id"],
        }

    x_token_configured = bool((env.get("X_BEARER_TOKEN") or "").strip())
    if x_selected and not x_token_configured:
        p.error("X_BEARER_TOKEN is required when source 'x' is configured")
    x_enabled = bool(x_selected and x_token_configured)
    if "truthsocial" in sources and not env.get("TRUTHSOCIAL_TOKEN"):
        logger.warning("source 'truthsocial' selected but TRUTHSOCIAL_TOKEN is unset — "
                       "Cloudflare will likely block it.")
    if not ticker_sources and not macro_themes and not x_enabled:
        p.error("no enabled ticker, macro, or X collection source")

    if args.release_rehearsal:
        if component is None or formal_runtime_identity is None:
            p.error("collector release rehearsal lacks exact runtime material")
        store = open_store(args.db, auto_migrate=False)
        try:
            try:
                rehearsal = run_formal_collector_release_rehearsal(
                    store,
                    now=time.time(),
                    component_configuration_id=component["configuration_id"],
                    collector_build_id=formal_runtime_identity["collector_build_id"],
                )
            except ValueError as exc:
                p.error(str(exc))
            print(canonical_json(rehearsal))
            return
        finally:
            store.close()

    store = open_store(args.db)
    try:
        store_label = _store_log_label(args.db)
        logger.info("Store: %s%s", store_label,
                    f" · macro: {len(macro_themes)} themes" if macro_themes else " · macro off")

        if args.once:
            # One-shot (cron/manual) always polls — gating is the daemon's job;
            # schedule cron during trading hours externally if desired.
            run_cycle(store, tickers, ticker_sources, macro_themes, x_enabled,
                      x_interval=args.x_interval, x_limit=args.x_limit,
                      x_topic_limit=args.x_topics, force_x=True)
        else:
            clock = TradingClock() if args.trading_hours else None
            poll_forever(store, tickers, ticker_sources, args.interval, macro_themes, clock,
                         x_enabled=x_enabled, x_interval=args.x_interval,
                         x_limit=args.x_limit, x_topic_limit=args.x_topics,
                         paper_heartbeat_max_age=float(
                             env.get("PAPER_HEARTBEAT_MAX_AGE", "0")
                         ) or None,
                         formal_runtime_identity=formal_runtime_identity)
    finally:
        store.close()


if __name__ == "__main__":
    main()
