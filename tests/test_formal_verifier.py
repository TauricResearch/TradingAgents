"""Self-contained, network-free replay of formal paper decisions."""

from __future__ import annotations

import json
import math
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import exchange_calendars as xcals
import pytest

from tradingagents.dataflows.media_store import collection_cycle_spec
from tradingagents.formal_experiment import (
    _bind_x_availability_to_selection,
    _finalized_x_cycle_availability,
    _shuffle_forecasts,
    _target,
    formal_decision_semantics,
    formal_trial_registration,
)
from tradingagents.formal_readout import FormalReadoutIntegrityError
from tradingagents.formal_verifier import (
    _COLLECTOR_SEMANTIC_COMPONENTS,
    _DECISION_SEMANTIC_COMPONENTS,
    FormalVerificationError,
    _validate_evidence_selection_manifest,
    _validate_invocation_receipts,
    verify_formal,
)
from tradingagents.global_research import (
    build_forecast_prompt,
    evidence_selection_manifest,
    formal_evidence_policy_manifest,
    formal_globalnews_selection_coverage,
    partition_formal_evidence,
    prepare_evidence,
)
from tradingagents.outcome_semantics import (
    OutcomeSemanticsResolutionError,
    outcome_semantics_id,
)
from tradingagents.paper_trading import PaperStore, decision_window
from tradingagents.poller import collector_semantics_manifest
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
    content_id,
    global_news_query_slot_label,
    model_identity,
)

OUTCOME_SEMANTICS_ID = outcome_semantics_id()


def _forecast_rows(universe: list[str], *, event_ids: list[str] | None = None) -> list[dict]:
    rows = []
    for index, ticker in enumerate(universe):
        edge = float(((index % 5) - 2) * 40)
        rows.append(
            {
                "ticker": ticker,
                "expected_excess_return_bps": edge,
                "probability_positive": 0.6 if edge > 0 else 0.4 if edge < 0 else 0.5,
                "confidence": 0.8,
                "abstain": False,
                "event_ids": list(event_ids or []),
                "rationale": "immutable model fixture",
            }
        )
    return rows


def _market_snapshots(universe: list[str], decision_date: str) -> dict[str, list[dict]]:
    snapshots = {}
    for index, ticker in enumerate(universe):
        base = 100.0 + index
        direction = 1.0 if index % 2 == 0 else -1.0
        snapshots[ticker] = [
            {"date": "2026-07-31", "open": base - 0.2, "close": base},
            {
                "date": "2026-08-03",
                "open": base,
                "close": base * (1.0 + direction * 0.008),
            },
            {
                "date": decision_date,
                "open": base * (1.0 + direction * 0.006),
                "close": base * (1.0 + direction * 0.003),
            },
        ]
    return snapshots


def _market_rows(
    snapshots: dict[str, list[dict]], universe: list[str]
) -> tuple[list[dict], list[dict]]:
    inverse_volatility = []
    momentum = []
    for ticker in universe:
        closes = [float(row["close"]) for row in snapshots[ticker]]
        returns = [closes[index] / closes[index - 1] - 1.0 for index in range(1, len(closes))]
        mean = sum(returns) / len(returns)
        volatility = math.sqrt(sum((value - mean) ** 2 for value in returns) / (len(returns) - 1))
        inverse_edge = min(500.0, 5.0 / volatility) if volatility > 0 else 0.0
        momentum_edge = max(-500.0, min(500.0, (closes[-1] / closes[0] - 1.0) * 10_000))
        for target, edge, rationale in (
            (
                inverse_volatility,
                inverse_edge,
                "point-in-time inverse-volatility baseline",
            ),
            (momentum, momentum_edge, "point-in-time 20-session momentum baseline"),
        ):
            target.append(
                {
                    "ticker": ticker,
                    "expected_excess_return_bps": edge,
                    "probability_positive": 0.6 if edge > 0 else 0.4 if edge < 0 else 0.5,
                    "confidence": 1.0,
                    "abstain": edge == 0,
                    "event_ids": [],
                    "rationale": rationale,
                }
            )
    return inverse_volatility, momentum


def _equal_weight_rows(universe: list[str]) -> list[dict]:
    return [
        {
            "ticker": ticker,
            "expected_excess_return_bps": 100.0,
            "probability_positive": 0.6,
            "confidence": 1.0,
            "abstain": False,
            "event_ids": [],
            "rationale": "equal-weight baseline",
        }
        for ticker in universe
    ]


def _neutral_public_rows(universe: list[str]) -> list[dict]:
    return [
        {
            "ticker": ticker,
            "expected_excess_return_bps": 0.0,
            "probability_positive": 0.5,
            "confidence": 0.0,
            "abstain": True,
            "event_ids": [],
            "rationale": "no eligible public-reaction evidence",
        }
        for ticker in universe
    ]


def _fixture_invocation_stage_order(decision_date: str, stages: list[str]) -> list[str]:
    policy = GLOBAL_EVENT_V2_PROTOCOL["forecast"]["invocation_order_policy"]
    calendar = xcals.get_calendar(
        policy["calendar"],
        start=policy["calendar_range_start"],
        end=policy["calendar_range_end"],
    )
    offset = calendar.sessions_distance(policy["epoch_session"], decision_date) - 1
    scheduled = policy["permutation_cycle"][offset % len(policy["permutation_cycle"])]
    required = set(stages)
    return [stage for stage in scheduled if stage in required]


def _missing_x_availability(cutoff: datetime) -> dict:
    period_key = (cutoff.date() - timedelta(days=1)).isoformat()
    cycle_spec = collection_cycle_spec(
        cycle_kind="x-daily",
        period_key=period_key,
        protocol_id=GLOBAL_EVENT_V2_PROTOCOL_ID,
        collector_semantics_id=GLOBAL_EVENT_V2_PROTOCOL["evidence"][
            "expected_collector_semantics_id"
        ],
        expected_static_slots=[
            ("xtrend", f"woeid:{int(woeid)}")
            for woeid in GLOBAL_EVENT_V2_PROTOCOL["evidence"]["x_trend_woeids"]
        ] + [("trendnews", "ranked-global-discovery")],
        max_dynamic_slots=int(
            GLOBAL_EVENT_V2_PROTOCOL["evidence"][
                "max_x_search_requests_per_utc_day"
            ]
        ),
    )
    return _finalized_x_cycle_availability({
        "schema_version": 1,
        "policy": dict(
            GLOBAL_EVENT_V2_PROTOCOL["evidence"]["x_formal_availability"]
        ),
        "period_key": period_key,
        "expected_collection_cycle_id": cycle_spec["collection_cycle_id"],
        "state": "missing",
        "collection_cycle_id": None,
        "manifest_id": None,
        "cycle_manifest": None,
        "collector_semantics_id": GLOBAL_EVENT_V2_PROTOCOL["evidence"][
            "expected_collector_semantics_id"
        ],
        "collector_build_id": None,
        "server_started_utc": None,
        "server_terminal_utc": None,
        "eligible_lineage": [],
    })


def _fixture_selection_manifest(rows: list[dict], cutoff: datetime) -> dict:
    manifest = evidence_selection_manifest(rows, as_of_utc=cutoff.timestamp())
    return _bind_x_availability_to_selection(
        manifest, _missing_x_availability(cutoff)
    )


