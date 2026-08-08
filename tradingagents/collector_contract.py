"""Stable compatibility contracts for global-event collection.

Collection identities describe the evidence stream, not the process that
produced it.  Builds, database drivers, alerts, and deployment code therefore
cannot invalidate otherwise compatible evidence.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from types import MappingProxyType
from typing import Any

from tradingagents.dataflows import media_sources

# Version tokens in the manifests are compatibility migrations: bump the
# relevant token when its named behavior changes, never for an implementation
# or operational refactor.
COLLECTOR_POLICY = "global-only-editorial-and-trend-reaction-v2"
COLLECTOR_COMPATIBILITY_PRECEDENCE = (
    "current-then-newest-compatible-to-oldest-v1"
)

_DISCOVERY_STOPWORDS = tuple(sorted({
    "a", "about", "according", "after", "against", "all", "amid", "an", "and",
    "are", "as", "at", "be", "before", "but", "by", "can", "confirms", "could",
    "for", "from", "has", "have", "how", "in", "into", "is", "it", "its", "may",
    "more", "new", "not", "of", "on", "or", "over", "report", "reports", "says",
    "than", "that", "the", "their", "this", "to", "up", "was", "what", "when",
    "where", "which", "who", "why", "will", "with", "would",
}))
_DISCOVERY_GENERIC_CAPITALIZED_TERMS = tuple(sorted({
    "Analysis", "Breaking", "Exclusive", "Explainer", "Here", "How", "Live", "My",
    "New", "Opinion", "The", "This", "Update", "What", "When", "Why",
}))

# All literals that can change ranked topic discovery live here. Nested values
# are immutable, while ``discovery_policy_manifest`` returns a plain JSON-ready
# projection for the collection identity.
DISCOVERY_POLICY = MappingProxyType({
    "version": "ranked-cross-source-topic-discovery-v3",
    "inputs": MappingProxyType({
        "ranked_feed_limit": 12,
        "categories": ("world", "business", "technology"),
        "exclude_low_information": True,
        "exclude_company_authored": True,
        "low_information_pattern": (
            r"\b(best|deal|discount|guide|hands[- ]on|how to|review|rumor|"
            r"versus|vs\.?|wishlist)\b"
        ),
        "low_information_flags": int(re.IGNORECASE | re.UNICODE),
    }),
    "normalization": MappingProxyType({
        "publisher_suffix_pattern": r"\s+-\s+[^-]{2,80}$",
        "word_pattern": r"[a-z0-9]+",
        "case": "lower",
        "stopwords": _DISCOVERY_STOPWORDS,
        "semantic_min_chars": 3,
        "semantic_short_allowlist": ("ai", "uk", "us"),
        "semantic_prefix_aliases": (("launch", "launch"),),
        "semantic_exact_aliases": (("worldwide", "world"),),
        "plural_suffix": "s",
        "plural_min_chars": 5,
    }),
    "story_grouping": MappingProxyType({
        "primary_jaccard_min": 0.58,
        "secondary_overlap_min": 3,
        "secondary_jaccard_min": 0.38,
        "resolution": "first-matching-input-group",
    }),
    "trend_matching": MappingProxyType({
        "leading_chars_to_strip": "#",
        "meaningful_min_chars": 4,
        "single_term_required_overlap": 1,
        "multiple_term_required_overlap": 2,
    }),
    "query": MappingProxyType({
        "token_pattern": r"[A-Za-z][A-Za-z0-9&.'’+-]*",
        "generic_capitalized_terms": _DISCOVERY_GENERIC_CAPITALIZED_TERMS,
        "capitalization": "initial-or-internal-uppercase-v1",
        "distinctive_token": "digit-or-internal-uppercase-or-single-uppercase-v1",
        "long_run_min_words": 4,
        "long_run_word_cap": 2,
        "phrase_word_cap": 3,
        "qualified_phrase_min_words": 2,
        "anchor_order": (
            "distinctive-desc",
            "word-count-desc",
            "character-count-desc",
        ),
        "anchor_cap": 1,
        "signal_min_chars": 4,
        "query_part_cap": 2,
        "fallback_signal_cap": 3,
        "phrase_quote": '"',
        "max_query_chars": 400,
    }),
    "ranking": MappingProxyType({
        "default_category": "general",
        "default_region": "unknown",
        "missing_created_utc": 0,
        "missing_rank": 10_000,
        "score_base": 100,
        "score_rank_cap": 20,
        "score_rank_weight": 4,
        "cross_feed_weight": 18,
        "cross_region_weight": 12,
        "cross_source_baseline_count": 1,
        "trend_match_weight": 30,
        "category_missing_rank": 20,
        "category_rank_weight": 2,
        "lineage_fields": (
            "external_id", "title", "body", "created_utc", "publisher",
            "metadata", "category", "region", "rank",
        ),
    }),
    "allocation": MappingProxyType({
        "topic_prefix": "trend_",
        "representation_order": "configured-category-order",
        "category_candidate_order": (
            "category-adjusted-score-desc",
            "created-utc-desc",
            "topic-key-asc",
            "query-asc",
        ),
        "remaining_candidate_order": (
            "score-desc", "created-utc-desc", "topic-key-asc", "query-asc",
        ),
        "fallback_category_order": ("rank-asc", "configured-category-order"),
        "search_request_grouping": "exact-query-with-sorted-label-union-v1",
        "search_request_order": "query-asc",
    }),
    "audit_record": MappingProxyType({
        "version": "content-addressed-full-input-and-decision-v1",
        "headline_fields": (
            "external_id", "title", "created_utc", "publisher",
            "category", "region", "rank",
        ),
        "headline_metadata_fields": ("publisher_domain",),
        "trend_fields": ("name", "tweet_count"),
        "selected_topic_fields": (
            "topic", "category", "query", "external_id", "title", "score",
        ),
    }),
})

_PROTOCOL_ID = re.compile(r"protocol_[0-9a-f]{24}")
_COLLECTOR_ID = re.compile(r"collector_[0-9a-f]{24}")
_IDENTITY_HISTORY_KEYS = {
    "protocol_id",
    "collector_semantics_id",
    "x_daily_static_slots",
    "x_daily_max_dynamic_slots",
    "reason",
}


def x_daily_static_slots(evidence: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    """Return the ordered non-search slots in one daily X collection cycle."""
    return tuple(
        ("xtrend", f"woeid:{int(woeid)}")
        for woeid in evidence["x_trend_woeids"]
    ) + (("trendnews", "ranked-global-discovery"),)


def x_daily_cycle_shape(
    evidence: Mapping[str, Any],
) -> tuple[tuple[tuple[str, str], ...], int]:
    """Return the immutable slot shape that identifies one daily X cycle."""
    return (
        x_daily_static_slots(evidence),
        int(evidence["max_x_search_requests_per_utc_day"]),
    )


def validated_collector_identity_history(
    entries: object,
    *,
    current_identity: tuple[str, str],
    current_x_daily_cycle_shape: tuple[tuple[tuple[str, str], ...], int],
) -> tuple[Mapping[str, Any], ...]:
    """Validate an append-only identity ledger whose last row is current."""
    if not isinstance(entries, list) or not entries:
        raise ValueError("collector identity history must be a non-empty list")

    seen: set[tuple[str, str]] = set()
    validated: list[Mapping[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) != _IDENTITY_HISTORY_KEYS:
            raise ValueError("collector identity history row has an invalid shape")
        protocol_id = entry["protocol_id"]
        collector_id = entry["collector_semantics_id"]
        static_slots = entry["x_daily_static_slots"]
        max_dynamic_slots = entry["x_daily_max_dynamic_slots"]
        reason = entry["reason"]
        if not isinstance(protocol_id, str) or _PROTOCOL_ID.fullmatch(protocol_id) is None:
            raise ValueError("collector history protocol ID is invalid")
        if not isinstance(collector_id, str) or _COLLECTOR_ID.fullmatch(collector_id) is None:
            raise ValueError("collector history semantics ID is invalid")
        if (
            not isinstance(static_slots, (list, tuple))
            or not static_slots
            or any(
                not isinstance(slot, (list, tuple))
                or len(slot) != 2
                or not all(isinstance(value, str) and value for value in slot)
                for slot in static_slots
            )
        ):
            raise ValueError("collector history X static slots are invalid")
        frozen_slots = tuple((slot[0], slot[1]) for slot in static_slots)
        if len(frozen_slots) != len(set(frozen_slots)):
            raise ValueError("collector history X static slots must be unique")
        if (
            isinstance(max_dynamic_slots, bool)
            or not isinstance(max_dynamic_slots, int)
            or max_dynamic_slots < 0
        ):
            raise ValueError("collector history X dynamic-slot cap is invalid")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("collector history row requires a reason")

        pair = (protocol_id, collector_id)
        if pair in seen:
            raise ValueError("collector identity history must be unique")
        seen.add(pair)
        validated.append(MappingProxyType({
            "protocol_id": protocol_id,
            "collector_semantics_id": collector_id,
            "x_daily_static_slots": frozen_slots,
            "x_daily_max_dynamic_slots": max_dynamic_slots,
            "reason": reason,
        }))

    current = validated[-1]
    current_shape = (
        current["x_daily_static_slots"],
        current["x_daily_max_dynamic_slots"],
    )
    if (
        (current["protocol_id"], current["collector_semantics_id"])
        != current_identity
        or current_shape != current_x_daily_cycle_shape
    ):
        raise ValueError(
            "collector identity history must append the derived current identity and shape"
        )
    return tuple(validated)


def collector_identity_history_manifest(
    entries: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Bind ordered identity pairs and frozen X shapes, excluding reason prose."""
    return [
        {
            "protocol_id": entry["protocol_id"],
            "collector_semantics_id": entry["collector_semantics_id"],
            "x_daily_cycle": {
                "expected_static_slots": entry["x_daily_static_slots"],
                "max_dynamic_slots": entry["x_daily_max_dynamic_slots"],
            },
        }
        for entry in entries
    ]


