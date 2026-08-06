from __future__ import annotations

import copy
import json

import pytest

from tradingagents.formal_configuration import (
    COLLECTOR_SETTING_FIELDS,
    PAPER_DECISION_SETTING_FIELDS,
    PAPER_MARKER_SETTING_FIELDS,
    FormalConfigurationError,
    build_component_configuration,
    build_release_configuration,
    validate_component_configuration,
    validate_release_configuration,
)
from tradingagents.research_protocol import GLOBAL_EVENT_V2_PROTOCOL


def collector_settings() -> dict:
    evidence = GLOBAL_EVENT_V2_PROTOCOL["evidence"]
    return {
        "collector_mode": "formal-global-news-v2",
        "media_auto_migrate": False,
        "poller_interval_seconds": evidence["query_cycle"][
            "collector_interval_seconds"
        ],
        "trading_hours_only": False,
        "ticker_watchlist": [],
        "enabled_sources": ["globalnews", "x"],
        "globalnews_enabled": True,
        "globalnews_query_slots": [
            {"provider": "globalnews", "query_key": f"{theme}:{query}"}
            for theme, queries in evidence["broad_news_queries"].items()
            for query in queries
        ],
        "globalnews_max_results_per_query": evidence[
            "max_global_news_results_per_query"
        ],
        "globalnews_retry_policy": evidence["query_cycle"][
            "globalnews_exception_retry_policy"
        ],
        "x_enabled": True,
        "x_cycle_interval_seconds": evidence["x_cycle_interval_seconds"],
        "x_max_topics": evidence["max_x_search_requests_per_utc_day"],
        "x_max_results_per_query": evidence["max_x_results_per_query"],
        "paper_heartbeat_max_age_seconds": 93_600,
        "collector_semantics_id": "collector_" + "1" * 24,
    }


def paper_decision_settings() -> dict:
    protocol = GLOBAL_EVENT_V2_PROTOCOL
    forecast = protocol["forecast"]
    invocation = forecast["invocation_policy"]
    return {
        "media_auto_migrate": False,
        "paper_auto_migrate": False,
        "run_id": "global-event-v2-confirmatory-001",
        "engine": "formal-global-v2",
        "universe": list(protocol["universe"]["symbols"]),
        "benchmark": protocol["portfolio"]["benchmark"],
        "analysts": ["news"],
        "global_topics_only": True,
        "media_poller_interval_seconds": protocol["evidence"]["query_cycle"][
            "collector_interval_seconds"
        ],
        "llm_provider": forecast["provider"],
        "requested_model": forecast["requested_model"],
        "allowed_models": sorted(
            f"{forecast['provider']}:{model}"
            for model in forecast["allowed_returned_models"]
        ),
        "llm_endpoint_class": forecast["endpoint_class"],
        "llm_backend_url": forecast["backend_url"],
        "llm_reasoning_effort": forecast["reasoning_effort"],
        "llm_temperature": forecast["temperature"],
        "llm_max_calls_per_decision": invocation["max_calls_per_decision"],
        "llm_max_calls_per_utc_day": invocation["max_calls_per_utc_day"],
        "llm_max_prompt_bytes": invocation["max_prompt_bytes"],
        "llm_max_completion_tokens": invocation["max_completion_tokens"],
        "llm_timeout_seconds": invocation["timeout_seconds"],
        "llm_sdk_max_retries": invocation["sdk_max_retries"],
        "worker_retry_attempts": 3,
        "worker_retry_seconds": 300.0,
        "replicates": 1,
        "portfolio_mode": protocol["portfolio"]["mode"],
        "trading_cost_bps": protocol["portfolio"]["trading_cost_bps"],
        "slippage_bps": protocol["portfolio"]["slippage_bps"],
        "annual_borrow_bps": 0.0,
        "decision_semantics_id": forecast["expected_decision_semantics_id"],
        "decision_authority": "durable-release-authorization-only",
    }


def paper_marker_settings() -> dict:
    protocol = GLOBAL_EVENT_V2_PROTOCOL
    return {
        "media_auto_migrate": False,
        "paper_auto_migrate": False,
        "run_id": "global-event-v2-confirmatory-001",
        "engine": "formal-global-v2",
        "universe": list(protocol["universe"]["symbols"]),
        "benchmark": protocol["portfolio"]["benchmark"],
        "worker_retry_attempts": 3,
        "worker_retry_seconds": 300.0,
        "portfolio_mode": protocol["portfolio"]["mode"],
        "trading_cost_bps": protocol["portfolio"]["trading_cost_bps"],
        "slippage_bps": protocol["portfolio"]["slippage_bps"],
        "annual_borrow_bps": 0.0,
        "price_vendor": "yfinance",
        "price_capture_delay_minutes": protocol["portfolio"]["price_capture"][
            "scheduled_delay_after_xnys_session_open_minutes"
        ],
        "mark_authority": "durable-release-authorization-only",
    }