def _invocation_receipt_pair(
    *,
    run_id: str,
    decision_date: str,
    ordinal: int,
    stage: str,
    bundle: dict,
    created_at: datetime,
    daily_count: int | None = None,
) -> list[dict]:
    invocation = GLOBAL_EVENT_V2_PROTOCOL["forecast"]["invocation_policy"]
    identity = {
        "scope": "formal-global-v2",
        "run_id": run_id,
        "decision_date": decision_date,
        "ordinal": ordinal,
        "stage": stage,
        "provider": bundle["provider"],
        "requested_model": bundle["requested_model"],
        "input_bundle_id": bundle["input_bundle_id"],
    }
    invocation_id = content_id(identity, prefix="invocation_")
    decision_key = f"llm:formal-global-v2:decision:{run_id}:{decision_date}"
    utc_day = created_at.date().isoformat()
    day_key = (
        f"llm:formal-global-v2:protocol:{GLOBAL_EVENT_V2_PROTOCOL_ID}:"
        f"utc-day:{utc_day}"
    )
    reservation = {
        "schema_version": 2,
        "invocation_id": invocation_id,
        **identity,
        "prompt_id": content_id({"prompt": bundle["prompt"]}, prefix="prompt_"),
        "prompt_bytes": len(bundle["prompt"].encode("utf-8")),
        "max_prompt_bytes": invocation["max_prompt_bytes"],
        "max_completion_tokens": invocation["max_completion_tokens"],
        "max_calls_per_decision": invocation["max_calls_per_decision"],
        "max_calls_per_utc_day": invocation["max_calls_per_utc_day"],
        "decision_counter_key": decision_key,
        "daily_counter_key": day_key,
        "utc_day": utc_day,
        "reserved_utc": created_at.isoformat(),
        "reservation_counts": {
            decision_key: float(ordinal),
            day_key: float(daily_count if daily_count is not None else ordinal),
        },
    }
    reservation_artifact_id = content_id(
        {
            "artifact_type": "llm_invocation_reserved",
            "content": reservation,
        },
        prefix="artifact_",
    )
    returned_model = bundle["response_metadata"]["model_name"]
    result = {
        "schema_version": 2,
        "invocation_id": invocation_id,
        **identity,
        "reservation_artifact_id": reservation_artifact_id,
        "status": "success",
        "returned_model": f"{bundle['provider']}:{returned_model}",
        "model_id": bundle["model_id"],
        "response_id": bundle["response_id"],
        "forecast_bundle_id": content_id(bundle, prefix="bundle_"),
        "usage_metadata": deepcopy(bundle["usage_metadata"]),
        "completed_utc": created_at.isoformat(),
        "elapsed_ms": 0,
    }
    created_utc = created_at.timestamp()
    return [
        {
            "artifact_type": "llm_invocation_reserved",
            "content": reservation,
            "created_utc": created_utc,
        },
        {
            "artifact_type": "llm_invocation_result",
            "content": result,
            "created_utc": created_utc,
        },
    ]


