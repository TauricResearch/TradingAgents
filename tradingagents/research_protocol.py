"""Frozen economic contract and identities for the global-event experiment.

The protocol identity changes only when the economic experiment changes.  Code,
container, dependency, and operational changes belong to the build identity so
ordinary reliability work cannot silently fork (or silently alter) a strategy.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_id(value: Any, *, prefix: str = "") -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"{prefix}{digest[:24]}"


GLOBAL_EVENT_V2_BROAD_NEWS_QUERIES: dict[str, list[str]] = {
    "rates": [
        "Federal Reserve interest rate decision when:7d",
        "inflation CPI outlook when:7d",
    ],
    "trade": [
        "global policy trade sanctions supply chains markets when:7d",
        "geopolitical conflict diplomacy global markets when:7d",
    ],
    "politics": [
        "global elections government policy political leadership markets when:7d",
        "US administration Congress courts policy global markets when:7d",
    ],
    "companies": [
        "corporate earnings OR mergers OR layoffs OR IPO when:7d",
    ],
    "technology": [
        "technology product launches AI research industry developments when:7d",
        "semiconductors data centers technology investment when:7d",
    ],
    "energy": ["oil prices OPEC energy commodities when:7d"],
}


# Formal news is fail-closed to exact publisher/domain pairs.  Collection keeps
# every Google News result for auditability, but only this deliberately small
# core can cross the forecast boundary. Sites that mix contributor, native-ad,
# partner, press-release, or sponsored pages on the same exact hostname are
# excluded because Google RSS does not expose enough article-level provenance
# to distinguish those pages. Aliases use the producer's normalized form.
GLOBAL_EVENT_V2_INDEPENDENT_EDITORIAL_SOURCES: dict[str, list[str]] = {
    "apnews.com": ["ap news", "associated press", "the associated press"],
    "bbc.co.uk": ["bbc", "bbc news"],
    "france24.com": ["france 24"],
    "news.sky.com": ["sky news"],
    "npr.org": ["npr"],
    "reuters.com": ["reuters"],
}


def global_news_query_slot_label(theme: str, query: str) -> str:
    """Return the stable internal association label for one frozen RSS slot."""
    return content_id(
        {"provider": "globalnews", "query_key": f"{theme}:{query}"},
        prefix="@QUERY_",
    ).upper()


# Keep the investable universe broad enough for a cross-section while limiting
# it to highly liquid US listings with representation from every major sector.
GLOBAL_EVENT_V2_PROTOCOL: dict[str, Any] = {
    "schema_version": 4,
    "name": "global-event-v2",
    "hypothesis": (
        "Point-in-time global-event and public-reaction evidence improves a "
        "cost-adjusted company portfolio over market-only deterministic baselines."
    ),
    "timing": {
        "decision_cutoff": "00:00:00Z after an XNYS decision session",
        "entry": "next XNYS scheduled regular-session open",
        "primary_mark": (
            "following XNYS provider regular-session daily adjusted open"
        ),
        "primary_horizon_sessions": 1,
    },
    "universe": {
        "selection": "frozen forward-only liquid US sector-balanced companies",
        "symbols": [
            "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JPM", "BRK-B",
            "XOM", "CVX", "LLY", "UNH", "WMT", "HD", "PG", "CAT", "GE",
            "NEE", "BA", "LIN",
        ],
        "sectors": {
            "AAPL": "technology", "MSFT": "technology", "NVDA": "technology",
            "AMZN": "consumer", "GOOGL": "communications", "META": "communications",
            "JPM": "financials", "BRK-B": "financials", "XOM": "energy",
            "CVX": "energy", "LLY": "healthcare", "UNH": "healthcare",
            "WMT": "consumer", "HD": "consumer", "PG": "consumer",
            "CAT": "industrials", "GE": "industrials", "NEE": "utilities",
            "BA": "industrials", "LIN": "materials",
        },
    },
    "evidence": {
        "lookback_days": 7,
        "allowed_sources": ["globalnews", "x"],
        "required_source_groups": [["globalnews"]],
        "broad_news_queries": GLOBAL_EVENT_V2_BROAD_NEWS_QUERIES,
        "max_global_news_results_per_query": 25,
        "query_cycle": {
            "collector_interval_seconds": 3600,
            "cycle_start_grace_seconds": 900,
            "require_every_slot_in_cutoff_cycle": True,
            "globalnews_exception_retry_policy": {
                "max_attempts_per_query_cycle": 3,
                "delays_seconds": [1.0, 4.0],
                "retry_on": "exception_only",
                "empty_response": "terminal_observed_empty_without_retry",
                "receipt_policy": "one_append_only_fetch_receipt_per_attempt",
            },
            "allowed_observed_empty_providers": [
                "polymarket", "trendnews", "x", "xtrend",
            ],
        },
        "expected_collector_semantics_id": "collector_fa2421d5a25636de4f035323",
        # The earlier collector used the same economic query/filter policy but
        # hashed now-retired release-rehearsal helpers into its build identity.
        # Keep that exact pair readable so already-captured evidence is not
        # discarded; no other protocol/collector combination is accepted.
        "compatible_collector_identities": [
            {
                "protocol_id": "protocol_485a418d45d44de9c0f45a94",
                "collector_semantics_id": "collector_cf5b90da1cd4d7db969389ee",
                "reason": (
                    "pre-content-vintage collector retained only when its exact "
                    "immutable receipt and per-item content lineage verifies"
                ),
            },
            {
                "protocol_id": "protocol_7382464b4f6a755d767f2699",
                "collector_semantics_id": "collector_aec83e329b85d5bf8654b2eb",
                "reason": "pre-simplification collector with equivalent evidence semantics",
            }
        ],
        "fetch_receipt_evidence_lineage": {
            "version": "atomic-provider-snapshot-content-v3",
            "persisted_item_lineage": "every stored media response item",
            "formal_projection_providers": ["globalnews", "trendnews", "x"],
            "google_news_content_vintages": (
                "retain the mutable Google cluster GUID as provider_external_id; "
                "store each exact normalized RSS rendering under a deterministic "
                "content-vintage external_id and select the latest successfully "
                "committed vintage available at the cutoff"
            ),
            "identical_response_duplicates": (
                "collapse an exact repeated content identity to one receipt item while "
                "retaining the union of its topic/ticker label associations; reject "
                "different raw content under one identity"
            ),
            "latest_vintage_observation": (
                "order repeated content vintages by the latest successful fetch receipt "
                "server_terminal_utc at the cutoff, with media observation time only "
                "for direct or legacy rows that lack receipt lineage"
            ),
            "evidence_id": (
                "sha256 content ID of source and stored content-vintage external_id"
            ),
            "raw_content_id": (
                "sha256 content ID of canonical provider snapshot content/provenance; "
                "receipt time and storage-derived labels are excluded"
            ),
            "observation_time_binding": (
                "PostgreSQL trigger-owned server_started_utc/server_terminal_utc authenticate "
                "the persistence window; formal cutoff eligibility uses server_terminal_utc, "
                "while worker-supplied request/receive times remain informational claims"
            ),
            "terminal_success_or_empty": (
                "atomically persist rows, per-item lineage, receipt, the sorted unique exact "
                "formally eligible {evidence_id,raw_content_id} objects, and an integer count "
                "equal to both the object-list and evidence-ID projection lengths"
            ),
            "coverage_binding": (
                "every selected globalnews candidate's exact evidence_id and raw_content_id "
                "must occur in its single deterministically assigned current-cycle receipt; "
                "a receipt with no assigned selected candidate need not contribute an item"
            ),
            "successful_zero_eligible_items": (
                "valid observed absence when the raw fetch succeeded and persisted []/0"
            ),
            "legacy_scalar_only_receipts": "ineligible",
            "collector_identity": (
                "receipt protocol_id and collector_semantics_id must exactly match "
                "the frozen protocol before lineage can bind"
            ),
        },
        "formal_input_policy_version": (
            "source-stratified-independent-editorial-v5-clean-x-ablation"
        ),
        "source_caps": {"globalnews": 80, "x": 20},
        "total_cap": 100,
        "history_candidate_limit": 4500,
        "history_candidate_buckets": {
            "version": "exact-slot-source-buckets-v1",
            "globalnews_per_query_slot": 400,
            "x": 500,
            "sentinel_rows": 1,
            "query_slot_order": "frozen-broad-news-query-order",
            "deduplicate_after_bucket_completeness": True,
            "multi_slot_assignment": (
                "lexicographically-smallest-sha256-source-nul-external-id-nul-slot"
            ),
        },
        "prompt_evidence_canonicalization": {
            "version": "bounded-whitelist-v1",
            "max_item_utf8_bytes": 1050,
            "max_title_utf8_bytes": 240,
            "max_text_utf8_bytes": 480,
            "max_publisher_utf8_bytes": 120,
            "max_domain_utf8_bytes": 128,
            "max_labels": 4,
            "max_label_utf8_bytes": 48,
            "bundle_max_external_id_utf8_bytes": 256,
            "bundle_max_title_utf8_bytes": 800,
            "bundle_max_text_utf8_bytes": 1200,
            "bundle_max_publisher_utf8_bytes": 160,
            "bundle_max_domain_utf8_bytes": 253,
            "bundle_max_article_url_utf8_bytes": 2048,
            "bundle_max_labels": 20,
            "bundle_max_label_utf8_bytes": 160,
            "metadata": "exact formal X fields only; empty for editorial news",
            "overflow_reduction_order": ["text", "title", "labels"],
        },
        "globalnews_cap_per_query_slot": 8,
        "require_selected_item_per_query_slot": False,
        "minimum_selected_globalnews_total": 1,
        "independent_editorial_policy": {
            "version": "strict-core-exact-publisher-host-pairs-v2",
            "require_exact_normalized_publisher_domain_pair": True,
            "sources": GLOBAL_EVENT_V2_INDEPENDENT_EDITORIAL_SOURCES,
        },
        "company_authored_material": "excluded at the forecast boundary",
        "without_public_reaction_excluded_sources": ["x"],
        "trendnews_role": (
            "collector-only provenance for selecting bounded X discussion topics; never "
            "forecast evidence, so public-reaction ablations differ only by X rows"
        ),
        "x_role": "unverified public reaction only",
        "x_unavailable_policy": (
            "retain the interval; use no X evidence and a neutral public-reaction target; "
            "reuse the champion bundle when canonical champion and no-reaction inputs match"
        ),
        "x_formal_availability": {
            "cycle_kind": "x-daily",
            "period_offset_utc_days": -1,
            "eligible_source": "x",
            "states": [
                "complete_with_eligible",
                "complete_zero_eligible",
                "incomplete",
                "missing",
            ],
            "unavailable_states": ["incomplete", "missing"],
            "unavailable_policy": "exclude_all_x_and_use_neutral_public_bundle",
            "zero_eligible_policy": "exclude_all_x_and_use_neutral_public_bundle",
            "cutoff_time_basis": "server_terminal_utc",
        },
        "x_cycle_interval_seconds": 86400,
        "x_cycle_recovery_stale_seconds": 900,
        "x_trend_woeids": [1, 23424977],
        "max_x_trend_requests_per_utc_day": 2,
        "max_x_search_requests_per_utc_day": 3,
        "max_x_results_per_query": 10,
        "x_billing_accounting": {
            "cost_units_meaning": (
                "one durable paid-request reservation, charged when the receipt starts; "
                "this is a request-budget unit and not a dollar amount"
            ),
            "billing_rate_snapshot": {
                "observed_utc_date": "2026-08-05",
                "official_source": "https://docs.x.com/x-api/getting-started/pricing",
                "usd_per_post_read": 0.005,
                "usd_per_user_read": 0.010,
                "usd_per_trend_read": 0.010,
                "daily_deduplication": "provider soft guarantee within UTC day",
            },
            "nominal_max_resources_per_day": {
                "trend_reads": 60,
                "post_reads": 30,
                "expanded_user_reads": 30,
            },
            "nominal_max_usd_per_day_before_deduplication": 1.05,
        },
        "x_formal_policy": {
            "version": "topic-diverse-public-reaction-v2-immutable-author",
            "required_evidence_role": "unverified_public_reaction",
            "required_immutable_author_id": True,
            "required_account_created_utc": True,
            "required_automation_signals_complete": True,
            "excluded_verified_types": ["business", "government"],
            "topic_labels": [
                "@TREND_WORLD", "@TREND_BUSINESS", "@TREND_TECHNOLOGY",
            ],
            "topic_assignment": (
                "lexicographically-smallest-sha256-source-nul-external-id-nul-topic"
            ),
            "max_automation_risk": 0.30,
            "required_author_metrics": [
                "followers_count", "following_count", "tweet_count",
            ],
            "required_engagement_metrics": [
                "like_count", "reply_count", "retweet_count", "quote_count",
            ],
            "engagement_weights": {
                "like_count": 1,
                "reply_count": 2,
                "retweet_count": 3,
                "quote_count": 3,
            },
            "minimum_engagement_score": 1,
            "normalized_text": (
                "NFKC-casefold; URLs become url; mentions become mention; retain "
                "unicode word and hashtag tokens; collapse whitespace"
            ),
            "normalized_text_min_chars": 12,
            "normalized_text_max_chars": 1000,
            "max_items_per_author": 2,
            "within_topic_order": [
                "engagement_score_desc", "automation_risk_asc",
                "published_utc_desc", "external_id_asc",
            ],
            "selection": "frozen-topic-order-round-robin",
        },
    },
    "forecast": {
        "provider": "openai",
        "requested_model": "gpt-5.4-mini",
        "allowed_returned_models": [
            "gpt-5.4-mini", "gpt-5.4-mini-2026-03-17",
        ],
        "endpoint_class": "native-provider-default",
        "backend_url": None,
        "reasoning_effort": "low",
        "temperature": None,
        "prompt_policy_version": (
            "global-event-structured-v5-bounded-explicit-excess-return"
        ),
        "structured_output_schema": (
            "daily-global-forecast-bounded-v4-coherent-grounded-onset"
        ),
        "invocation_policy": {
            "max_calls_per_decision": 3,
            "max_calls_per_utc_day": 3,
            "max_prompt_bytes": 160000,
            "max_completion_tokens": 8000,
            "timeout_seconds": 180,
            "sdk_max_retries": 0,
            "require_nonempty_response_id": True,
            "successful_result_binding": (
                "content ID of the exact persisted ForecastBundle payload"
            ),
        },
        "invocation_order_policy": {
            "version": "xnys-session-six-permutation-counterbalance-v1",
            "calendar": "XNYS",
            "calendar_range_start": "2020-01-02",
            "calendar_range_end": "2030-12-31",
            "epoch_session": "2020-01-02",
            "available_stages": [
                "champion",
                "without_public_reaction",
                "public_reaction_only",
            ],
            "permutation_cycle": [
                ["champion", "without_public_reaction", "public_reaction_only"],
                ["champion", "public_reaction_only", "without_public_reaction"],
                ["without_public_reaction", "champion", "public_reaction_only"],
                ["without_public_reaction", "public_reaction_only", "champion"],
                ["public_reaction_only", "champion", "without_public_reaction"],
                ["public_reaction_only", "without_public_reaction", "champion"],
            ],
            "assignment": (
                "zero-based XNYS session distance from epoch modulo six selects the "
                "full permutation; retain only stages whose distinct inputs require a call"
            ),
            "purpose": (
                "for a constant required-stage set, exactly counterbalance model/provider "
                "call-order effects in every six consecutive XNYS decision sessions; "
                "use no outcomes"
            ),
        },
        "decision_semantics_policy": "formal-decision-source-content-v2-indirect",
        "expected_decision_semantics_id": "semantics_b19c1be7bea3173a302b27e7",
        "unit": (
            "each asset's next-session-to-following-session provider daily adjusted-open "
            "total return minus SPY's return from the same captured provider vintage, "
            "in basis points"
        ),
        "min_bps": -500,
        "max_bps": 500,
        "abstention_allowed": True,
        "forecast_coherence": {
            "event_onset_utc": (
                "null or a timezone-aware UTC ISO-8601 instant no later than the "
                "decision cutoff"
            ),
            "abstain_true": (
                "expected_excess_return_bps=0, probability_positive=0.5, confidence=0; "
                "event citations may explain the abstention"
            ),
            "abstain_false": (
                "at least one event_id, confidence>0, nonzero expected excess return; "
                "positive edge requires probability_positive>0.5 and negative edge "
                "requires probability_positive<0.5"
            ),
        },
    },
    "portfolio": {
        "mode": "long-only",
        "gross_limit": 1.0,
        "max_weight": 0.10,
        "max_sector_weight": 0.30,
        "turnover_hurdle_bps": 10.0,
        "minimum_trade_weight": 0.005,
        "cash_allowed": True,
        "benchmark": "SPY",
        "trading_cost_bps": 5.0,
        "slippage_bps": 5.0,
        "return_accounting": {
            "strategy_interval_net_return": (
                "(1 - entry_turnover * (trading_cost_bps + slippage_bps) / 10000) "
                "* (1 + next-open-to-following-open holdings-and-cash return "
                "- interval borrow cost) - 1"
            ),
            "entry_turnover": (
                "absolute target-minus-prior-held weight change measured at the entry open"
            ),
            "first_target_entry_cost": "included",
            "endpoint_rebalance_cost": (
                "belongs to the next interval and is never shifted backward"
            ),
            "initialization_ledger_mark": "excluded from the analysis sample",
            "benchmark": (
                "same authenticated immutable SPY next-open-to-following-open return vector"
            ),
        },
        "price_capture": {
            "vendor_class": "research-only market-data adapter",
            "open_semantics": (
                "yfinance unadjusted and adjusted regular-session daily-bar Open as first "
                "persisted from the captured response; not an independently authenticated "
                "listing-exchange opening-auction print"
            ),
            "scheduled_delay_after_xnys_session_open_minutes": 15,
            "terminal_deadline": "strictly before the next XNYS scheduled session open",
            "late_backfill": (
                "forbidden; a missing capture after the terminal deadline is an integrity "
                "failure that blocks confirmatory readout"
            ),
            "receipt": (
                "append-only exact session, server persistence time, worker-claimed vendor "
                "request/response times, vendor, raw daily open, adjusted daily open, cash "
                "dividend, split ratio, and content-addressed same-vintage return component"
            ),
            "correction_policy": (
                "later vendor corrections never mutate a receipt or return vector"
            ),
        },
        "corporate_actions": {
            "ordinary_splits_and_cash_distributions": (
                "use both endpoint adjusted opens from one captured vendor vintage and require "
                "the current endpoint to agree with the same-session raw/action receipt"
            ),
            "symbol_change_delisting_merger_or_missing_provider_daily_open": (
                "never replace the frozen constituent, fill forward, or impute zero; absent a "
                "frozen adapter capable of capturing the exact provider daily-open total-return "
                "component "
                "before the capture deadline, append an integrity failure and block readout"
            ),
            "survivorship_repair": "forbidden",
        },
        "cash": {
            "instrument": "USD",
            "annual_yield_proxy": "^IRX 13-week Treasury bill yield index close",
            "observation_policy": (
                "latest session close strictly before the held open-to-open interval"
            ),
            "accrual": "simple annual yield percent times calendar days divided by 360",
        },
    },
    "strategies": [
        "global_events_champion",
        "global_events_without_public_reaction",
        "public_reaction_only",
        "market_only",
        "equal_weight",
        "momentum",
        "stale_events_negative_control",
        "shuffled_events_negative_control",
    ],
    "review_gates": {
        "materialization": {
            "automatic_clock": (
                "after the champion mark and all eight synchronized shadow marks, "
                "called after every committed mark during catch-up"
            ),
            "exact_completed_intervals": [20, 60, 126, 252],
            "late_or_skipped_gate": "fail closed; never backfill after a later interval",
            "storage": (
                "one content-addressed report artifact and one append-only exact-gate "
                "run label; repeat materialization is identity-idempotent"
            ),
            "routine_output": "report and artifact IDs only; outcomes withheld",
            "explicit_view": (
                "only an already-materialized exact report; every outcome-bearing view "
                "appends a separate formal_outcome_access receipt before artifact read"
            ),
            "analysis_parameters": "none caller-tunable",
        },
        "20": {
            "scope": "operations-only",
            "materialize_when_completed_intervals_equals": 20,
            "report": {
                "assignment_counts": "target-applied and carry-forward disposition counts",
                "attempt_counts": (
                    "started, failed, bundle-resolved, and unresolved terminal-state counts"
                ),
                "mark_completeness": (
                    "exactly 21 champion marks and 21 marks for each frozen strategy"
                ),
                "receipt_counts": (
                    "price receipt, decision bundle, and LLM reservation/result "
                    "operational counts only"
                ),
            },
            "data_access_boundary": (
                "must never select or read forecast payloads, target weights, mark NAV, "
                "period returns, benchmark returns, or authenticated return vectors"
            ),
            "outcome_access_receipt": "forbidden because no outcome may be read",
            "forbidden": "all forecasts, weights, NAV, returns, and efficacy statistics",
            "efficacy_action": "forbidden",
        },
        "60": {
            "scope": "data-and-calibration-only",
            "materialize_when_completed_intervals_equals": 60,
            "access_order": "commit formal_outcome_access before reading any outcome",
            "cohort": (
                "all asset forecasts from target_applied assignments among exactly the "
                "first 60 immutable intervals; carry-forward intervals contribute no "
                "forecast observations, are not imputed, and their outcome vectors are "
                "not read by this gate"
            ),
            "realized_asset_excess_return": (
                "authenticated adjusted-open asset return minus SPY return from the same "
                "immutable return vector, multiplied by 10000 basis points"
            ),
            "calibration": {
                "brier_score": (
                    "arithmetic mean of (probability_positive - 1[realized excess > 0])^2 "
                    "over every cohort asset forecast"
                ),
                "expected_excess_mae_bps": (
                    "arithmetic mean absolute expected-minus-realized excess basis points "
                    "over every cohort asset forecast"
                ),
                "probability_bins": [
                    "[0.0,0.2)", "[0.2,0.4)", "[0.4,0.6)",
                    "[0.6,0.8)", "[0.8,1.0]",
                ],
                "bin_fields": [
                    "count", "mean_forecast_probability", "realized_positive_rate",
                ],
                "empty_sample_or_bin": "count zero and numeric summaries null",
            },
            "integrity": (
                "offline replay every included decision; require exact universe, neutral "
                "abstentions, coherent grounded active forecasts, valid event-to-evidence "
                "citations, and authenticated same-vector returns"
            ),
            "balance": (
                "counts of selected champion evidence occurrences across successful daily "
                "bundles by frozen source, global-news query slot, and X topic; repeated "
                "evidence on different days counts once per daily input occurrence"
            ),
            "forbidden": "strategy ranking, return differences, promotion, stopping, or extension",
            "efficacy_action": "forbidden",
        },
        "126": {
            "scope": "locked-descriptive-nonconclusive",
            "materialize_when_completed_intervals_equals": 126,
            "access_order": "no outcome-access receipt because no outcome may be read",
            "operational_integrity_only": {
                "registered_strategy_paths": "aggregate count only",
                "intervals_per_path": 126,
                "marks_per_path_including_initialization": 127,
                "assignment_and_bundle_counts": "aggregate counts only",
                "strategy_identities_withheld": True,
                "efficacy_statistics_withheld": True,
            },
            "artifact_type": "formal_interim_operational_integrity_report",
            "report_type": "global-event-v2-blinded-operational-integrity-interim",
            "label": "formal-review-126-descriptive",
            "forbidden": (
                "named strategies, target weights, NAV, return vectors, per-path returns or "
                "descriptives, benchmark efficacy, tests, ranks, promotion, model selection, "
                "protocol tuning, stopping, or extension"
            ),
            "efficacy_action": "forbidden",
        },
        "252": {
            "scope": "sole-confirmatory-readout",
            "allowed": "the frozen primary, robustness, multiplicity, and promotion gates",
            "efficacy_action": "human review only; live capital is never automatic",
        },
    },
    "analysis": {
        "version": "global-event-v2-confirmatory-v1",
        "trial_clock": {
            "inception": "first atomically persisted decision under this protocol",
            "holding_intervals": 252,
            "exclude_initialization_mark": True,
            "consecutive_xnys_intervals": True,
            "efficacy_stopping_or_extension": "forbidden",
            "confirmatory_retest_after_failure": "forbidden",
            "interim_review_schedule_sessions": [20, 60, 126, 252],
            "all_outcome_access_must_be_immutably_labeled": True,
        },
        "primary_estimand": {
            "paired_difference": "global_events_champion minus market_only net period return",
            "aggregation": "arithmetic mean across every scheduled holding interval",
            "alternative": "greater",
            "minimum_effect_bps_per_session": 1.0,
        },
        "primary_test": {
            "null": "mean paired difference <= 0",
            "alternative": "mean paired difference > 0",
            "standard_error": "Newey-West Bartlett HAC",
            "lags": 5,
            "one_sided_alpha": 0.025,
            "pass_rule": "97.5% one-sided lower confidence bound > 0",
            "winsorization_or_outlier_deletion": "forbidden",
        },
        "bootstrap_robustness": {
            "method": "moving-block bootstrap of paired mean",
            "block_length": 5,
            "trials": 10000,
            "seed": 1729,
            "lower_quantile": 0.025,
            "pass_rule": "lower quantile > 0",
        },
        "missingness": {
            "failed_decision": (
                "intent-to-treat carry-forward of every strategy's prior target; "
                "scheduled interval remains in the primary sample"
            ),
            "x_unavailable": "retain interval under the frozen evidence fallback policy",
            "missing_mark": (
                "retry from the authenticated immutable return vector; no zero imputation; "
                "unresolved or asymmetric marks block readout"
            ),
            "minimum_successful_decision_sets": 240,
            "required_synchronized_marks": 252,
        },
        "multiplicity": {
            "confirmatory_family": ["champion_vs_market_only"],
            "confirmatory_method": "single primary hypothesis",
            "secondary_family": [
                "champion_vs_without_public_reaction",
                "champion_vs_public_reaction_only",
                "champion_vs_equal_weight",
                "champion_vs_momentum",
                "champion_vs_stale_events_negative_control",
                "champion_vs_shuffled_events_negative_control",
                "champion_vs_spy",
            ],
            "secondary_method": "Holm one-sided familywise error control",
            "secondary_familywise_alpha": 0.05,
            "secondary_cannot_rescue_primary": True,
        },
        "selection_bias_diagnostics": {
            "applicability": (
                "the champion is frozen before this prospective outcome sample; the eight "
                "concurrent forward arms are estimands and controls, not a development-search "
                "universe, so they must never be presented as the trial count for DSR or PBO"
            ),
            "development_selection_audit": {
                "optional": True,
                "must_precede_first_formal_trial_activity": True,
                "content_addressed": True,
                "candidate_ids": "complete unique set of every development variant evaluated",
                "deflated_sharpe_inputs": (
                    "one frozen finite historical Sharpe for every candidate from an identical "
                    "development sample; otherwise DSR status is not_identified"
                ),
                "pbo_inputs": (
                    "one aligned historical return path for every candidate over the identical "
                    "observations; otherwise PBO status is not_identified"
                ),
                "missing_or_incomplete": (
                    "report not_identified, never substitute the registered forward arms or an "
                    "invented effective trial count"
                ),
            },
            "deflated_sharpe_ratio": {
                "candidate_source": "complete pre-outcome development selection audit only",
                "periods_per_year": 252,
            },
            "cscv_probability_backtest_overfit": {
                "partitions": 10,
                "candidate_source": (
                    "complete aligned pre-outcome development return paths only"
                ),
            },
            "confirmatory_or_promotion_gate": False,
        },
        "drawdown": {
            "equity_curve": (
                "compound every decision-aligned net interval return from 1.0 in frozen "
                "session order; initialization ledger mark is excluded"
            ),
            "drawdown": "equity divided by prior running peak minus 1",
            "maximum_drawdown": "minimum drawdown over all 252 scheduled intervals",
            "disadvantage_vs_market_only_percentage_points": (
                "absolute champion maximum-drawdown magnitude minus absolute market-only "
                "maximum-drawdown magnitude, multiplied by 100"
            ),
        },
        "change_control": {
            "integrity_or_leakage_breach": (
                "invalidate and permanently label the confirmatory run; never repair history"
            ),
            "behavior_preserving_operational_fix": (
                "allowed only with an immutable incident label, unchanged decision semantic "
                "identity, and successful before/after offline replay; trial clock does not reset"
            ),
            "semantic_change": (
                "any evidence, prompt, model, validation, allocator, universe, timing, cost, "
                "marking, analysis, or promotion change requires a new protocol and run"
            ),
            "outcome_informed_variant": (
                "register as a separate exploratory descendant with outcome_accessed=true; "
                "it can never be treated as this confirmatory trial"
            ),
        },
    },
    "promotion": {
        "live_capital": "never automatic",
        "requires": {
            "operations_integrity_restore_alert_replay": True,
            "verifier_and_mark_vector_completeness": 1.0,
            "minimum_decision_availability": 240,
            "primary_hac_bootstrap_and_one_bp_effect_gates": True,
            "without_public_reaction": {
                "holm_adjusted_p_below": 0.05,
                "minimum_effect_bps_per_session": 0.25,
            },
            "holm_significant_positive_vs": [
                "equal_weight", "momentum", "stale_events_negative_control",
                "shuffled_events_negative_control",
            ],
            "positive_point_estimate_vs": ["public_reaction_only", "SPY"],
            "selection_bias_diagnostics_applicability_review": True,
            "max_drawdown_disadvantage_vs_market_only_percentage_points_at_most": 5.0,
            "attribution_concentration_review": True,
            "explicit_human_approval": True,
            "approval_creates_separate_tiny_cap_shadow_or_live_protocol": True,
        },
    },
}

GLOBAL_EVENT_V2_PROTOCOL_ID = content_id(GLOBAL_EVENT_V2_PROTOCOL, prefix="protocol_")


_FLY_DEPLOYMENT_IMAGE_REF = re.compile(
    r"registry\.fly\.io/(?P<app>[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)"
    r":deployment-(?P<deployment>[0-9A-HJKMNP-TV-Z]{26})"
)
_EXPLICIT_BUILD_MATERIAL = re.compile(
    r"(?:sha256:[0-9a-f]{64}|[0-9a-f]{40}|[0-9a-f]{64}|build_[0-9a-f]{24})"
)


def runtime_build_manifest(env: Mapping[str, str] | None = None) -> dict | None:
    """Authenticate production build material without a caller-selected override.

    Fly's runtime-provided deployment image reference wins whenever any Fly
    identity is present. A generic ``TRADINGAGENTS_BUILD_ID`` can therefore
    never mask the platform image actually running the worker.
    """
    values = os.environ if env is None else env
    image_ref = (values.get("FLY_IMAGE_REF") or "").strip()
    app_name = (values.get("FLY_APP_NAME") or "").strip()
    fly_present = bool(image_ref or app_name or (values.get("FLY_MACHINE_ID") or "").strip())
    if fly_present:
        match = _FLY_DEPLOYMENT_IMAGE_REF.fullmatch(image_ref)
        if match is None or not app_name or match.group("app") != app_name:
            raise ValueError(
                "Fly build identity requires the runtime deployment image for FLY_APP_NAME"
            )
        return {
            "schema_version": 1,
            "platform": "fly",
            "app_name": app_name,
            "image_ref": image_ref,
            "deployment_id": match.group("deployment"),
        }

    explicit = (values.get("TRADINGAGENTS_BUILD_ID") or "").strip()
    revision = (values.get("GIT_REVISION") or "").strip().lower()
    material = explicit or revision
    if material:
        if _EXPLICIT_BUILD_MATERIAL.fullmatch(material) is None:
            raise ValueError(
                "explicit build identity must be a full digest, revision, or content ID"
            )
        return {
            "schema_version": 1,
            "platform": "explicit",
            "material": material,
        }
    return None


def build_identity() -> str:
    """Return an operational identity without changing protocol semantics."""
    runtime_manifest = runtime_build_manifest()
    if runtime_manifest is not None:
        return content_id(runtime_manifest, prefix="build_")
    try:
        package_version = version("tradingagents")
    except PackageNotFoundError:
        package_version = "source"
    # In a source checkout, hash the complete installed package plus dependency
    # declarations. This is a fallback for local reproducibility; production
    # should inject an immutable Git/image ID.
    package = Path(__file__).resolve().parent
    files = []
    for path in sorted(package.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        files.append({
            "path": path.relative_to(package).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    project = package.parent
    for name in ("pyproject.toml", "uv.lock"):
        path = project / name
        if path.exists():
            files.append({
                "path": name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
    return content_id({"version": package_version, "files": files}, prefix="build_")


def model_identity(provider: str, requested_model: str, response_metadata: dict | None = None) -> str:
    metadata = response_metadata or {}
    returned = (
        metadata.get("model_name")
        or metadata.get("model")
        or metadata.get("model_id")
        or requested_model
    )
    return content_id(
        {"provider": provider, "requested_model": requested_model, "returned_model": returned},
        prefix="model_",
    )