def release_configuration() -> dict:
    return build_release_configuration(
        build_component_configuration("collector", collector_settings()),
        build_component_configuration("paper_decision", paper_decision_settings()),
        build_component_configuration("paper_marker", paper_marker_settings()),
    )


@pytest.mark.unit
def test_component_schemas_are_explicit_and_complete():
    assert set(collector_settings()) == set(COLLECTOR_SETTING_FIELDS)
    assert set(paper_decision_settings()) == set(PAPER_DECISION_SETTING_FIELDS)
    assert set(paper_marker_settings()) == set(PAPER_MARKER_SETTING_FIELDS)


@pytest.mark.unit
def test_complete_configuration_material_is_content_addressed_and_replayable():
    payload = release_configuration()

    assert validate_release_configuration(payload) == payload
    assert validate_component_configuration(
        payload["collector_configuration"], expected_role="collector"
    ) == payload["collector_configuration"]
    assert validate_component_configuration(
        payload["paper_decision_configuration"], expected_role="paper_decision"
    ) == payload["paper_decision_configuration"]
    assert validate_component_configuration(
        payload["paper_marker_configuration"], expected_role="paper_marker"
    ) == payload["paper_marker_configuration"]
    binding = payload["configuration_binding"]
    assert binding["collector_configuration_id"] \
        == payload["collector_configuration"]["configuration_id"]
    assert binding["paper_decision_configuration_id"] \
        == payload["paper_decision_configuration"]["configuration_id"]
    assert binding["paper_marker_configuration_id"] \
        == payload["paper_marker_configuration"]["configuration_id"]
    assert binding["configuration_manifest_id"] \
        == payload["configuration_manifest"]["configuration_manifest_id"]


@pytest.mark.unit
@pytest.mark.parametrize("role", ("collector", "paper_decision", "paper_marker"))
def test_missing_or_extra_component_setting_fails_closed(role):
    settings = {
        "collector": collector_settings,
        "paper_decision": paper_decision_settings,
        "paper_marker": paper_marker_settings,
    }[role]()
    missing = dict(settings)
    missing.pop(next(iter(missing)))
    with pytest.raises(FormalConfigurationError, match="exact schema"):
        build_component_configuration(role, missing)

    extra = {**settings, "secret_token": "must-never-persist"}
    with pytest.raises(FormalConfigurationError, match="exact schema"):
        build_component_configuration(role, extra)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("role", "field", "replacement"),
    [
        ("collector", "poller_interval_seconds", 7200),
        ("collector", "globalnews_enabled", False),
        ("collector", "ticker_watchlist", ["NVDA"]),
        ("collector", "x_max_topics", 4),
        ("paper_decision", "llm_max_calls_per_utc_day", 4),
        (
            "paper_decision",
            "universe",
            list(reversed(GLOBAL_EVENT_V2_PROTOCOL["universe"]["symbols"])),
        ),
        ("paper_decision", "global_topics_only", False),
        ("paper_marker", "price_vendor", "unfrozen-vendor"),
        ("paper_marker", "price_capture_delay_minutes", 5),
    ],
)
def test_protocol_or_scope_drift_is_rejected(role, field, replacement):
    settings = {
        "collector": collector_settings,
        "paper_decision": paper_decision_settings,
        "paper_marker": paper_marker_settings,
    }[role]()
    settings[field] = replacement
    with pytest.raises(FormalConfigurationError):
        build_component_configuration(role, settings)


@pytest.mark.unit
def test_operational_retry_change_gets_a_new_configuration_id():
    original = build_component_configuration(
        "paper_decision", paper_decision_settings()
    )
    changed_settings = paper_decision_settings()
    changed_settings["worker_retry_seconds"] = 60.0
    changed = build_component_configuration("paper_decision", changed_settings)

    assert changed["configuration_id"] != original["configuration_id"]


@pytest.mark.unit
def test_release_payload_contains_no_secret_or_connection_material():
    rendered = json.dumps(release_configuration(), sort_keys=True).lower()

    for forbidden in (
        "bearer",
        "api_key",
        "password",
        "database_url",
        "media_db_url",
        "webhook_url",
    ):
        assert forbidden not in rendered


@pytest.mark.unit
def test_tampered_component_or_binding_cannot_reuse_release_identity():
    payload = release_configuration()
    tampered = copy.deepcopy(payload)
    tampered["paper_decision_configuration"]["settings"][
        "worker_retry_seconds"
    ] = 1.0
    with pytest.raises(FormalConfigurationError):
        validate_release_configuration(tampered)

    tampered = copy.deepcopy(payload)
    tampered["configuration_binding"]["paper_marker_configuration_id"] = (
        "config_" + "0" * 24
    )
    with pytest.raises(FormalConfigurationError):
        validate_release_configuration(tampered)
