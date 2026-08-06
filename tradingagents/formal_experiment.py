"""Formal global-event paper experiment orchestration."""

from __future__ import annotations

import hashlib
import inspect
import math
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from importlib.metadata import version as package_version

import exchange_calendars as xcals
import pandas as pd

from tradingagents import (
    backtest,
    formal_roles,
    formal_runtime,
    global_research,
    llm_guard,
    poller,
)
from tradingagents.adapters.portfolio import LegacyOptimizerForecastWeightPolicy
from tradingagents.compat import portfolio as portfolio_compat
from tradingagents.compat.portfolio import target_from_legacy_weights, target_to_legacy_weights
from tradingagents.dataflows import media_sources, media_store
from tradingagents.dataflows.media_sources import looks_company_authored
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.domain import (
    forecasts as forecast_contracts,
    instruments as instrument_contracts,
    portfolios as portfolio_contracts,
    time as time_contracts,
)
from tradingagents.domain.forecasts import ForecastEstimate, ForecastHorizon
from tradingagents.domain.ids import (
    ForecastId,
    ModelId,
    PortfolioId,
    ProtocolId,
    RunId,
    StrategyId,
    TargetPortfolioId,
)
from tradingagents.domain.instruments import provisional_listing
from tradingagents.domain.portfolios import (
    PortfolioConstraints,
    PortfolioMode,
    TargetContext,
)
from tradingagents.domain.time import AsOf
from tradingagents.global_research import (
    AssetForecast,
    DailyGlobalForecast,
    ForecastBundle,
    GlobalEvent,
    _evidence_id,
    _formal_query_slot,
    _row_order_key,
    bind_receipt_coverage_to_selection,
    build_forecast_prompt,
    evidence_selection_manifest,
    evidence_window,
    formal_evidence_policy_manifest,
    formal_globalnews_selection_coverage,
    invoke_global_forecast,
    is_company_authored_evidence,
    is_formally_eligible_evidence,
    is_independent_editorial_evidence,
    partition_formal_evidence,
    prepare_evidence,
)
from tradingagents.llm_clients import create_llm_client, openai_client
from tradingagents.llm_clients.capabilities import get_capabilities
from tradingagents.llm_guard import LLMCallPolicy, PersistentLLMCallGuard
from tradingagents.portfolio_backtest import (
    _allocate_capped,
    _project_long_only,
    optimize_forecast_weights,
)
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
    canonical_json,
    content_id,
)


class FormalDecisionWindowExpiredError(ValueError):
    """Raised when formal computation reaches or crosses its executable open."""


_FORMAL_FORECAST_POLICY = GLOBAL_EVENT_V2_PROTOCOL["forecast"]
_FORMAL_INVOCATION_POLICY = _FORMAL_FORECAST_POLICY["invocation_policy"]
FORMAL_LLM_SDK_MAX_RETRIES = int(_FORMAL_INVOCATION_POLICY["sdk_max_retries"])
FORMAL_LLM_MAX_PROMPT_BYTES = int(_FORMAL_INVOCATION_POLICY["max_prompt_bytes"])
FORMAL_LLM_PROMPT_BYTES_CEILING = 200_000
FORMAL_LLM_MAX_COMPLETION_TOKENS = int(
    _FORMAL_INVOCATION_POLICY["max_completion_tokens"]
)
FORMAL_LLM_COMPLETION_TOKENS_CEILING = 20_000
FORMAL_LLM_TIMEOUT_SECONDS = int(_FORMAL_INVOCATION_POLICY["timeout_seconds"])
FORMAL_LLM_TIMEOUT_SECONDS_CEILING = 300
FORMAL_COLLECTOR_INTERVAL_SECONDS = int(
    GLOBAL_EVENT_V2_PROTOCOL["evidence"]["query_cycle"]["collector_interval_seconds"]
)
FORMAL_COLLECTOR_CYCLE_START_GRACE_SECONDS = int(
    GLOBAL_EVENT_V2_PROTOCOL["evidence"]["query_cycle"]["cycle_start_grace_seconds"]
)


def _formal_evidence_query_slots(config: dict | None = None) -> list[tuple[str, str]]:
    """Return every configured broad-news query required before activation."""
    themes = GLOBAL_EVENT_V2_PROTOCOL["evidence"]["broad_news_queries"]
    slots = list(dict.fromkeys(
        ("globalnews", f"{theme}:{query}")
        for theme, queries in themes.items()
        for query in queries
    ))
    if config is not None:
        configured = config.get("macro_themes", {})
        configured_slots = list(dict.fromkeys(
            ("globalnews", f"{theme}:{query}")
            for theme, spec in configured.items()
            for query in spec.get("queries", [])
        ))
        if configured_slots != slots:
            raise ValueError("configured broad-news queries differ from the frozen protocol")
    return slots


def _formal_collector_cycle_window(
    cutoff: datetime, interval_seconds: int | None = None
) -> tuple[int, datetime]:
    """Bound evidence receipts to the collector cycle immediately before cutoff."""
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("formal coverage cutoff must be timezone-aware")
    if interval_seconds is None:
        interval_seconds = FORMAL_COLLECTOR_INTERVAL_SECONDS
    if isinstance(interval_seconds, bool) or not isinstance(interval_seconds, int) \
            or interval_seconds != FORMAL_COLLECTOR_INTERVAL_SECONDS:
        raise ValueError(
            "formal collector interval must exactly match the frozen protocol"
        )
    window_seconds = interval_seconds + FORMAL_COLLECTOR_CYCLE_START_GRACE_SECONDS
    return interval_seconds, cutoff.astimezone(timezone.utc) - timedelta(
        seconds=window_seconds
    )


def _formal_coverage(
    media, cutoff: datetime, evidence_query_slots: list[tuple[str, str]],
    *, interval_seconds: int | None = None,
) -> dict:
    """Require every broad-news slot to have a receipt in the cutoff cycle."""
    interval_seconds, lower_bound = _formal_collector_cycle_window(
        cutoff, interval_seconds
    )
    window_seconds = interval_seconds + FORMAL_COLLECTOR_CYCLE_START_GRACE_SECONDS
    coverage = media.coverage_report(
        cutoff.timestamp(),
        GLOBAL_EVENT_V2_PROTOCOL["evidence"]["required_source_groups"],
        max_age_seconds=float(window_seconds),
        expected_query_slots=evidence_query_slots,
        require_lineage_query_slots=evidence_query_slots,
        min_started_utc=lower_bound.timestamp(),
    )
    return {
        **coverage,
        "collector_interval_seconds": interval_seconds,
        "cycle_start_grace_seconds": FORMAL_COLLECTOR_CYCLE_START_GRACE_SECONDS,
        "cycle_lower_bound_utc": lower_bound.timestamp(),
    }


def _formal_selection_coverage(
    selection_manifest: dict, evidence_query_slots: list[tuple[str, str]]
) -> dict:
    """Require useful strict-core news while preserving honest slot absences."""
    expected = [
        query_key
        for provider, query_key in evidence_query_slots
        if provider == "globalnews"
    ]
    if expected != list(global_research.FORMAL_GLOBALNEWS_QUERY_SLOTS):
        raise ValueError("formal evidence slots differ from the frozen selection policy")
    return formal_globalnews_selection_coverage(selection_manifest)


def _finalized_x_cycle_availability(payload: dict) -> dict:
    return {
        "availability_id": content_id(payload, prefix="xavail_"),
        **payload,
    }