def discovery_policy_manifest() -> dict[str, Any]:
    """Return a detached JSON-ready projection of the frozen discovery policy."""
    def plain(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {key: plain(item) for key, item in value.items()}
        if isinstance(value, tuple):
            return [plain(item) for item in value]
        return value

    return plain(DISCOVERY_POLICY)


def collection_protocol_manifest(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Describe what is requested and admitted to the evidence stream."""
    query_cycle = evidence["query_cycle"]
    x_policy = evidence["x_formal_policy"]
    retry = query_cycle["globalnews_exception_retry_policy"]
    circuit_breaker = query_cycle["globalnews_cycle_circuit_breaker"]
    editorial = evidence["independent_editorial_policy"]
    return deepcopy({
        "schema_version": 1,
        "policy": COLLECTOR_POLICY,
        "scope": {
            "sources": evidence["allowed_sources"],
            "required_source_groups": evidence["required_source_groups"],
            "ticker_watchlist": False,
            "broad_editorial_news": True,
            "trend_derived_x_reaction": True,
        },
        "news": {
            "request": {
                "endpoint": media_sources._GLOBAL_NEWS_RSS,
                "lookback_days": evidence["lookback_days"],
                "queries": evidence["broad_news_queries"],
                "results_per_query": evidence["max_global_news_results_per_query"],
            },
            "schedule": {
                "interval_seconds": query_cycle["collector_interval_seconds"],
                "cycle_start_grace_seconds": query_cycle[
                    "cycle_start_grace_seconds"
                ],
                "require_every_slot": query_cycle[
                    "require_every_slot_in_cutoff_cycle"
                ],
            },
            "failure_policy": {
                "retry": {
                    "version": "provider-transient-only-v1",
                    "max_attempts_per_slot": retry[
                        "max_attempts_per_query_cycle"
                    ],
                    "delays_seconds": retry["delays_seconds"],
                    "retry_observed_empty": False,
                    "append_receipt_per_attempt": True,
                },
                "circuit_breaker": {
                    "version": "hourly-query-cycle-v1",
                    "failed_slots_before_open": circuit_breaker[
                        "failed_query_slots_before_open"
                    ],
                    "skip_remaining_slots": True,
                },
            },
            "admission": {
                "independent_editorial": {
                    "version": editorial["version"],
                    "require_exact_publisher_domain_pair": editorial[
                        "require_exact_normalized_publisher_domain_pair"
                    ],
                    "sources": editorial["sources"],
                },
                "company_authored_allowed": False,
                "company_authorship_classifier": {
                    "corporate_markers": media_sources._CORPORATE_SOURCE_MARKERS,
                    "editorial_markers": media_sources._EDITORIAL_SOURCE_MARKERS,
                    "first_party_headline_pattern": (
                        media_sources._FIRST_PARTY_HEADLINE.pattern
                    ),
                    "first_party_headline_flags": int(
                        media_sources._FIRST_PARTY_HEADLINE.flags
                    ),
                },
            },
        },
        "discovery": {
            "ranked_feeds": media_sources._GOOGLE_TOP_NEWS_RSS,
            "policy": discovery_policy_manifest(),
        },
        "x": {
            "adapter_policy": media_sources.global_x_adapter_policy_manifest(),
            "request": {
                "trend_woeids": evidence["x_trend_woeids"],
                "results_per_search": evidence["max_x_results_per_query"],
            },
            "schedule": {
                "interval_seconds": evidence["x_cycle_interval_seconds"],
                "recovery_stale_seconds": evidence[
                    "x_cycle_recovery_stale_seconds"
                ],
                "start_earliest_utc_seconds": evidence[
                    "x_cycle_start_earliest_utc_seconds"
                ],
                "start_minimum_remaining_utc_seconds": evidence[
                    "x_cycle_start_minimum_remaining_utc_seconds"
                ],
                "max_trend_requests_per_day": evidence[
                    "max_x_trend_requests_per_utc_day"
                ],
                "max_search_requests_per_day": evidence[
                    "max_x_search_requests_per_utc_day"
                ],
                "static_slots": x_daily_static_slots(evidence),
                "same_day_identity_precedence": (
                    COLLECTOR_COMPATIBILITY_PRECEDENCE
                ),
            },
            "admission": {
                key: x_policy[key]
                for key in (
                    "version",
                    "required_evidence_role",
                    "required_immutable_author_id",
                    "required_account_created_utc",
                    "required_automation_signals_complete",
                    "required_profile_screening_complete",
                    "known_verified_types",
                    "excluded_verified_types",
                    "organization_signal_flags",
                    "exclude_any_organization_signal",
                    "profile_screening_limitation",
                    "topic_labels",
                    "topic_assignment",
                    "max_automation_risk",
                    "required_author_metrics",
                    "required_engagement_metrics",
                    "engagement_weights",
                    "minimum_engagement_score",
                    "normalized_text_min_chars",
                    "normalized_text_max_chars",
                )
            } | {"text_normalization": "nfkc-public-reaction-tokens-v1"},
        },
    })


def collector_semantics_manifest(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Describe receipt, normalization, and stored wire-format compatibility."""
    query_cycle = evidence["query_cycle"]
    response = query_cycle["provider_response_validation"]
    lineage = evidence["fetch_receipt_evidence_lineage"]
    return deepcopy({
        "schema_version": 1,
        "normalization": {
            "provider_rows": "global-media-row-v1",
            "google_news_content_vintages": "google-news-content-vintage-v3",
            "x_expanded_authors": "x-expanded-author-metrics-v3-canonical-aliases",
            "maximum_response_bytes": media_sources._MAX_PROVIDER_RESPONSE_BYTES,
            "provider_responses": {
                "version": "strict-provider-response-v1",
                "transient_http_statuses": response[
                    "transient_http_statuses"
                ],
                "globalnews": "rss2-direct-channel-items-v1",
                "topnews": "complete-nonempty-ranked-feed-set-v1",
                "x_recent_search": "expanded-author-strict-v2-canonical-post-aliases",
                "x_trends": "nonempty-ranked-trends-v1",
            },
        },
        "receipts": {
            "fetch_lineage": {
                "version": lineage["version"],
                "formal_projection_providers": lineage[
                    "formal_projection_providers"
                ],
                "evidence_identity": "sha256-source-external-id-v1",
                "raw_content_identity": "sha256-normalized-provider-content-v1",
                "observation_time": "server-terminal-before-cutoff-v1",
            },
            "allowed_observed_empty_providers": query_cycle[
                "allowed_observed_empty_providers"
            ],
        },
        "wire_formats": {
            "collection_cycle_identity": 1,
            "collection_cycle_manifest": 2,
            "fetch_receipt_metadata": 1,
            "media_store_row": 1,
        },
    })