def _record_replayable_decision(
    store: PaperStore,
    *,
    artifact_mutator=None,
    receipt_mutator=None,
    bypass_receipt_validation: bool | None = None,
    artifact_id_override: str | None = None,
    absent_slot_index: int | None = None,
) -> str:
    run_id = "formal-replay"
    decision_date = "2026-08-04"
    cutoff, next_open, entry_date = decision_window(decision_date)
    created_at = datetime(2026, 8, 5, 1, tzinfo=timezone.utc)
    universe = list(GLOBAL_EVENT_V2_PROTOCOL["universe"]["symbols"])
    strategies = list(GLOBAL_EVENT_V2_PROTOCOL["strategies"])
    champion_rows = _forecast_rows(universe, event_ids=["event_01"])
    without_public_rows = deepcopy(champion_rows)
    public_rows = _neutral_public_rows(universe)
    stale_rows = [
        {**row, "rationale": "no prior formal forecast available"}
        for row in _neutral_public_rows(universe)
    ]
    shuffled_rows = _shuffle_forecasts(champion_rows)
    snapshots = _market_snapshots(universe, decision_date)
    market_rows, momentum_rows = _market_rows(snapshots, universe)
    equal_rows = _equal_weight_rows(universe)
    strategy_rows = {
        "global_events_champion": champion_rows,
        "global_events_without_public_reaction": without_public_rows,
        "public_reaction_only": public_rows,
        "market_only": market_rows,
        "equal_weight": equal_rows,
        "momentum": momentum_rows,
        "stale_events_negative_control": stale_rows,
        "shuffled_events_negative_control": shuffled_rows,
    }
    prior = dict.fromkeys(universe, 0.0)

    query_parts = [
        (theme, query)
        for theme, queries in GLOBAL_EVENT_V2_PROTOCOL["evidence"]["broad_news_queries"].items()
        for query in queries
    ]
    candidate_rows = []
    for index, (theme, query) in enumerate(query_parts):
        if index == absent_slot_index:
            continue
        candidate_rows.append(
            {
                "source": "globalnews",
                "external_id": f"fixture-{index}",
                "ticker": f"@{theme.upper()}",
                "labels": [
                    f"@{theme.upper()}",
                    global_news_query_slot_label(theme, query),
                ],
                "created_utc": cutoff.timestamp() - 7_200 - index * 60,
                "fetched_utc": cutoff.timestamp() - 3_600 - index * 30,
                "author": "Reuters",
                "title": f"Global development {index}",
                "body": f"A consequential global development occurred {index}.",
                "metadata": {
                    "article_url": f"https://news.google.com/articles/fixture-{index}",
                    "publisher_domain": "reuters.com",
                },
            }
        )
    evidence = prepare_evidence(candidate_rows)
    x_cycle_availability = _missing_x_availability(cutoff)
    selection_manifest = _fixture_selection_manifest(candidate_rows, cutoff)
    selection_coverage = formal_globalnews_selection_coverage(selection_manifest)
    input_bundle_id = content_id(
        {
            "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
            "decision_date": decision_date,
            "universe": universe,
            "evidence": evidence,
        },
        prefix="input_",
    )
    requested_model = GLOBAL_EVENT_V2_PROTOCOL["forecast"]["requested_model"]
    response_metadata = {"model_name": requested_model}
    llm_model_id = model_identity("openai", requested_model, response_metadata)
    events = [
        {
            "event_id": "event_01",
            "summary": "A consequential global development occurred.",
            "onset_utc": None,
            "geographies": ["global"],
            "entities": [],
            "transmission_mechanism": "Broad changes in expected cash flows.",
            "novelty": 0.8,
            "uncertainty": 0.4,
            "evidence_ids": [row["evidence_id"] for row in evidence],
            "independent_source_count": 1,
            "source_types": ["globalnews"],
            "public_reaction": None,
        }
    ]
    parsed_forecast = {
        "horizon": "next-open-to-open",
        "market_regime": "uncertain",
        "events": events,
        "forecasts": deepcopy(champion_rows),
    }
    champion = {
        "input_bundle_id": input_bundle_id,
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "model_id": llm_model_id,
        "provider": "openai",
        "requested_model": requested_model,
        "response_id": "response-fixture",
        "response_metadata": response_metadata,
        "usage_metadata": {"input_tokens": 10, "output_tokens": 10},
        "raw_response": {
            "id": "response-fixture",
            "response_metadata": response_metadata,
        },
        "prompt": build_forecast_prompt(
            decision_date=decision_date, evidence=evidence, universe=universe
        ),
        "evidence": evidence,
        "forecast": parsed_forecast,
    }
    without_public = deepcopy(champion)
    collector_interval_seconds = 3_600
    collector_cycle_grace_seconds = 900
    cycle_lower_bound = (
        cutoff.timestamp() - collector_interval_seconds - collector_cycle_grace_seconds
    )
    receipt_started = cycle_lower_bound + 60
    coverage = {
        "complete": True,
        "cutoff_utc": cutoff.timestamp(),
        "collector_interval_seconds": collector_interval_seconds,
        "cycle_start_grace_seconds": collector_cycle_grace_seconds,
        "cycle_lower_bound_utc": cycle_lower_bound,
        "missing_source_groups": [],
        "missing_query_slots": [],
        "query_slots": [],
        "receipt_lineage_binding_version": "assigned-manifest-content-v2",
        "receipt_lineage_binding_complete": True,
        "expected_collector_semantics_id": GLOBAL_EVENT_V2_PROTOCOL["evidence"][
            "expected_collector_semantics_id"
        ],
    }
    evidence_query_slots = [["globalnews", f"{theme}:{query}"] for theme, query in query_parts]
    for index, (_, query_key) in enumerate(evidence_query_slots):
        started = receipt_started + index
        eligible_ids = selection_manifest["eligible_evidence_ids_by_query_slot"][query_key]
        selected_ids = selection_manifest["selected_evidence_ids_by_query_slot"][query_key]
        receipt_ids = list(selected_ids)
        eligible_lineage = sorted(
            [
                {
                    "evidence_id": candidate["evidence_id"],
                    "raw_content_id": candidate["raw_content_id"],
                }
                for candidate in selection_manifest["candidates"]
                if candidate["source"] == "globalnews"
                and candidate["query_slot"] == query_key
                and candidate["evidence_id"] in receipt_ids
            ],
            key=lambda item: (item["evidence_id"], item["raw_content_id"]),
        )
        coverage["query_slots"].append(
            {
                "provider": "globalnews",
                "query_key": query_key,
                "run": {
                    "provider": "globalnews",
                    "query_key": query_key,
                    "status": "success",
                    "started_utc": started,
                    "received_utc": started + 1,
                    "completed_utc": started + 2,
                    "server_started_utc": started,
                    "server_terminal_utc": started + 2,
                    "collector_build_id": "build_000000000000000000000001",
                    "item_count": 1,
                    "inserted_count": 1,
                    "error": None,
                    "cost_units": 0.0,
                    "cursor_after": None,
                    "metadata_json": json.dumps(
                        {
                            "labels": [],
                            "kind": "media",
                            "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
                            "collector_semantics_id": GLOBAL_EVENT_V2_PROTOCOL["evidence"][
                                "expected_collector_semantics_id"
                            ],
                        },
                        sort_keys=True,
                    ),
                    "formal_eligible_item_count": len(receipt_ids),
                    "formal_eligible_evidence_ids": receipt_ids,
                    "formal_eligible_evidence_ids_json": json.dumps(
                        receipt_ids, separators=(",", ":")
                    ),
                    "formal_eligible_lineage": eligible_lineage,
                    "formal_eligible_lineage_json": json.dumps(
                        eligible_lineage,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                },
                "allow_empty": False,
                "require_eligible": False,
                "require_lineage": True,
                "healthy": True,
                "reason": None,
                "lineage_bound": True,
                "lineage_evidence_ids": sorted(set(receipt_ids) & set(eligible_ids)),
                "lineage_items": eligible_lineage,
                "required_selected_evidence_ids": selected_ids,
                "required_selected_lineage": eligible_lineage,
                "unbacked_selected_evidence_ids": [],
                "unbacked_selected_lineage": [],
                "collector_identity_matches": True,
            }
        )
    coverage["x_cycle_availability"] = x_cycle_availability
    invocation = GLOBAL_EVENT_V2_PROTOCOL["forecast"]["invocation_policy"]
    llm_policy = {
        "allowed_models": sorted(
            f"openai:{model}"
            for model in GLOBAL_EVENT_V2_PROTOCOL["forecast"]["allowed_returned_models"]
        ),
        "max_calls_per_decision": invocation["max_calls_per_decision"],
        "max_calls_per_utc_day": invocation["max_calls_per_utc_day"],
    }
    model_ids = {
        "global_events_champion": llm_model_id,
        "global_events_without_public_reaction": llm_model_id,
        "public_reaction_only": "model_none",
        "market_only": "model_deterministic_market",
        "equal_weight": "model_deterministic_equal_weight",
        "momentum": "model_deterministic_momentum",
        "stale_events_negative_control": "model_stored_forecast",
        "shuffled_events_negative_control": llm_model_id,
    }
    targets = {
        strategy: _target(
            None,
            run_id,
            strategy,
            rows,
            universe,
            cutoff=cutoff,
            next_open=next_open,
            entry_date=entry_date,
            created_at=created_at,
            model_id=model_ids[strategy],
            current_weights=prior,
        )
        for strategy, rows in strategy_rows.items()
    }
    decision_semantics = formal_decision_semantics()
    registered_outcome_semantics_id = OUTCOME_SEMANTICS_ID
    configuration_binding = {
        "configuration_manifest_id": "config_" + "1" * 24,
        "collector_configuration_id": "config_" + "2" * 24,
        "paper_decision_configuration_id": "config_" + "3" * 24,
        "paper_marker_configuration_id": "config_" + "4" * 24,
    }
    trial_registration = formal_trial_registration(
        run_id,
        decision_semantics,
        outcome_semantics_id=registered_outcome_semantics_id,
        configuration_binding=configuration_binding,
    )
    prior_weight_lineage = {}
    for strategy in strategies:
        base = {
            "weights": dict(prior),
            "source_kind": "initial_zero",
            "source_session_date": None,
            "source_decision_date": None,
        }
        prior_weight_lineage[strategy] = {
            **base,
            "lineage_id": content_id(base, prefix="weights_"),
        }
    stale_lineage = {
        "source_kind": "initial_neutral",
        "source_decision_date": None,
        "forecast_content_id": content_id(stale_rows, prefix="forecasts_"),
    }
    artifact = {
        "schema_version": 3,
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "build_id": "build_000000000000000000000001",
        "run_id": run_id,
        "decision_date": decision_date,
        "attempt_ordinal": 1,
        "universe": universe,
        "decision_context": {
            "cutoff_utc": cutoff.isoformat(),
            "next_open_utc": next_open.isoformat(),
            "entry_date": entry_date,
            "target_created_at_utc": created_at.isoformat(),
        },
        "coverage": coverage,
        "required_evidence_query_slots": evidence_query_slots,
        "evidence_policy": formal_evidence_policy_manifest(),
        "x_cycle_availability": x_cycle_availability,
        "evidence_selection_manifest": selection_manifest,
        "evidence_selection_coverage": selection_coverage,
        "decision_semantics": decision_semantics,
        "trial_registration_id": trial_registration["registration_id"],
        "llm_policy": {
            **llm_policy,
            "max_prompt_bytes": invocation["max_prompt_bytes"],
            "max_completion_tokens": invocation["max_completion_tokens"],
            "timeout_seconds": invocation["timeout_seconds"],
            "sdk_max_retries": invocation["sdk_max_retries"],
            "endpoint_class": GLOBAL_EVENT_V2_PROTOCOL["forecast"]["endpoint_class"],
            "backend_url": GLOBAL_EVENT_V2_PROTOCOL["forecast"]["backend_url"],
            "reasoning_effort": GLOBAL_EVENT_V2_PROTOCOL["forecast"]["reasoning_effort"],
            "temperature": GLOBAL_EVENT_V2_PROTOCOL["forecast"]["temperature"],
            "structured_output_schema": GLOBAL_EVENT_V2_PROTOCOL["forecast"][
                "structured_output_schema"
            ],
        },
        "invocation_stage_order": _fixture_invocation_stage_order(decision_date, ["champion"]),
        "champion": deepcopy(champion),
        "without_public_reaction": without_public,
        "public_reaction_only": None,
        "market_inputs": {
            "ohlc": snapshots,
            "market_only": deepcopy(market_rows),
            "momentum": deepcopy(momentum_rows),
        },
        "stale_input_lineage": stale_lineage,
        "strategy_inputs": {
            strategy: {
                "forecasts": deepcopy(strategy_rows[strategy]),
                "prior_weights": dict(prior),
                "prior_weight_lineage": prior_weight_lineage[strategy],
                "model_id": model_ids[strategy],
            }
            for strategy in strategies
        },
        "strategy_targets": targets,
    }
    invocation_receipts = _invocation_receipt_pair(
        run_id=run_id,
        decision_date=decision_date,
        ordinal=1,
        stage="champion",
        bundle=champion,
        created_at=created_at,
    )
    if artifact_mutator is not None:
        artifact_mutator(artifact)
    if receipt_mutator is not None:
        receipt_mutator(invocation_receipts)
    artifact_id = artifact_id_override or content_id(artifact, prefix="artifact_")
    config = {
        "engine": "formal-global-v2",
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "tickers": universe,
        "benchmark": GLOBAL_EVENT_V2_PROTOCOL["portfolio"]["benchmark"],
        "cost_bps": 5.0,
        "slippage_bps": 5.0,
        "annual_borrow_bps": 0.0,
        "cash_policy": GLOBAL_EVENT_V2_PROTOCOL["portfolio"]["cash"],
        "llm_model": f"openai:{requested_model}",
        "llm_endpoint_class": GLOBAL_EVENT_V2_PROTOCOL["forecast"]["endpoint_class"],
        "llm_backend_url": GLOBAL_EVENT_V2_PROTOCOL["forecast"]["backend_url"],
        "llm_reasoning_effort": GLOBAL_EVENT_V2_PROTOCOL["forecast"]["reasoning_effort"],
        "llm_temperature": GLOBAL_EVENT_V2_PROTOCOL["forecast"]["temperature"],
        "llm_policy": llm_policy,
        "llm_sdk_max_retries": invocation["sdk_max_retries"],
        "llm_max_prompt_bytes": invocation["max_prompt_bytes"],
        "llm_max_completion_tokens": invocation["max_completion_tokens"],
        "llm_timeout_seconds": invocation["timeout_seconds"],
        "evidence_query_slots": evidence_query_slots,
        "collector_interval_seconds": collector_interval_seconds,
        "collector_cycle_start_grace_seconds": collector_cycle_grace_seconds,
        "evidence_policy": formal_evidence_policy_manifest(),
        "decision_semantics": decision_semantics,
        "outcome_semantics_id": registered_outcome_semantics_id,
        "configuration_binding": configuration_binding,
        "trial_registration_id": trial_registration["registration_id"],
    }
    store.register_protocol(
        GLOBAL_EVENT_V2_PROTOCOL_ID, GLOBAL_EVENT_V2_PROTOCOL, created_at.timestamp()
    )
    store.create_run(run_id, config, created_at.timestamp())
    store.register_confirmatory_trial(run_id, created_at.timestamp(), trial_registration)
    store.record_formal_attempt_started(run_id, decision_date, entry_date, created_at.timestamp())
    for receipt in invocation_receipts:
        store.record_artifact(receipt["artifact_type"], receipt["content"], receipt["created_utc"])

    def persist():
        store.record_formal_decision(
            run_id=run_id,
            decision_date=decision_date,
            entry_date=entry_date,
            created_utc=created_at.timestamp(),
            protocol_id=GLOBAL_EVENT_V2_PROTOCOL_ID,
            build_id="build_000000000000000000000001",
            model_id=llm_model_id,
            input_bundle_id=input_bundle_id,
            artifact_id=artifact_id,
            artifact=artifact,
            coverage=coverage,
            events=events,
            forecasts=champion_rows,
            strategy_targets=targets,
        )

    should_bypass_receipt_validation = (
        artifact_mutator is not None or artifact_id_override is not None
        if bypass_receipt_validation is None
        else bypass_receipt_validation
    )
    if should_bypass_receipt_validation:
        validate = store._validate_invocation_receipts_before_persistence
        store._validate_invocation_receipts_before_persistence = lambda *_args, **_kwargs: None
        try:
            persist()
        finally:
            store._validate_invocation_receipts_before_persistence = validate
    else:
        persist()
    return run_id


class _OutcomeSemanticsGuardStore:
    run_id = "formal-verifier-semantics-guard"

    def __init__(self, mutation: str):
        self.config = {"outcome_semantics_id": OUTCOME_SEMANTICS_ID}
        self.registration = {
            "label": "confirmatory-trial",
            "created_utc": 1.0,
            "details": {"outcome_semantics_id": OUTCOME_SEMANTICS_ID},
        }
        self.outcome_reads = 0
        if mutation == "missing":
            self.config.pop("outcome_semantics_id")
        elif mutation == "registration_disagreement":
            self.registration["details"]["outcome_semantics_id"] = (
                "outcome_semantics_" + "0" * 64
            )
        elif mutation == "installed_drift":
            drifted = "outcome_semantics_" + "0" * 64
            self.config["outcome_semantics_id"] = drifted
            self.registration["details"]["outcome_semantics_id"] = drifted
        else:
            raise AssertionError(mutation)

    def run_config(self, run_id):
        assert run_id == self.run_id
        return deepcopy(self.config)

    def confirmatory_registration(self, run_id):
        assert run_id == self.run_id
        return deepcopy(self.registration)

    def formal_bundle(self, *_args, **_kwargs):
        self.outcome_reads += 1
        raise AssertionError("outcome-semantics failure reached formal bundle access")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("mutation", "error", "message"),
    [
        ("missing", FormalReadoutIntegrityError, "disagree on outcome semantics"),
        (
            "registration_disagreement",
            FormalReadoutIntegrityError,
            "disagree on outcome semantics",
        ),
        (
            "installed_drift",
            OutcomeSemanticsResolutionError,
            "differ from preregistration",
        ),
    ],
)
def test_verifier_rejects_outcome_semantics_before_bundle_read(
    mutation,
    error,
    message,
):
    store = _OutcomeSemanticsGuardStore(mutation)

    with pytest.raises(error, match=message):
        verify_formal(store, store.run_id)

    assert store.outcome_reads == 0