def _formal_x_cycle_availability(
    media, cutoff: datetime, candidate_rows: list[dict],
) -> tuple[dict, list[dict]]:
    """Project only exact prior-UTC-day X lineage available by the cutoff."""
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("formal X availability cutoff must be timezone-aware")
    cutoff = cutoff.astimezone(timezone.utc)
    policy = GLOBAL_EVENT_V2_PROTOCOL["evidence"]["x_formal_availability"]
    if (
        policy.get("cycle_kind") != "x-daily"
        or policy.get("period_offset_utc_days") != -1
        or policy.get("eligible_source") != "x"
        or policy.get("cutoff_time_basis") != "server_terminal_utc"
    ):
        raise ValueError("formal X availability policy is unsupported")
    period_date = cutoff.date() + timedelta(
        days=int(policy["period_offset_utc_days"])
    )
    period_key = period_date.isoformat()
    period_instant = datetime.combine(
        period_date, datetime.min.time(), tzinfo=timezone.utc
    ).timestamp()
    spec = poller._x_collection_cycle_spec(
        period_instant,
        int(GLOBAL_EVENT_V2_PROTOCOL["evidence"][
            "max_x_search_requests_per_utc_day"
        ]),
    )
    expected_cycle_id = spec["collection_cycle_id"]
    base = {
        "schema_version": 1,
        "policy": dict(policy),
        "period_key": period_key,
        "expected_collection_cycle_id": expected_cycle_id,
    }
    cycle = media.collection_cycle(expected_cycle_id)
    non_x_rows = [row for row in candidate_rows if row.get("source") != "x"]
    if cycle is None:
        return _finalized_x_cycle_availability({
            **base,
            "state": "missing",
            "collection_cycle_id": None,
            "manifest_id": None,
            "cycle_manifest": None,
            "collector_semantics_id": spec["identity"]["collector_semantics_id"],
            "collector_build_id": None,
            "server_started_utc": None,
            "server_terminal_utc": None,
            "eligible_lineage": [],
        }), non_x_rows
    if not cycle.get("identity_valid") or cycle.get("identity") != spec["identity"]:
        raise ValueError("formal X cycle identity is invalid")

    server_started = cycle.get("server_started_utc")
    server_terminal = cycle.get("server_terminal_utc")
    trusted_terminal = (
        cycle.get("status") in {"complete", "incomplete"}
        and cycle.get("manifest_valid") is True
        and isinstance(server_started, (int, float))
        and not isinstance(server_started, bool)
        and math.isfinite(float(server_started))
        and isinstance(server_terminal, (int, float))
        and not isinstance(server_terminal, bool)
        and math.isfinite(float(server_terminal))
        and float(server_started) <= float(server_terminal) <= cutoff.timestamp()
        and isinstance(cycle.get("collector_build_id"), str)
        and media_store._COLLECTOR_BUILD_ID.fullmatch(
            cycle["collector_build_id"]
        ) is not None
    )
    observed_manifest = cycle.get("manifest") if trusted_terminal else None
    if trusted_terminal and (
        observed_manifest.get("schema_version") != 2
        or observed_manifest.get("server_started_utc") != server_started
        or observed_manifest.get("server_terminal_utc") != server_terminal
        or observed_manifest.get("collector_build_id")
        != cycle.get("collector_build_id")
    ):
        raise ValueError("formal X cycle manifest omits server/build provenance")
    provenance = {
        **base,
        "collection_cycle_id": expected_cycle_id,
        "manifest_id": cycle.get("manifest_id") if trusted_terminal else None,
        "cycle_manifest": observed_manifest,
        "collector_semantics_id": cycle.get("collector_semantics_id"),
        "collector_build_id": (
            cycle.get("collector_build_id") if trusted_terminal else None
        ),
        "server_started_utc": server_started if trusted_terminal else None,
        "server_terminal_utc": server_terminal if trusted_terminal else None,
    }
    if not trusted_terminal or cycle.get("status") != "complete":
        return _finalized_x_cycle_availability({
            **provenance, "state": "incomplete", "eligible_lineage": [],
        }), non_x_rows

    receipt_lineage = media.collection_cycle_formal_lineage(
        expected_cycle_id, provider=policy["eligible_source"]
    )
    manifest_x_lineage = {
        (slot.get("fetch_run_id"), raw_content_id)
        for slot in observed_manifest.get("slot_receipts", [])
        if isinstance(slot, dict) and slot.get("provider") == policy["eligible_source"]
        for raw_content_id in slot.get("raw_content_ids", [])
    }
    if any(
        (item.get("fetch_run_id"), item.get("raw_content_id"))
        not in manifest_x_lineage
        for item in receipt_lineage
    ):
        raise ValueError("formal X lineage is absent from the cycle manifest")
    receipt_runs_by_pair: dict[tuple[str, str], set[str]] = {}
    for item in receipt_lineage:
        pair = (item["evidence_id"], item["raw_content_id"])
        receipt_runs_by_pair.setdefault(pair, set()).add(item["fetch_run_id"])

    eligible_rows: list[dict] = []
    eligible_pairs: set[tuple[str, str]] = set()
    for row in candidate_rows:
        if row.get("source") != policy["eligible_source"]:
            continue
        pair = (_evidence_id(row), global_research._raw_content_id(row))
        if pair in receipt_runs_by_pair and is_formally_eligible_evidence(
            row, as_of_utc=cutoff.timestamp()
        ):
            eligible_rows.append(row)
            eligible_pairs.add(pair)
    eligible_lineage = [
        {
            "evidence_id": evidence,
            "raw_content_id": raw,
            "fetch_run_ids": sorted(receipt_runs_by_pair[(evidence, raw)]),
        }
        for evidence, raw in sorted(eligible_pairs)
    ]
    state = (
        "complete_with_eligible" if eligible_lineage
        else "complete_zero_eligible"
    )
    availability = _finalized_x_cycle_availability({
        **provenance, "state": state, "eligible_lineage": eligible_lineage,
    })
    return availability, non_x_rows + eligible_rows


def _bind_x_availability_to_selection(
    selection_manifest: dict, availability: dict,
) -> dict:
    """Content-bind the exact X availability projection into formal selection."""
    if selection_manifest.get("schema_version") != 2:
        raise ValueError("formal selection manifest version is unsupported")
    payload = {
        key: value
        for key, value in selection_manifest.items()
        if key != "manifest_id"
    }
    payload["schema_version"] = 3
    payload["x_cycle_availability"] = availability
    return {"manifest_id": content_id(payload, prefix="selection_"), **payload}


def _formal_invocation_stage_order(
    decision_date: str, stages: list[str] | tuple[str, ...]
) -> list[str]:
    """Return the preregistered, outcome-blind order for paid forecast calls."""
    try:
        parsed_date = date.fromisoformat(decision_date)
    except (TypeError, ValueError) as exc:
        raise ValueError("formal invocation order requires an ISO decision date") from exc
    if parsed_date.isoformat() != decision_date:
        raise ValueError("formal invocation order requires a canonical ISO decision date")
    if not isinstance(stages, (list, tuple)) or not stages:
        raise ValueError("formal invocation order requires at least one stage")
    if any(not isinstance(stage, str) or not stage for stage in stages) \
            or len(set(stages)) != len(stages):
        raise ValueError("formal invocation stages must be unique non-empty strings")

    policy = _FORMAL_FORECAST_POLICY["invocation_order_policy"]
    available = policy.get("available_stages")
    if not isinstance(available, list) \
            or any(not isinstance(stage, str) or not stage for stage in available) \
            or len(set(available)) != len(available) \
            or "champion" not in available:
        raise ValueError("formal invocation-order policy is malformed")
    if "champion" not in stages or not set(stages).issubset(available):
        raise ValueError("formal invocation stages differ from the frozen policy")
    cycle = policy.get("permutation_cycle")
    expected_permutations = math.factorial(len(available))
    if not isinstance(cycle, list) or len(cycle) != expected_permutations \
            or any(
                not isinstance(permutation, list)
                or len(permutation) != len(available)
                or set(permutation) != set(available)
                for permutation in cycle
            ) \
            or len({tuple(permutation) for permutation in cycle}) != len(cycle):
        raise ValueError("formal invocation-order permutation cycle is malformed")
    calendar_name = policy.get("calendar")
    calendar_start = policy.get("calendar_range_start")
    calendar_end = policy.get("calendar_range_end")
    epoch_session = policy.get("epoch_session")
    if any(
        not isinstance(value, str) or not value
        for value in (calendar_name, calendar_start, calendar_end, epoch_session)
    ):
        raise ValueError("formal invocation-order calendar policy is malformed")
    try:
        calendar = xcals.get_calendar(
            calendar_name, start=calendar_start, end=calendar_end
        )
        if not calendar.is_session(epoch_session) \
                or not calendar.is_session(decision_date):
            raise ValueError("formal invocation date is not a frozen calendar session")
        session_offset = calendar.sessions_distance(
            epoch_session, decision_date
        ) - 1
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "formal invocation date is outside the frozen calendar policy"
        ) from exc
    if session_offset < 0:
        raise ValueError("formal invocation date precedes the frozen calendar epoch")
    scheduled = cycle[session_offset % len(cycle)]
    required = set(stages)
    return [stage for stage in scheduled if stage in required]


def _without_public_reaction_bundle(
    champion: ForecastBundle,
    champion_rows: list[dict],
    without_reaction_rows: list[dict],
    invoke: Callable[[list[dict]], ForecastBundle],
) -> ForecastBundle:
    """Reuse the champion when the ablation has the identical bounded input."""
    if prepare_evidence(champion_rows) == prepare_evidence(without_reaction_rows):
        return champion
    return invoke(without_reaction_rows)


def _checked_before_open(
    clock: Callable[[], datetime], next_open: datetime, *, stage: str
) -> datetime:
    """Read a live/injected clock and fail closed at the executable boundary."""
    observed = clock()
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("formal decision clock must return a timezone-aware datetime")
    observed = observed.astimezone(timezone.utc)
    if observed >= next_open:
        raise FormalDecisionWindowExpiredError(
            f"formal {stage} crossed the next open; refusing a retroactive decision"
        )
    return observed


def _provider_kwargs(config: dict) -> dict:
    provider = config["llm_provider"].lower()
    kwargs = {}
    keys = {
        "google": "google_thinking_level",
        "openai": "openai_reasoning_effort",
        "anthropic": "anthropic_effort",
    }
    key = keys.get(provider)
    if key and config.get(key):
        kwargs["thinking_level" if provider == "google" else "effort" if provider == "anthropic"
               else "reasoning_effort"] = config[key]
    for source, target in (("temperature", "temperature"), ("llm_max_retries", "max_retries")):
        if config.get(source) is not None:
            kwargs[target] = config[source]
    return kwargs


