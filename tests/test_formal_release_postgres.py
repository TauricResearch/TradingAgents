"""Real PostgreSQL lifecycle coverage for the formal release transaction.

This test intentionally requires a pristine disposable database migrated through
013.  It exercises the real trigger/RLS/transaction behavior that the unit-test
connection doubles cannot prove.  The administrator URL must authenticate
directly as a non-superuser LOGIN that is a member of the MPG-like NOLOGIN
``schema_admin`` role.
"""

from __future__ import annotations

import copy
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from tests.test_formal_activation import (
    _configuration_payload,
    _images,
)
from tradingagents import formal_release, ops_cli, poller
from tradingagents.dataflows.media_sources import _row
from tradingagents.dataflows.media_store import (
    _normalize_pg_url,
    open_store,
)
from tradingagents.formal_activation import (
    IMAGE_ROLES,
    build_alert_delivery_payload,
    build_alert_delivery_receipt,
    build_restore_rehearsal_payload,
    build_runtime_preflight_payload,
)
from tradingagents.outcome_semantics import outcome_semantics_id
from tradingagents.research_protocol import GLOBAL_EVENT_V2_PROTOCOL


class _InjectedReleaseFailure(RuntimeError):
    """Deterministic failure raised after a real middle receipt insert."""


def _release_database_url() -> str:
    value = os.getenv("TRADINGAGENTS_TEST_POSTGRES_RELEASE_URL")
    if not value:
        pytest.skip("TRADINGAGENTS_TEST_POSTGRES_RELEASE_URL is not configured")
    return _normalize_pg_url(value)


def _assert_direct_mpg_schema_admin(engine) -> None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT current_user::text AS current_role,"
                "session_user::text AS session_role,"
                "pg_catalog.pg_has_role(current_user,'schema_admin','MEMBER') "
                "AS schema_admin_member,"
                "(SELECT role.rolsuper FROM pg_catalog.pg_roles AS role "
                "WHERE role.rolname=current_user) AS is_superuser"
            )
        ).mappings().one()
    assert row == {
        "current_role": "tradingagents-app-v2",
        "session_role": "tradingagents-app-v2",
        "schema_admin_member": True,
        "is_superuser": False,
    }


def _count(engine, table_name: str) -> int:
    allowed = {
        "experiment_registry",
        "paper_runs",
        "formal_trial_registry",
        "paper_run_labels",
        "formal_role_split_decommissions",
        "formal_release_receipts",
        "formal_trial_authorizations",
    }
    assert table_name in allowed
    with engine.connect() as conn:
        return int(
            conn.execute(text(f"SELECT count(*) FROM public.{table_name}")).scalar_one()
        )


def _release_state(engine) -> dict[str, Any]:
    """Snapshot exact durable bytes and database-derived timestamps."""

    queries = {
        "protocol": (
            "SELECT protocol_id,created_utc,manifest_json FROM public.experiment_registry "
            "ORDER BY protocol_id"
        ),
        "run": (
            "SELECT run_id,created_utc,config_json FROM public.paper_runs ORDER BY run_id"
        ),
        "registry": (
            "SELECT protocol_id,run_id,registration_id,created_utc,details_json "
            "FROM public.formal_trial_registry ORDER BY protocol_id"
        ),
        "label": (
            "SELECT run_id,label,created_utc,details_json FROM public.paper_run_labels "
            "ORDER BY run_id,label"
        ),
        "decommission": (
            "SELECT decommission_id,legacy_role,decommissioned_utc,contract_id,details_json "
            "FROM public.formal_role_split_decommissions ORDER BY decommission_id"
        ),
        "receipts": (
            "SELECT receipt_id,receipt_type,protocol_id,run_id,created_utc,content_json "
            "FROM public.formal_release_receipts ORDER BY receipt_type"
        ),
        "authorization": (
            "SELECT protocol_id,run_id,registration_id,authorization_id,authorized_utc,"
            "outcome_semantics_id,configuration_manifest_id,collector_configuration_id,"
            "paper_decision_configuration_id,paper_marker_configuration_id,"
            "collector_build_id,paper_decision_build_id,paper_marker_build_id,"
            "authorization_json FROM public.formal_trial_authorizations "
            "ORDER BY protocol_id"
        ),
    }
    with engine.connect() as conn:
        state = {
            name: [dict(row) for row in conn.execute(text(sql)).mappings().all()]
            for name, sql in queries.items()
        }
        state["legacy_can_insert_targets"] = bool(
            conn.execute(
                text(
                    "SELECT pg_catalog.has_table_privilege("
                    "'tradingagents-paper','public.paper_targets','INSERT')"
                )
            ).scalar_one()
        )
    return state


