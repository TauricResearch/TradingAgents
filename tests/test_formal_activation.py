from __future__ import annotations

import copy

import pytest

from tradingagents.formal_activation import (
    FormalActivationError,
    build_alert_delivery_payload,
    build_alert_delivery_receipt,
    build_collector_rehearsal_payload,
    build_release_receipt,
    build_restore_rehearsal_payload,
    build_runtime_preflight_payload,
    build_trial_authorization,
    image_attestation,
    require_runtime_authorization,
    validate_release_receipt,
    validate_trial_authorization,
)
from tradingagents.formal_configuration import (
    build_component_configuration,
    build_release_configuration,
)
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
)

COLLECTOR_REF = "registry.fly.io/tradagent:deployment-01KZAE0P4ER12SS2215QXBSN0H"
PAPER_DECISION_REF = (
    "registry.fly.io/tradagent-paper-decision:deployment-01KZAD8T2KXJJJXAM2JJW8E447"
)
PAPER_MARKER_REF = "registry.fly.io/tradagent-paper-marker:deployment-01KZAF9N3MYKKKYCY3KKX9F558"
COLLECTOR_DIGEST = "sha256:" + "1" * 64
PAPER_DECISION_DIGEST = "sha256:" + "2" * 64
PAPER_MARKER_DIGEST = "sha256:" + "3" * 64
PROTOCOL_ID = GLOBAL_EVENT_V2_PROTOCOL_ID
RUN_ID = "global-event-v2-confirmatory-001"
REGISTRATION_ID = "registration_" + "4" * 24
OUTCOME_ID = "outcome_semantics_" + "5" * 64


def _collection_cycle_manifest(collector_build: str) -> dict:
    evidence = GLOBAL_EVENT_V2_PROTOCOL["evidence"]
    static_slots = sorted(
        [
            {"provider": "globalnews", "query_key": f"{theme}:{query}"}
            for theme, queries in evidence["broad_news_queries"].items()
            for query in queries
        ]
        + [
            {"provider": "xtrend", "query_key": f"woeid:{int(woeid)}"}
            for woeid in evidence["x_trend_woeids"]
        ]
        + [
            {"provider": "trendnews", "query_key": "ranked-global-discovery"}
        ],
        key=lambda row: (row["provider"], row["query_key"]),
    )
    return {
        "schema_version": 2,
        "collection_cycle_id": "cycle_" + "8" * 24,
        "cycle_kind": "formal-release-rehearsal-v1",
        "period_key": "release-20260806T120000.000000Z",
        "protocol_id": PROTOCOL_ID,
        "collector_semantics_id": GLOBAL_EVENT_V2_PROTOCOL["evidence"][
            "expected_collector_semantics_id"
        ],
        "collector_build_id": collector_build,
        "started_utc": 1_000.0,
        "completed_utc": 1_001.0,
        "server_started_utc": 1_000.0,
        "server_terminal_utc": 1_001.0,
        "status": "complete",
        "expected_static_slots": static_slots,
        "expected_dynamic_slots": [],
        "slot_receipts": [
            {
                "slot_kind": "static",
                **slot,
                "fetch_run_id": f"fetch_fixture_{index}",
                "status": "success",
                "item_count": 1,
                "raw_content_ids": [f"raw_{index:024x}"],
            }
            for index, slot in enumerate(static_slots, start=1)
        ],
    }


def _images():
    return (
        image_attestation(
            app_name="tradagent",
            image_ref=COLLECTOR_REF,
            image_digest=COLLECTOR_DIGEST,
        ),
        image_attestation(
            app_name="tradagent-paper-decision",
            image_ref=PAPER_DECISION_REF,
            image_digest=PAPER_DECISION_DIGEST,
        ),
        image_attestation(
            app_name="tradagent-paper-marker",
            image_ref=PAPER_MARKER_REF,
            image_digest=PAPER_MARKER_DIGEST,
        ),
    )