def create_forecast_llm(
    config: dict | None = None,
    *,
    max_completion_tokens: int = FORMAL_LLM_MAX_COMPLETION_TOKENS,
    timeout_seconds: int = FORMAL_LLM_TIMEOUT_SECONDS,
):
    # The persistent budget counts application invocations. Disable opaque SDK
    # retries so one reservation cannot silently fan out into several paid calls.
    config = dict(config or DEFAULT_CONFIG)
    config["llm_max_retries"] = FORMAL_LLM_SDK_MAX_RETRIES
    return create_llm_client(
        provider=config["llm_provider"], model=config["quick_think_llm"],
        base_url=config.get("backend_url"),
        max_completion_tokens=max_completion_tokens,
        timeout=timeout_seconds,
        **_provider_kwargs(config),
    ).get_llm()


def _formal_llm_policy(args) -> LLMCallPolicy:
    """Build the explicit production policy; missing values fail closed."""
    return LLMCallPolicy.from_values(
        getattr(args, "llm_model_allowlist", None),
        getattr(args, "llm_max_calls_per_decision", None),
        getattr(args, "llm_max_calls_per_utc_day", None),
    )


def _formal_prompt_limit(args) -> int:
    value = getattr(args, "llm_max_prompt_bytes", FORMAL_LLM_MAX_PROMPT_BYTES)
    if isinstance(value, bool) or not isinstance(value, int) or not (
        1 <= value <= FORMAL_LLM_PROMPT_BYTES_CEILING
    ):
        raise ValueError(
            "formal LLM prompt-byte limit must be between 1 and "
            f"{FORMAL_LLM_PROMPT_BYTES_CEILING}"
        )
    if value != FORMAL_LLM_MAX_PROMPT_BYTES:
        raise ValueError("formal LLM prompt-byte limit differs from the frozen protocol")
    return value


def _bounded_positive_int(args, name: str, default: int, ceiling: int, label: str) -> int:
    value = getattr(args, name, default)
    if isinstance(value, bool) or not isinstance(value, int) or not (1 <= value <= ceiling):
        raise ValueError(f"formal {label} must be between 1 and {ceiling}")
    return value


def _formal_completion_limit(args) -> int:
    value = _bounded_positive_int(
        args, "llm_max_completion_tokens", FORMAL_LLM_MAX_COMPLETION_TOKENS,
        FORMAL_LLM_COMPLETION_TOKENS_CEILING, "LLM completion-token limit",
    )
    if value != FORMAL_LLM_MAX_COMPLETION_TOKENS:
        raise ValueError("formal LLM completion-token limit differs from the frozen protocol")
    return value


def _formal_timeout(args) -> int:
    value = _bounded_positive_int(
        args, "llm_timeout_seconds", FORMAL_LLM_TIMEOUT_SECONDS,
        FORMAL_LLM_TIMEOUT_SECONDS_CEILING, "LLM timeout seconds",
    )
    if value != FORMAL_LLM_TIMEOUT_SECONDS:
        raise ValueError("formal LLM timeout differs from the frozen protocol")
    return value


def _reported_output_tokens(usage: dict | None) -> int | None:
    """Normalize common provider usage keys without estimating missing usage."""
    payload = usage or {}
    for key in ("output_tokens", "completion_tokens"):
        value = payload.get(key)
        if type(value) is int and value >= 0:
            return value
    return None


def _invoke_guarded_forecast(
    *, guard: PersistentLLMCallGuard, llm, provider: str, requested_model: str,
    decision_date: str, rows: list[dict], universe: list[str],
    max_prompt_bytes: int = FORMAL_LLM_MAX_PROMPT_BYTES,
    max_completion_tokens: int = FORMAL_LLM_MAX_COMPLETION_TOKENS,
    invocation_stage: str = "forecast",
    artifact_recorder=None,
) -> ForecastBundle:
    """Bound input/spend, record the attempt, invoke once, and authenticate output."""
    evidence = prepare_evidence(rows)
    if not evidence:
        raise ValueError("global-event forecast requires point-in-time evidence")
    prompt = build_forecast_prompt(
        decision_date=decision_date, evidence=evidence, universe=universe
    )
    prompt_bytes = len(prompt.encode("utf-8"))
    if prompt_bytes > max_prompt_bytes:
        raise ValueError(
            f"formal LLM prompt exceeds the {max_prompt_bytes}-byte cost ceiling"
        )
    if isinstance(max_completion_tokens, bool) or not isinstance(max_completion_tokens, int) \
            or not (1 <= max_completion_tokens <= FORMAL_LLM_COMPLETION_TOKENS_CEILING):
        raise ValueError("formal LLM completion-token limit is invalid")
    if not isinstance(invocation_stage, str) or not invocation_stage:
        raise ValueError("formal LLM invocation stage must be non-empty")
    input_bundle_id = content_id(
        {
            "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
            "decision_date": decision_date,
            "universe": universe,
            "evidence": evidence,
        },
        prefix="input_",
    )
    if artifact_recorder is None \
            or not callable(getattr(artifact_recorder, "reserve_llm_invocation", None)) \
            or not callable(
                getattr(artifact_recorder, "record_llm_invocation_result", None)
            ):
        raise ValueError(
            "formal LLM invocation requires an atomic reservation/result recorder"
        )
    reservation_spec = guard.reservation_spec(
        provider,
        requested_model,
        decision_date=decision_date,
        stage=invocation_stage,
        input_bundle_id=input_bundle_id,
        prompt_id=content_id({"prompt": prompt}, prefix="prompt_"),
        prompt_bytes=prompt_bytes,
        max_prompt_bytes=max_prompt_bytes,
        max_completion_tokens=max_completion_tokens,
    )
    atomic_reservation = artifact_recorder.reserve_llm_invocation(reservation_spec)
    if not isinstance(atomic_reservation, dict) \
            or set(atomic_reservation) != {
                "reservation_counts",
                "reservation_receipt",
                "reservation_artifact_id",
            }:
        raise RuntimeError("formal LLM atomic reservation result is malformed")
    reservation_receipt = atomic_reservation["reservation_receipt"]
    reservation_artifact_id = atomic_reservation["reservation_artifact_id"]
    if (
        not isinstance(reservation_receipt, dict)
        or reservation_receipt.get("reservation_counts")
        != atomic_reservation["reservation_counts"]
        or reservation_receipt.get("prompt_id") != reservation_spec["prompt_id"]
        or any(
                reservation_receipt.get(field) != reservation_spec[field]
                for field in (
                    "scope",
                    "run_id",
                    "decision_date",
                    "stage",
                    "provider",
                    "requested_model",
                    "input_bundle_id",
                    "prompt_bytes",
                    "max_prompt_bytes",
                    "max_completion_tokens",
                )
        )
        or reservation_receipt.get("max_calls_per_decision")
        != guard.policy.max_calls_per_decision
        or reservation_receipt.get("max_calls_per_utc_day")
        != guard.policy.max_calls_per_utc_day
        or not all(
            isinstance(reservation_receipt.get(field), str)
            and bool(reservation_receipt[field])
            for field in (
                "decision_counter_key",
                "daily_counter_key",
                "utc_day",
            )
        )
    ):
        raise RuntimeError("formal LLM reservation receipt differs from its request")
    invocation_identity = {
        field: reservation_receipt[field]
        for field in (
            "scope",
            "run_id",
            "decision_date",
            "ordinal",
            "stage",
            "provider",
            "requested_model",
            "input_bundle_id",
        )
    }
    invocation_id = reservation_receipt.get("invocation_id")
    if not isinstance(invocation_id, str) or invocation_id != content_id(
        invocation_identity, prefix="invocation_"
    ) or reservation_artifact_id != content_id(
        {
            "artifact_type": "llm_invocation_reserved",
            "content": reservation_receipt,
        },
        prefix="artifact_",
    ):
        raise RuntimeError("formal LLM reservation identity is malformed")
    started_monotonic = time.monotonic()
    try:
        bundle = invoke_global_forecast(
            llm=llm, provider=provider, requested_model=requested_model,
            decision_date=decision_date, rows=rows, universe=universe,
        )
        if bundle.input_bundle_id != input_bundle_id \
                or bundle.provider != provider \
                or bundle.requested_model != requested_model:
            raise ValueError("formal LLM bundle identity does not match its reservation")
        returned_identity = guard.require_returned_model(
            provider, requested_model, bundle.response_metadata
        )
        if not isinstance(bundle.response_id, str) or not bundle.response_id.strip():
            raise ValueError("formal LLM response omitted its immutable response ID")
        output_tokens = _reported_output_tokens(bundle.usage_metadata)
        if output_tokens is not None and output_tokens > max_completion_tokens:
            raise ValueError("formal LLM reported output above its completion-token ceiling")
        bundle_payload = bundle.as_dict()
        if not isinstance(bundle_payload, dict):
            raise ValueError("formal LLM bundle projection is malformed")
        forecast_bundle_id = content_id(bundle_payload, prefix="bundle_")
    except Exception as exc:
        completed = datetime.now(timezone.utc)
        failed_receipt = {
            "schema_version": 2,
            "invocation_id": invocation_id,
            **invocation_identity,
            "reservation_artifact_id": reservation_artifact_id,
            "status": "failed",
            "error_type": type(exc).__name__,
            "completed_utc": completed.isoformat(),
            "elapsed_ms": round((time.monotonic() - started_monotonic) * 1000),
        }
        try:
            artifact_recorder.record_llm_invocation_result(
                failed_receipt, completed.timestamp()
            )
        except Exception as receipt_exc:
            exc.add_note(
                "formal failed-invocation result receipt could not be appended: "
                f"{type(receipt_exc).__name__}"
            )
        raise
    completed = datetime.now(timezone.utc)
    artifact_recorder.record_llm_invocation_result(
        {
            "schema_version": 2,
            "invocation_id": invocation_id,
            **invocation_identity,
            "reservation_artifact_id": reservation_artifact_id,
            "status": "success",
            "returned_model": returned_identity,
            "model_id": bundle.model_id,
            "response_id": bundle.response_id,
            "usage_metadata": bundle.usage_metadata,
            "forecast_bundle_id": forecast_bundle_id,
            "completed_utc": completed.isoformat(),
            "elapsed_ms": round((time.monotonic() - started_monotonic) * 1000),
        },
        completed.timestamp(),
    )
    return bundle