def _run_real_collector_rehearsal(
    admin_url: str, monkeypatch, *, now: float | None = None
) -> dict[str, Any]:
    collector_image = _images()[0]
    collector_ref = collector_image["image_ref"]
    monkeypatch.setenv("FLY_APP_NAME", "tradagent")
    monkeypatch.setenv("FLY_IMAGE_REF", collector_ref)
    monkeypatch.setenv("FLY_MACHINE_ID", "release-postgres-integration")

    def fetch_news(query, captured, theme, *, limit):
        assert limit == GLOBAL_EVENT_V2_PROTOCOL["evidence"][
            "max_global_news_results_per_query"
        ]
        query_id = sum(query.encode("utf-8"))
        capture_id = int(captured * 1_000_000)
        return [
            _row(
                "globalnews",
                f"release-{theme}-{query_id}-{capture_id}",
                f"@{theme}",
                captured,
                author="Reuters",
                created_utc=captured - 1,
                title="Independent global developments report",
                metadata={
                    "article_url": (
                        "https://news.google.com/articles/"
                        f"{theme}-{query_id}-{capture_id}"
                    ),
                    "publisher_domain": "reuters.com",
                },
            )
        ]

    monkeypatch.setattr(poller, "fetch_global_news", fetch_news)
    monkeypatch.setattr(
        poller,
        "fetch_x_trends",
        lambda woeid: [{"name": f"World discussion {woeid}", "tweet_count": 10}],
    )
    monkeypatch.setattr(poller, "fetch_top_news_headlines", lambda: [])

    store = open_store(admin_url, auto_migrate=False)
    try:
        rehearsal = poller.run_formal_collector_release_rehearsal(
            store,
            now=time.time() if now is None else now,
            component_configuration_id=_configuration_payload()[
                "configuration_binding"
            ]["collector_configuration_id"],
            collector_build_id=collector_image["build_id"],
        )
    finally:
        store.close()
    assert rehearsal["passed"] is True
    assert len(rehearsal["manifest"]["expected_static_slots"]) == 13
    return rehearsal


def _release_inputs(collector_rehearsal: dict[str, Any]) -> dict[str, Any]:
    configuration = _configuration_payload()
    binding = configuration["configuration_binding"]
    images = dict(zip(IMAGE_ROLES, _images(), strict=True))
    outcome_id = outcome_semantics_id()

    runtime_materials = {
        role: {
            "component_configuration": configuration[f"{role}_configuration"],
            "preflight_payload": build_runtime_preflight_payload(
                role=role,
                build_id=images[role]["build_id"],
                component_configuration_id=binding[f"{role}_configuration_id"],
                outcome_semantics_id=(None if role == "collector" else outcome_id),
            ),
        }
        for role in IMAGE_ROLES
    }
    runtime_commands = {
        "collector": ["--formal-collector"],
        "paper_decision": ["decision-daemon"],
        "paper_marker": ["marker-daemon"],
    }
    machine_inventories = {
        role: [
            {
                "id": f"release-postgres-{role}",
                "state": "started",
                "config": {
                    "image": images[role]["image_ref"],
                    "init": {"cmd": runtime_commands[role]},
                    "metadata": {"fly_process_group": "app"},
                },
                "image_ref": {"digest": images[role]["image_digest"]},
            }
        ]
        for role in IMAGE_ROLES
    }

    cycle_manifest = collector_rehearsal["manifest"]
    observed = max(time.time(), float(cycle_manifest["server_terminal_utc"])) + 0.001
    restore_rehearsal = build_restore_rehearsal_payload(
        source_cluster_fingerprint="sha256:" + "a" * 64,
        restored_cluster_fingerprint="sha256:" + "b" * 64,
        backup_fingerprint="sha256:" + "c" * 64,
        backup_completed_utc=observed,
        collector_rehearsal=collector_rehearsal,
        formal_trial_activity_rows=0,
        verification_completed_utc=observed + 0.001,
    )
    route_fingerprint = "sha256:" + "f" * 64
    alert_delivery = build_alert_delivery_payload(
        deliveries={
            role: build_alert_delivery_receipt(
                role=role,
                build_id=images[role]["build_id"],
                component_configuration_id=binding[f"{role}_configuration_id"],
                route_fingerprint=route_fingerprint,
                client_observed_utc=observed + 0.002 + index * 0.001,
            )
            for index, role in enumerate(IMAGE_ROLES)
        }
    )
    return {
        "runtime_materials": runtime_materials,
        "machine_inventories": machine_inventories,
        "restore_rehearsal": restore_rehearsal,
        "alert_delivery": alert_delivery,
    }