def _configuration_payload():
    protocol = GLOBAL_EVENT_V2_PROTOCOL
    evidence = protocol["evidence"]
    forecast = protocol["forecast"]
    invocation = forecast["invocation_policy"]
    collector = build_component_configuration(
        "collector",
        {
            "collector_mode": "formal-global-news-v2",
            "media_auto_migrate": False,
            "poller_interval_seconds": evidence["query_cycle"]["collector_interval_seconds"],
            "trading_hours_only": False,
            "ticker_watchlist": [],
            "enabled_sources": sorted(evidence["allowed_sources"]),
            "globalnews_enabled": True,
            "globalnews_query_slots": [
                {"provider": "globalnews", "query_key": f"{theme}:{query}"}
                for theme, queries in evidence["broad_news_queries"].items()
                for query in queries
            ],
            "globalnews_max_results_per_query": evidence["max_global_news_results_per_query"],
            "globalnews_retry_policy": evidence["query_cycle"]["globalnews_exception_retry_policy"],
            "x_enabled": True,
            "x_cycle_interval_seconds": evidence["x_cycle_interval_seconds"],
            "x_max_topics": evidence["max_x_search_requests_per_utc_day"],
            "x_max_results_per_query": evidence["max_x_results_per_query"],
            "paper_heartbeat_max_age_seconds": 93_600,
            "collector_semantics_id": evidence["expected_collector_semantics_id"],
        },
    )
    paper_decision = build_component_configuration(
        "paper_decision",
        {
            "media_auto_migrate": False,
            "paper_auto_migrate": False,
            "run_id": RUN_ID,
            "engine": "formal-global-v2",
            "universe": list(protocol["universe"]["symbols"]),
            "benchmark": protocol["portfolio"]["benchmark"],
            "analysts": ["news"],
            "global_topics_only": True,
            "media_poller_interval_seconds": evidence["query_cycle"]["collector_interval_seconds"],
            "llm_provider": forecast["provider"],
            "requested_model": forecast["requested_model"],
            "allowed_models": sorted(
                f"{forecast['provider']}:{model}" for model in forecast["allowed_returned_models"]
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
        },
    )
    paper_marker = build_component_configuration(
        "paper_marker",
        {
            "media_auto_migrate": False,
            "paper_auto_migrate": False,
            "run_id": RUN_ID,
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
        },
    )
    return build_release_configuration(collector, paper_decision, paper_marker)


def _receipt_payloads(
    collector_build: str,
    paper_decision_build: str,
    paper_marker_build: str,
) -> dict:
    configuration = _configuration_payload()
    binding = configuration["configuration_binding"]
    restore = build_restore_rehearsal_payload(
        source_cluster_fingerprint="sha256:" + "a" * 64,
        restored_cluster_fingerprint="sha256:" + "b" * 64,
        backup_fingerprint="sha256:" + "c" * 64,
        backup_completed_utc=1_002.0,
        collector_rehearsal=build_collector_rehearsal_payload(
            final_collection_cycle_manifest=_collection_cycle_manifest(
                collector_build
            ),
            component_configuration_id=binding["collector_configuration_id"],
        ),
        formal_trial_activity_rows=0,
        verification_completed_utc=1_003.0,
    )
    route_fingerprint = "sha256:" + "f" * 64
    alert = build_alert_delivery_payload(
        deliveries={
            role: build_alert_delivery_receipt(
                role=role,
                build_id=build_id,
                component_configuration_id=binding[f"{role}_configuration_id"],
                route_fingerprint=route_fingerprint,
                client_observed_utc=1_004.0 + index,
            )
            for index, (role, build_id) in enumerate(
                (
                    ("collector", collector_build),
                    ("paper_decision", paper_decision_build),
                    ("paper_marker", paper_marker_build),
                )
            )
        }
    )
    return {
        "configuration": configuration,
        "collector_preflight": build_runtime_preflight_payload(
            role="collector",
            build_id=collector_build,
            component_configuration_id=binding["collector_configuration_id"],
        ),
        "paper_decision_preflight": build_runtime_preflight_payload(
            role="paper_decision",
            build_id=paper_decision_build,
            component_configuration_id=binding["paper_decision_configuration_id"],
            outcome_semantics_id=OUTCOME_ID,
        ),
        "paper_marker_preflight": build_runtime_preflight_payload(
            role="paper_marker",
            build_id=paper_marker_build,
            component_configuration_id=binding["paper_marker_configuration_id"],
            outcome_semantics_id=OUTCOME_ID,
        ),
        "restore_rehearsal": restore,
        "alert_delivery": alert,
        "runtime_role_decommission": {
            "passed": True,
            "decommission_id": "decommission_" + "7" * 24,
            "legacy_role": "tradingagents-paper",
            "decision_role": "tradingagents-paper-decision",
            "marker_role": "tradingagents-paper-marker",
        },
    }


def _authorization():
    collector, paper_decision, paper_marker = _images()
    payloads = _receipt_payloads(
        collector["build_id"],
        paper_decision["build_id"],
        paper_marker["build_id"],
    )
    receipts = {
        receipt_type: build_release_receipt(
            receipt_type=receipt_type,
            protocol_id=PROTOCOL_ID,
            run_id=RUN_ID,
            payload=payload,
        )
        for receipt_type, payload in payloads.items()
    }
    authorization = build_trial_authorization(
        protocol_id=PROTOCOL_ID,
        run_id=RUN_ID,
        registration_id=REGISTRATION_ID,
        outcome_semantics_id=OUTCOME_ID,
        configuration_binding=payloads["configuration"]["configuration_binding"],
        collector_image=collector,
        paper_decision_image=paper_decision,
        paper_marker_image=paper_marker,
        release_receipt_ids={key: value["receipt_id"] for key, value in receipts.items()},
    )
    return authorization, receipts


@pytest.mark.unit
def test_release_receipts_and_authorization_are_content_addressed():
    authorization, receipts = _authorization()

    assert validate_trial_authorization(authorization) == authorization
    assert all(validate_release_receipt(receipt) == receipt for receipt in receipts.values())
    assert authorization["authorization_id"].startswith("activation_")
    assert authorization["images"]["collector"]["image_digest"] == COLLECTOR_DIGEST
    assert authorization["images"]["paper_decision"]["image_digest"] == PAPER_DECISION_DIGEST
    assert authorization["images"]["paper_marker"]["image_digest"] == PAPER_MARKER_DIGEST


@pytest.mark.unit
@pytest.mark.parametrize(
    "path,replacement",
    [
        (("outcome_semantics_id",), "outcome_semantics_" + "0" * 64),
        (
            ("configuration_binding", "paper_decision_configuration_id"),
            "config_" + "0" * 24,
        ),
        (("images", "paper_marker", "image_digest"), "sha256:" + "0" * 64),
        (("images", "paper_decision", "image_ref"), COLLECTOR_REF),
        (("release_receipt_ids", "alert_delivery"), "release_" + "0" * 24),
    ],
)
def test_any_authorization_material_change_requires_a_new_id(path, replacement):
    authorization, _ = _authorization()
    changed = copy.deepcopy(authorization)
    cursor = changed
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = replacement

    with pytest.raises(FormalActivationError):
        validate_trial_authorization(changed)


@pytest.mark.unit
def test_image_build_id_cannot_be_forged():
    authorization, _ = _authorization()
    authorization["images"]["paper_marker"]["build_id"] = "build_" + "0" * 24

    with pytest.raises(FormalActivationError, match="bind one exact runtime image"):
        validate_trial_authorization(authorization)


@pytest.mark.unit
@pytest.mark.parametrize(
    "receipt_type,field,replacement",
    [
        ("collector_preflight", "runtime_ready", False),
        ("paper_decision_preflight", "role", "collector"),
        ("paper_marker_preflight", "runtime_ready", False),
        ("restore_rehearsal", "passed", False),
        ("alert_delivery", "delivered", False),
        ("runtime_role_decommission", "legacy_role", "still-active"),
    ],
)
def test_failed_release_evidence_cannot_form_a_receipt(receipt_type, field, replacement):
    collector, paper_decision, paper_marker = _images()
    payload = _receipt_payloads(
        collector["build_id"],
        paper_decision["build_id"],
        paper_marker["build_id"],
    )[receipt_type]
    payload[field] = replacement

    with pytest.raises(FormalActivationError):
        build_release_receipt(
            receipt_type=receipt_type,
            protocol_id=PROTOCOL_ID,
            run_id=RUN_ID,
            payload=payload,
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("backup", "backup_id"), "backup_" + "0" * 24),
        (("verification", "verification_id"), "verification_" + "0" * 24),
        (("rehearsal_manifest_id",), "rehearsal_" + "0" * 24),
        (("collector_rehearsal", "manifest_id"), "cycle_manifest_" + "0" * 24),
        (("collector_rehearsal", "manifest", "status"), "incomplete"),
        (("verification", "formal_trial_activity_rows"), 1),
        (("verification", "external_calls"), 1),
    ],
)
def test_restore_rehearsal_recomputes_every_nested_identity(path, replacement):
    collector, paper_decision, paper_marker = _images()
    payload = _receipt_payloads(
        collector["build_id"],
        paper_decision["build_id"],
        paper_marker["build_id"],
    )["restore_rehearsal"]
    cursor = payload
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = replacement

    with pytest.raises(FormalActivationError):
        build_release_receipt(
            receipt_type="restore_rehearsal",
            protocol_id=PROTOCOL_ID,
            run_id=RUN_ID,
            payload=payload,
        )