@pytest.mark.unit
def test_independent_verifier_component_set_matches_current_producer():
    assert set(formal_decision_semantics()["components"]) == set(_DECISION_SEMANTIC_COMPONENTS)
    assert set(collector_semantics_manifest()["components"]) == set(_COLLECTOR_SEMANTIC_COMPONENTS)


@pytest.mark.unit
def test_verify_formal_replays_all_strategies_without_external_calls(tmp_path, monkeypatch):
    store = PaperStore(str(tmp_path / "paper.db"))
    run_id = _record_replayable_decision(store)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("offline verifier attempted an external call")

    monkeypatch.setattr("tradingagents.global_research.invoke_global_forecast", forbidden)
    monkeypatch.setattr("tradingagents.backtest._load_prices", forbidden)

    receipt = verify_formal(store, run_id)

    assert receipt["ok"] is True
    assert receipt["forecasts"] == 20
    assert receipt["strategies_replayed"] == 8
    assert receipt["external_calls"] == 0
    store.close()


@pytest.mark.unit
def test_verify_formal_accepts_fresh_successful_zero_lineage_observed_absence(
    tmp_path,
):
    store = PaperStore(str(tmp_path / "paper.db"))
    run_id = _record_replayable_decision(store, absent_slot_index=0)

    receipt = verify_formal(store, run_id)

    artifact = store.formal_bundle(run_id)["artifact"]["content"]
    absent_slot = artifact["required_evidence_query_slots"][0][1]
    assert receipt["ok"] is True
    assert absent_slot in artifact["evidence_selection_coverage"]["observed_absent_query_slots"]
    assert artifact["coverage"]["query_slots"][0]["run"]["formal_eligible_item_count"] == 0
    assert artifact["coverage"]["query_slots"][0]["run"]["formal_eligible_evidence_ids"] == []
    assert artifact["coverage"]["query_slots"][0]["run"]["formal_eligible_lineage"] == []
    store.close()


