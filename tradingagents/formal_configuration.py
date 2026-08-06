"""Content-addressed runtime configuration for the formal experiment.

Release authorization stores the complete non-secret configuration material,
not merely opaque IDs. Each worker recomputes its own component ID at runtime;
the administrative release receipt binds both components and their combined
manifest. Emergency pause flags and credentials are deliberately outside this
document: pause never grants authority, and secret values must never be stored.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
    content_id,
)

COMPONENT_ROLES = ("collector", "paper_decision", "paper_marker")
_COMPONENT_TYPE = "formal-runtime-component"
_RELEASE_TYPE = "formal-runtime-release"
_CONFIG_ID = re.compile(r"^config_[0-9a-f]{24}$")
_COLLECTOR_ID = re.compile(r"^collector_[0-9a-f]{24}$")
_SEMANTICS_ID = re.compile(r"^semantics_[0-9a-f]{24}$")

COLLECTOR_SETTING_FIELDS = frozenset({
    "collector_mode",
    "media_auto_migrate",
    "poller_interval_seconds",
    "trading_hours_only",
    "ticker_watchlist",
    "enabled_sources",
    "globalnews_enabled",
    "globalnews_query_slots",
    "globalnews_max_results_per_query",
    "globalnews_retry_policy",
    "x_enabled",
    "x_cycle_interval_seconds",
    "x_max_topics",
    "x_max_results_per_query",
    "paper_heartbeat_max_age_seconds",
    "collector_semantics_id",
})

PAPER_DECISION_SETTING_FIELDS = frozenset({
    "media_auto_migrate",
    "paper_auto_migrate",
    "run_id",
    "engine",
    "universe",
    "benchmark",
    "analysts",
    "global_topics_only",
    "media_poller_interval_seconds",
    "llm_provider",
    "requested_model",
    "allowed_models",
    "llm_endpoint_class",
    "llm_backend_url",
    "llm_reasoning_effort",
    "llm_temperature",
    "llm_max_calls_per_decision",
    "llm_max_calls_per_utc_day",
    "llm_max_prompt_bytes",
    "llm_max_completion_tokens",
    "llm_timeout_seconds",
    "llm_sdk_max_retries",
    "worker_retry_attempts",
    "worker_retry_seconds",
    "replicates",
    "portfolio_mode",
    "trading_cost_bps",
    "slippage_bps",
    "annual_borrow_bps",
    "decision_semantics_id",
    "decision_authority",
})

PAPER_MARKER_SETTING_FIELDS = frozenset({
    "media_auto_migrate",
    "paper_auto_migrate",
    "run_id",
    "engine",
    "universe",
    "benchmark",
    "worker_retry_attempts",
    "worker_retry_seconds",
    "portfolio_mode",
    "trading_cost_bps",
    "slippage_bps",
    "annual_borrow_bps",
    "price_vendor",
    "price_capture_delay_minutes",
    "mark_authority",
})


class FormalConfigurationError(ValueError):
    """Raised when formal runtime configuration is incomplete or inconsistent."""


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FormalConfigurationError(f"{label} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str] | frozenset[str], label: str) -> None:
    if set(value) != set(expected):
        raise FormalConfigurationError(f"{label} has an invalid exact schema")


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise FormalConfigurationError(f"{label} must be a canonical non-empty string")
    return value


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise FormalConfigurationError(f"{label} must be an integer >= {minimum}")
    return value


def _number(value: Any, label: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FormalConfigurationError(f"{label} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < minimum:
        raise FormalConfigurationError(f"{label} must be a finite number >= {minimum}")
    return normalized


def _optional_string(value: Any, label: str) -> str | None:
    return None if value is None else _string(value, label)


def _optional_number(value: Any, label: str, *, minimum: float = 0.0) -> float | None:
    return None if value is None else _number(value, label, minimum=minimum)


def _string_list(
    value: Any,
    label: str,
    *,
    sorted_unique: bool = False,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, (list, tuple)) or (not value and not allow_empty):
        qualifier = "a string list" if allow_empty else "a non-empty string list"
        raise FormalConfigurationError(f"{label} must be {qualifier}")
    normalized = [_string(item, f"{label} item") for item in value]
    if len(normalized) != len(set(normalized)):
        raise FormalConfigurationError(f"{label} must not contain duplicates")
    if sorted_unique and normalized != sorted(normalized):
        raise FormalConfigurationError(f"{label} must be sorted")
    return normalized


def _expected_globalnews_slots() -> list[dict[str, str]]:
    return [
        {"provider": "globalnews", "query_key": f"{theme}:{query}"}
        for theme, queries in GLOBAL_EVENT_V2_PROTOCOL["evidence"][
            "broad_news_queries"
        ].items()
        for query in queries
    ]


def _collector_settings(value: Any) -> dict[str, Any]:
    settings = _object(value, "collector settings")
    _exact_keys(settings, COLLECTOR_SETTING_FIELDS, "collector settings")
    if settings["media_auto_migrate"] is not False:
        raise FormalConfigurationError("collector runtime migrations must be disabled")
    if settings["collector_mode"] != "formal-global-news-v2":
        raise FormalConfigurationError("formal collector mode is invalid")
    if settings["trading_hours_only"] is not False:
        raise FormalConfigurationError("global collector cannot be exchange-hours-only")
    ticker_watchlist = _string_list(
        settings["ticker_watchlist"],
        "ticker watchlist",
        sorted_unique=True,
        allow_empty=True,
    )
    if ticker_watchlist:
        raise FormalConfigurationError("formal collector cannot use a ticker watchlist")
    if settings["globalnews_enabled"] is not True:
        raise FormalConfigurationError("formal collector requires global-news collection")
    if settings["x_enabled"] is not True:
        raise FormalConfigurationError("formal collector requires the bounded X source")
    sources = _string_list(settings["enabled_sources"], "enabled_sources", sorted_unique=True)
    expected_sources = sorted(GLOBAL_EVENT_V2_PROTOCOL["evidence"]["allowed_sources"])
    if sources != expected_sources:
        raise FormalConfigurationError(
            "formal collector source selection differs from the protocol"
        )
    slots_value = settings["globalnews_query_slots"]
    if not isinstance(slots_value, (list, tuple)):
        raise FormalConfigurationError("globalnews_query_slots must be a list")
    slots: list[dict[str, str]] = []
    for index, item in enumerate(slots_value):
        slot = _object(item, f"globalnews_query_slots[{index}]")
        _exact_keys(slot, {"provider", "query_key"}, "globalnews query slot")
        slots.append({
            "provider": _string(slot["provider"], "globalnews slot provider"),
            "query_key": _string(slot["query_key"], "globalnews slot query key"),
        })
    if slots != _expected_globalnews_slots():
        raise FormalConfigurationError("globalnews query slots differ from the protocol")
    retry_policy = _object(settings["globalnews_retry_policy"], "globalnews retry policy")
    expected_retry = GLOBAL_EVENT_V2_PROTOCOL["evidence"]["query_cycle"][
        "globalnews_exception_retry_policy"
    ]
    if dict(retry_policy) != expected_retry:
        raise FormalConfigurationError("globalnews retry policy differs from the protocol")
    collector_id = _string(settings["collector_semantics_id"], "collector semantics ID")
    if _COLLECTOR_ID.fullmatch(collector_id) is None:
        raise FormalConfigurationError("collector semantics ID is malformed")
    evidence = GLOBAL_EVENT_V2_PROTOCOL["evidence"]
    normalized = {
        "collector_mode": "formal-global-news-v2",
        "media_auto_migrate": False,
        "poller_interval_seconds": _integer(
            settings["poller_interval_seconds"], "poller interval", minimum=1
        ),
        "trading_hours_only": False,
        "ticker_watchlist": [],
        "enabled_sources": sources,
        "globalnews_enabled": True,
        "globalnews_query_slots": slots,
        "globalnews_max_results_per_query": _integer(
            settings["globalnews_max_results_per_query"],
            "globalnews result limit",
            minimum=1,
        ),
        "globalnews_retry_policy": dict(retry_policy),
        "x_enabled": True,
        "x_cycle_interval_seconds": _integer(
            settings["x_cycle_interval_seconds"], "X cycle interval", minimum=1
        ),
        "x_max_topics": _integer(settings["x_max_topics"], "X topic limit", minimum=1),
        "x_max_results_per_query": _integer(
            settings["x_max_results_per_query"], "X result limit", minimum=1
        ),
        "paper_heartbeat_max_age_seconds": _integer(
            settings["paper_heartbeat_max_age_seconds"],
            "paper heartbeat maximum age",
            minimum=1,
        ),
        "collector_semantics_id": collector_id,
    }
    if normalized["poller_interval_seconds"] != int(
        evidence["query_cycle"]["collector_interval_seconds"]
    ) or normalized["globalnews_max_results_per_query"] != int(
        evidence["max_global_news_results_per_query"]
    ) or normalized["x_cycle_interval_seconds"] != int(
        evidence["x_cycle_interval_seconds"]
    ) or normalized["x_max_topics"] != int(
        evidence["max_x_search_requests_per_utc_day"]
    ) or normalized["x_max_results_per_query"] != int(
        evidence["max_x_results_per_query"]
    ):
        raise FormalConfigurationError("collector limits differ from the protocol")
    return normalized


def _paper_decision_settings(value: Any) -> dict[str, Any]:
    settings = _object(value, "paper decision settings")
    _exact_keys(
        settings,
        PAPER_DECISION_SETTING_FIELDS,
        "paper decision settings",
    )
    if settings["media_auto_migrate"] is not False \
            or settings["paper_auto_migrate"] is not False:
        raise FormalConfigurationError("paper decision runtime migrations must be disabled")
    if settings["global_topics_only"] is not True:
        raise FormalConfigurationError("formal paper runtime must use global topics only")
    if settings["decision_authority"] != "durable-release-authorization-only":
        raise FormalConfigurationError("paper decision authority policy is invalid")
    universe = _string_list(settings["universe"], "paper universe")
    analysts = _string_list(settings["analysts"], "paper analysts", sorted_unique=True)
    allowed_models = _string_list(
        settings["allowed_models"], "allowed models", sorted_unique=True
    )
    protocol = GLOBAL_EVENT_V2_PROTOCOL
    forecast = protocol["forecast"]
    invocation = forecast["invocation_policy"]
    decision_id = _string(settings["decision_semantics_id"], "decision semantics ID")
    if _SEMANTICS_ID.fullmatch(decision_id) is None:
        raise FormalConfigurationError("decision semantics ID is malformed")
    normalized = {
        "media_auto_migrate": False,
        "paper_auto_migrate": False,
        "run_id": _string(settings["run_id"], "paper run ID"),
        "engine": _string(settings["engine"], "paper engine"),
        "universe": universe,
        "benchmark": _string(settings["benchmark"], "paper benchmark"),
        "analysts": analysts,
        "global_topics_only": True,
        "media_poller_interval_seconds": _integer(
            settings["media_poller_interval_seconds"],
            "paper media poller interval",
            minimum=1,
        ),
        "llm_provider": _string(settings["llm_provider"], "LLM provider"),
        "requested_model": _string(settings["requested_model"], "requested model"),
        "allowed_models": allowed_models,
        "llm_endpoint_class": _string(
            settings["llm_endpoint_class"], "LLM endpoint class"
        ),
        "llm_backend_url": _optional_string(
            settings["llm_backend_url"], "LLM backend URL"
        ),
        "llm_reasoning_effort": _string(
            settings["llm_reasoning_effort"], "LLM reasoning effort"
        ),
        "llm_temperature": _optional_number(
            settings["llm_temperature"], "LLM temperature"
        ),
        "llm_max_calls_per_decision": _integer(
            settings["llm_max_calls_per_decision"],
            "LLM calls per decision",
            minimum=1,
        ),
        "llm_max_calls_per_utc_day": _integer(
            settings["llm_max_calls_per_utc_day"],
            "LLM calls per UTC day",
            minimum=1,
        ),
        "llm_max_prompt_bytes": _integer(
            settings["llm_max_prompt_bytes"], "LLM prompt bytes", minimum=1
        ),
        "llm_max_completion_tokens": _integer(
            settings["llm_max_completion_tokens"],
            "LLM completion tokens",
            minimum=1,
        ),
        "llm_timeout_seconds": _integer(
            settings["llm_timeout_seconds"], "LLM timeout", minimum=1
        ),
        "llm_sdk_max_retries": _integer(
            settings["llm_sdk_max_retries"], "LLM SDK retries"
        ),
        "worker_retry_attempts": _integer(
            settings["worker_retry_attempts"], "worker retry attempts", minimum=1
        ),
        "worker_retry_seconds": _number(
            settings["worker_retry_seconds"], "worker retry delay"
        ),
        "replicates": _integer(settings["replicates"], "replicates", minimum=1),
        "portfolio_mode": _string(settings["portfolio_mode"], "portfolio mode"),
        "trading_cost_bps": _number(settings["trading_cost_bps"], "trading cost"),
        "slippage_bps": _number(settings["slippage_bps"], "slippage"),
        "annual_borrow_bps": _number(settings["annual_borrow_bps"], "borrow cost"),
        "decision_semantics_id": decision_id,
        "decision_authority": "durable-release-authorization-only",
    }
    expected_models = sorted(
        f"{forecast['provider']}:{model}"
        for model in forecast["allowed_returned_models"]
    )
    if normalized["engine"] != "formal-global-v2" \
            or normalized["universe"] != protocol["universe"]["symbols"] \
            or normalized["benchmark"] != protocol["portfolio"]["benchmark"] \
            or normalized["analysts"] != ["news"] \
            or normalized["media_poller_interval_seconds"] != int(
                protocol["evidence"]["query_cycle"]["collector_interval_seconds"]
            ) \
            or normalized["llm_provider"] != forecast["provider"] \
            or normalized["requested_model"] != forecast["requested_model"] \
            or normalized["allowed_models"] != expected_models \
            or normalized["llm_endpoint_class"] != forecast["endpoint_class"] \
            or normalized["llm_backend_url"] != forecast["backend_url"] \
            or normalized["llm_reasoning_effort"] != forecast["reasoning_effort"] \
            or normalized["llm_temperature"] != forecast["temperature"] \
            or normalized["llm_max_calls_per_decision"] != int(
                invocation["max_calls_per_decision"]
            ) \
            or normalized["llm_max_calls_per_utc_day"] != int(
                invocation["max_calls_per_utc_day"]
            ) \
            or normalized["llm_max_prompt_bytes"] != int(invocation["max_prompt_bytes"]) \
            or normalized["llm_max_completion_tokens"] != int(
                invocation["max_completion_tokens"]
            ) \
            or normalized["llm_timeout_seconds"] != int(invocation["timeout_seconds"]) \
            or normalized["llm_sdk_max_retries"] != int(
                invocation["sdk_max_retries"]
            ) \
            or normalized["replicates"] != 1 \
            or normalized["portfolio_mode"] != protocol["portfolio"]["mode"] \
            or normalized["trading_cost_bps"] != float(
                protocol["portfolio"]["trading_cost_bps"]
            ) \
            or normalized["slippage_bps"] != float(
                protocol["portfolio"]["slippage_bps"]
            ) \
            or normalized["annual_borrow_bps"] != 0.0 \
            or normalized["decision_semantics_id"] != forecast[
                "expected_decision_semantics_id"
            ]:
        raise FormalConfigurationError("paper decision settings differ from the protocol")
    return normalized


def _paper_marker_settings(value: Any) -> dict[str, Any]:
    settings = _object(value, "paper marker settings")
    _exact_keys(
        settings,
        PAPER_MARKER_SETTING_FIELDS,
        "paper marker settings",
    )
    if settings["media_auto_migrate"] is not False \
            or settings["paper_auto_migrate"] is not False:
        raise FormalConfigurationError("paper marker runtime migrations must be disabled")
    if settings["mark_authority"] != "durable-release-authorization-only":
        raise FormalConfigurationError("paper mark authority policy is invalid")
    protocol = GLOBAL_EVENT_V2_PROTOCOL
    normalized = {
        "media_auto_migrate": False,
        "paper_auto_migrate": False,
        "run_id": _string(settings["run_id"], "paper marker run ID"),
        "engine": _string(settings["engine"], "paper marker engine"),
        "universe": _string_list(settings["universe"], "paper marker universe"),
        "benchmark": _string(settings["benchmark"], "paper marker benchmark"),
        "worker_retry_attempts": _integer(
            settings["worker_retry_attempts"],
            "paper marker retry attempts",
            minimum=1,
        ),
        "worker_retry_seconds": _number(
            settings["worker_retry_seconds"], "paper marker retry delay"
        ),
        "portfolio_mode": _string(settings["portfolio_mode"], "portfolio mode"),
        "trading_cost_bps": _number(settings["trading_cost_bps"], "trading cost"),
        "slippage_bps": _number(settings["slippage_bps"], "slippage"),
        "annual_borrow_bps": _number(settings["annual_borrow_bps"], "borrow cost"),
        "price_vendor": _string(settings["price_vendor"], "price vendor"),
        "price_capture_delay_minutes": _integer(
            settings["price_capture_delay_minutes"],
            "price capture delay",
            minimum=1,
        ),
        "mark_authority": "durable-release-authorization-only",
    }
    if normalized["engine"] != "formal-global-v2" \
            or normalized["universe"] != protocol["universe"]["symbols"] \
            or normalized["benchmark"] != protocol["portfolio"]["benchmark"] \
            or normalized["portfolio_mode"] != protocol["portfolio"]["mode"] \
            or normalized["trading_cost_bps"] != float(
                protocol["portfolio"]["trading_cost_bps"]
            ) \
            or normalized["slippage_bps"] != float(
                protocol["portfolio"]["slippage_bps"]
            ) \
            or normalized["annual_borrow_bps"] != 0.0 \
            or normalized["price_vendor"] != "yfinance" \
            or normalized["price_capture_delay_minutes"] != int(
                protocol["portfolio"]["price_capture"][
                    "scheduled_delay_after_xnys_session_open_minutes"
                ]
            ):
        raise FormalConfigurationError("paper marker settings differ from the protocol")
    return normalized


def build_component_configuration(role: str, settings: Mapping[str, Any]) -> dict:
    """Build one exact non-secret worker configuration manifest."""
    if role not in COMPONENT_ROLES:
        raise FormalConfigurationError("component role is not allowed")
    normalizers = {
        "collector": _collector_settings,
        "paper_decision": _paper_decision_settings,
        "paper_marker": _paper_marker_settings,
    }
    normalized_settings = normalizers[role](settings)
    base = {
        "schema_version": 1,
        "configuration_type": _COMPONENT_TYPE,
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "role": role,
        "settings": normalized_settings,
    }
    return {**base, "configuration_id": content_id(base, prefix="config_")}


def validate_component_configuration(value: Any, *, expected_role: str | None = None) -> dict:
    """Validate and recompute one component manifest."""
    document = _object(value, "component configuration")
    _exact_keys(
        document,
        {
            "schema_version",
            "configuration_type",
            "protocol_id",
            "role",
            "settings",
            "configuration_id",
        },
        "component configuration",
    )
    role = _string(document["role"], "component role")
    if document["schema_version"] != 1 \
            or document["configuration_type"] != _COMPONENT_TYPE \
            or document["protocol_id"] != GLOBAL_EVENT_V2_PROTOCOL_ID \
            or role not in COMPONENT_ROLES \
            or (expected_role is not None and role != expected_role):
        raise FormalConfigurationError("component configuration identity is invalid")
    rebuilt = build_component_configuration(role, document["settings"])
    if document["configuration_id"] != rebuilt["configuration_id"]:
        raise FormalConfigurationError("component configuration is not content-addressed")
    return rebuilt


def build_release_configuration(
    collector_configuration: Mapping[str, Any],
    paper_decision_configuration: Mapping[str, Any],
    paper_marker_configuration: Mapping[str, Any],
) -> dict:
    """Bind both complete component manifests into one release payload."""
    collector = validate_component_configuration(
        collector_configuration, expected_role="collector"
    )
    paper_decision = validate_component_configuration(
        paper_decision_configuration, expected_role="paper_decision"
    )
    paper_marker = validate_component_configuration(
        paper_marker_configuration, expected_role="paper_marker"
    )
    base = {
        "schema_version": 1,
        "configuration_type": _RELEASE_TYPE,
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "components": {
            "collector": collector["configuration_id"],
            "paper_decision": paper_decision["configuration_id"],
            "paper_marker": paper_marker["configuration_id"],
        },
    }
    release_manifest = {
        **base,
        "configuration_manifest_id": content_id(base, prefix="config_"),
    }
    binding = {
        "configuration_manifest_id": release_manifest["configuration_manifest_id"],
        "collector_configuration_id": collector["configuration_id"],
        "paper_decision_configuration_id": paper_decision["configuration_id"],
        "paper_marker_configuration_id": paper_marker["configuration_id"],
    }
    return {
        "configuration_binding": binding,
        "configuration_manifest": release_manifest,
        "collector_configuration": collector,
        "paper_decision_configuration": paper_decision,
        "paper_marker_configuration": paper_marker,
    }


def validate_release_configuration(value: Any) -> dict:
    """Validate the complete persisted configuration release payload."""
    payload = _object(value, "release configuration")
    _exact_keys(
        payload,
        {
            "configuration_binding",
            "configuration_manifest",
            "collector_configuration",
            "paper_decision_configuration",
            "paper_marker_configuration",
        },
        "release configuration",
    )
    rebuilt = build_release_configuration(
        payload["collector_configuration"],
        payload["paper_decision_configuration"],
        payload["paper_marker_configuration"],
    )
    manifest = _object(payload["configuration_manifest"], "configuration manifest")
    _exact_keys(
        manifest,
        {
            "schema_version",
            "configuration_type",
            "protocol_id",
            "components",
            "configuration_manifest_id",
        },
        "configuration manifest",
    )
    binding = _object(payload["configuration_binding"], "configuration binding")
    _exact_keys(
        binding,
        {
            "configuration_manifest_id",
            "collector_configuration_id",
            "paper_decision_configuration_id",
            "paper_marker_configuration_id",
        },
        "configuration binding",
    )
    if dict(manifest) != rebuilt["configuration_manifest"] \
            or dict(binding) != rebuilt["configuration_binding"]:
        raise FormalConfigurationError("release configuration bindings are inconsistent")
    if any(_CONFIG_ID.fullmatch(value) is None for value in binding.values()):
        raise FormalConfigurationError("release configuration IDs are malformed")
    return rebuilt