@pytest.mark.unit
def test_restore_rehearsal_requires_isolation_and_coherent_ordering():
    collector, paper_decision, paper_marker = _images()
    manifest = _collection_cycle_manifest(collector["build_id"])
    collector_rehearsal = build_collector_rehearsal_payload(
        final_collection_cycle_manifest=manifest,
        component_configuration_id=_configuration_payload()[
            "configuration_binding"
        ]["collector_configuration_id"],
    )
    with pytest.raises(FormalActivationError, match="isolated cluster"):
        build_restore_rehearsal_payload(
            source_cluster_fingerprint="sha256:" + "a" * 64,
            restored_cluster_fingerprint="sha256:" + "a" * 64,
            backup_fingerprint="sha256:" + "c" * 64,
            backup_completed_utc=1_002.0,
            collector_rehearsal=collector_rehearsal,
            formal_trial_activity_rows=0,
            verification_completed_utc=1_003.0,
        )
    with pytest.raises(FormalActivationError, match="order collection"):
        build_restore_rehearsal_payload(
            source_cluster_fingerprint="sha256:" + "a" * 64,
            restored_cluster_fingerprint="sha256:" + "b" * 64,
            backup_fingerprint="sha256:" + "c" * 64,
            backup_completed_utc=999.0,
            collector_rehearsal=collector_rehearsal,
            formal_trial_activity_rows=0,
            verification_completed_utc=1_003.0,
        )

    with pytest.raises(FormalActivationError, match="zero formal trial activity"):
        build_restore_rehearsal_payload(
            source_cluster_fingerprint="sha256:" + "a" * 64,
            restored_cluster_fingerprint="sha256:" + "b" * 64,
            backup_fingerprint="sha256:" + "c" * 64,
            backup_completed_utc=1_002.0,
            collector_rehearsal=collector_rehearsal,
            formal_trial_activity_rows=1,
            verification_completed_utc=1_003.0,
        )