def _forecast_rows(bundle: ForecastBundle) -> list[dict]:
    return [forecast.model_dump(mode="json") for forecast in bundle.forecast.forecasts]


def _neutral_forecasts(universe: list[str], rationale: str) -> list[dict]:
    return [AssetForecast(
        ticker=ticker, expected_excess_return_bps=0.0, probability_positive=0.5,
        confidence=0.0, abstain=True, event_ids=[], rationale=rationale,
    ).model_dump(mode="json") for ticker in universe]


def _market_rows(
    universe: list[str], decision_date: str
) -> tuple[list[dict], list[dict], dict[str, list[dict]]]:
    """Point-in-time inverse-volatility and momentum signals for shadow portfolios."""
    start = (datetime.strptime(decision_date, "%Y-%m-%d") - timedelta(days=60)).strftime(
        "%Y-%m-%d"
    )
    inverse_vol = []
    momentum = []
    snapshots = {}
    cutoff_session = date.fromisoformat(decision_date)
    for ticker in universe:
        frame = backtest._load_prices(ticker, start, decision_date, 1)
        # Price vendors may return either a naive session index or an
        # exchange-localized one. Compare exchange session dates directly;
        # converting the cutoff to a naive Timestamp makes pandas reject the
        # latter, while converting everything to UTC can shift midnight labels
        # into the prior session.
        session_dates = pd.DatetimeIndex(pd.to_datetime(frame.index)).date
        eligible = frame.loc[[session <= cutoff_session for session in session_dates]]
        closes = [float(value) for value in eligible["Close"].tail(21)]
        snapshots[ticker] = [
            {"date": pd.Timestamp(index).date().isoformat(),
             "open": float(row["Open"]), "close": float(row["Close"])}
            for index, row in eligible.tail(21).iterrows()
        ]
        returns = [closes[index] / closes[index - 1] - 1.0 for index in range(1, len(closes))]
        volatility = (
            math.sqrt(sum((value - sum(returns) / len(returns)) ** 2 for value in returns)
                      / (len(returns) - 1)) if len(returns) >= 2 else None
        )
        inverse_edge = min(500.0, 5.0 / volatility) if volatility and volatility > 0 else 0.0
        momentum_edge = max(-500.0, min(500.0, (closes[-1] / closes[0] - 1.0) * 10_000)) \
            if len(closes) >= 2 else 0.0
        for target, edge, label in (
            (inverse_vol, inverse_edge, "point-in-time inverse-volatility baseline"),
            (momentum, momentum_edge, "point-in-time 20-session momentum baseline"),
        ):
            target.append({
                "ticker": ticker, "expected_excess_return_bps": edge,
                "probability_positive": 0.6 if edge > 0 else 0.4 if edge < 0 else 0.5,
                "confidence": 1.0, "abstain": edge == 0, "event_ids": [],
                "rationale": label,
            })
    return inverse_vol, momentum, snapshots


def _shuffle_forecasts(rows: list[dict]) -> list[dict]:
    """Deterministic cross-sectional rotation registered as a negative control."""
    ordered = sorted(rows, key=lambda row: row["ticker"])
    values = [
        (
            row["expected_excess_return_bps"],
            row["probability_positive"],
            row["confidence"],
            row["abstain"],
            list(row.get("event_ids", [])),
        )
        for row in ordered
    ]
    rotated = values[1:] + values[:1]
    return [{
        **row,
        "expected_excess_return_bps": rotated[index][0],
        "probability_positive": rotated[index][1],
        "confidence": rotated[index][2],
        "abstain": rotated[index][3],
        "event_ids": rotated[index][4],
        "rationale": "pre-registered deterministic ticker-rotation negative control",
    } for index, row in enumerate(ordered)]


def _target(
    store,
    run_id: str,
    strategy: str,
    rows: list[dict],
    universe: list[str],
    *,
    cutoff: datetime,
    next_open: datetime,
    entry_date: str,
    created_at: datetime,
    model_id: str,
    current_weights: dict[str, float] | None = None,
) -> dict:
    """Run the legacy optimizer through a fail-closed canonical parity seam."""
    protocol = GLOBAL_EVENT_V2_PROTOCOL["portfolio"]
    current = (
        store.latest_strategy_weights(run_id, strategy, universe)
        if current_weights is None
        else {ticker: float(weight) for ticker, weight in current_weights.items()}
    )
    if set(current) != set(universe):
        raise ValueError("current strategy weights must exactly match the formal universe")
    result = optimize_forecast_weights(
        rows, current_weights=current,
        sectors=GLOBAL_EVENT_V2_PROTOCOL["universe"]["sectors"],
        gross_limit=protocol["gross_limit"], max_weight=protocol["max_weight"],
        max_sector_weight=protocol["max_sector_weight"],
        turnover_hurdle_bps=protocol["turnover_hurdle_bps"],
        minimum_trade_weight=protocol["minimum_trade_weight"],
    )
    legacy = {"weights": result.weights, "diagnostics": asdict(result)}

    listings = tuple(provisional_listing(ticker) for ticker in universe)
    by_symbol = {listing.symbol: listing.instrument_id for listing in listings}
    as_of = AsOf(
        decision_cutoff=cutoff,
        calendar="XNYS",
        timezone_name="America/New_York",
        entry_session=date.fromisoformat(entry_date),
    )
    context = TargetContext(
        target_portfolio_id=TargetPortfolioId(content_id(
            {
                "run_id": run_id,
                "strategy": strategy,
                "cutoff": cutoff.isoformat(),
                "current_weights": current,
                "portfolio_constraints": protocol,
                "allocator": "legacy-forecast-optimizer-v1",
                "rows": rows,
                "result": legacy,
            },
            prefix="target_",
        )),
        portfolio_id=PortfolioId(f"formal:{run_id}:{strategy}"),
        run_id=RunId(run_id),
        strategy_id=StrategyId(strategy),
        protocol_id=ProtocolId(GLOBAL_EVENT_V2_PROTOCOL_ID),
        as_of=as_of,
        effective_at=next_open,
        created_at=created_at,
        producer="formal-global-v2",
    )
    forecasts = tuple(
        ForecastEstimate(
            forecast_id=ForecastId(content_id(
                {
                    "run_id": run_id,
                    "strategy": strategy,
                    "cutoff": cutoff.isoformat(),
                    "row": row,
                },
                prefix="forecast_",
            )),
            instrument_id=by_symbol[str(row["ticker"]).upper()],
            run_id=RunId(run_id),
            protocol_id=ProtocolId(GLOBAL_EVENT_V2_PROTOCOL_ID),
            model_id=ModelId(model_id),
            as_of=as_of,
            horizon=ForecastHorizon.NEXT_OPEN_TO_OPEN,
            expected_excess_return_bps=row["expected_excess_return_bps"],
            probability_positive=row["probability_positive"],
            confidence=row["confidence"],
            abstain=row["abstain"],
            event_ids=tuple(row.get("event_ids", ())),
            rationale=row["rationale"],
        )
        for row in rows
    )
    constraints = PortfolioConstraints(
        mode=PortfolioMode.LONG_ONLY,
        gross_limit=protocol["gross_limit"],
        max_weight=protocol["max_weight"],
        max_sector_weight=protocol["max_sector_weight"],
        turnover_hurdle_bps=protocol["turnover_hurdle_bps"],
        minimum_trade_weight=protocol["minimum_trade_weight"],
    )
    canonical_target = LegacyOptimizerForecastWeightPolicy().allocate(
        forecasts=forecasts,
        current_weights={by_symbol[ticker]: weight for ticker, weight in current.items()},
        listings=listings,
        sectors={
            by_symbol[ticker]: GLOBAL_EVENT_V2_PROTOCOL["universe"]["sectors"][ticker]
            for ticker in universe
        },
        constraints=constraints,
        context=context,
    )
    round_trip = target_to_legacy_weights(canonical_target)
    if round_trip != legacy:
        raise RuntimeError(
            f"canonical target parity failed for {run_id}/{strategy}; refusing to persist"
        )
    return round_trip