@pytest.mark.unit
@pytest.mark.parametrize("field", ["protocol_id", "collector_semantics_id"])
def test_verify_formal_rejects_receipt_collector_identity_tampering(tmp_path, field):
    store = PaperStore(str(tmp_path / "paper.db"))

    def tamper(artifact):
        run = artifact["coverage"]["query_slots"][0]["run"]
        metadata = json.loads(run["metadata_json"])
        metadata[field] = f"{field}_tampered"
        run["metadata_json"] = json.dumps(metadata, sort_keys=True)

    run_id = _record_replayable_decision(store, artifact_mutator=tamper)

    with pytest.raises(FormalVerificationError, match="exact lineage provenance"):
        verify_formal(store, run_id)
    store.close()


@pytest.mark.unit
def test_verify_formal_rejects_selected_evidence_without_receipt_lineage(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))

    def unbind_selected(artifact):
        slot = artifact["coverage"]["query_slots"][0]
        slot["run"]["formal_eligible_item_count"] = 0
        slot["run"]["formal_eligible_evidence_ids"] = []
        slot["run"]["formal_eligible_evidence_ids_json"] = "[]"
        slot["run"]["formal_eligible_lineage"] = []
        slot["run"]["formal_eligible_lineage_json"] = "[]"

    run_id = _record_replayable_decision(store, artifact_mutator=unbind_selected)

    with pytest.raises(FormalVerificationError, match="exact lineage provenance"):
        verify_formal(store, run_id)
    store.close()


@pytest.mark.unit
@pytest.mark.parametrize(
    "onset",
    ["2026-08-05T00:00:01Z", "2026-08-04T23:00:00+00:00"],
)
def test_verify_formal_rejects_noncanonical_or_future_event_onset(tmp_path, onset):
    store = PaperStore(str(tmp_path / "paper.db"))

    def alter_onset(artifact):
        artifact["champion"]["forecast"]["events"][0]["onset_utc"] = onset

    run_id = _record_replayable_decision(store, artifact_mutator=alter_onset)

    with pytest.raises(FormalVerificationError, match="cutoff-safe"):
        verify_formal(store, run_id)
    store.close()


@pytest.mark.unit
def test_verify_formal_binds_result_receipt_to_exact_forecast_bundle(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))

    def mutate_stored_bundle(artifact):
        artifact["champion"]["raw_response"]["post_receipt_mutation"] = True

    run_id = _record_replayable_decision(store, artifact_mutator=mutate_stored_bundle)

    with pytest.raises(
        FormalVerificationError,
        match="model/response does not match its stored bundle",
    ):
        verify_formal(store, run_id)
    store.close()


@pytest.mark.unit
def test_selection_verifier_replays_immutable_diverse_public_reaction():
    decision_date = "2026-08-04"
    cutoff, _next_open, _entry_date = decision_window(decision_date)
    theme, query = next(
        (theme, query)
        for theme, queries in GLOBAL_EVENT_V2_PROTOCOL["evidence"]["broad_news_queries"].items()
        for query in queries
    )
    rows = [
        {
            "source": "globalnews",
            "external_id": "immutable-news",
            "labels": [global_news_query_slot_label(theme, query)],
            "created_utc": cutoff.timestamp() - 3_600,
            "fetched_utc": cutoff.timestamp() - 1_800,
            "author": "Reuters",
            "title": "Independent global report",
            "body": "Independent reporting establishes the global event.",
            "metadata": {
                "article_url": "https://www.reuters.com/world/immutable-news/",
                "publisher_domain": "reuters.com",
            },
        }
    ]
    x_specs = [
        ("x-world-1", "1001", "@TREND_WORLD", "Public reaction world one", 9),
        ("x-business-1", "1001", "@TREND_BUSINESS", "Public reaction business one", 8),
        ("x-tech-cap", "1001", "@TREND_TECHNOLOGY", "Public reaction tech capped", 7),
        ("x-tech-2", "2002", "@TREND_TECHNOLOGY", "Public reaction tech two", 6),
        ("x-world-dup", "3003", "@TREND_WORLD", "Public reaction world one", 1),
    ]
    for index, (external_id, author_id, topic, body, likes) in enumerate(x_specs):
        rows.append(
            {
                "source": "x",
                "external_id": external_id,
                "labels": [topic],
                "created_utc": cutoff.timestamp() - 2_000 - index,
                "fetched_utc": cutoff.timestamp() - 1_000 - index,
                "author": None,
                "title": body,
                "body": body,
                "metadata": {
                    "evidence_role": "unverified_public_reaction",
                    "author_id": author_id,
                    "author_username": f"observer{author_id}",
                    "account_created_utc": cutoff.timestamp() - 100_000,
                    "automation_signals_complete": True,
                    "verified_type": None,
                    "automation_risk": 0.1,
                    "engagement": {
                        "like_count": likes,
                        "reply_count": 0,
                        "retweet_count": 0,
                        "quote_count": 0,
                    },
                    "author_metrics": {
                        "followers_count": 100,
                        "following_count": 50,
                        "tweet_count": 500,
                    },
                },
            }
        )

    manifest = _fixture_selection_manifest(rows, cutoff)
    champion_rows, without_rows, public_rows = partition_formal_evidence(
        rows, as_of_utc=cutoff.timestamp()
    )
    errors: list[str] = []
    _validate_evidence_selection_manifest(
        manifest,
        cutoff=cutoff,
        bundle_evidence={
            "champion": prepare_evidence(champion_rows),
            "without_public_reaction": prepare_evidence(without_rows),
            "public_reaction_only": prepare_evidence(public_rows),
        },
        selection_coverage=formal_globalnews_selection_coverage(manifest),
        errors=errors,
    )

    assert errors == []
    selected_x = [
        candidate
        for candidate in manifest["candidates"]
        if candidate["source"] == "x" and "champion" in candidate["selected_for"]
    ]
    assert {candidate["public_reaction_topic"] for candidate in selected_x} == {
        "@TREND_WORLD",
        "@TREND_BUSINESS",
        "@TREND_TECHNOLOGY",
    }
    assert sum(candidate["author_id"] == "1001" for candidate in selected_x) == 2
    selected_by_role = manifest["ordered_selected_evidence_ids"]
    assert set(selected_by_role["champion"]) - set(selected_by_role["without_public_reaction"]) == {
        candidate["evidence_id"] for candidate in selected_x
    }
    assert set(selected_by_role["public_reaction_only"]) == {
        candidate["evidence_id"] for candidate in selected_x
    }

    tampered = deepcopy(manifest)
    selected = next(
        candidate
        for candidate in tampered["candidates"]
        if candidate["source"] == "x" and candidate["disposition"] == "selected"
    )
    selected["automation_signals_complete"] = False
    tamper_errors: list[str] = []
    _validate_evidence_selection_manifest(
        tampered,
        cutoff=cutoff,
        bundle_evidence={
            "champion": prepare_evidence(champion_rows),
            "without_public_reaction": prepare_evidence(without_rows),
            "public_reaction_only": prepare_evidence(public_rows),
        },
        selection_coverage=formal_globalnews_selection_coverage(manifest),
        errors=tamper_errors,
    )
    assert "evidence selection eligibility mismatch" in tamper_errors