@pytest.mark.unit
def test_alert_aggregate_recomputes_child_ids_and_requires_one_route():
    collector, paper_decision, paper_marker = _images()
    payloads = _receipt_payloads(
        collector["build_id"],
        paper_decision["build_id"],
        paper_marker["build_id"],
    )
    alert = payloads["alert_delivery"]
    alert["deliveries"]["paper_marker"]["client_observed_utc"] += 1.0
    with pytest.raises(FormalActivationError, match="content-addressed"):
        build_release_receipt(
            receipt_type="alert_delivery",
            protocol_id=PROTOCOL_ID,
            run_id=RUN_ID,
            payload=alert,
        )

    deliveries = copy.deepcopy(payloads["alert_delivery"]["deliveries"])
    deliveries["paper_marker"] = build_alert_delivery_receipt(
        role="paper_marker",
        build_id=paper_marker["build_id"],
        component_configuration_id=payloads["configuration"]["configuration_binding"][
            "paper_marker_configuration_id"
        ],
        route_fingerprint="sha256:" + "e" * 64,
        client_observed_utc=1_006.0,
    )
    with pytest.raises(FormalActivationError, match="share one exact route"):
        build_alert_delivery_payload(deliveries=deliveries)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("protocol_id", "run_id"),
    [
        ("protocol_" + "0" * 24, RUN_ID),
        (PROTOCOL_ID, "different-formal-run"),
    ],
)
def test_configuration_receipt_must_match_its_exact_protocol_and_run(protocol_id, run_id):
    with pytest.raises(FormalActivationError, match="protocol or run"):
        build_release_receipt(
            receipt_type="configuration",
            protocol_id=protocol_id,
            run_id=run_id,
            payload=_configuration_payload(),
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("component_configuration_id", "config_" + "0" * 24),
        ("outcome_semantics_id", "outcome_semantics_" + "0" * 64),
        ("preflight_manifest_id", "preflight_" + "0" * 24),
    ],
)
def test_paper_preflight_cannot_reuse_identity_for_different_material(field, replacement):
    collector, paper_decision, paper_marker = _images()
    payload = _receipt_payloads(
        collector["build_id"],
        paper_decision["build_id"],
        paper_marker["build_id"],
    )["paper_decision_preflight"]
    payload[field] = replacement

    with pytest.raises(FormalActivationError, match="content-addressed"):
        build_release_receipt(
            receipt_type="paper_decision_preflight",
            protocol_id=PROTOCOL_ID,
            run_id=RUN_ID,
            payload=payload,
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("role", "app_name", "image_ref"),
    [
        ("paper_decision", "tradagent-paper-decision", PAPER_DECISION_REF),
        ("paper_marker", "tradagent-paper-marker", PAPER_MARKER_REF),
    ],
)
def test_runtime_requires_the_exact_platform_provided_paper_deployment(role, app_name, image_ref):
    authorization, _ = _authorization()
    result = require_runtime_authorization(
        authorization,
        role=role,
        outcome_semantics_id=OUTCOME_ID,
        component_configuration_id=authorization["configuration_binding"][
            f"{role}_configuration_id"
        ],
        env={
            "FLY_APP_NAME": app_name,
            "FLY_MACHINE_ID": "machine-1",
            "FLY_IMAGE_REF": image_ref,
            "TRADINGAGENTS_BUILD_ID": "build_" + "0" * 24,
        },
    )

    assert result == authorization["authorization_id"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "mutation",
    [
        {"FLY_APP_NAME": "tradagent", "FLY_IMAGE_REF": COLLECTOR_REF},
        {
            "FLY_APP_NAME": "tradagent-paper-decision",
            "FLY_IMAGE_REF": (
                "registry.fly.io/tradagent-paper-decision:deployment-01KZAE0P4ER12SS2215QXBSN0H"
            ),
        },
        {"TRADINGAGENTS_BUILD_ID": "build_" + "1" * 24},
    ],
)
def test_runtime_rejects_wrong_or_non_platform_image(mutation):
    authorization, _ = _authorization()

    with pytest.raises(FormalActivationError):
        require_runtime_authorization(
            authorization,
            role="paper_decision",
            outcome_semantics_id=OUTCOME_ID,
            component_configuration_id=authorization["configuration_binding"][
                "paper_decision_configuration_id"
            ],
            env=mutation,
        )


@pytest.mark.unit
def test_runtime_rejects_outcome_semantics_drift():
    authorization, _ = _authorization()

    with pytest.raises(FormalActivationError, match="outcome semantics"):
        require_runtime_authorization(
            authorization,
            role="paper_decision",
            outcome_semantics_id="outcome_semantics_" + "0" * 64,
            component_configuration_id=authorization["configuration_binding"][
                "paper_decision_configuration_id"
            ],
            env={
                "FLY_APP_NAME": "tradagent-paper-decision",
                "FLY_IMAGE_REF": PAPER_DECISION_REF,
            },
        )


@pytest.mark.unit
def test_runtime_rejects_configuration_drift():
    authorization, _ = _authorization()

    with pytest.raises(FormalActivationError, match="configuration"):
        require_runtime_authorization(
            authorization,
            role="paper_marker",
            outcome_semantics_id=OUTCOME_ID,
            component_configuration_id="config_" + "0" * 24,
            env={
                "FLY_APP_NAME": "tradagent-paper-marker",
                "FLY_IMAGE_REF": PAPER_MARKER_REF,
            },
        )