def formal_decision_semantics() -> dict:
    """Content-address the exact code that can change a formal target.

    The protocol describes the economic contract, while this manifest catches
    an implementation edit made without the required protocol revision. It is
    deliberately narrower than the whole image so logging, alerting, and other
    behavior-preserving operational changes do not reset a trial.
    """
    from tradingagents import paper_trading as paper_ledger

    # Every indirect helper is explicit. Hashing only the public wrapper is not
    # sufficient: changing (for example) X normalization, history SQL, model
    # transport kwargs, or a legacy-conversion helper can alter a target while
    # leaving the wrapper's source text untouched.
    components = {
        "global_event_schema": GlobalEvent,
        "global_event_onset_validator": GlobalEvent.canonicalize_onset_utc,
        "asset_forecast_schema": AssetForecast,
        "daily_forecast_schema": DailyGlobalForecast,
        "forecast_bundle_schema": ForecastBundle,
        "canonical_forecast_schema": forecast_contracts.ForecastEstimate,
        "canonical_asof_schema": time_contracts.AsOf,
        "canonical_listing_schema": instrument_contracts.ListingRef,
        "canonical_target_allocation_schema": portfolio_contracts.TargetAllocation,
        "canonical_allocation_diagnostics_schema": (
            portfolio_contracts.AllocationDiagnostics
        ),
        "canonical_target_portfolio_schema": portfolio_contracts.TargetPortfolio,
        "canonical_json_encoding": canonical_json,
        "content_identity": content_id,
        "evidence_policy_manifest": formal_evidence_policy_manifest,
        "evidence_window": evidence_window,
        "evidence_history_bucket_limits": global_research._history_bucket_limits_manifest,
        "evidence_history_bucket_counts": global_research._history_bucket_counts,
        "evidence_history_bucket_validation": (
            global_research._validate_history_bucket_counts
        ),
        "evidence_selection_manifest": evidence_selection_manifest,
        "globalnews_selection_coverage": formal_globalnews_selection_coverage,
        "receipt_selection_binding": bind_receipt_coverage_to_selection,
        "coverage_query_slots": _formal_evidence_query_slots,
        "collector_semantics_manifest_builder": poller.collector_semantics_manifest,
        "x_collection_cycle_spec": poller._x_collection_cycle_spec,
        "collection_cycle_spec": media_store.collection_cycle_spec,
        "collection_cycle_manifest": media_store._collection_cycle_manifest,
        "collection_cycle_manifest_attachment": (
            media_store._attach_collection_cycle_payloads
        ),
        "collection_cycle_relation_verification": (
            media_store._verify_collection_cycle_relations
        ),
        "collection_cycle_item_verification": media_store._verified_cycle_item_rows,
        "collection_cycle_formal_lineage_replay": (
            media_store._verified_cycle_formal_lineage
        ),
        "sqlite_collection_cycle_query": media_store.SqliteMediaStore.collection_cycle,
        "postgres_collection_cycle_query": (
            media_store.SqlAlchemyMediaStore.collection_cycle
        ),
        "sqlite_collection_cycle_formal_lineage": (
            media_store.SqliteMediaStore.collection_cycle_formal_lineage
        ),
        "postgres_collection_cycle_formal_lineage": (
            media_store.SqlAlchemyMediaStore.collection_cycle_formal_lineage
        ),
        "coverage_cycle_window": _formal_collector_cycle_window,
        "coverage_reason": media_store._coverage_reason,
        "coverage_result": media_store._coverage_result,
        "receipt_id_encoding": media_store._encoded_formal_evidence_ids,
        "receipt_id_projection": media_store._attach_formal_evidence_ids,
        "receipt_terminal_validation": media_store._validate_fetch_completion,
        "receipt_terminal_reason": media_store._terminal_receipt_reason,
        "media_identity_conflict": media_store._media_rows_conflict,
        "media_batch_coherence": media_store._validate_batch_media_coherence,
        "sqlite_coverage_query": media_store.SqliteMediaStore.coverage_report,
        "postgres_coverage_query": media_store.SqlAlchemyMediaStore.coverage_report,
        "coverage_receipt_gate": _formal_coverage,
        "selection_coverage_gate": _formal_selection_coverage,
        "x_availability_finalization": _finalized_x_cycle_availability,
        "x_availability_projection": _formal_x_cycle_availability,
        "x_availability_selection_binding": _bind_x_availability_to_selection,
        "evidence_identity": _evidence_id,
        "raw_evidence_identity": global_research._raw_content_id,
        "text_identity": global_research._text_sha256,
        "stable_bucket_assignment": global_research._stable_bucket_assignment,
        "evidence_matching_query_slots": global_research._formal_query_slots,
        "evidence_query_slot": _formal_query_slot,
        "evidence_ordering": _row_order_key,
        "evidence_utf8_bounding": global_research._utf8_prefix,
        "formal_metadata_projection": global_research._formal_metadata_projection,
        "prompt_evidence_projection": global_research._prompt_evidence_projection,
        "company_authorship_classifier": looks_company_authored,
        "company_authorship_boundary": is_company_authored_evidence,
        "publisher_normalization": global_research._publisher_key,
        "independent_editorial_boundary": is_independent_editorial_evidence,
        "formal_evidence_ineligibility": (
            global_research.formal_evidence_ineligibility_reason
        ),
        "formal_evidence_eligibility": is_formally_eligible_evidence,
        "x_author_identity": global_research._normalized_x_author,
        "x_text_normalization": global_research._normalized_x_text,
        "x_matching_topics": global_research._matching_x_topics,
        "x_assigned_topic": global_research._assigned_x_topic,
        "x_nonnegative_integer": global_research._nonnegative_int,
        "x_engagement_score": global_research._x_engagement_score,
        "x_ineligibility": global_research._x_formal_ineligibility_reason,
        "x_ranking": global_research._x_rank_key,
        "x_selection": global_research._select_x_rows,
        "evidence_partition": partition_formal_evidence,
        "evidence_preparation": prepare_evidence,
        "forecast_prompt": build_forecast_prompt,
        "forecast_validation": invoke_global_forecast,
        "decision_window_guard": _checked_before_open,
        "provider_kwargs": _provider_kwargs,
        "forecast_client_factory": create_forecast_llm,
        "llm_policy_builder": _formal_llm_policy,
        "llm_prompt_limit": _formal_prompt_limit,
        "bounded_positive_integer": _bounded_positive_int,
        "llm_completion_limit": _formal_completion_limit,
        "llm_timeout": _formal_timeout,
        "llm_usage_normalization": _reported_output_tokens,
        "llm_invocation_stage_order": _formal_invocation_stage_order,
        "llm_invocation": _invoke_guarded_forecast,
        "llm_model_key": llm_guard.model_key,
        "llm_call_policy": LLMCallPolicy,
        "llm_call_guard": PersistentLLMCallGuard,
        "llm_reservation_spec": PersistentLLMCallGuard.reservation_spec,
        "atomic_llm_reservation": paper_ledger.PaperStore.reserve_llm_invocation,
        "llm_frozen_budget_policy": paper_ledger.PaperStore._frozen_llm_budget_policy,
        "sqlite_budget_reservation": (
            paper_ledger.PaperStore._reserve_sqlite_formal_llm_budget
        ),
        "postgres_budget_reservation": (
            paper_ledger.PaperStore._reserve_postgres_formal_llm_budget
        ),
        "llm_reservation_preinsert_boundary": (
            paper_ledger.PaperStore._before_llm_reservation_artifact_insert
        ),
        "llm_result_persistence": (
            paper_ledger.PaperStore.record_llm_invocation_result
        ),
        "llm_reservation_transaction": (
            paper_ledger.PaperStore._trial_lifecycle_transaction
        ),
        "runtime_authorization_row_validation": (
            paper_ledger.PaperStore._validated_authorization_row
        ),
        "runtime_authorization_gate": (
            paper_ledger.PaperStore.require_formal_runtime_authorization
        ),
        "runtime_authorization_context": (
            paper_ledger.PaperStore.authenticated_formal_runtime
        ),
        "runtime_role_preflight_validation": (
            formal_roles.validate_runtime_role_preflight
        ),
        "runtime_component_configuration": (
            formal_runtime.paper_component_configuration
        ),
        "formal_decision_state_projection": (
            paper_ledger.PaperStore.formal_decision_state
        ),
        "formal_decision_weight_projection": (
            paper_ledger.PaperStore.formal_decision_weight_snapshots
        ),
        "formal_decision_slot_validation": (
            paper_ledger.PaperStore._validate_formal_decision_slot
        ),
        "formal_decision_slot_projection_validation": (
            formal_roles.validate_decision_slot_projection
        ),
        "llm_client_factory": create_llm_client,
        "openai_client_configuration": openai_client.OpenAIClient.get_llm,
        "openai_structured_output": (
            openai_client.NormalizedChatOpenAI.with_structured_output
        ),
        "model_capability_resolution": get_capabilities,
        "forecast_row_projection": _forecast_rows,
        "sqlite_evidence_history": media_store.SqliteMediaStore.history_asof,
        "postgres_evidence_history": media_store.SqlAlchemyMediaStore.history_asof,
        "public_reaction_ablation": _without_public_reaction_bundle,
        "neutral_control": _neutral_forecasts,
        "market_history_loader": backtest._load_prices,
        "market_controls": _market_rows,
        "shuffle_control": _shuffle_forecasts,
        "allocator_capped_budget": _allocate_capped,
        "allocator_projection": _project_long_only,
        "legacy_optimizer": optimize_forecast_weights,
        "canonical_allocator": LegacyOptimizerForecastWeightPolicy.allocate,
        "legacy_symbol_validation": portfolio_compat._legacy_symbol,
        "legacy_float_validation": portfolio_compat._legacy_float,
        "legacy_listing_index": portfolio_compat._listing_index,
        "legacy_to_canonical_target": target_from_legacy_weights,
        "canonical_to_legacy_target": target_to_legacy_weights,
        "portfolio_constraints_schema": PortfolioConstraints,
        "target_context_schema": TargetContext,
        "listing_identity": provisional_listing,
        "target_construction": _target,
        "formal_operation_lock": paper_ledger.formal_operation_lock,
        "sqlite_formal_operation_lock": (
            paper_ledger._sqlite_formal_operation_lock
        ),
        "postgres_formal_operation_lock": (
            paper_ledger._postgres_formal_operation_lock
        ),
        "formal_decision_locked_orchestration": _decide_formal_locked,
        "formal_decision_orchestration": decide_formal,
    }
    source_hashes = {
        name: hashlib.sha256(
            inspect.getsource(component).encode("utf-8")
        ).hexdigest()
        for name, component in components.items()
    }
    openai_spec = openai_client.OPENAI_COMPATIBLE_PROVIDERS["openai"]
    semantic_values = {
        "collector_semantics": poller.collector_semantics_manifest(),
        "invocation_order_policy": _FORMAL_FORECAST_POLICY[
            "invocation_order_policy"
        ],
        "formal_operation_lock_policy": {
            "scope": "database-url-and-run-id",
            "reentrancy": "same-thread",
            "sqlite": "run-scoped-exclusive-flock",
            "postgres": "dedicated-autocommit-session-advisory-lock",
        },
        "llm_invocation_receipt_policy": {
            "schema_version": 2,
            "reservation": "counter-increment-and-artifact-in-one-transaction",
            "result_cardinality": "one-terminal-result-per-reservation",
            "provider_call_transaction": "none",
        },
        "decision_projection_contract": {
            "held_weight_policy": formal_roles.DECISION_HELD_WEIGHT_POLICY,
            "weight_projection_sql": formal_roles.DECISION_WEIGHT_PROJECTION_SQL,
            "slot_projection_sql": formal_roles.DECISION_SLOT_PROJECTION_SQL,
        },
        "company_authorship_classifier": {
            "corporate_source_markers": list(media_sources._CORPORATE_SOURCE_MARKERS),
            "editorial_source_markers": list(media_sources._EDITORIAL_SOURCE_MARKERS),
            "first_party_headline_pattern": media_sources._FIRST_PARTY_HEADLINE.pattern,
            "first_party_headline_flags": media_sources._FIRST_PARTY_HEADLINE.flags,
        },
        "openai_transport": {
            "chat_class": (
                f"{openai_spec.chat_class.__module__}."
                f"{openai_spec.chat_class.__qualname__}"
            ),
            "base_url": openai_spec.base_url,
            "base_url_env": openai_spec.base_url_env,
            "key_optional": openai_spec.key_optional,
            "require_base_url": openai_spec.require_base_url,
            "use_responses_api": openai_spec.use_responses_api,
            "passthrough_kwargs": list(openai_client._PASSTHROUGH_KWARGS),
            "requested_model_capabilities": asdict(
                get_capabilities(_FORMAL_FORECAST_POLICY["requested_model"])
            ),
        },
        "runtime_semantic_dependencies": {
            distribution: package_version(distribution)
            for distribution in (
                "exchange-calendars",
                "langchain-core",
                "langchain-openai",
                "pandas",
                "pydantic",
                "yfinance",
            )
        },
    }
    manifest = {
        "schema_version": 2,
        "policy": "formal-decision-source-content-v2-indirect",
        "components": source_hashes,
        "semantic_values": semantic_values,
    }
    return {**manifest, "semantic_id": content_id(manifest, prefix="semantics_")}