@pytest.mark.unit
def test_selection_verifier_rejects_collector_only_trendnews_candidates():
    decision_date = "2026-08-04"
    cutoff, _next_open, _entry_date = decision_window(decision_date)
    theme, query = next(
        (theme, query)
        for theme, queries in GLOBAL_EVENT_V2_PROTOCOL["evidence"]["broad_news_queries"].items()
        for query in queries
    )
    rows = [
        {
            "source": "globalnews",
            "external_id": "strict-core-news",
            "labels": [global_news_query_slot_label(theme, query)],
            "created_utc": cutoff.timestamp() - 3_600,
            "fetched_utc": cutoff.timestamp() - 1_800,
            "author": "Reuters",
            "title": "Independent global report",
            "body": "Independent reporting establishes the global event.",
            "metadata": {
                "article_url": "https://www.reuters.com/world/strict-core-news/",
                "publisher_domain": "reuters.com",
            },
        },
        {
            "source": "trendnews",
            "external_id": "collector-discovery-only",
            "labels": ["@TREND_WORLD"],
            "created_utc": cutoff.timestamp() - 3_500,
            "fetched_utc": cutoff.timestamp() - 1_700,
            "author": "Reuters",
            "title": "Discovery signal must never enter a formal history bucket",
            "body": "Collector-only topic-discovery provenance.",
            "metadata": {
                "article_url": "https://www.reuters.com/world/discovery-only/",
                "publisher_domain": "reuters.com",
            },
        },
    ]
    manifest = _fixture_selection_manifest(rows, cutoff)
    champion_rows, without_rows, public_rows = partition_formal_evidence(
        rows, as_of_utc=cutoff.timestamp()
    )
    bundles = {
        "champion": prepare_evidence(champion_rows),
        "without_public_reaction": prepare_evidence(without_rows),
        "public_reaction_only": prepare_evidence(public_rows),
    }
    errors: list[str] = []

    _validate_evidence_selection_manifest(
        manifest,
        cutoff=cutoff,
        bundle_evidence=bundles,
        selection_coverage=formal_globalnews_selection_coverage(manifest),
        errors=errors,
    )

    assert all(row["source"] != "trendnews" for evidence in bundles.values() for row in evidence)
    assert "evidence selection contains a source outside formal history buckets" in errors


@pytest.mark.unit
def test_frozen_invocation_cycle_exactly_counterbalances_252_xnys_sessions():
    stages = ["champion", "without_public_reaction", "public_reaction_only"]
    calendar = xcals.get_calendar("XNYS", start="2020-01-02", end="2030-12-31")
    sessions = calendar.sessions_in_range("2025-01-02", "2026-12-31")[:252]
    full_position_counts = {stage: [0, 0, 0] for stage in stages}
    two_stage_position_counts = {stage: [0, 0] for stage in ("champion", "public_reaction_only")}
    for session in sessions:
        decision_date = session.date().isoformat()
        for position, stage in enumerate(_fixture_invocation_stage_order(decision_date, stages)):
            full_position_counts[stage][position] += 1
        for position, stage in enumerate(
            _fixture_invocation_stage_order(decision_date, ["champion", "public_reaction_only"])
        ):
            two_stage_position_counts[stage][position] += 1

    assert len(sessions) == 252
    assert set(map(tuple, full_position_counts.values())) == {(84, 84, 84)}
    assert set(map(tuple, two_stage_position_counts.values())) == {(126, 126)}


@pytest.mark.unit
def test_invocation_receipt_ordinals_follow_counterbalanced_stage_order(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))
    run_id = _record_replayable_decision(store)
    decision_date = "2026-08-04"
    cutoff, _next_open, _entry_date = decision_window(decision_date)
    champion = deepcopy(store.formal_bundle(run_id)["artifact"]["content"]["champion"])
    without_public = deepcopy(champion)
    without_public["evidence"] = without_public["evidence"][:-1]
    without_public["input_bundle_id"] = "input_without_public"
    public_only = deepcopy(champion)
    public_only["input_bundle_id"] = "input_public_only"
    stage_bundles = {
        "champion": champion,
        "without_public_reaction": without_public,
        "public_reaction_only": public_only,
    }
    expected_order = _fixture_invocation_stage_order(decision_date, list(stage_bundles))

    def receipts_for(order):
        rows = []
        for ordinal, stage in enumerate(order, start=1):
            rows.extend(
                _invocation_receipt_pair(
                    run_id=run_id,
                    decision_date=decision_date,
                    ordinal=ordinal,
                    stage=stage,
                    bundle=stage_bundles[stage],
                    created_at=datetime(2026, 8, 5, 1, 0, ordinal, tzinfo=timezone.utc),
                    daily_count=ordinal,
                )
            )
        for row in rows:
            row["artifact_id"] = content_id(
                {
                    "artifact_type": row["artifact_type"],
                    "content": row["content"],
                },
                prefix="artifact_",
            )
        return rows

    errors: list[str] = []
    _validate_invocation_receipts(
        receipts_for(expected_order),
        run_id=run_id,
        decision_date=decision_date,
        cutoff=cutoff,
        persisted_at=datetime(2026, 8, 5, 2, tzinfo=timezone.utc),
        champion=champion,
        without_public=without_public,
        public_only=public_only,
        stored_stage_order=expected_order,
        errors=errors,
    )
    assert errors == []

    tamper_errors: list[str] = []
    _validate_invocation_receipts(
        receipts_for(list(reversed(expected_order))),
        run_id=run_id,
        decision_date=decision_date,
        cutoff=cutoff,
        persisted_at=datetime(2026, 8, 5, 2, tzinfo=timezone.utc),
        champion=champion,
        without_public=without_public,
        public_only=public_only,
        stored_stage_order=expected_order,
        errors=tamper_errors,
    )
    assert "LLM invocation stages differ from required forecast bundles" in tamper_errors
    store.close()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("missing_result", "receipt count differs from required stages"),
        ("missing_reservation", "orphan LLM invocation result receipt"),
        ("extra_stage", "stages differ from required forecast bundles"),
        ("duplicate_result", "not exactly one-to-one"),
        ("identity_tamper", "reservation/result self-identities disagree"),
        ("counter_tamper", "reservation counter keys or values are invalid"),
        ("ceiling_tamper", "reservation policy ceilings differ from protocol"),
        ("response_tamper", "model/response does not match its stored bundle"),
    ],
)
def test_verify_formal_reconciles_invocation_receipts(tmp_path, case, message):
    store = PaperStore(str(tmp_path / "paper.db"))

    def refresh_reservation_pointer(receipts):
        reservation = receipts[0]["content"]
        receipts[1]["content"]["reservation_artifact_id"] = content_id(
            {
                "artifact_type": "llm_invocation_reserved",
                "content": reservation,
            },
            prefix="artifact_",
        )

    def mutate(receipts):
        if case == "missing_result":
            receipts.pop()
        elif case == "missing_reservation":
            receipts.pop(0)
        elif case == "extra_stage":
            extra_reservation = deepcopy(receipts[0])
            extra_result = deepcopy(receipts[1])
            identity_fields = (
                "scope",
                "run_id",
                "decision_date",
                "ordinal",
                "stage",
                "provider",
                "requested_model",
                "input_bundle_id",
            )
            extra_reservation["content"]["ordinal"] = 2
            extra_reservation["content"]["stage"] = "public_reaction_only"
            decision_key = next(
                key
                for key in extra_reservation["content"]["reservation_counts"]
                if ":decision:" in key
            )
            day_key = next(
                key
                for key in extra_reservation["content"]["reservation_counts"]
                if ":utc-day:" in key
            )
            extra_reservation["content"]["reservation_counts"] = {
                decision_key: 2.0,
                day_key: 2.0,
            }
            identity = {field: extra_reservation["content"][field] for field in identity_fields}
            invocation_id = content_id(identity, prefix="invocation_")
            extra_reservation["content"]["invocation_id"] = invocation_id
            for field in identity_fields:
                extra_result["content"][field] = identity[field]
            extra_result["content"]["invocation_id"] = invocation_id
            extra_result["content"]["reservation_artifact_id"] = content_id(
                {
                    "artifact_type": "llm_invocation_reserved",
                    "content": extra_reservation["content"],
                },
                prefix="artifact_",
            )
            receipts.extend([extra_reservation, extra_result])
        elif case == "duplicate_result":
            duplicate = deepcopy(receipts[1])
            duplicate["content"]["elapsed_ms"] = 1
            receipts.append(duplicate)
        elif case == "identity_tamper":
            receipts[1]["content"]["input_bundle_id"] = "input_tampered"
        elif case == "counter_tamper":
            decision_key = next(
                key for key in receipts[0]["content"]["reservation_counts"] if ":decision:" in key
            )
            receipts[0]["content"]["reservation_counts"][decision_key] = 2.0
            refresh_reservation_pointer(receipts)
        elif case == "ceiling_tamper":
            receipts[0]["content"]["max_prompt_bytes"] += 1
            refresh_reservation_pointer(receipts)
        elif case == "response_tamper":
            receipts[1]["content"]["response_id"] = "response-tampered"

    run_id = _record_replayable_decision(
        store,
        receipt_mutator=mutate,
        bypass_receipt_validation=True,
    )

    with pytest.raises(FormalVerificationError, match=message):
        verify_formal(store, run_id)
    store.close()


