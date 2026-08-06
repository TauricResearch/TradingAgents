"""Fail-closed, redacted behavior for the production operations CLI."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib

from tradingagents import ops_cli
from tradingagents.formal_activation import build_alert_delivery_receipt
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
)


@pytest.mark.unit
def test_fly_workers_explicitly_disable_runtime_migrations():
    root = Path(__file__).resolve().parents[1]
    collector = tomllib.loads((root / "fly.toml").read_text())
    decision = tomllib.loads((root / "fly.paper.decision.toml").read_text())
    marker = tomllib.loads((root / "fly.paper.marker.toml").read_text())

    assert collector["env"]["MEDIA_AUTO_MIGRATE"] == "false"
    assert collector["env"]["MEDIA_COLLECTION_ENABLED"] == "false"
    assert decision["processes"] == {"app": "decision-daemon"}
    assert marker["processes"] == {"app": "marker-daemon"}
    assert decision["env"]["MEDIA_AUTO_MIGRATE"] == "false"
    assert decision["env"]["PAPER_AUTO_MIGRATE"] == "false"
    assert decision["env"]["PAPER_DECISIONS_ENABLED"] == "false"
    assert marker["env"]["MEDIA_AUTO_MIGRATE"] == "false"
    assert marker["env"]["PAPER_AUTO_MIGRATE"] == "false"
    assert marker["env"]["PAPER_MARKS_ENABLED"] == "false"


def _paper_env(component: str = "paper-decision") -> dict[str, str]:
    app = "tradagent-paper-decision" if component == "paper-decision" else "tradagent-paper-marker"
    env = {
        "MEDIA_DB_URL": "postgresql://runtime:database-secret@db.example/research",
        "MEDIA_AUTO_MIGRATE": "false",
        "PAPER_AUTO_MIGRATE": "false",
        "PAPER_ENGINE": "formal-global-v2",
        "PAPER_RUN_ID": "global-event-v2-confirmatory-001",
        "PAPER_TICKERS": ",".join(GLOBAL_EVENT_V2_PROTOCOL["universe"]["symbols"]),
        "PAPER_BENCHMARK": "SPY",
        "PAPER_RETRY_ATTEMPTS": "3",
        "PAPER_RETRY_SECONDS": "300",
        "PAPER_PORTFOLIO_MODE": "long-only",
        "PAPER_TRADING_COST_BPS": "5",
        "PAPER_SLIPPAGE_BPS": "5",
        "PAPER_ANNUAL_BORROW_BPS": "0",
        "TRADINGAGENTS_ALERT_WEBHOOK_URL": "https://hooks.invalid/secret-path",
        "FLY_APP_NAME": app,
        "FLY_MACHINE_ID": "machine-1",
        "FLY_IMAGE_REF": (
            f"registry.fly.io/{app}:deployment-01KZAE0P4ER12SS2215QXBSN0H"
        ),
    }
    if component == "paper-decision":
        env.update({
            "PAPER_DECISIONS_ENABLED": "false",
            "PAPER_ANALYSTS": "news",
            "PAPER_GLOBAL_TOPICS_ONLY": "true",
            "PAPER_LLM_MODEL_ALLOWLIST": (
                "openai:gpt-5.4-mini,openai:gpt-5.4-mini-2026-03-17"
            ),
            "PAPER_LLM_MAX_CALLS_PER_DECISION": "3",
            "PAPER_LLM_MAX_CALLS_PER_UTC_DAY": "3",
            "PAPER_LLM_MAX_PROMPT_BYTES": "160000",
            "PAPER_LLM_MAX_COMPLETION_TOKENS": "8000",
            "PAPER_LLM_TIMEOUT_SECONDS": "180",
            "TRADINGAGENTS_OPENAI_REASONING_EFFORT": "low",
            "TRADINGAGENTS_LLM_MAX_RETRIES": "0",
            "OPENAI_API_KEY": "sk-model-secret-123456789",
            "MEDIA_POLLER_INTERVAL": "3600",
        })
    elif component == "paper-marker":
        env["PAPER_MARKS_ENABLED"] = "false"
    else:
        raise ValueError("test paper component is invalid")
    return env


def _collector_env() -> dict[str, str]:
    return {
        "MEDIA_DB_URL": "postgresql://runtime:database-secret@db.example/research",
        "MEDIA_AUTO_MIGRATE": "false",
        "MEDIA_COLLECTION_ENABLED": "false",
        "MEDIA_POLLER_SOURCES": "x",
        "MEDIA_POLLER_INTERVAL": "3600",
        "MEDIA_POLLER_TRADING_HOURS": "false",
        "MEDIA_POLLER_X_INTERVAL": "86400",
        "MEDIA_POLLER_X_TOPICS": "3",
        "MEDIA_POLLER_X_LIMIT": "10",
        "PAPER_HEARTBEAT_MAX_AGE": "93600",
        "X_BEARER_TOKEN": "x-secret-token",
        "TRADINGAGENTS_ALERT_WEBHOOK_URL": "https://hooks.invalid/secret-path",
        "FLY_APP_NAME": "tradagent",
        "FLY_MACHINE_ID": "machine-1",
        "FLY_IMAGE_REF": (
            "registry.fly.io/tradagent:"
            "deployment-01KZAE0P4ER12SS2215QXBSN0H"
        ),
    }


class FakeStore:
    dialect = "postgresql"

    def __init__(self, now: float, *, missing_slot: bool = False):
        cutoff = datetime(2026, 8, 6, tzinfo=timezone.utc).timestamp()
        keys = sorted(ops_cli._expected_global_news_keys())
        if missing_slot:
            keys = keys[:-1]
        self.rows = [
            {
                "provider": "globalnews",
                "query_key": key,
                "started_utc": cutoff - 120,
                "completed_utc": cutoff - 60,
                "status": "success",
                "formal_eligible_item_count": 1,
                "formal_eligible_evidence_ids": [
                    f"evidence_{index:024x}"
                ],
                "formal_eligible_lineage": [{
                    "evidence_id": f"evidence_{index:024x}",
                    "raw_content_id": f"raw_{index:024x}",
                }],
                "cursor_after": cutoff - 60,
                "metadata_json": json.dumps({
                    "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
                    "collector_semantics_id": GLOBAL_EVENT_V2_PROTOCOL["evidence"][
                        "expected_collector_semantics_id"
                    ],
                }),
            }
            for index, key in enumerate(keys, start=1)
        ]
        self.rows.append(
            {
                "provider": "polymarket",
                "query_key": "energy:empty",
                "started_utc": cutoff - 90,
                "completed_utc": cutoff - 30,
                "status": "empty",
                "cursor_after": None,
            }
        )
        self.meta = {
            "poller:last_cycle_utc": now - 60,
            "poller:last_failure_utc": None,
        }
        self.meta_reads = []
        self.closed = False

    def coverage_report(self, *_args, **_kwargs):
        return {"complete": True}

    def fetch_runs(self, *, provider=None, limit=100):
        rows = [row for row in self.rows if provider is None or row["provider"] == provider]
        return rows[:limit]

    def get_meta(self, key):
        self.meta_reads.append(key)
        return self.meta.get(key)

    def close(self):
        self.closed = True


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class _MappingResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class _SplitRoleConnection:
    def __init__(self, role_row):
        self.role_row = role_row
        self.statements = []

    def execute(self, statement, _params=None):
        sql = str(statement)
        self.statements.append(sql)
        if "has_schema_privilege" in sql or "has_database_privilege" in sql:
            return _ScalarResult(False)
        if "formal_role_split_preflight" in sql:
            return _MappingResult([self.role_row])
        if "formal_trial_authorizations" in sql:
            return _MappingResult([{"authorization_json": "fixture"}])
        raise AssertionError(f"unexpected split-role SQL: {sql}")


class _ConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_args):
        return False


class _SplitRoleEngine:
    def __init__(self, connection):
        self.connection = connection
        self.connect_count = 0

    def connect(self):
        self.connect_count += 1
        return _ConnectionContext(self.connection)


class _TriggerCatalogConnection:
    def __init__(self, rows):
        self.rows = rows
        self.statement = ""

    def execute(self, statement):
        self.statement = str(statement)
        return _RowsResult(self.rows)


class _SequenceConnection:
    def __init__(self, *row_sets):
        self.row_sets = list(row_sets)
        self.statements = []

    def execute(self, statement, _params=None):
        self.statements.append(str(statement))
        return _RowsResult(self.row_sets.pop(0))


def _migration_006_function_source(name: str) -> str:
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "006_atomic_fetch_lineage.sql"
    ).read_text()
    match = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{re.escape(name)}\([^)]*\).*?"
        r"AS \$\$(.*?)\$\$;",
        migration,
        flags=re.DOTALL,
    )
    assert match is not None
    return match.group(1)


def _migration_005_function_source(name: str) -> str:
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "005_formal_primary_run_registry.sql"
    ).read_text()
    match = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{re.escape(name)}\(\).*?"
        r"AS \$\$(.*?)\$\$;",
        migration,
        flags=re.DOTALL,
    )
    assert match is not None
    return match.group(1)


def _migration_010_function_source(name: str) -> str:
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "010_formal_artifact_governance.sql"
    ).read_text()
    match = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{re.escape(name)}\([^)]*\).*?"
        r"AS \$\$(.*?)\$\$;",
        migration,
        flags=re.DOTALL,
    )
    assert match is not None
    return match.group(1)


def _migration_011_function_source(name: str) -> str:
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "011_formal_llm_budget_and_attempt_binding.sql"
    ).read_text()
    match = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{re.escape(name)}\([^)]*\).*?"
        r"AS \$\$(.*?)\$\$;",
        migration,
        flags=re.DOTALL,
    )
    assert match is not None
    return match.group(1)


def _migration_fetch_lifecycle_function_source() -> str:
    return _migration_006_function_source("enforce_fetch_run_lifecycle")


def _fetch_lifecycle_trigger_row(**overrides):
    fields = {
        "table_schema": "public",
        "table_name": "fetch_runs",
        "table_kind": "r",
        "trigger_name": "immutable_fetch_runs",
        "function_schema": "public",
        "function_name": "enforce_fetch_run_lifecycle",
        "enabled": "O",
        "internal": False,
        "type_bits": 31,
        "attribute_numbers": "",
        "unconditional": True,
        "function_argument_count": 0,
        "returns_trigger": True,
        "function_language": "plpgsql",
        "security_definer": False,
        "function_kind": "f",
        "ordinary_trigger": True,
        "not_deferrable": True,
        "not_initially_deferred": True,
        "function_source": _migration_fetch_lifecycle_function_source(),
        "function_comment": ops_cli._FETCH_RECEIPT_LIFECYCLE_CONTRACT,
        "function_config": ["search_path=pg_catalog"],
        "leakproof": False,
        "volatility": "v",
        "parallel_safety": "u",
        "strict": False,
        "returns_set": False,
        "default_acl": True,
        "no_binary_binding": True,
        "runtime_is_not_owner": True,
        "runtime_is_not_owner_member": True,
        "trusted_language": True,
        "trigger_argument_count": 0,
        "trigger_argument_bytes": 0,
        "not_partition_clone": True,
        "no_old_transition_table": True,
        "no_new_transition_table": True,
        "public_execute_revoked": False,
    }
    fields.update(overrides)
    return tuple(fields.values())


def _fetch_item_trigger_row(**overrides):
    fields = {
        "table_name": "fetch_run_items",
        "trigger_name": "immutable_fetch_run_items",
        "function_name": "enforce_fetch_run_item_lifecycle",
        "type_bits": 31,
        "function_source": _migration_006_function_source(
            "enforce_fetch_run_item_lifecycle"
        ),
        "function_comment": ops_cli._FETCH_ITEM_LIFECYCLE_CONTRACT,
    }
    fields.update(overrides)
    return _fetch_lifecycle_trigger_row(**fields)


def _fetch_content_trigger_row(**overrides):
    fields = {
        "table_name": "fetch_runs",
        "trigger_name": "validate_fetch_run_content_completion",
        "function_name": "enforce_fetch_run_content_completion",
        "type_bits": 19,
        "function_source": _migration_006_function_source(
            "enforce_fetch_run_content_completion"
        ),
        "function_comment": ops_cli._FETCH_CONTENT_COMPLETION_CONTRACT,
    }
    fields.update(overrides)
    return _fetch_lifecycle_trigger_row(**fields)


def _formal_registry_trigger_row(
    table_name: str,
    trigger_name: str,
    function_name: str,
    function_comment: str,
    **overrides,
):
    fields = {
        "table_name": table_name,
        "trigger_name": trigger_name,
        "function_name": function_name,
        "type_bits": 7,
        "function_source": _migration_005_function_source(function_name),
        "function_comment": function_comment,
        "default_acl": False,
        "public_execute_revoked": True,
    }
    fields.update(overrides)
    return _fetch_lifecycle_trigger_row(**fields)


def _append_only_trigger_row(table_name: str, **overrides):
    fields = {
        "table_name": table_name,
        "trigger_name": f"immutable_{table_name}",
        "function_name": "reject_append_only_mutation",
        "type_bits": 27,
        "function_source": _migration_005_function_source(
            "reject_append_only_mutation"
        ),
        "function_comment": ops_cli._APPEND_ONLY_CONTRACT,
    }
    fields.update(overrides)
    return _fetch_lifecycle_trigger_row(**fields)


def _formal_governance_trigger_row(
    table_name: str, trigger_name: str, function_name: str, **overrides
):
    function_hash, function_comment = ops_cli._FORMAL_GOVERNANCE_TRIGGER_CONTRACTS[
        function_name
    ]
    fields = {
        "table_name": table_name,
        "trigger_name": trigger_name,
        "function_name": function_name,
        "type_bits": 7,
        "function_source": _migration_010_function_source(function_name),
        "function_comment": function_comment,
        "default_acl": False,
        "public_execute_revoked": True,
        "security_definer": function_name == "enforce_formal_artifact_governance",
    }
    assert ops_cli._normalized_pg_prosrc_sha256(fields["function_source"]) == function_hash
    fields.update(overrides)
    return _fetch_lifecycle_trigger_row(**fields)


def _formal_governance_helper_row(name: str, **overrides):
    source_hash, comment, arguments, return_type, strict = (
        ops_cli._FORMAL_GOVERNANCE_HELPER_CONTRACTS[name]
    )
    fields = {
        "function_schema": "public",
        "function_name": name,
        "identity_arguments": arguments,
        "return_type": return_type,
        "language": "sql",
        "security_definer": False,
        "function_kind": "f",
        "function_source": _migration_010_function_source(name),
        "function_comment": comment,
        "function_config": ["search_path=pg_catalog"],
        "leakproof": False,
        "volatility": "i",
        "parallel_safety": "u",
        "strict": strict,
        "returns_set": False,
        "no_binary_binding": True,
        "runtime_is_not_owner": True,
        "runtime_is_not_owner_member": True,
        "trusted_language": True,
        "public_execute_revoked": True,
    }
    assert ops_cli._normalized_pg_prosrc_sha256(fields["function_source"]) == source_hash
    fields.update(overrides)
    return tuple(fields.values())


def _formal_llm_trigger_row(
    table_name: str, trigger_name: str, function_name: str, **overrides
):
    contracts = {
        "enforce_formal_decision_bundle_attempt": (
            ops_cli._FORMAL_LLM_ATTEMPT_BINDING_PROSRC_SHA256,
            ops_cli._FORMAL_LLM_ATTEMPT_BINDING_CONTRACT,
        ),
        "enforce_no_attempt_retry_after_llm_reservation": (
            ops_cli._FORMAL_LLM_NO_RETRY_PROSRC_SHA256,
            ops_cli._FORMAL_LLM_NO_RETRY_CONTRACT,
        ),
    }
    function_hash, function_comment = contracts[function_name]
    fields = {
        "table_name": table_name,
        "trigger_name": trigger_name,
        "function_name": function_name,
        "type_bits": 7,
        "function_source": _migration_011_function_source(function_name),
        "function_comment": function_comment,
        "default_acl": False,
        "public_execute_revoked": True,
    }
    assert ops_cli._normalized_pg_prosrc_sha256(fields["function_source"]) == function_hash
    fields.update(overrides)
    return _fetch_lifecycle_trigger_row(**fields)


def _formal_llm_reservation_function_row(**overrides):
    fields = {
        "function_schema": "public",
        "function_name": "reserve_formal_llm_invocation_budget",
        "identity_arguments": (
            "p_run_id text, p_decision_date text, p_stage text, p_provider text, "
            "p_requested_model text, p_input_bundle_id text, p_prompt_id text, "
            "p_prompt_bytes integer, p_max_prompt_bytes integer, "
            "p_max_completion_tokens integer"
        ),
        "function_result": (
            "TABLE(reservation_artifact_id text, reservation_receipt_json text, "
            "decision_count integer, daily_count integer, utc_day text, "
            "reserved_utc double precision, max_calls_per_decision integer, "
            "max_calls_per_utc_day integer, decision_counter_key text, "
            "daily_counter_key text)"
        ),
        "language": "plpgsql",
        "security_definer": True,
        "function_kind": "f",
        "function_source": _migration_011_function_source(
            "reserve_formal_llm_invocation_budget"
        ),
        "function_comment": ops_cli._FORMAL_LLM_RESERVATION_CONTRACT,
        "function_config": ["search_path=pg_catalog"],
        "leakproof": False,
        "volatility": "v",
        "parallel_safety": "u",
        "strict": False,
        "returns_set": True,
        "no_binary_binding": True,
        "runtime_is_not_owner": True,
        "runtime_is_not_owner_member": True,
        "trusted_language": True,
        "public_execute_revoked": True,
        "runtime_execute": True,
    }
    fields.update(overrides)
    return tuple(fields.values())


def _lineage_validator_row(**overrides):
    fields = {
        "function_schema": "public",
        "function_name": "formal_evidence_lineage_is_valid",
        "argument_count": 2,
        "returns_boolean": True,
        "language": "sql",
        "security_definer": False,
        "function_kind": "f",
        "function_source": _migration_006_function_source(
            "formal_evidence_lineage_is_valid"
        ),
        "function_comment": ops_cli._FORMAL_LINEAGE_VALIDATOR_CONTRACT,
        "function_config": ["search_path=pg_catalog"],
        "leakproof": False,
        "volatility": "i",
        "parallel_safety": "u",
        "strict": True,
        "returns_set": False,
        "default_acl": True,
        "no_binary_binding": True,
        "runtime_is_not_owner": True,
        "runtime_is_not_owner_member": True,
        "trusted_language": True,
        "identity_arguments": "evidence_ids_text text, lineage_text text",
    }
    fields.update(overrides)
    return tuple(fields.values())


def _fetch_lineage_contract_connection(lifecycle_rows=None, **validator_overrides):
    return _SequenceConnection(
        [_fetch_lifecycle_trigger_row()] if lifecycle_rows is None else lifecycle_rows,
        [_fetch_item_trigger_row(), _fetch_content_trigger_row()],
        [_lineage_validator_row(**validator_overrides)],
    )


@pytest.mark.unit
def test_trigger_discovery_uses_unfiltered_postgres_catalog_and_full_contract():
    connection = _TriggerCatalogConnection(
        [
            _append_only_trigger_row("paper_decisions"),
            _append_only_trigger_row("paper_targets"),
        ]
    )

    tables = ops_cli._installed_immutable_trigger_tables(connection)

    assert tables == {"paper_decisions", "paper_targets"}
    assert "pg_catalog.pg_trigger" in connection.statement
    assert "information_schema.triggers" not in connection.statement
    assert "trigger_function.prosrc" in connection.statement
    assert "trigger_function.proconfig" in connection.statement
    assert "trigger_function.proowner" in connection.statement
    assert "CAST(trigger.tgtype AS integer)" in connection.statement

    for override in (
        {"function_source": "BEGIN RETURN OLD; END"},
        {"function_comment": "stale"},
        {"function_config": ["search_path=public"]},
        {"security_definer": True},
        {"runtime_is_not_owner": False},
        {"type_bits": 31},
    ):
        assert ops_cli._installed_immutable_trigger_tables(
            _TriggerCatalogConnection([
                _append_only_trigger_row("paper_decisions", **override)
            ])
        ) == set()


@pytest.mark.unit
def test_primary_registry_contract_requires_unique_keys_and_every_insert_guard():
    activity_tables = {
        "paper_decisions",
        "paper_decision_bundles",
        "paper_events",
        "paper_forecasts",
        "paper_targets",
        "paper_strategy_targets",
        "paper_marks",
        "paper_strategy_marks",
        "paper_price_receipts",
        "paper_decision_attempt_events",
        "paper_price_capture_attempt_events",
        "paper_price_capture_batches",
        "paper_price_integrity_failures",
        "paper_interval_assignments",
    }
    constraints = [
        ("p", ["protocol_id"]),
        ("u", ["run_id"]),
        ("u", ["registration_id"]),
    ]
    triggers = [
        _formal_registry_trigger_row(
            "formal_trial_registry",
            "validate_formal_trial_registry_insert",
            "enforce_formal_trial_registry_insert",
            ops_cli._FORMAL_REGISTRY_INSERT_CONTRACT,
        ),
        _formal_registry_trigger_row(
            "paper_artifacts",
            "require_formal_primary_run",
            "enforce_formal_artifact_primary_run",
            ops_cli._FORMAL_PRIMARY_ARTIFACT_CONTRACT,
            enabled="A",
        ),
        _formal_registry_trigger_row(
            "paper_run_labels",
            "guard_confirmatory_run_label",
            "enforce_formal_run_label",
            ops_cli._FORMAL_PRIMARY_LABEL_CONTRACT,
        ),
        *[
            _formal_registry_trigger_row(
                table,
                "require_formal_primary_run",
                "enforce_formal_primary_run_activity",
                ops_cli._FORMAL_PRIMARY_ACTIVITY_CONTRACT,
            )
            for table in activity_tables
        ],
    ]

    assert ops_cli._formal_registry_contract_is_installed(
        _SequenceConnection(constraints, triggers)
    )
    assert not ops_cli._formal_registry_contract_is_installed(
        _SequenceConnection(constraints, triggers[:-1])
    )
    assert not ops_cli._formal_registry_contract_is_installed(
        _SequenceConnection(constraints[:-1], triggers)
    )
    tampered_source = list(triggers)
    tampered_source[0] = _formal_registry_trigger_row(
        "formal_trial_registry",
        "validate_formal_trial_registry_insert",
        "enforce_formal_trial_registry_insert",
        ops_cli._FORMAL_REGISTRY_INSERT_CONTRACT,
        function_source="BEGIN RETURN NEW; END",
    )
    assert not ops_cli._formal_registry_contract_is_installed(
        _SequenceConnection(constraints, tampered_source)
    )
    unsafe_search_path = list(triggers)
    unsafe_search_path[-1] = _formal_registry_trigger_row(
        str(triggers[-1][1]),
        "require_formal_primary_run",
        "enforce_formal_primary_run_activity",
        ops_cli._FORMAL_PRIMARY_ACTIVITY_CONTRACT,
        function_config=["search_path=public"],
    )
    assert not ops_cli._formal_registry_contract_is_installed(
        _SequenceConnection(constraints, unsafe_search_path)
    )
    public_execute = list(triggers)
    public_execute[1] = _formal_registry_trigger_row(
        "paper_artifacts",
        "require_formal_primary_run",
        "enforce_formal_artifact_primary_run",
        ops_cli._FORMAL_PRIMARY_ARTIFACT_CONTRACT,
        public_execute_revoked=False,
    )
    assert not ops_cli._formal_registry_contract_is_installed(
        _SequenceConnection(constraints, public_execute)
    )


@pytest.mark.unit
def test_formal_governance_preflight_authenticates_triggers_helpers_and_hashes():
    triggers = [
        _formal_governance_trigger_row(
            "paper_artifacts",
            "govern_formal_artifact_insert",
            "enforce_formal_artifact_governance",
        ),
        _formal_governance_trigger_row(
            "paper_run_labels",
            "govern_formal_label_insert",
            "enforce_formal_label_governance",
        ),
    ]
    helpers = [
        _formal_governance_helper_row(name)
        for name in ops_cli._FORMAL_GOVERNANCE_HELPER_CONTRACTS
    ]
    assert ops_cli._formal_governance_contract_is_installed(
        _SequenceConnection(triggers, helpers)
    )

    assert not ops_cli._formal_governance_contract_is_installed(
        _SequenceConnection(triggers[:-1], helpers)
    )
    tampered_helpers = list(helpers)
    tampered_helpers[0] = _formal_governance_helper_row(
        "formal_jsonb_exact_keys", function_source="SELECT TRUE"
    )
    assert not ops_cli._formal_governance_contract_is_installed(
        _SequenceConnection(triggers, tampered_helpers)
    )
    unsafe_triggers = list(triggers)
    unsafe_triggers[0] = _formal_governance_trigger_row(
        "paper_artifacts",
        "govern_formal_artifact_insert",
        "enforce_formal_artifact_governance",
        function_config=["search_path=public"],
    )
    assert not ops_cli._formal_governance_contract_is_installed(
        _SequenceConnection(unsafe_triggers, helpers)
    )


@pytest.mark.unit
def test_formal_llm_preflight_authenticates_function_triggers_schema_and_acl():
    triggers = [
        _formal_llm_trigger_row(
            "paper_decision_bundles",
            "validate_formal_decision_bundle_attempt",
            "enforce_formal_decision_bundle_attempt",
        ),
        _formal_llm_trigger_row(
            "paper_decision_attempt_events",
            "reject_attempt_retry_after_llm_reservation",
            "enforce_no_attempt_retry_after_llm_reservation",
        ),
    ]
    columns = [
        "bucket_date:date:true",
        "counter_key:text:true",
        "counter_kind:text:true",
        "first_reserved_utc:double precision:true",
        "frozen_limit:integer:true",
        "last_reserved_utc:double precision:true",
        "protocol_id:text:true",
        "reserved_calls:integer:true",
        "run_id:text:true",
        "scope:text:true",
    ]
    keys = [
        "p:counter_key",
        "u:scope,protocol_id,run_id,counter_kind,bucket_date",
    ]
    function = [_formal_llm_reservation_function_row()]
    table = [(columns, keys, True, True, True, True, True)]

    assert ops_cli._formal_llm_budget_contract_is_installed(
        _SequenceConnection(triggers, function, table)
    )
    assert not ops_cli._formal_llm_budget_contract_is_installed(
        _SequenceConnection(triggers[:-1], function, table)
    )
    assert not ops_cli._formal_llm_budget_contract_is_installed(
        _SequenceConnection(
            triggers,
            [_formal_llm_reservation_function_row(security_definer=False)],
            table,
        )
    )
    assert not ops_cli._formal_llm_budget_contract_is_installed(
        _SequenceConnection(
            triggers,
            function,
            [(columns, keys, True, False, True, True, True)],
        )
    )


@pytest.mark.unit
def test_primary_registry_preflight_binds_exact_configured_run():
    run_id = "global-event-v2-confirmatory-001"
    registration_id = "registration_000000000000000000000001"
    created_utc = 1_786_000_000.0
    details = {
        "registration_type": "confirmatory",
        "run_id": run_id,
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "registration_id": registration_id,
        "outcomes_accessed_before_registration": False,
    }
    config = {
        "engine": "formal-global-v2",
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "trial_registration_id": registration_id,
    }
    details_json = json.dumps(details, sort_keys=True, separators=(",", ":"))
    connection = _SequenceConnection(
        [
            (
                GLOBAL_EVENT_V2_PROTOCOL_ID,
                run_id,
                registration_id,
                created_utc,
                details_json,
            )
        ],
        [(json.dumps(config),)],
        [(created_utc, details_json)],
    )

    check = ops_cli._formal_primary_registry_check(connection, run_id)

    assert check.name == "database.primary_confirmatory_run"
    assert check.passed
    assert run_id not in check.detail


@pytest.mark.unit
@pytest.mark.parametrize(
    ("registry_rows", "configured_run_id"),
    [
        ([], "configured-run"),
        (
            [
                (GLOBAL_EVENT_V2_PROTOCOL_ID, "run-a", "registration-a", 1.0, "{}"),
                (GLOBAL_EVENT_V2_PROTOCOL_ID, "run-b", "registration-b", 1.0, "{}"),
            ],
            "run-a",
        ),
        (
            [(GLOBAL_EVENT_V2_PROTOCOL_ID, "other-run", "registration-a", 1.0, "{}")],
            "configured-run",
        ),
    ],
    ids=["absent", "multiple", "mismatch"],
)
def test_primary_registry_preflight_rejects_absent_multiple_or_mismatch(
    registry_rows, configured_run_id
):
    check = ops_cli._formal_primary_registry_check(
        _SequenceConnection(registry_rows), configured_run_id
    )

    assert check.name == "database.primary_confirmatory_run"
    assert not check.passed


@pytest.mark.unit
@pytest.mark.parametrize("enabled", ["O", "A"])
def test_fetch_receipt_lifecycle_trigger_accepts_enabled_exact_binding(enabled):
    connection = _SequenceConnection(
        [_fetch_lifecycle_trigger_row(enabled=enabled)],
        [_fetch_item_trigger_row(), _fetch_content_trigger_row()],
        [_lineage_validator_row()],
    )

    check = ops_cli._fetch_receipt_lifecycle_check(connection)

    assert check.name == "database.terminal_fetch_receipts_immutable"
    assert check.passed
    assert all("information_schema.triggers" not in sql for sql in connection.statements)
    assert "pg_catalog.pg_trigger" in connection.statements[0]
    assert "immutable_fetch_runs" in connection.statements[0]
    assert "formal_evidence_lineage_is_valid" in connection.statements[2]


@pytest.mark.unit
def test_fetch_receipt_lifecycle_body_fingerprint_is_tied_to_migration_006():
    source = _migration_fetch_lifecycle_function_source()
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "006_atomic_fetch_lineage.sql"
    ).read_text()

    assert (
        ops_cli._normalized_pg_prosrc_sha256(source)
        == ops_cli._FETCH_RECEIPT_LIFECYCLE_PROSRC_SHA256
    )
    assert ops_cli._FETCH_RECEIPT_LIFECYCLE_CONTRACT in migration
    assert "SET search_path = pg_catalog" in migration
    assert "pg_catalog.to_jsonb(NEW)" in source


@pytest.mark.unit
@pytest.mark.parametrize(
    ("function_name", "expected_hash", "expected_contract"),
    [
        (
            "enforce_fetch_run_item_lifecycle",
            ops_cli._FETCH_ITEM_LIFECYCLE_PROSRC_SHA256,
            ops_cli._FETCH_ITEM_LIFECYCLE_CONTRACT,
        ),
        (
            "enforce_fetch_run_content_completion",
            ops_cli._FETCH_CONTENT_COMPLETION_PROSRC_SHA256,
            ops_cli._FETCH_CONTENT_COMPLETION_CONTRACT,
        ),
        (
            "formal_evidence_lineage_is_valid",
            ops_cli._FORMAL_LINEAGE_VALIDATOR_PROSRC_SHA256,
            ops_cli._FORMAL_LINEAGE_VALIDATOR_CONTRACT,
        ),
    ],
)
def test_content_lineage_body_fingerprints_are_tied_to_migration_006(
    function_name, expected_hash, expected_contract
):
    source = _migration_006_function_source(function_name)
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "006_atomic_fetch_lineage.sql"
    ).read_text()

    assert ops_cli._normalized_pg_prosrc_sha256(source) == expected_hash
    assert expected_contract in migration


@pytest.mark.unit
@pytest.mark.parametrize(
    "rows",
    [
        [],
        [_fetch_lifecycle_trigger_row(enabled="D")],
        [_fetch_lifecycle_trigger_row(enabled="R")],
        [_fetch_lifecycle_trigger_row(table_name="some_other_table")],
        [_fetch_lifecycle_trigger_row(table_schema="shadow")],
        [_fetch_lifecycle_trigger_row(function_name="reject_append_only_mutation")],
        [_fetch_lifecycle_trigger_row(function_schema="shadow")],
        [_fetch_lifecycle_trigger_row(type_bits=27)],
        [_fetch_lifecycle_trigger_row(attribute_numbers="7")],
        [_fetch_lifecycle_trigger_row(unconditional=False)],
        [_fetch_lifecycle_trigger_row(function_source="BEGIN RETURN NEW; END")],
        [_fetch_lifecycle_trigger_row(function_comment="stale-contract")],
        [_fetch_lifecycle_trigger_row(function_config=None)],
        [_fetch_lifecycle_trigger_row(function_config=["search_path=public"])],
        [_fetch_lifecycle_trigger_row(security_definer=True)],
        [_fetch_lifecycle_trigger_row(leakproof=True)],
        [_fetch_lifecycle_trigger_row(default_acl=False)],
        [_fetch_lifecycle_trigger_row(runtime_is_not_owner=False)],
        [_fetch_lifecycle_trigger_row(runtime_is_not_owner_member=False)],
        [_fetch_lifecycle_trigger_row(trigger_argument_count=1, trigger_argument_bytes=8)],
        [_fetch_lifecycle_trigger_row(not_partition_clone=False)],
    ],
    ids=[
        "missing",
        "disabled",
        "replica-only",
        "wrong-table",
        "wrong-table-schema",
        "wrong-function",
        "wrong-function-schema",
        "missing-insert-event",
        "column-limited-update",
        "conditional",
        "no-op-function-body",
        "stale-function-contract",
        "missing-search-path-config",
        "wrong-search-path-config",
        "security-definer",
        "leakproof",
        "unexpected-acl",
        "runtime-owns-function",
        "runtime-inherits-function-owner",
        "unexpected-trigger-argument",
        "partition-clone",
    ],
)
def test_fetch_receipt_lifecycle_trigger_fails_closed_on_wrong_catalog_binding(rows):
    check = ops_cli._fetch_receipt_lifecycle_check(
        _fetch_lineage_contract_connection(lifecycle_rows=rows)
    )

    assert check.name == "database.terminal_fetch_receipts_immutable"
    assert not check.passed


@pytest.mark.unit
@pytest.mark.parametrize(
    "content_rows",
    [
        [],
        [_fetch_item_trigger_row()],
        [_fetch_content_trigger_row()],
        [_fetch_item_trigger_row(function_source="BEGIN RETURN NEW; END"),
         _fetch_content_trigger_row()],
        [_fetch_item_trigger_row(), _fetch_content_trigger_row(type_bits=31)],
        [_fetch_item_trigger_row(), _fetch_content_trigger_row(function_config=None)],
    ],
    ids=[
        "missing-both",
        "missing-completion",
        "missing-items",
        "item-noop-body",
        "completion-wrong-events",
        "completion-missing-search-path",
    ],
)
def test_content_lineage_trigger_contract_fails_closed(content_rows):
    connection = _SequenceConnection(
        [_fetch_lifecycle_trigger_row()],
        content_rows,
        [_lineage_validator_row()],
    )

    assert not ops_cli._fetch_receipt_lifecycle_check(connection).passed


@pytest.mark.unit
@pytest.mark.parametrize(
    "overrides",
    [
        {"function_source": "SELECT TRUE"},
        {"function_comment": "stale-contract"},
        {"function_config": None},
        {"security_definer": True},
        {"volatility": "v"},
        {"strict": False},
        {"runtime_is_not_owner": False},
        {"identity_arguments": "lineage_text text, evidence_ids_text text"},
    ],
)
def test_formal_lineage_validator_contract_fails_closed(overrides):
    assert not ops_cli._fetch_receipt_lifecycle_check(
        _fetch_lineage_contract_connection(**overrides)
    ).passed


@pytest.mark.unit
def test_non_postgres_split_security_preflight_names_role_contract_failure():
    class NonPostgresStore:
        dialect = "sqlite"

    checks = ops_cli._postgres_security_checks(NonPostgresStore(), "paper-decision")

    role_contract = next(
        check
        for check in checks
        if check.name == "database.formal_role_split_contract"
    )
    assert not role_contract.passed


@pytest.mark.unit
@pytest.mark.parametrize(
    ("component", "login"),
    [
        ("paper-decision", "tradingagents-paper-decision"),
        ("paper-marker", "tradingagents-paper-marker"),
    ],
)
def test_split_preflight_authenticates_role_and_authorization_on_same_connection(
    monkeypatch, component, login
):
    from tradingagents.formal_roles import ROLE_SPLIT_CONTRACT_ID
    from tradingagents.paper_trading import PaperStore

    role_row = {
        "current_role": login,
        "session_role": login,
        "contract_id": ROLE_SPLIT_CONTRACT_ID,
        "ready": True,
        "legacy_decommissioned": True,
        "policy_contract_matches": True,
    }
    connection = _SplitRoleConnection(role_row)
    engine = _SplitRoleEngine(connection)
    store = type("Store", (), {"dialect": "postgresql", "engine": engine})()
    monkeypatch.setattr(
        ops_cli,
        "_formal_primary_registry_check",
        lambda *_args: ops_cli.CheckResult(
            "database.primary_confirmatory_run", True, "fixture registry passes"
        ),
    )
    monkeypatch.setattr(
        ops_cli,
        "_runtime_material",
        lambda *_args: {"component_configuration": {"configuration_id": "config_fixture"}},
    )
    monkeypatch.setattr(
        PaperStore,
        "_validated_authorization_row",
        staticmethod(lambda *_args, **_kwargs: {"authorization_id": "authorization_fixture"}),
    )
    monkeypatch.setattr(
        "tradingagents.formal_activation.require_runtime_authorization",
        lambda *_args, **_kwargs: "authorization_fixture",
    )

    checks = ops_cli._postgres_security_checks(
        store,
        component,
        "global-event-v2-confirmatory-001",
        _paper_env(component),
    )

    assert engine.connect_count == 1
    assert any("formal_role_split_preflight" in sql for sql in connection.statements)
    assert any("formal_trial_authorizations" in sql for sql in connection.statements)
    assert next(
        check for check in checks if check.name == "database.formal_role_split_contract"
    ).passed
    assert next(
        check for check in checks if check.name == "database.runtime_authorization"
    ).passed


@pytest.mark.unit
@pytest.mark.parametrize(
    "override",
    [
        {"current_role": "schema_admin"},
        {"session_role": "tradingagents-paper-marker"},
        {"ready": False},
        {"legacy_decommissioned": False},
        {"policy_contract_matches": False},
    ],
)
def test_split_preflight_rejects_wrong_login_set_role_or_rls_drift(
    monkeypatch, override
):
    from tradingagents.formal_roles import ROLE_SPLIT_CONTRACT_ID

    row = {
        "current_role": "tradingagents-paper-decision",
        "session_role": "tradingagents-paper-decision",
        "contract_id": ROLE_SPLIT_CONTRACT_ID,
        "ready": True,
        "legacy_decommissioned": True,
        "policy_contract_matches": True,
        **override,
    }
    connection = _SplitRoleConnection(row)
    store = type(
        "Store",
        (),
        {"dialect": "postgresql", "engine": _SplitRoleEngine(connection)},
    )()
    monkeypatch.setattr(
        ops_cli,
        "_formal_primary_registry_check",
        lambda *_args: ops_cli.CheckResult(
            "database.primary_confirmatory_run", True, "fixture registry passes"
        ),
    )

    checks = ops_cli._postgres_security_checks(
        store,
        "paper-decision",
        "global-event-v2-confirmatory-001",
        _paper_env(),
    )

    assert not next(
        check for check in checks if check.name == "database.formal_role_split_contract"
    ).passed


@pytest.mark.unit
def test_precision_discovery_requires_every_replay_column_to_be_float8():
    rows = [
        (table, column, "float8")
        for table, column in ops_cli._POSTGRES_DOUBLE_PRECISION_COLUMNS
    ]
    assert not ops_cli._non_double_precision_columns(
        _TriggerCatalogConnection(rows)
    )

    narrowed = list(rows)
    table, column, _ = narrowed[0]
    narrowed[0] = (table, column, "float4")
    assert ops_cli._non_double_precision_columns(
        _TriggerCatalogConnection(narrowed)
    ) == {(table, column)}


@pytest.mark.unit
def test_preflight_refuses_database_open_when_auto_migrate_is_not_disabled():
    env = _paper_env()
    env["MEDIA_AUTO_MIGRATE"] = "true"
    opened = []

    report = ops_cli.run_preflight(
        "paper-decision",
        env=env,
        now=datetime(2026, 8, 6, 1, tzinfo=timezone.utc),
        store_factory=lambda url: opened.append(url),
    )

    assert not report.ready
    assert not opened
    assert any(
        check.name == "database.connection" and not check.passed for check in report.checks
    )
    assert "database-secret" not in json.dumps(report.as_dict())


@pytest.mark.unit
def test_preflight_rejects_retired_combined_paper_component():
    with pytest.raises(ValueError, match="paper-decision"):
        ops_cli.run_preflight("paper", env=_paper_env())


@pytest.mark.unit
@pytest.mark.parametrize(
    ("component", "pause_name"),
    [
        ("collector", "MEDIA_COLLECTION_ENABLED"),
        ("paper-decision", "PAPER_DECISIONS_ENABLED"),
        ("paper-marker", "PAPER_MARKS_ENABLED"),
    ],
)
def test_component_preflight_requires_its_own_explicit_pause(component, pause_name):
    env = _collector_env() if component == "collector" else _paper_env(component)
    env[pause_name] = "true"

    checks = ops_cli._configuration_checks(component, env)

    pause_check = next(check for check in checks if check.name.endswith("_paused"))
    assert not pause_check.passed


@pytest.mark.unit
@pytest.mark.parametrize(
    ("component", "credential"),
    [
        ("collector", "OPENAI_API_KEY"),
        ("collector", "ROBINHOOD_PASSWORD"),
        ("collector", "TRUTHSOCIAL_TOKEN"),
        ("paper-decision", "X_BEARER_TOKEN"),
        ("paper-decision", "ANTHROPIC_API_KEY"),
        ("paper-decision", "ALPHA_VANTAGE_API_KEY"),
        ("paper-marker", "OPENAI_API_KEY"),
        ("paper-marker", "X_BEARER_TOKEN"),
        ("paper-marker", "FIDELITY_PASSWORD"),
    ],
)
def test_component_preflight_rejects_cross_role_credentials(component, credential):
    env = _collector_env() if component == "collector" else _paper_env(component)
    env[credential] = "prohibited-secret"

    checks = ops_cli._configuration_checks(component, env)

    assert not next(
        check for check in checks if check.name == "config.formal_component"
    ).passed


@pytest.mark.unit
def test_marker_preflight_requires_no_model_configuration_or_credential():
    checks = ops_cli._configuration_checks("paper-marker", _paper_env("paper-marker"))

    assert all(check.passed for check in checks)


@pytest.mark.unit
def test_decision_preflight_requires_its_exact_model_credential():
    env = _paper_env()
    env.pop("OPENAI_API_KEY")

    checks = ops_cli._configuration_checks("paper-decision", env)

    assert not next(
        check for check in checks if check.name == "config.formal_component"
    ).passed


@pytest.mark.unit
def test_paper_preflight_requires_configured_primary_run_id(monkeypatch):
    env = _paper_env()
    env.pop("PAPER_RUN_ID")
    now = datetime(2026, 8, 6, 1, tzinfo=timezone.utc)
    store = FakeStore(now.timestamp())
    monkeypatch.setattr(ops_cli, "_postgres_security_checks", lambda *_args: [])

    report = ops_cli.run_preflight(
        "paper-decision", env=env, now=now, store_factory=lambda _url: store
    )
    check = next(check for check in report.checks if check.name == "config.formal_component")

    assert not report.ready
    assert not check.passed
    assert "global-event-v2-confirmatory-001" not in json.dumps(report.as_dict())


@pytest.mark.unit
def test_preflight_redacts_database_exception(monkeypatch):
    env = _paper_env()
    database_url = env["MEDIA_DB_URL"]

    def fail(_url):
        raise RuntimeError(f"could not connect to {database_url}")

    report = ops_cli.run_preflight(
        "paper-decision",
        env=env,
        now=datetime(2026, 8, 6, 1, tzinfo=timezone.utc),
        store_factory=fail,
    )
    encoded = json.dumps(report.as_dict(), sort_keys=True)

    assert not report.ready
    assert database_url not in encoded
    assert "database-secret" not in encoded
    assert "RuntimeError" in encoded


@pytest.mark.unit
def test_preflight_passes_discoverable_runtime_checks(monkeypatch):
    env = _paper_env()
    now = datetime(2026, 8, 6, 1, tzinfo=timezone.utc)
    store = FakeStore(now.timestamp())
    monkeypatch.setattr(
        ops_cli,
        "_postgres_security_checks",
        lambda _store, _component, *_args, **_kwargs: [
            ops_cli.CheckResult("database.security_fixture", True, "security checks passed")
        ],
    )

    report = ops_cli.run_preflight(
        "paper-decision", env=env, now=now, store_factory=lambda _url: store
    )

    assert report.ready
    assert store.closed
    assert next(
        check for check in report.checks if check.name == "data.expected_global_news_slots"
    ).passed
    encoded = json.dumps(report.as_dict(), sort_keys=True)
    assert "database-secret" not in encoded
    assert "secret-path" not in encoded
    assert "sk-model-secret" not in encoded
    assert not any(key.startswith("paper:last_") for key in store.meta_reads)


@pytest.mark.unit
def test_marker_preflight_skips_decision_receipts_and_legacy_heartbeats(monkeypatch):
    env = _paper_env("paper-marker")
    now = datetime(2026, 8, 6, 1, tzinfo=timezone.utc)
    store = FakeStore(now.timestamp())
    monkeypatch.setattr(ops_cli, "_postgres_security_checks", lambda *_args: [])

    report = ops_cli.run_preflight(
        "paper-marker", env=env, now=now, store_factory=lambda _url: store
    )

    assert report.ready
    assert store.meta_reads == []
    assert not any(check.name.startswith("data.") for check in report.checks)


@pytest.mark.unit
def test_default_preflight_store_explicitly_disables_migrations(monkeypatch):
    from tradingagents.dataflows import media_store

    env = _paper_env("paper-marker")
    now = datetime(2026, 8, 6, 1, tzinfo=timezone.utc)
    store = FakeStore(now.timestamp())
    opened = []

    def open_without_migration(url, *, auto_migrate):
        opened.append((url, auto_migrate))
        return store

    monkeypatch.setattr(media_store, "open_store", open_without_migration)
    monkeypatch.setattr(ops_cli, "_postgres_security_checks", lambda *_args: [])

    report = ops_cli.run_preflight("paper-marker", env=env, now=now)

    assert report.ready
    assert opened == [(env["MEDIA_DB_URL"], False)]


def _paused_health_row(component: str, now: float) -> dict:
    return {
        "runtime_component": component,
        "event_type": "paused",
        "observed_utc": now - 10,
        "latest_success_utc": None,
        "latest_failure_utc": None,
        "latest_paused_utc": now - 10,
    }


@pytest.mark.unit
def test_collector_health_requires_two_fresh_authorized_paused_workers(monkeypatch):
    from tradingagents import poller

    now = datetime(2026, 8, 6, 1, tzinfo=timezone.utc).timestamp()
    release = {"authorized": True, "collector_configuration_id": "config_collector"}
    rows = [_paused_health_row("decision", now), _paused_health_row("marker", now)]
    monkeypatch.setattr(
        ops_cli,
        "_runtime_material",
        lambda *_args: {
            "component_configuration": {"configuration_id": "config_collector"},
            "preflight_payload": {"build_id": "build_collector"},
        },
    )
    monkeypatch.setattr(
        poller,
        "_formal_runtime_health_projection",
        lambda *_args, **_kwargs: (release, rows),
    )
    monkeypatch.setattr(
        poller,
        "_validated_formal_runtime_health_projection",
        lambda release_value, row_values: (release_value, row_values),
    )

    checks = ops_cli._formal_runtime_health_checks(object(), _collector_env(), now)

    assert all(check.passed for check in checks)


@pytest.mark.unit
def test_paused_heartbeat_cannot_mask_an_equal_timestamp_failure(monkeypatch):
    from tradingagents import poller

    now = datetime(2026, 8, 6, 1, tzinfo=timezone.utc).timestamp()
    rows = [_paused_health_row("decision", now), _paused_health_row("marker", now)]
    rows[0]["latest_success_utc"] = now - 20
    rows[0]["latest_failure_utc"] = now - 20
    monkeypatch.setattr(
        ops_cli,
        "_runtime_material",
        lambda *_args: {
            "component_configuration": {"configuration_id": "config_collector"},
            "preflight_payload": {"build_id": "build_collector"},
        },
    )
    monkeypatch.setattr(
        poller,
        "_formal_runtime_health_projection",
        lambda *_args, **_kwargs: (
            {"authorized": True, "collector_configuration_id": "config_collector"},
            rows,
        ),
    )
    monkeypatch.setattr(
        poller,
        "_validated_formal_runtime_health_projection",
        lambda release_value, row_values: (release_value, row_values),
    )

    checks = ops_cli._formal_runtime_health_checks(object(), _collector_env(), now)

    decision = next(
        check for check in checks if check.name == "health.paper_decision_paused"
    )
    marker = next(
        check for check in checks if check.name == "health.paper_marker_paused"
    )
    assert not decision.passed
    assert marker.passed


@pytest.mark.unit
@pytest.mark.parametrize("failure", ["unauthorized", "missing", "stale", "active"])
def test_collector_health_fails_closed_for_incomplete_split_state(monkeypatch, failure):
    from tradingagents import poller

    now = datetime(2026, 8, 6, 1, tzinfo=timezone.utc).timestamp()
    release = {"authorized": True, "collector_configuration_id": "config_collector"}
    rows = [_paused_health_row("decision", now), _paused_health_row("marker", now)]
    if failure == "unauthorized":
        release = {"authorized": False, "collector_configuration_id": None}
        rows = []
    elif failure == "missing":
        rows.pop()
    elif failure == "stale":
        rows[0]["observed_utc"] = now - 100_000
        rows[0]["latest_paused_utc"] = now - 100_000
    else:
        rows[0]["event_type"] = "success"
        rows[0]["latest_success_utc"] = rows[0]["observed_utc"]
        rows[0]["latest_paused_utc"] = None
    monkeypatch.setattr(
        ops_cli,
        "_runtime_material",
        lambda *_args: {
            "component_configuration": {"configuration_id": "config_collector"},
            "preflight_payload": {"build_id": "build_collector"},
        },
    )
    monkeypatch.setattr(
        poller,
        "_formal_runtime_health_projection",
        lambda *_args, **_kwargs: (release, rows),
    )
    monkeypatch.setattr(
        poller,
        "_validated_formal_runtime_health_projection",
        lambda release_value, row_values: (release_value, row_values),
    )

    checks = ops_cli._formal_runtime_health_checks(object(), _collector_env(), now)

    assert not all(check.passed for check in checks)


@pytest.mark.unit
def test_preflight_fails_when_one_expected_news_slot_is_missing(monkeypatch):
    env = _paper_env()
    now = datetime(2026, 8, 6, 1, tzinfo=timezone.utc)
    store = FakeStore(now.timestamp(), missing_slot=True)
    monkeypatch.setattr(ops_cli, "_postgres_security_checks", lambda *_args: [])

    report = ops_cli.run_preflight(
        "paper-decision", env=env, now=now, store_factory=lambda _url: store
    )
    slot = next(
        check for check in report.checks if check.name == "data.expected_global_news_slots"
    )

    assert not report.ready
    assert not slot.passed
    assert slot.detail.startswith("only 9/10")


@pytest.mark.unit
def test_preflight_rejects_old_slot_success_outside_cutoff_cycle(monkeypatch):
    env = _paper_env()
    now = datetime(2026, 8, 6, 1, tzinfo=timezone.utc)
    store = FakeStore(now.timestamp())
    cutoff = datetime(2026, 8, 6, tzinfo=timezone.utc).timestamp()
    for row in store.rows:
        if row["provider"] == "globalnews":
            row["started_utc"] = cutoff - 4_501
    monkeypatch.setattr(ops_cli, "_postgres_security_checks", lambda *_args: [])

    report = ops_cli.run_preflight(
        "paper-decision", env=env, now=now, store_factory=lambda _url: store
    )
    slot = next(
        check for check in report.checks if check.name == "data.expected_global_news_slots"
    )

    assert not report.ready
    assert not slot.passed
    assert slot.detail.startswith("only 0/10")


@pytest.mark.unit
@pytest.mark.parametrize("newer_state", ["running", "completed_after_cutoff"])
def test_preflight_uses_latest_started_cutoff_candidate_per_news_slot(
    monkeypatch, newer_state
):
    env = _paper_env()
    now = datetime(2026, 8, 6, 1, tzinfo=timezone.utc)
    cutoff = datetime(2026, 8, 6, tzinfo=timezone.utc).timestamp()
    store = FakeStore(now.timestamp())
    newer = dict(store.rows[0])
    newer["fetch_run_id"] = "fetch_newer"
    newer["started_utc"] = cutoff - 20
    if newer_state == "running":
        newer["status"] = "running"
        newer["completed_utc"] = None
    else:
        newer["completed_utc"] = cutoff + 20
    store.rows.append(newer)
    monkeypatch.setattr(ops_cli, "_postgres_security_checks", lambda *_args: [])

    report = ops_cli.run_preflight(
        "paper-decision", env=env, now=now, store_factory=lambda _url: store
    )
    slot = next(
        check for check in report.checks
        if check.name == "data.expected_global_news_slots"
    )

    assert not report.ready
    assert not slot.passed
    assert slot.detail.startswith("only 9/10")


@pytest.mark.unit
def test_preflight_ignores_receipt_started_after_cutoff(monkeypatch):
    env = _paper_env()
    now = datetime(2026, 8, 6, 1, tzinfo=timezone.utc)
    cutoff = datetime(2026, 8, 6, tzinfo=timezone.utc).timestamp()
    store = FakeStore(now.timestamp())
    post_cutoff = dict(store.rows[0])
    post_cutoff["fetch_run_id"] = "fetch_post_cutoff"
    post_cutoff["started_utc"] = cutoff + 20
    post_cutoff["completed_utc"] = cutoff + 40
    store.rows.append(post_cutoff)
    monkeypatch.setattr(ops_cli, "_postgres_security_checks", lambda *_args: [])

    report = ops_cli.run_preflight(
        "paper-decision", env=env, now=now, store_factory=lambda _url: store
    )
    slot = next(
        check for check in report.checks
        if check.name == "data.expected_global_news_slots"
    )

    assert report.ready
    assert slot.passed


@pytest.mark.unit
def test_preflight_accepts_one_audited_strict_core_absence(monkeypatch):
    env = _paper_env()
    now = datetime(2026, 8, 6, 1, tzinfo=timezone.utc)
    store = FakeStore(now.timestamp())
    store.rows[0]["status"] = "empty"
    store.rows[0]["cursor_after"] = None
    store.rows[0]["formal_eligible_item_count"] = 0
    store.rows[0]["formal_eligible_evidence_ids"] = []
    store.rows[0]["formal_eligible_lineage"] = []
    monkeypatch.setattr(ops_cli, "_postgres_security_checks", lambda *_args: [])

    report = ops_cli.run_preflight(
        "paper-decision", env=env, now=now, store_factory=lambda _url: store
    )
    slot = next(
        check for check in report.checks if check.name == "data.expected_global_news_slots"
    )

    assert report.ready
    assert slot.passed


@pytest.mark.unit
def test_preflight_rejects_when_every_receipt_has_no_strict_core_news(monkeypatch):
    env = _paper_env()
    now = datetime(2026, 8, 6, 1, tzinfo=timezone.utc)
    store = FakeStore(now.timestamp())
    for row in store.rows:
        if row["provider"] == "globalnews":
            row["formal_eligible_item_count"] = 0
            row["formal_eligible_evidence_ids"] = []
            row["formal_eligible_lineage"] = []
    monkeypatch.setattr(ops_cli, "_postgres_security_checks", lambda *_args: [])

    report = ops_cli.run_preflight(
        "paper-decision", env=env, now=now, store_factory=lambda _url: store
    )
    slots = next(
        check for check in report.checks
        if check.name == "data.expected_global_news_slots"
    )
    available = next(
        check for check in report.checks
        if check.name == "data.strict_core_news_available"
    )

    assert not report.ready
    assert slots.passed
    assert not available.passed


@pytest.mark.unit
def test_preflight_rejects_inconsistent_eligible_evidence_lineage(monkeypatch):
    env = _paper_env()
    now = datetime(2026, 8, 6, 1, tzinfo=timezone.utc)
    store = FakeStore(now.timestamp())
    store.rows[0]["formal_eligible_evidence_ids"] = [
        "evidence_000000000000000000000001",
        "evidence_000000000000000000000001",
    ]
    monkeypatch.setattr(ops_cli, "_postgres_security_checks", lambda *_args: [])

    report = ops_cli.run_preflight(
        "paper-decision", env=env, now=now, store_factory=lambda _url: store
    )
    slot = next(
        check for check in report.checks
        if check.name == "data.expected_global_news_slots"
    )

    assert not report.ready
    assert not slot.passed
    assert slot.detail.startswith("only 9/10")


@pytest.mark.unit
def test_preflight_rejects_identity_only_or_malformed_content_lineage(monkeypatch):
    env = _paper_env()
    now = datetime(2026, 8, 6, 1, tzinfo=timezone.utc)
    store = FakeStore(now.timestamp())
    store.rows[0]["formal_eligible_lineage"][0]["raw_content_id"] = "raw_tampered"
    monkeypatch.setattr(ops_cli, "_postgres_security_checks", lambda *_args: [])

    report = ops_cli.run_preflight(
        "paper-decision", env=env, now=now, store_factory=lambda _url: store
    )
    slot = next(
        check for check in report.checks
        if check.name == "data.expected_global_news_slots"
    )

    assert not report.ready
    assert not slot.passed


@pytest.mark.unit
@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"protocol_id": "protocol_stale", "collector_semantics_id": "collector_stale"},
        {
            "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
            "collector_semantics_id": "collector_stale",
        },
        "not-json",
    ],
)
def test_preflight_rejects_stale_or_malformed_collector_identity(
    monkeypatch, metadata
):
    env = _paper_env()
    now = datetime(2026, 8, 6, 1, tzinfo=timezone.utc)
    store = FakeStore(now.timestamp())
    store.rows[0]["metadata_json"] = (
        metadata if isinstance(metadata, str) else json.dumps(metadata)
    )
    monkeypatch.setattr(ops_cli, "_postgres_security_checks", lambda *_args: [])

    report = ops_cli.run_preflight(
        "paper-decision", env=env, now=now, store_factory=lambda _url: store
    )
    slot = next(
        check for check in report.checks
        if check.name == "data.expected_global_news_slots"
    )

    assert not report.ready
    assert not slot.passed
    assert slot.detail.startswith("only 9/10")


@pytest.mark.unit
def test_preflight_rejects_paid_x_receipt_without_atomic_budget_lineage(monkeypatch):
    env = _paper_env()
    now = datetime(2026, 8, 6, 1, tzinfo=timezone.utc)
    store = FakeStore(now.timestamp())
    store.rows.append({
        "provider": "x",
        "query_key": '"global event" reaction',
        "started_utc": now.timestamp() - 120,
        "completed_utc": now.timestamp() - 60,
        "status": "success",
        "item_count": 10,
        "inserted_count": 10,
        "cost_units": 1.0,
        "cursor_after": now.timestamp() - 60,
        "metadata_json": "{}",
    })
    monkeypatch.setattr(ops_cli, "_postgres_security_checks", lambda *_args: [])

    report = ops_cli.run_preflight(
        "paper-decision", env=env, now=now, store_factory=lambda _url: store
    )
    accounting = next(
        check for check in report.checks if check.name == "data.x_request_accounting"
    )

    assert not report.ready
    assert not accounting.passed


@pytest.mark.unit
@pytest.mark.parametrize(
    ("key", "value", "failed_check"),
    [
        ("PAPER_LLM_MODEL_ALLOWLIST", "openai:unexpected-model", "config.formal_component"),
        ("PAPER_LLM_MAX_CALLS_PER_DECISION", "0", "config.formal_component"),
        ("PAPER_LLM_MAX_CALLS_PER_UTC_DAY", "4", "config.formal_component"),
        ("PAPER_LLM_MAX_PROMPT_BYTES", "159999", "config.formal_component"),
        ("PAPER_LLM_MAX_COMPLETION_TOKENS", "8001", "config.formal_component"),
        ("PAPER_LLM_TIMEOUT_SECONDS", "179", "config.formal_component"),
        ("TRADINGAGENTS_LLM_BACKEND_URL", "https://proxy.invalid", "config.formal_component"),
        (
            "TRADINGAGENTS_OPENAI_REASONING_EFFORT", "medium",
            "config.formal_component",
        ),
        ("TRADINGAGENTS_TEMPERATURE", "0.2", "config.formal_component"),
        ("PAPER_RETRY_ATTEMPTS", "27", "config.worker_retry_envelope"),
        ("TRADINGAGENTS_LLM_MAX_RETRIES", "1", "config.llm_sdk_retries_disabled"),
    ],
)
def test_preflight_fails_closed_on_unsafe_llm_policy(
    monkeypatch, key, value, failed_check
):
    env = _paper_env()
    env[key] = value
    now = datetime(2026, 8, 6, 1, tzinfo=timezone.utc)
    store = FakeStore(now.timestamp())
    monkeypatch.setattr(ops_cli, "_postgres_security_checks", lambda *_args: [])

    report = ops_cli.run_preflight(
        "paper-decision", env=env, now=now, store_factory=lambda _url: store
    )

    assert not report.ready
    assert not next(check for check in report.checks if check.name == failed_check).passed


@pytest.mark.unit
@pytest.mark.parametrize("component", ["collector", "paper-decision", "paper-marker"])
def test_alert_test_never_prints_endpoint(monkeypatch, capsys, component):
    endpoint = "https://hooks.invalid/super-secret"
    monkeypatch.setenv("TRADINGAGENTS_ALERT_WEBHOOK_URL", endpoint)
    captured = {}
    role = ops_cli._INTERNAL_COMPONENT_ROLES[component]
    material = {
        "component_configuration": {
            "configuration_id": "config_" + "1" * 24,
        },
        "preflight_payload": {"build_id": "build_" + "2" * 24},
    }

    def delivered(component, event, **kwargs):
        captured.update({"component": component, "event": event, **kwargs})
        return True

    monkeypatch.setattr(ops_cli, "_runtime_material", lambda *_args: material)
    monkeypatch.setattr(ops_cli, "emit_alert", delivered)
    assert (
        ops_cli._alert_test(
            component,
            timeout=2.0,
            json_output=True,
            observed_utc=1_786_000_000.0,
        )
        == 0
    )
    output = capsys.readouterr().out

    assert endpoint not in output
    assert "super-secret" not in output
    assert json.loads(output) == build_alert_delivery_receipt(
        role=role,
        build_id=material["preflight_payload"]["build_id"],
        component_configuration_id=material["component_configuration"][
            "configuration_id"
        ],
        route_fingerprint="sha256:"
        + hashlib.sha256(endpoint.encode("utf-8")).hexdigest(),
        client_observed_utc=1_786_000_000.0,
    )
    assert captured["component"] == component
    assert captured["event"] == "operator_delivery_test"


@pytest.mark.unit
def test_alert_json_fails_before_delivery_when_runtime_material_is_invalid(
    monkeypatch, capsys
):
    endpoint = "https://hooks.invalid/super-secret"
    monkeypatch.setenv("TRADINGAGENTS_ALERT_WEBHOOK_URL", endpoint)
    called = []
    monkeypatch.setattr(
        ops_cli,
        "_runtime_material",
        lambda *_args: (_ for _ in ()).throw(ValueError("secret configuration detail")),
    )
    monkeypatch.setattr(
        ops_cli, "emit_alert", lambda *_args, **_kwargs: called.append(True)
    )

    assert ops_cli._alert_test("collector", timeout=2.0, json_output=True) == 1
    output = capsys.readouterr().out

    assert not called
    assert json.loads(output) == {
        "status": "failed",
        "error_code": "runtime_material_invalid",
    }
    assert endpoint not in output
    assert "secret configuration detail" not in output


@pytest.mark.unit
def test_alert_test_fails_closed_without_endpoint(monkeypatch, capsys):
    monkeypatch.delenv("TRADINGAGENTS_ALERT_WEBHOOK_URL", raising=False)
    called = []
    monkeypatch.setattr(ops_cli, "emit_alert", lambda *_args, **_kwargs: called.append(True))

    assert ops_cli._alert_test("collector", timeout=2.0, json_output=False) == 1
    assert not called
    assert "not configured" in capsys.readouterr().out


@pytest.mark.unit
def test_restore_rehearsal_builder_requires_env_only_database_and_redacts(capsys):
    secret_path = Path("/tmp/super-secret-collector-proof.json")
    args = SimpleNamespace(
        collector_rehearsal=secret_path,
        paper_decision_material=Path("/tmp/super-secret-decision-proof.json"),
        source_cluster_fingerprint="sha256:" + "a" * 64,
        restored_cluster_fingerprint="sha256:" + "b" * 64,
        backup_fingerprint="sha256:" + "c" * 64,
        backup_completed_utc=1_000.0,
    )

    assert ops_cli._build_restore_rehearsal_command(args, env={}) == 1
    output = capsys.readouterr().out

    assert "super-secret" not in output
    assert json.loads(output) == {
        "status": "failed",
        "error_code": "restore_rehearsal_invalid",
    }