def formal_trial_registration(
    run_id: str,
    decision_semantics: dict,
    *,
    outcome_semantics_id: str,
    configuration_binding: Mapping[str, str],
) -> dict:
    """Build the immutable executable/configuration-bound trial registration."""
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("formal trial run ID must be non-empty")
    if (
        not isinstance(outcome_semantics_id, str)
        or re.fullmatch(r"outcome_semantics_[0-9a-f]{64}", outcome_semantics_id)
        is None
    ):
        raise ValueError("formal outcome semantics identity is malformed")
    expected_configuration_fields = {
        "configuration_manifest_id",
        "collector_configuration_id",
        "paper_decision_configuration_id",
        "paper_marker_configuration_id",
    }
    if (
        not isinstance(configuration_binding, Mapping)
        or set(configuration_binding) != expected_configuration_fields
        or any(
            not isinstance(value, str)
            or re.fullmatch(r"config_[0-9a-f]{24}", value) is None
            for value in configuration_binding.values()
        )
    ):
        raise ValueError("formal configuration binding is malformed")
    decision_semantics_id = decision_semantics.get("semantic_id")
    if (
        not isinstance(decision_semantics_id, str)
        or re.fullmatch(r"semantics_[0-9a-f]{24}", decision_semantics_id) is None
    ):
        raise ValueError("formal decision semantics identity is malformed")
    analysis = GLOBAL_EVENT_V2_PROTOCOL["analysis"]
    base = {
        "schema_version": 2,
        "registration_type": "confirmatory",
        "run_id": run_id,
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "analysis_id": content_id(analysis, prefix="analysis_"),
        "review_gates_id": content_id(
            GLOBAL_EVENT_V2_PROTOCOL["review_gates"], prefix="reviews_"
        ),
        "decision_semantics_id": decision_semantics_id,
        "outcome_semantics_id": outcome_semantics_id,
        "configuration_binding": {
            key: configuration_binding[key]
            for key in sorted(expected_configuration_fields)
        },
        "registered_strategies": list(GLOBAL_EVENT_V2_PROTOCOL["strategies"]),
        "confirmatory_family": list(analysis["multiplicity"]["confirmatory_family"]),
        "secondary_family": list(analysis["multiplicity"]["secondary_family"]),
        "trial_clock": analysis["trial_clock"],
        "parent_run_id": None,
        "outcomes_accessed_before_registration": False,
    }
    return {**base, "registration_id": content_id(base, prefix="registration_")}


def formal_run_configuration(
    *,
    release_configuration: Mapping,
    decision_semantics: dict,
    outcome_semantics_id: str,
) -> dict:
    """Project an exact release payload into the immutable paper-run config."""
    from tradingagents.formal_configuration import validate_release_configuration

    release = validate_release_configuration(release_configuration)
    decision = release["paper_decision_configuration"]["settings"]
    collector = release["collector_configuration"]["settings"]
    llm_policy = LLMCallPolicy.from_values(
        ",".join(decision["allowed_models"]),
        int(decision["llm_max_calls_per_decision"]),
        int(decision["llm_max_calls_per_utc_day"]),
    )
    selected_model = llm_policy.require_model(
        decision["llm_provider"], decision["requested_model"]
    )
    evidence_policy = formal_evidence_policy_manifest()
    registration = formal_trial_registration(
        decision["run_id"],
        decision_semantics,
        outcome_semantics_id=outcome_semantics_id,
        configuration_binding=release["configuration_binding"],
    )
    return {
        "engine": "formal-global-v2",
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "tickers": list(decision["universe"]),
        "benchmark": decision["benchmark"],
        "cost_bps": decision["trading_cost_bps"],
        "slippage_bps": decision["slippage_bps"],
        "annual_borrow_bps": decision["annual_borrow_bps"],
        "cash_policy": GLOBAL_EVENT_V2_PROTOCOL["portfolio"]["cash"],
        "llm_model": selected_model,
        "llm_endpoint_class": decision["llm_endpoint_class"],
        "llm_backend_url": decision["llm_backend_url"],
        "llm_reasoning_effort": decision["llm_reasoning_effort"],
        "llm_temperature": decision["llm_temperature"],
        "llm_policy": llm_policy.manifest(),
        "llm_sdk_max_retries": decision["llm_sdk_max_retries"],
        "llm_max_prompt_bytes": decision["llm_max_prompt_bytes"],
        "llm_max_completion_tokens": decision["llm_max_completion_tokens"],
        "llm_timeout_seconds": decision["llm_timeout_seconds"],
        "evidence_query_slots": [
            (slot["provider"], slot["query_key"])
            for slot in collector["globalnews_query_slots"]
        ],
        "collector_interval_seconds": collector["poller_interval_seconds"],
        "collector_cycle_start_grace_seconds": (
            FORMAL_COLLECTOR_CYCLE_START_GRACE_SECONDS
        ),
        "evidence_policy": evidence_policy,
        "decision_semantics": decision_semantics,
        "outcome_semantics_id": outcome_semantics_id,
        "configuration_binding": release["configuration_binding"],
        "trial_registration_id": registration["registration_id"],
    }