@pytest.mark.unit
def test_formal_persistence_rejects_an_incomplete_invocation_receipt_set(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))

    with pytest.raises(ValueError, match="receipt set is incomplete or contains extras"):
        _record_replayable_decision(
            store,
            receipt_mutator=lambda receipts: receipts.pop(),
        )

    assert store.has_decision("formal-replay", "2026-08-04") is False
    store.close()


@pytest.mark.unit
def test_formal_bundle_projects_only_the_decisions_invocation_receipts(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))
    run_id = _record_replayable_decision(store)
    unrelated = _invocation_receipt_pair(
        run_id="another-run",
        decision_date="2026-08-04",
        ordinal=1,
        stage="champion",
        bundle=store.formal_bundle(run_id)["artifact"]["content"]["champion"],
        created_at=datetime(2026, 8, 5, 1, tzinfo=timezone.utc),
    )
    for receipt in unrelated:
        store.record_artifact(receipt["artifact_type"], receipt["content"], receipt["created_utc"])

    projected = store.formal_bundle(run_id)["invocation_receipts"]

    assert len(projected) == 2
    assert {row["content"]["run_id"] for row in projected} == {run_id}
    store.close()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("schema", "replayable version 3"),
        ("query_slots", "differ from frozen protocol"),
        ("eligible_receipt", "exact lineage provenance"),
        ("content_lineage", "exact lineage provenance"),
        ("evidence_id", "evidence identity hash mismatch"),
        ("evidence_whitelist", "prepared evidence schema mismatch"),
        ("evidence_utf8_bound", "frozen UTF-8 bound"),
        ("publisher_domain", "publisher/domain pair is not allowed"),
        ("article_url", "article URL provenance is malformed"),
        ("query_cap", "per-query-slot evidence cap"),
        ("selection_hash", "selection manifest content hash mismatch"),
        ("selection_coverage", "selected-evidence query-slot coverage mismatch"),
        ("invocation_order", "stage order differs from frozen policy"),
        ("grounding", "independent-source grounding mismatch"),
        ("semantics", "decision semantics content hash mismatch"),
        ("semantic_lock_policy", "formal-operation-lock values mismatch"),
        ("semantic_receipt_policy", "LLM-receipt values mismatch"),
        ("registration", "artifact trial registration identity mismatch"),
        ("stale_lineage", "stale forecast lineage content hash mismatch"),
        ("weight_lineage", "prior-weight lineage mismatch"),
        ("shuffle", "shuffled_events_negative_control forecast reconstruction mismatch"),
    ],
)
def test_verify_formal_rejects_v3_provenance_and_lineage_tampering(tmp_path, case, message):
    store = PaperStore(str(tmp_path / "paper.db"))

    def tamper(artifact):
        champion = artifact["champion"]
        if case == "schema":
            artifact["schema_version"] = 2
        elif case == "query_slots":
            artifact["required_evidence_query_slots"].pop()
        elif case == "eligible_receipt":
            artifact["coverage"]["query_slots"][0]["run"]["formal_eligible_item_count"] = 0
        elif case == "content_lineage":
            slot = artifact["coverage"]["query_slots"][0]
            fake_lineage = [
                {
                    "evidence_id": slot["run"]["formal_eligible_evidence_ids"][0],
                    "raw_content_id": "raw_" + "0" * 24,
                }
            ]
            slot["run"]["formal_eligible_lineage"] = fake_lineage
            slot["run"]["formal_eligible_lineage_json"] = json.dumps(
                fake_lineage,
                sort_keys=True,
                separators=(",", ":"),
            )
            slot["lineage_items"] = fake_lineage
            slot["required_selected_lineage"] = fake_lineage
        elif case == "evidence_id":
            champion["evidence"][0]["evidence_id"] = "evidence_tampered"
        elif case == "evidence_whitelist":
            champion["evidence"][0]["untrusted_extra_field"] = "leak"
        elif case == "evidence_utf8_bound":
            champion["evidence"][0]["title"] = "é" * 401
        elif case == "publisher_domain":
            evidence = champion["evidence"][0]
            evidence["publisher_domain"] = "openai.com"
            evidence["metadata"]["publisher_domain"] = "openai.com"
        elif case == "article_url":
            evidence = champion["evidence"][0]
            evidence["article_url"] = "file:///private/article"
            evidence["metadata"]["article_url"] = "file:///private/article"
        elif case == "query_cap":
            template = deepcopy(champion["evidence"][0])
            for index in range(8):
                row = deepcopy(template)
                row["external_id"] = f"cap-tamper-{index}"
                row["evidence_id"] = content_id(
                    {"source": "globalnews", "external_id": row["external_id"]},
                    prefix="evidence_",
                )
                champion["evidence"].append(row)
        elif case == "selection_hash":
            artifact["evidence_selection_manifest"]["candidate_count"] += 1
        elif case == "selection_coverage":
            artifact["evidence_selection_coverage"]["selected_query_slots"].pop()
        elif case == "invocation_order":
            artifact["invocation_stage_order"] = []
        elif case == "grounding":
            champion["forecast"]["events"][0]["independent_source_count"] = 99
        elif case == "semantics":
            artifact["decision_semantics"]["components"]["forecast_prompt"] = "0" * 64
        elif case == "semantic_lock_policy":
            artifact["decision_semantics"]["semantic_values"]["formal_operation_lock_policy"][
                "reentrancy"
            ] = "unbounded"
        elif case == "semantic_receipt_policy":
            artifact["decision_semantics"]["semantic_values"]["llm_invocation_receipt_policy"][
                "reservation"
            ] = "counter-only"
        elif case == "registration":
            artifact["trial_registration_id"] = "registration_tampered"
        elif case == "stale_lineage":
            artifact["stale_input_lineage"]["forecast_content_id"] = "forecasts_tampered"
        elif case == "weight_lineage":
            artifact["strategy_inputs"]["momentum"]["prior_weight_lineage"]["lineage_id"] = (
                "weights_tampered"
            )
        elif case == "shuffle":
            artifact["strategy_inputs"]["shuffled_events_negative_control"]["forecasts"][0][
                "event_ids"
            ] = []

    run_id = _record_replayable_decision(store, artifact_mutator=tamper)

    with pytest.raises(FormalVerificationError, match=message):
        verify_formal(store, run_id)
    store.close()


@pytest.mark.unit
def test_persistence_rejects_artifact_hash_mismatch_before_verification(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))

    with pytest.raises(ValueError, match="artifact ID is not content-addressed"):
        _record_replayable_decision(
            store,
            artifact_id_override="artifact_intentionally_wrong",
        )

    assert store.has_decision("formal-replay", "2026-08-04") is False
    store.close()