def _inspect_restore_clone(
    *,
    admin_url: str,
    collector_rehearsal: dict[str, Any],
    decision_material: dict[str, Any],
    tmp_path,
    capsys,
    suffix: str,
) -> dict[str, Any]:
    collector_path = tmp_path / f"collector-{suffix}.json"
    decision_path = tmp_path / f"decision-{suffix}.json"
    collector_path.write_text(json.dumps(collector_rehearsal), encoding="utf-8")
    decision_path.write_text(json.dumps(decision_material), encoding="utf-8")
    args = SimpleNamespace(
        collector_rehearsal=collector_path,
        paper_decision_material=decision_path,
        source_cluster_fingerprint="sha256:" + "a" * 64,
        restored_cluster_fingerprint="sha256:" + "b" * 64,
        backup_fingerprint="sha256:" + "c" * 64,
        backup_completed_utc=(
            float(collector_rehearsal["server_completed_utc"]) + 0.000_001
        ),
    )
    assert ops_cli._build_restore_rehearsal_command(
        args,
        env={"TRADINGAGENTS_RESTORE_DB_URL": admin_url},
    ) == 0
    return json.loads(capsys.readouterr().out)


@pytest.mark.integration
def test_postgres_formal_release_full_transaction_lifecycle(
    monkeypatch, tmp_path, capsys
):
    admin_url = _release_database_url()
    engine = create_engine(admin_url, pool_pre_ping=True)
    try:
        _assert_direct_mpg_schema_admin(engine)
        assert _count(engine, "formal_role_split_decommissions") == 0
        assert _count(engine, "formal_release_receipts") == 0
        assert _count(engine, "formal_trial_authorizations") == 0
        assert _count(engine, "experiment_registry") == 0
        assert _count(engine, "paper_runs") == 0

        collector_rehearsal = _run_real_collector_rehearsal(
            admin_url, monkeypatch, now=time.time() - 86_400
        )
        inputs = _release_inputs(collector_rehearsal)
        inputs["restore_rehearsal"] = _inspect_restore_clone(
            admin_url=admin_url,
            collector_rehearsal=collector_rehearsal,
            decision_material=inputs["runtime_materials"]["paper_decision"],
            tmp_path=tmp_path,
            capsys=capsys,
            suffix="initial",
        )
        plan = formal_release.build_formal_release_plan(**inputs)

        original_insert_receipt = formal_release._insert_receipt

        def fail_after_middle_receipt(conn, receipt):
            original_insert_receipt(conn, receipt)
            if receipt["receipt_type"] == "paper_marker_preflight":
                raise _InjectedReleaseFailure("injected after a real middle receipt")

        with monkeypatch.context() as patch:
            patch.setattr(formal_release, "_insert_receipt", fail_after_middle_receipt)
            with pytest.raises(_InjectedReleaseFailure, match="real middle receipt"):
                formal_release.execute_formal_release(
                    admin_db_url=admin_url,
                    plan=plan,
                )

        # Bootstrap is intentionally a prior idempotent transaction. Every
        # release row and the trigger-driven legacy-role retirement roll back.
        rolled_back = _release_state(engine)
        assert len(rolled_back["protocol"]) == 1
        assert len(rolled_back["run"]) == 1
        assert len(rolled_back["registry"]) == 1
        assert len(rolled_back["label"]) == 1
        assert rolled_back["decommission"] == []
        assert rolled_back["receipts"] == []
        assert rolled_back["authorization"] == []
        assert rolled_back["legacy_can_insert_targets"] is True

        # A newer running or incomplete protocol cycle invalidates otherwise
        # exact restore evidence. This guards the race between rehearsal and
        # authorization rather than considering only newer complete cycles.
        store = open_store(admin_url, auto_migrate=False)
        try:
            blocking_cycle_id = store.start_collection_cycle(
                poller._formal_release_collection_cycle_spec(time.time() - 1),
                started_utc=time.time(),
            )
            blocking_cycle = store.finish_collection_cycle(
                blocking_cycle_id,
                completed_utc=time.time(),
            )
        finally:
            store.close()
        assert blocking_cycle["status"] == "incomplete"
        with pytest.raises(DBAPIError, match="final completed cycle"):
            formal_release.execute_formal_release(
                admin_db_url=admin_url,
                plan=plan,
            )
        assert _release_state(engine) == rolled_back

        # A new exact rehearsal can supersede the incomplete attempt. Use a
        # separate UTC request-budget day so the immutable X reservations from
        # the first rehearsal remain untouched.
        current_rehearsal = _run_real_collector_rehearsal(
            admin_url, monkeypatch, now=time.time()
        )
        inputs = _release_inputs(current_rehearsal)
        inputs["restore_rehearsal"] = _inspect_restore_clone(
            admin_url=admin_url,
            collector_rehearsal=current_rehearsal,
            decision_material=inputs["runtime_materials"]["paper_decision"],
            tmp_path=tmp_path,
            capsys=capsys,
            suffix="current",
        )
        plan = formal_release.build_formal_release_plan(**inputs)

        # Concurrent identical operators serialize on the transaction-level
        # advisory lock: exactly one writes and the other observes idempotence.
        with ThreadPoolExecutor(max_workers=2) as executor:
            releases = list(
                executor.map(
                    lambda _index: formal_release.execute_formal_release(
                        admin_db_url=admin_url,
                        plan=plan,
                    ),
                    range(2),
                )
            )
        assert sorted(release["status"] for release in releases) == [
            "already_released",
            "released",
        ]
        assert sorted(release["database_writes"] for release in releases) == [
            False,
            True,
        ]

        durable = _release_state(engine)
        assert len(durable["decommission"]) == 1
        assert len(durable["receipts"]) == 7
        assert len(durable["authorization"]) == 1
        assert durable["legacy_can_insert_targets"] is False

        retried = formal_release.execute_formal_release(
            admin_db_url=admin_url,
            plan=plan,
        )
        assert retried["status"] == "already_released"
        assert retried["database_writes"] is False
        assert _release_state(engine) == durable

        immutable_mutations = (
            "UPDATE public.formal_release_receipts SET content_json=content_json",
            "DELETE FROM public.formal_trial_authorizations",
        )
        for statement in immutable_mutations:
            with pytest.raises(DBAPIError, match="append-only"), engine.begin() as conn:
                conn.execute(text(statement))
        assert _release_state(engine) == durable

        drifted_inputs = copy.deepcopy(inputs)
        drifted_inputs["machine_inventories"]["collector"][0]["image_ref"][
            "digest"
        ] = "sha256:" + "0" * 64
        drifted_plan = formal_release.build_formal_release_plan(**drifted_inputs)
        assert drifted_plan.authorization["authorization_id"] != plan.authorization[
            "authorization_id"
        ]
        with pytest.raises(
            formal_release.FormalReleaseError,
            match="durable formal authorization differs from the plan",
        ):
            formal_release.execute_formal_release(
                admin_db_url=admin_url,
                plan=drifted_plan,
            )
        assert _release_state(engine) == durable
    finally:
        engine.dispose()