def bootstrap_formal_trial(
    *,
    db_url: str,
    release_configuration: Mapping,
    created_utc: float | None = None,
) -> dict:
    """Preregister a paused trial without reading evidence or calling providers.

    This is an administrator workflow, deliberately separate from decision and
    marker workers.  Database grants/triggers remain the authority over who may
    execute it.
    """
    from tradingagents.formal_configuration import validate_release_configuration
    from tradingagents.outcome_semantics import outcome_semantics_id
    from tradingagents.paper_trading import PaperStore

    release = validate_release_configuration(release_configuration)
    decision_semantics = formal_decision_semantics()
    expected_semantics_id = GLOBAL_EVENT_V2_PROTOCOL["forecast"][
        "expected_decision_semantics_id"
    ]
    if decision_semantics["semantic_id"] != expected_semantics_id:
        raise ValueError("formal decision implementation differs from the frozen protocol")
    outcome_id = outcome_semantics_id()
    run_config = formal_run_configuration(
        release_configuration=release,
        decision_semantics=decision_semantics,
        outcome_semantics_id=outcome_id,
    )
    run_id = release["paper_decision_configuration"]["settings"]["run_id"]
    registration = formal_trial_registration(
        run_id,
        decision_semantics,
        outcome_semantics_id=outcome_id,
        configuration_binding=release["configuration_binding"],
    )
    timestamp = (
        datetime.now(timezone.utc).timestamp()
        if created_utc is None
        else float(created_utc)
    )
    if not math.isfinite(timestamp):
        raise ValueError("formal bootstrap time must be finite")
    store = PaperStore(db_url, auto_migrate=False)
    try:
        store.register_protocol(
            GLOBAL_EVENT_V2_PROTOCOL_ID, GLOBAL_EVENT_V2_PROTOCOL, timestamp
        )
        store.create_run(run_id, run_config, timestamp)
        store.register_confirmatory_trial(run_id, timestamp, registration)
    finally:
        store.close()
    return {
        "run_id": run_id,
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "registration_id": registration["registration_id"],
        "outcome_semantics_id": outcome_id,
        "configuration_binding": release["configuration_binding"],
        "provider_calls": 0,
        "trial_authorized": False,
    }