@pytest.mark.unit
def test_verify_formal_rejects_future_evidence(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))

    def inject_future(artifact):
        cutoff = artifact["decision_context"]["cutoff_utc"]
        artifact["champion"]["evidence"][0]["received_utc"] = cutoff

    run_id = _record_replayable_decision(store, artifact_mutator=inject_future)

    with pytest.raises(FormalVerificationError, match="received_utc cutoff"):
        verify_formal(store, run_id)
    store.close()


@pytest.mark.unit
def test_verify_formal_requires_champion_and_no_x_bundles(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))

    def remove_no_x(artifact):
        artifact["without_public_reaction"] = None

    run_id = _record_replayable_decision(store, artifact_mutator=remove_no_x)

    with pytest.raises(
        FormalVerificationError, match="without_public_reaction forecast bundle missing"
    ):
        verify_formal(store, run_id)
    store.close()


@pytest.mark.unit
def test_verify_formal_rejects_collector_only_source_in_no_reaction_bundle(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))

    def contaminate_no_reaction(artifact):
        artifact["without_public_reaction"]["evidence"][0]["source"] = "trendnews"

    run_id = _record_replayable_decision(store, artifact_mutator=contaminate_no_reaction)

    with pytest.raises(FormalVerificationError, match="disallowed evidence source"):
        verify_formal(store, run_id)
    store.close()


@pytest.mark.unit
def test_verify_formal_requires_bundle_reuse_for_identical_ablation_input(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))

    def duplicate_call_result(artifact):
        artifact["without_public_reaction"]["response_id"] = "unexpected-second-call"

    run_id = _record_replayable_decision(store, artifact_mutator=duplicate_call_result)

    with pytest.raises(FormalVerificationError, match="did not reuse the champion bundle"):
        verify_formal(store, run_id)
    store.close()


@pytest.mark.unit
def test_verify_formal_rejects_corporate_source_marker(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))

    def inject_company_source(artifact):
        artifact["champion"]["evidence"][0]["publisher_or_author"] = "Official Blog"

    run_id = _record_replayable_decision(store, artifact_mutator=inject_company_source)

    with pytest.raises(FormalVerificationError, match="company-authored evidence"):
        verify_formal(store, run_id)
    store.close()


@pytest.mark.unit
def test_verify_formal_reconstructs_prompt_from_evidence(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))

    def alter_prompt(artifact):
        artifact["champion"]["prompt"] += "\nUnrecorded instruction"

    run_id = _record_replayable_decision(store, artifact_mutator=alter_prompt)

    with pytest.raises(FormalVerificationError, match="prompt reconstruction mismatch"):
        verify_formal(store, run_id)
    store.close()


@pytest.mark.unit
def test_verify_formal_reconstructs_market_rows_from_ohlc(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))

    def alter_ohlc(artifact):
        artifact["market_inputs"]["ohlc"]["AAPL"][-1]["close"] *= 1.2

    run_id = _record_replayable_decision(store, artifact_mutator=alter_ohlc)

    with pytest.raises(
        FormalVerificationError, match="market-only rows differ from OHLC reconstruction"
    ):
        verify_formal(store, run_id)
    store.close()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("strategy", "message"),
    [
        ("equal_weight", "equal_weight forecast reconstruction mismatch"),
        (
            "shuffled_events_negative_control",
            "shuffled_events_negative_control forecast reconstruction mismatch",
        ),
    ],
)
def test_verify_formal_reconstructs_deterministic_strategy_rows(tmp_path, strategy, message):
    store = PaperStore(str(tmp_path / "paper.db"))

    def alter_rows(artifact):
        artifact["strategy_inputs"][strategy]["forecasts"][0]["expected_excess_return_bps"] += 1.0

    run_id = _record_replayable_decision(store, artifact_mutator=alter_rows)

    with pytest.raises(FormalVerificationError, match=message):
        verify_formal(store, run_id)
    store.close()


@pytest.mark.unit
def test_verify_formal_requires_stale_control_rows(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))

    def remove_stale_rows(artifact):
        del artifact["strategy_inputs"]["stale_events_negative_control"]["forecasts"]

    run_id = _record_replayable_decision(store, artifact_mutator=remove_stale_rows)

    with pytest.raises(FormalVerificationError, match="stale-control forecast input missing"):
        verify_formal(store, run_id)
    store.close()


@pytest.mark.unit
def test_verify_formal_rejects_unallowlisted_returned_model(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))

    def substitute_model(artifact):
        artifact["champion"]["response_metadata"]["model_name"] = "other-model"

    run_id = _record_replayable_decision(store, artifact_mutator=substitute_model)

    with pytest.raises(FormalVerificationError, match="returned model is outside"):
        verify_formal(store, run_id)
    store.close()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda bundle: bundle.__setitem__("requested_model", "other-model"),
            "requested model differs from frozen run configuration",
        ),
        (
            lambda bundle: bundle.__setitem__("response_metadata", {}),
            "returned model metadata missing",
        ),
        (
            lambda bundle: bundle.__setitem__("model_id", "model_tampered"),
            "model identity hash mismatch",
        ),
    ],
)
def test_verify_formal_checks_exact_model_metadata(tmp_path, mutation, message):
    store = PaperStore(str(tmp_path / "paper.db"))

    def alter_model_metadata(artifact):
        mutation(artifact["champion"])

    run_id = _record_replayable_decision(store, artifact_mutator=alter_model_metadata)

    with pytest.raises(FormalVerificationError, match=message):
        verify_formal(store, run_id)
    store.close()


@pytest.mark.unit
def test_verify_formal_rejects_llm_envelope_drift(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))

    def expand_completion_budget(artifact):
        artifact["llm_policy"]["max_completion_tokens"] = 20_001

    run_id = _record_replayable_decision(store, artifact_mutator=expand_completion_budget)

    with pytest.raises(FormalVerificationError, match="invocation policy differs"):
        verify_formal(store, run_id)
    store.close()


@pytest.mark.unit
def test_verify_formal_recomputes_every_allocator_target(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))

    def alter_target(artifact):
        artifact["strategy_targets"]["momentum"]["weights"]["AAPL"] = 0.099

    run_id = _record_replayable_decision(store, artifact_mutator=alter_target)

    with pytest.raises(FormalVerificationError, match="momentum target replay mismatch"):
        verify_formal(store, run_id)
    store.close()


@pytest.mark.unit
def test_verify_formal_rejects_server_receipt_before_cutoff_cycle_window(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))

    def move_receipt_before_cycle(artifact):
        coverage = artifact["coverage"]
        coverage["query_slots"][0]["run"]["server_started_utc"] = (
            coverage["cycle_lower_bound_utc"] - 1
        )

    run_id = _record_replayable_decision(store, artifact_mutator=move_receipt_before_cycle)

    with pytest.raises(FormalVerificationError, match="outside the cutoff cycle"):
        verify_formal(store, run_id)
    store.close()


@pytest.mark.unit
def test_verify_formal_rejects_trendnews_in_champion_prompt_evidence(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))

    def inject_collector_only_source(artifact):
        artifact["champion"]["evidence"][0]["source"] = "trendnews"

    run_id = _record_replayable_decision(
        store,
        artifact_mutator=inject_collector_only_source,
    )

    with pytest.raises(FormalVerificationError, match="disallowed evidence source"):
        verify_formal(store, run_id)
    store.close()


@pytest.mark.unit
def test_verify_formal_rejects_first_party_company_launch_evidence(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))

    def inject_company_release(artifact):
        evidence = artifact["champion"]["evidence"][0]
        evidence["publisher_or_author"] = "OpenAI"
        evidence["title"] = "Introducing GPT-X - OpenAI"

    run_id = _record_replayable_decision(store, artifact_mutator=inject_company_release)

    with pytest.raises(FormalVerificationError, match="company-authored evidence"):
        verify_formal(store, run_id)
    store.close()