def _decide_formal_locked(
    args,
    now_utc: datetime | None = None,
    *,
    clock: Callable[[], datetime] | None = None,
) -> dict:
    """Create one shared forecast while the caller holds the operation lock."""
    # Imports avoid a module cycle: paper_trading exposes the store and calendar.
    from tradingagents.dataflows.media_store import open_store
    from tradingagents.paper_trading import PaperStore, current_decision_date, decision_window

    live_clock = clock or (lambda: datetime.now(timezone.utc))
    now = now_utc or live_clock()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("formal decision start time must be timezone-aware")
    now = now.astimezone(timezone.utc)
    decision_date = current_decision_date(now)
    cutoff, next_open, entry_date = decision_window(decision_date)
    universe = list(GLOBAL_EVENT_V2_PROTOCOL["universe"]["symbols"])
    configured = sorted({ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()})
    if configured != sorted(universe):
        raise ValueError("formal run ticker universe must exactly match the frozen protocol")
    provider = DEFAULT_CONFIG["llm_provider"]
    requested_model = DEFAULT_CONFIG["quick_think_llm"]
    llm_policy = _formal_llm_policy(args)
    max_prompt_bytes = _formal_prompt_limit(args)
    max_completion_tokens = _formal_completion_limit(args)
    timeout_seconds = _formal_timeout(args)
    forecast_policy = GLOBAL_EVENT_V2_PROTOCOL["forecast"]
    if provider != forecast_policy["provider"] \
            or requested_model != forecast_policy["requested_model"]:
        raise ValueError("configured formal provider/model differs from the frozen protocol")
    if DEFAULT_CONFIG.get("backend_url") != forecast_policy["backend_url"]:
        raise ValueError("formal endpoint differs from the frozen native-provider endpoint")
    if DEFAULT_CONFIG.get("openai_reasoning_effort") \
            != forecast_policy["reasoning_effort"]:
        raise ValueError("formal reasoning effort differs from the frozen protocol")
    if DEFAULT_CONFIG.get("temperature") != forecast_policy["temperature"]:
        raise ValueError("formal temperature differs from the frozen protocol")
    expected_models = frozenset(
        f"{provider}:{model}" for model in forecast_policy["allowed_returned_models"]
    )
    if llm_policy.allowed_models != expected_models:
        raise ValueError("formal model allowlist differs from the frozen protocol")
    expected_invocation = forecast_policy["invocation_policy"]
    if llm_policy.max_calls_per_decision \
            != int(expected_invocation["max_calls_per_decision"]) \
            or llm_policy.max_calls_per_utc_day \
            != int(expected_invocation["max_calls_per_utc_day"]):
        raise ValueError("formal LLM call budgets differ from the frozen protocol")
    selected_model = llm_policy.require_model(provider, requested_model)
    evidence_query_slots = _formal_evidence_query_slots()
    collector_interval_seconds, _ = _formal_collector_cycle_window(cutoff)
    evidence_policy = formal_evidence_policy_manifest()
    decision_semantics = formal_decision_semantics()
    expected_semantics_id = forecast_policy["expected_decision_semantics_id"]
    if decision_semantics["semantic_id"] != expected_semantics_id:
        raise ValueError("formal decision implementation differs from the frozen protocol")
    from tradingagents.formal_runtime import paper_component_configuration
    from tradingagents.outcome_semantics import outcome_semantics_id

    resolved_outcome_semantics_id = outcome_semantics_id()
    decision_configuration = paper_component_configuration(
        args,
        role="paper_decision",
        decision_semantics_id=decision_semantics["semantic_id"],
        env=os.environ,
    )
    store = PaperStore(args.db, auto_migrate=False)
    media = None
    attempt_ordinal: int | None = None
    failure_reason = "configuration_failed"
    try:
        runtime_authorization = store.require_formal_runtime_authorization(
            args.run_id,
            role="paper_decision",
            component_configuration=decision_configuration,
            outcome_semantics_id=resolved_outcome_semantics_id,
            env=os.environ,
        )
        authorization = runtime_authorization["authorization"]
        state = store.formal_decision_state(
            args.run_id, authorization=authorization
        )
        if state["terminal_price_integrity_failure"]:
            raise ValueError("terminal price integrity failure blocks formal decisions")
        run_config = state["config"]
        registration_row = store.confirmatory_registration(args.run_id)
        if registration_row is None:
            raise ValueError("formal decision requires its preregistered primary trial")
        trial_registration = registration_row["details"]
        expected_registration = formal_trial_registration(
            args.run_id,
            decision_semantics,
            outcome_semantics_id=resolved_outcome_semantics_id,
            configuration_binding=authorization["configuration_binding"],
        )
        if (
            trial_registration != expected_registration
            or run_config.get("trial_registration_id")
            != expected_registration["registration_id"]
            or run_config.get("llm_model") != selected_model
            or run_config.get("llm_policy") != llm_policy.manifest()
            or run_config.get("evidence_query_slots")
            != [list(slot) for slot in evidence_query_slots]
            or run_config.get("collector_interval_seconds")
            != collector_interval_seconds
            or run_config.get("evidence_policy") != evidence_policy
            or run_config.get("decision_semantics") != decision_semantics
        ):
            raise ValueError("formal runtime differs from its preregistered trial")
        if store.has_decision(args.run_id, decision_date):
            # The same decision window spans weekends and exchange holidays.
            # A daily daemon restart may therefore revisit an already-frozen
            # Friday decision before the next session exists.  Treat that as
            # an authenticated idempotent success: do not reopen the evidence
            # store, fetch market data, construct a model client, or reserve
            # another invocation.
            return {
                "decision_date": decision_date,
                "entry_date": entry_date,
                "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
                "already_recorded": True,
                "portfolio_outputs_withheld": True,
            }
        if store.formal_invocation_receipts(args.run_id, decision_date):
            raise ValueError(
                "formal decision already consumed an invocation reservation; "
                "the scheduled interval must carry forward without a same-day retry"
            )
        # Open the evidence store only after image/config/role authorization
        # and the idempotent duplicate check.  Its constructor is required to
        # be migration-disabled in formal mode.
        media = open_store(args.db)
        attempt_ordinal = store.record_formal_attempt_started(
            args.run_id, decision_date, entry_date, now.timestamp()
        )
        failure_reason = "coverage_gate_failed"
        coverage = _formal_coverage(
            media,
            cutoff,
            evidence_query_slots,
            interval_seconds=collector_interval_seconds,
        )
        if not coverage["complete"]:
            raise ValueError(
                "source completeness gate failed: "
                f"{len(coverage['missing_source_groups'])} source groups and "
                f"{len(coverage['missing_query_slots'])} query slots missing"
            )
        candidate_rows = evidence_window(media, decision_date)
        x_cycle_availability, candidate_rows = _formal_x_cycle_availability(
            media, cutoff, candidate_rows
        )
        selection_manifest = evidence_selection_manifest(
            candidate_rows, as_of_utc=cutoff.timestamp()
        )
        selection_manifest = _bind_x_availability_to_selection(
            selection_manifest, x_cycle_availability
        )
        coverage = bind_receipt_coverage_to_selection(
            coverage, selection_manifest
        )
        coverage = {
            **coverage,
            "x_cycle_availability": x_cycle_availability,
        }
        if not coverage["complete"]:
            raise ValueError(
                "formal receipt-to-evidence lineage binding failed for "
                f"{len(coverage['missing_query_slots'])} query slots"
            )
        selection_coverage = _formal_selection_coverage(
            selection_manifest, evidence_query_slots
        )
        if not selection_coverage["complete"]:
            raise ValueError(
                "formal selected-evidence coverage has only "
                f"{selection_coverage['selected_globalnews_total']} strict-core items; "
                "at least "
                f"{selection_coverage['minimum_selected_globalnews_total']} is required"
            )
        rows, non_x_rows, x_rows = partition_formal_evidence(
            candidate_rows, as_of_utc=cutoff.timestamp()
        )
        # Resolve every deterministic external input and prior ledger state
        # before reserving a paid model call. A market-data outage, malformed
        # stale snapshot, or asymmetric prior portfolio must fail without
        # consuming the day's scarce forecast budget.
        failure_reason = "market_data_failed"
        market_rows, momentum_rows, market_snapshots = _market_rows(
            universe, decision_date
        )
        equal_rows = [{
            "ticker": ticker, "expected_excess_return_bps": 100.0,
            "probability_positive": 0.6, "confidence": 1.0, "abstain": False,
            "event_ids": [], "rationale": "equal-weight baseline",
        } for ticker in universe]
        failure_reason = "target_construction_failed"
        stale_snapshot = store.latest_formal_forecast_snapshot(args.run_id)
        stale_rows = (
            stale_snapshot["forecasts"] if stale_snapshot is not None
            else _neutral_forecasts(universe, "no prior formal forecast available")
        )
        stale_lineage = {
            "source_kind": (
                "stored_formal_forecast" if stale_snapshot is not None
                else "initial_neutral"
            ),
            "source_decision_date": (
                stale_snapshot["decision_date"] if stale_snapshot is not None else None
            ),
            "forecast_content_id": content_id(stale_rows, prefix="forecasts_"),
        }
        prior_weight_lineage = store.formal_decision_weight_snapshots(
            args.run_id, universe
        )
        for lineage in prior_weight_lineage.values():
            lineage["lineage_id"] = content_id(lineage, prefix="weights_")
        prior_weights = {
            strategy: lineage["weights"]
            for strategy, lineage in prior_weight_lineage.items()
        }
        failure_reason = "llm_failed"
        call_guard = PersistentLLMCallGuard(
            llm_policy,
            scope="formal-global-v2",
            run_id=args.run_id,
            decision_date=decision_date,
        )
        llm = create_forecast_llm(
            max_completion_tokens=max_completion_tokens,
            timeout_seconds=timeout_seconds,
        )
        stage_rows = {"champion": rows}
        if prepare_evidence(rows) != prepare_evidence(non_x_rows):
            stage_rows["without_public_reaction"] = non_x_rows
        if x_rows:
            stage_rows["public_reaction_only"] = x_rows
        invocation_stage_order = _formal_invocation_stage_order(
            decision_date, list(stage_rows)
        )
        invocation_bundles = {}
        for invocation_stage in invocation_stage_order:
            invocation_bundles[invocation_stage] = _invoke_guarded_forecast(
                guard=call_guard, llm=llm, provider=provider,
                requested_model=requested_model,
                decision_date=decision_date, rows=stage_rows[invocation_stage],
                universe=universe,
                max_prompt_bytes=max_prompt_bytes,
                max_completion_tokens=max_completion_tokens,
                invocation_stage=invocation_stage,
                artifact_recorder=store,
            )
        champion = invocation_bundles["champion"]
        no_reaction = invocation_bundles.get(
            "without_public_reaction", champion
        )
        public_rows = _neutral_forecasts(universe, "no eligible public-reaction evidence")
        public_bundle = invocation_bundles.get("public_reaction_only")
        if public_bundle is not None:
            public_rows = _forecast_rows(public_bundle)
        champion_rows = _forecast_rows(champion)
        no_reaction_rows = _forecast_rows(no_reaction)
        strategy_rows = {
            "global_events_champion": champion_rows,
            "global_events_without_public_reaction": no_reaction_rows,
            "public_reaction_only": public_rows,
            "market_only": market_rows,
            "equal_weight": equal_rows,
            "momentum": momentum_rows,
            "stale_events_negative_control": stale_rows,
            "shuffled_events_negative_control": _shuffle_forecasts(champion_rows),
        }
        strategy_model_ids = {
            "global_events_champion": champion.model_id,
            "global_events_without_public_reaction": no_reaction.model_id,
            "public_reaction_only": public_bundle.model_id if public_bundle else "model_none",
            "market_only": "model_deterministic_market",
            "equal_weight": "model_deterministic_equal_weight",
            "momentum": "model_deterministic_momentum",
            "stale_events_negative_control": "model_stored_forecast",
            "shuffled_events_negative_control": champion.model_id,
        }
        failure_reason = "decision_window_expired"
        target_created_at = _checked_before_open(
            live_clock, next_open, stage="target construction"
        )
        failure_reason = "target_construction_failed"
        if set(prior_weights) != set(strategy_rows):
            raise RuntimeError("frozen strategy set differs from preloaded prior state")
        targets = {
            strategy: _target(
                store,
                args.run_id,
                strategy,
                forecasts,
                universe,
                cutoff=cutoff,
                next_open=next_open,
                entry_date=entry_date,
                created_at=target_created_at,
                model_id=strategy_model_ids[strategy],
                current_weights=prior_weights[strategy],
            )
            for strategy, forecasts in strategy_rows.items()
        }
        build_id = runtime_authorization["build_id"]
        artifact = {
            "schema_version": 3,
            "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
            "build_id": build_id,
            "run_id": args.run_id,
            "decision_date": decision_date,
            "attempt_ordinal": attempt_ordinal,
            "universe": universe,
            "decision_context": {
                "cutoff_utc": cutoff.isoformat(),
                "next_open_utc": next_open.isoformat(),
                "entry_date": entry_date,
                "target_created_at_utc": target_created_at.isoformat(),
            },
            "coverage": coverage,
            "required_evidence_query_slots": evidence_query_slots,
            "evidence_policy": evidence_policy,
            "x_cycle_availability": x_cycle_availability,
            "evidence_selection_manifest": selection_manifest,
            "evidence_selection_coverage": selection_coverage,
            "decision_semantics": decision_semantics,
            "trial_registration_id": trial_registration["registration_id"],
            "llm_policy": {
                **llm_policy.manifest(),
                "max_prompt_bytes": max_prompt_bytes,
                "max_completion_tokens": max_completion_tokens,
                "timeout_seconds": timeout_seconds,
                "sdk_max_retries": FORMAL_LLM_SDK_MAX_RETRIES,
                "endpoint_class": forecast_policy["endpoint_class"],
                "backend_url": forecast_policy["backend_url"],
                "reasoning_effort": forecast_policy["reasoning_effort"],
                "temperature": forecast_policy["temperature"],
                "structured_output_schema": forecast_policy[
                    "structured_output_schema"
                ],
            },
            "invocation_stage_order": invocation_stage_order,
            "champion": champion.as_dict(),
            "without_public_reaction": no_reaction.as_dict(),
            "public_reaction_only": public_bundle.as_dict() if public_bundle else None,
            "market_inputs": {
                "ohlc": market_snapshots, "market_only": market_rows,
                "momentum": momentum_rows,
            },
            "stale_input_lineage": stale_lineage,
            "strategy_inputs": {
                strategy: {
                    "forecasts": forecasts,
                    "prior_weights": prior_weights[strategy],
                    "prior_weight_lineage": prior_weight_lineage[strategy],
                    "model_id": strategy_model_ids[strategy],
                }
                for strategy, forecasts in strategy_rows.items()
            },
            "strategy_targets": targets,
        }
        artifact_id = content_id(artifact, prefix="artifact_")
        failure_reason = "decision_window_expired"
        persisted_at = _checked_before_open(live_clock, next_open, stage="persistence")
        failure_reason = "persistence_failed"
        store.record_formal_decision(
            run_id=args.run_id, decision_date=decision_date, entry_date=entry_date,
            created_utc=persisted_at.timestamp(), protocol_id=GLOBAL_EVENT_V2_PROTOCOL_ID,
            build_id=build_id, model_id=champion.model_id,
            input_bundle_id=champion.input_bundle_id, artifact_id=artifact_id,
            artifact=artifact, coverage=coverage,
            events=[event.model_dump(mode="json") for event in champion.forecast.events],
            forecasts=champion_rows, strategy_targets=targets,
        )
        return {
            "decision_date": decision_date, "entry_date": entry_date,
            "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
            "input_bundle_id": champion.input_bundle_id,
            "artifact_id": artifact_id,
            "events": len(champion.forecast.events), "assets": len(champion_rows),
            "strategies": sorted(targets),
            "x_availability_state": x_cycle_availability["state"],
            "portfolio_outputs_withheld": True,
        }
    except Exception as exc:
        if attempt_ordinal is not None:
            try:
                store.record_formal_attempt_failed(
                    args.run_id,
                    decision_date,
                    attempt_ordinal,
                    datetime.now(timezone.utc).timestamp(),
                    failure_reason,
                )
            except Exception:  # Preserve the causal failure without leaking details.
                exc.add_note(
                    "formal attempt failure provenance could not be appended"
                )
        raise
    finally:
        if media is not None:
            media.close()
        store.close()


def decide_formal(
    args,
    now_utc: datetime | None = None,
    *,
    clock: Callable[[], datetime] | None = None,
) -> dict:
    """Serialize and append one complete formal decision operation."""
    from tradingagents.paper_trading import formal_operation_lock

    with formal_operation_lock(args.db, args.run_id):
        return _decide_formal_locked(args, now_utc, clock=clock)
