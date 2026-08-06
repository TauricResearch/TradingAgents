"""Production preflight, alert delivery, and guarded administrator release.

This command deliberately accepts no database URL or webhook URL arguments.
Credentials must arrive through the environment and are never rendered. Formal
release consumes only offline JSON evidence paths, plans by default, and writes
only after an explicit ``--execute``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.operations import emit_alert
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
)

_DISABLED = {"0", "false", "no", "off"}
_ENABLED = {"1", "true", "yes", "on"}
_MAX_COVERAGE_AGE_SECONDS = 108_000.0
_FETCH_AUDIT_LIMIT = 1_000
_FORMAL_EVIDENCE_ID = re.compile(r"evidence_[0-9a-f]{24}")
_FORMAL_RAW_CONTENT_ID = re.compile(r"raw_[0-9a-f]{24}")
_RUNTIME_COMPONENTS = ("collector", "paper-decision", "paper-marker")
_PAPER_RUNTIME_COMPONENTS = frozenset({"paper-decision", "paper-marker"})
_INTERNAL_COMPONENT_ROLES = {
    "collector": "collector",
    "paper-decision": "paper_decision",
    "paper-marker": "paper_marker",
}
_COLLECTOR_DATABASE_ROLE = "tradingagents-ingest-v2"
_FETCH_RECEIPT_LIFECYCLE_PROSRC_SHA256 = (
    "2cc223eeb01e1d364a19288558d94bdf5e95f43ab95c00cb441087bbec8e30d4"
)
_FETCH_RECEIPT_LIFECYCLE_CONTRACT = (
    "tradingagents.fetch-run-lifecycle.v2;normalized-prosrc-sha256="
    f"{_FETCH_RECEIPT_LIFECYCLE_PROSRC_SHA256}"
)
_FETCH_ITEM_LIFECYCLE_PROSRC_SHA256 = (
    "3b09b817e4945f2fe39b831a7695ad2c8ee0acd7e19084ed1ff31ee7b2d989fa"
)
_FETCH_ITEM_LIFECYCLE_CONTRACT = (
    "tradingagents.fetch-run-item-lifecycle.v1;normalized-prosrc-sha256="
    f"{_FETCH_ITEM_LIFECYCLE_PROSRC_SHA256}"
)
_FETCH_CONTENT_COMPLETION_PROSRC_SHA256 = (
    "26e4ec999f2e0a92b95e2d5c0dfa93373a40ebf2c0301a309afa6fa32f616514"
)
_FETCH_CONTENT_COMPLETION_CONTRACT = (
    "tradingagents.fetch-run-content-completion.v1;normalized-prosrc-sha256="
    f"{_FETCH_CONTENT_COMPLETION_PROSRC_SHA256}"
)
_FORMAL_LINEAGE_VALIDATOR_PROSRC_SHA256 = (
    "d98785b2b63fb1f34786e706acae1c5898c26ac69a9c6598ad06dfb7128a62fe"
)
_FORMAL_LINEAGE_VALIDATOR_CONTRACT = (
    "tradingagents.formal-evidence-lineage.v1;normalized-prosrc-sha256="
    f"{_FORMAL_LINEAGE_VALIDATOR_PROSRC_SHA256}"
)
_FORMAL_REGISTRY_INSERT_PROSRC_SHA256 = (
    "0328846a8f4ec182bf55ce0850a6c0b80c80ea9bd7afe0550e4b1b7d99494009"
)
_FORMAL_REGISTRY_INSERT_CONTRACT = (
    "tradingagents.formal-primary-registry-insert.v1;normalized-prosrc-sha256="
    f"{_FORMAL_REGISTRY_INSERT_PROSRC_SHA256}"
)
_FORMAL_PRIMARY_ACTIVITY_PROSRC_SHA256 = (
    "6e334ab1ee2217b262744505279a8b0da361128eed4e327c7605a70de547bf2e"
)
_FORMAL_PRIMARY_ACTIVITY_CONTRACT = (
    "tradingagents.formal-primary-run-activity.v1;normalized-prosrc-sha256="
    f"{_FORMAL_PRIMARY_ACTIVITY_PROSRC_SHA256}"
)
_FORMAL_PRIMARY_ARTIFACT_PROSRC_SHA256 = (
    "cfa9ec896396a6bd8d049471594500cb886e696d8628db36f98ac3b93ea59255"
)
_FORMAL_PRIMARY_ARTIFACT_CONTRACT = (
    "tradingagents.formal-primary-artifact.v1;normalized-prosrc-sha256="
    f"{_FORMAL_PRIMARY_ARTIFACT_PROSRC_SHA256}"
)
_FORMAL_PRIMARY_LABEL_PROSRC_SHA256 = (
    "05dbd7df121d2a2a565329653acfd0f7bd6e6cd9108ff83006af0e95ebfa384c"
)
_FORMAL_PRIMARY_LABEL_CONTRACT = (
    "tradingagents.formal-primary-run-label.v1;normalized-prosrc-sha256="
    f"{_FORMAL_PRIMARY_LABEL_PROSRC_SHA256}"
)
_APPEND_ONLY_PROSRC_SHA256 = "cbac8c2f827d925e5c161ad98ef5512d55a556b7097e1c38435a401a7dd5d214"
_APPEND_ONLY_CONTRACT = "tradingagents.append-only.v1"
_MAX_RELEASE_EVIDENCE_BYTES = 2_000_000

_FORMAL_PRICE_ATTEMPT_PROSRC_SHA256 = (
    "f8c4a473648ba138a244047baf63bd044f58874fef1eaa421192f1bc74720588"
)
_FORMAL_PRICE_BATCH_PROSRC_SHA256 = (
    "5afaea253e470dfbbc7856ec870da1a23f3bdae20c6bf9c1a02abb314a5d94ae"
)
_FORMAL_PRICE_RECEIPT_PROSRC_SHA256 = (
    "1e0374f548678bf1a580be10032b70a80284be78f69b74e3e104f2ec82e6868a"
)
_FORMAL_PRICE_COMPLETION_PROSRC_SHA256 = (
    "248b68941c1d9c098a5901dbe708d3acb23b29c30c81561e8e82d9e7bc61c6be"
)
_FORMAL_PRICE_MARK_PROSRC_SHA256 = (
    "86624999729c1909298c8d2b4a3c8d7317b14ba1f5e0a1eab1115823d9194065"
)
_FORMAL_PRICE_TERMINAL_PROSRC_SHA256 = (
    "d40d48d749d72c3c45ee5b7e847f47b9267b2e38b6074aa62424164e97add431"
)
_FORMAL_PRICE_ACTIVITY_PROSRC_SHA256 = (
    "65efefa5d115fcf339662ab1d8913ab0273a17b6f2a688d72c1469d257427d0f"
)
_FORMAL_PRICE_CONTRACTS = {
    "enforce_formal_price_attempt_event": (
        _FORMAL_PRICE_ATTEMPT_PROSRC_SHA256,
        "tradingagents.formal-price-attempt.v1;normalized-prosrc-sha256="
        f"{_FORMAL_PRICE_ATTEMPT_PROSRC_SHA256}",
    ),
    "enforce_formal_price_capture_batch": (
        _FORMAL_PRICE_BATCH_PROSRC_SHA256,
        "tradingagents.formal-price-batch.v1;normalized-prosrc-sha256="
        f"{_FORMAL_PRICE_BATCH_PROSRC_SHA256}",
    ),
    "enforce_formal_price_receipt": (
        _FORMAL_PRICE_RECEIPT_PROSRC_SHA256,
        "tradingagents.formal-price-receipt.v1;normalized-prosrc-sha256="
        f"{_FORMAL_PRICE_RECEIPT_PROSRC_SHA256}",
    ),
    "enforce_formal_price_batch_completion": (
        _FORMAL_PRICE_COMPLETION_PROSRC_SHA256,
        "tradingagents.formal-price-completion.v1;normalized-prosrc-sha256="
        f"{_FORMAL_PRICE_COMPLETION_PROSRC_SHA256}",
    ),
    "enforce_formal_mark_price_batch": (
        _FORMAL_PRICE_MARK_PROSRC_SHA256,
        "tradingagents.formal-price-mark.v1;normalized-prosrc-sha256="
        f"{_FORMAL_PRICE_MARK_PROSRC_SHA256}",
    ),
    "enforce_formal_price_terminal_failure": (
        _FORMAL_PRICE_TERMINAL_PROSRC_SHA256,
        "tradingagents.formal-price-terminal.v1;normalized-prosrc-sha256="
        f"{_FORMAL_PRICE_TERMINAL_PROSRC_SHA256}",
    ),
    "enforce_no_terminal_formal_price_failure": (
        _FORMAL_PRICE_ACTIVITY_PROSRC_SHA256,
        "tradingagents.formal-price-terminal-activity.v1;normalized-prosrc-sha256="
        f"{_FORMAL_PRICE_ACTIVITY_PROSRC_SHA256}",
    ),
}

_FORMAL_GOVERNANCE_ARTIFACT_PROSRC_SHA256 = (
    "09a18750fe2a369ab2ca060d6603c0dd0a0b953bbffb2fca87d167cbab7e4b8d"
)
_FORMAL_GOVERNANCE_LABEL_PROSRC_SHA256 = (
    "d931191828411953462cba13bae58f78897eedaec68094fd87143876404235ca"
)
_FORMAL_GOVERNANCE_TRIGGER_CONTRACTS = {
    "enforce_formal_artifact_governance": (
        _FORMAL_GOVERNANCE_ARTIFACT_PROSRC_SHA256,
        "tradingagents.formal-artifact-governance.v1;normalized-prosrc-sha256="
        f"{_FORMAL_GOVERNANCE_ARTIFACT_PROSRC_SHA256}",
    ),
    "enforce_formal_label_governance": (
        _FORMAL_GOVERNANCE_LABEL_PROSRC_SHA256,
        "tradingagents.formal-label-governance.v1;normalized-prosrc-sha256="
        f"{_FORMAL_GOVERNANCE_LABEL_PROSRC_SHA256}",
    ),
}
_FORMAL_GOVERNANCE_HELPER_CONTRACTS = {
    "formal_jsonb_exact_keys": (
        "44a0350f8be93d2ad11c5a3bae3a2cfa1b42fb227bcd4d1529dba4f931675453",
        "tradingagents.formal-jsonb-exact-keys.v1;normalized-prosrc-sha256="
        "44a0350f8be93d2ad11c5a3bae3a2cfa1b42fb227bcd4d1529dba4f931675453",
        "document jsonb, expected_keys text[]",
        "boolean",
        False,
    ),
    "formal_jsonb_has_forbidden_outcome_key": (
        "78220265c7fbb70712504ba9332277e86ed4f8bd5d5f4230e8eb56ae045c4cc6",
        "tradingagents.formal-jsonb-forbidden-outcome-key.v1;"
        "normalized-prosrc-sha256="
        "78220265c7fbb70712504ba9332277e86ed4f8bd5d5f4230e8eb56ae045c4cc6",
        "document jsonb",
        "boolean",
        False,
    ),
    "formal_jsonb_contains_key_value": (
        "ffc301b34ddbd5bcc6d304b6b0f2a10ed3be7b186356b56d7f90ca28a7177f07",
        "tradingagents.formal-jsonb-contains-key-value.v1;"
        "normalized-prosrc-sha256="
        "ffc301b34ddbd5bcc6d304b6b0f2a10ed3be7b186356b56d7f90ca28a7177f07",
        "document jsonb, target_key text, target_value text",
        "boolean",
        True,
    ),
    "formal_jsonb_content_id": (
        "fb1b0abd5f2a96d219a3cf691541675ac059e08e12e348fb7fb185c4100e3223",
        "tradingagents.formal-jsonb-content-id.v1;normalized-prosrc-sha256="
        "fb1b0abd5f2a96d219a3cf691541675ac059e08e12e348fb7fb185c4100e3223",
        "document jsonb, id_prefix text",
        "text",
        True,
    ),
}

_FORMAL_LLM_ATTEMPT_BINDING_PROSRC_SHA256 = (
    "1e9613a9150c51e41ffe72fd120b2c3bb1213a3d4d4b786e052bb0ee8859a58e"
)
_FORMAL_LLM_ATTEMPT_BINDING_CONTRACT = (
    "tradingagents.formal-decision-attempt-binding.v1;normalized-prosrc-sha256="
    f"{_FORMAL_LLM_ATTEMPT_BINDING_PROSRC_SHA256}"
)
_FORMAL_LLM_NO_RETRY_PROSRC_SHA256 = (
    "32247a653505236e9605b2b08bdc6859ec41ad1809099664d34052af43a40114"
)
_FORMAL_LLM_NO_RETRY_CONTRACT = (
    "tradingagents.formal-attempt-no-retry-after-reservation.v1;"
    "normalized-prosrc-sha256="
    f"{_FORMAL_LLM_NO_RETRY_PROSRC_SHA256}"
)
_FORMAL_LLM_RESERVATION_PROSRC_SHA256 = (
    "083360a3e261ff35bdbff9a366a24d4039660f9fcb4b6e4f1e49d6d655c2958e"
)
_FORMAL_LLM_RESERVATION_CONTRACT = (
    "tradingagents.formal-llm-atomic-reservation.v1;normalized-prosrc-sha256="
    f"{_FORMAL_LLM_RESERVATION_PROSRC_SHA256}"
)

_POSTGRES_DOUBLE_PRECISION_COLUMNS = frozenset(
    {
        ("schema_migrations", "applied_utc"),
        ("paper_runs", "created_utc"),
        ("paper_decisions", "created_utc"),
        ("paper_decisions", "score"),
        ("paper_targets", "created_utc"),
        ("paper_marks", "captured_utc"),
        ("paper_marks", "nav"),
        ("paper_marks", "benchmark_nav"),
        ("paper_marks", "period_return"),
        ("paper_marks", "benchmark_period_return"),
        ("paper_marks", "turnover"),
        ("paper_marks", "trading_cost"),
        ("paper_marks", "borrow_cost"),
        ("paper_marks", "benchmark_open"),
        ("experiment_registry", "created_utc"),
        ("formal_trial_registry", "created_utc"),
        ("paper_run_labels", "created_utc"),
        ("paper_artifacts", "created_utc"),
        ("paper_decision_bundles", "created_utc"),
        ("paper_strategy_targets", "created_utc"),
        ("paper_strategy_marks", "captured_utc"),
        ("paper_strategy_marks", "nav"),
        ("paper_strategy_marks", "benchmark_nav"),
        ("paper_strategy_marks", "period_return"),
        ("paper_strategy_marks", "benchmark_period_return"),
        ("paper_strategy_marks", "turnover"),
        ("paper_strategy_marks", "trading_cost"),
        ("paper_strategy_marks", "borrow_cost"),
        ("paper_strategy_marks", "benchmark_open"),
        ("paper_price_receipts", "captured_utc"),
        ("paper_price_receipts", "raw_open"),
        ("paper_price_receipts", "adjusted_open"),
        ("paper_price_receipts", "dividend"),
        ("paper_price_receipts", "split_ratio"),
        ("paper_price_capture_attempt_events", "created_utc"),
        ("paper_price_capture_attempt_events", "observed_utc"),
        ("paper_price_capture_batches", "scheduled_utc"),
        ("paper_price_capture_batches", "started_utc"),
        ("paper_price_capture_batches", "completed_utc"),
        ("paper_price_capture_batches", "persisted_utc"),
        ("paper_price_capture_batches", "deadline_utc"),
        ("paper_price_integrity_failures", "detected_utc"),
        ("paper_price_integrity_failures", "scheduled_utc"),
        ("paper_price_integrity_failures", "deadline_utc"),
        ("paper_decision_attempt_events", "created_utc"),
        ("paper_interval_assignments", "created_utc"),
        ("media_posts", "created_utc"),
        ("media_posts", "fetched_utc"),
        ("media_labels", "linked_utc"),
        ("media_observations", "observed_utc"),
        ("macro_odds", "captured_utc"),
        ("macro_odds", "probability"),
        ("macro_odds", "volume"),
        ("macro_odds", "resolution_utc"),
        ("poll_state", "value"),
        ("fetch_runs", "started_utc"),
        ("fetch_runs", "received_utc"),
        ("fetch_runs", "completed_utc"),
        ("fetch_runs", "cost_units"),
        ("fetch_runs", "cursor_before"),
        ("fetch_runs", "cursor_after"),
        ("fetch_run_items", "observed_utc"),
    }
)


@dataclass(frozen=True)
class CheckResult:
    """One non-secret operational assertion."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class PreflightReport:
    """Aggregated result suitable for humans or deployment automation."""

    component: str
    checks: tuple[CheckResult, ...]

    @property
    def ready(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)

    def as_dict(self) -> dict:
        return {
            "component": self.component,
            "runtime_ready": self.ready,
            "checks": [asdict(check) for check in self.checks],
            "scope": (
                "read-only runtime checks; database restore and offline staging replay "
                "remain separate runbook gates"
            ),
        }


def _check(name: str, passed: bool, success: str, failure: str) -> CheckResult:
    return CheckResult(name=name, passed=bool(passed), detail=success if passed else failure)


def _normalized(value: str | None) -> str:
    return (value or "").strip().lower()


def _configured(env: Mapping[str, str], key: str) -> bool:
    return bool((env.get(key) or "").strip())


def _explicitly_disabled(env: Mapping[str, str], key: str) -> bool:
    return _normalized(env.get(key)) in _DISABLED


def _explicitly_enabled(env: Mapping[str, str], key: str) -> bool:
    return _normalized(env.get(key)) in _ENABLED


def _paper_runtime_arguments(component: str, env: Mapping[str, str]) -> SimpleNamespace:
    """Reconstruct the same non-secret values consumed by the split worker.

    The canonical component builder below remains the schema and policy
    authority.  This adapter only gives it the values that the paper CLI reads
    from the environment; credentials stay in ``env`` and are never copied into
    the returned component document.
    """

    common = {
        "run_id": env.get("PAPER_RUN_ID"),
        "engine": env.get("PAPER_ENGINE", "legacy-ratings"),
        "tickers": env.get("PAPER_TICKERS"),
        "benchmark": env.get("PAPER_BENCHMARK", "SPY"),
        "portfolio_mode": env.get("PAPER_PORTFOLIO_MODE", "long-only"),
        "cost_bps": float(env.get("PAPER_TRADING_COST_BPS", "5")),
        "slippage_bps": float(env.get("PAPER_SLIPPAGE_BPS", "5")),
        "annual_borrow_bps": float(env.get("PAPER_ANNUAL_BORROW_BPS", "300")),
    }
    if component == "paper-marker":
        return SimpleNamespace(**common)
    if component != "paper-decision":
        raise ValueError("paper runtime component is not allowlisted")
    return SimpleNamespace(
        **common,
        analysts=env.get("PAPER_ANALYSTS", "market,social,news"),
        global_topics_only=_explicitly_enabled(env, "PAPER_GLOBAL_TOPICS_ONLY"),
        llm_model_allowlist=env.get("PAPER_LLM_MODEL_ALLOWLIST"),
        llm_max_calls_per_decision=int(
            env.get("PAPER_LLM_MAX_CALLS_PER_DECISION", "3")
        ),
        llm_max_calls_per_utc_day=int(
            env.get("PAPER_LLM_MAX_CALLS_PER_UTC_DAY", "3")
        ),
        llm_max_prompt_bytes=int(env.get("PAPER_LLM_MAX_PROMPT_BYTES", "160000")),
        llm_max_completion_tokens=int(
            env.get("PAPER_LLM_MAX_COMPLETION_TOKENS", "8000")
        ),
        llm_timeout_seconds=int(env.get("PAPER_LLM_TIMEOUT_SECONDS", "180")),
        replicates=int(env.get("PAPER_REPLICATES", "1")),
    )


def _runtime_material(component: str, env: Mapping[str, str]) -> dict:
    """Build exact, non-secret in-image material without opening a DB/provider."""

    from tradingagents.formal_runtime import (
        in_image_preflight_identity,
        paper_component_configuration,
    )
    from tradingagents.outcome_semantics import outcome_semantics_id

    if component == "collector":
        from tradingagents import poller

        args = poller._build_parser(env).parse_args(  # noqa: SLF001 - same runtime parser
            ["--formal-collector", "--release-material"]
        )
        explicit = poller._comma_separated(  # noqa: SLF001 - same runtime normalization
            args.sources, lowercase=True
        ) or None
        sources = poller.resolve_sources(explicit, env=env)
        macro_themes = poller.DEFAULT_CONFIG.get("macro_themes", {}) if args.macro else {}
        configuration = poller._formal_collector_runtime_material(  # noqa: SLF001
            args,
            sources=sources,
            macro_themes=macro_themes,
            env=env,
            require_release_environment=True,
        )
        return in_image_preflight_identity(configuration, env=env)

    role = _INTERNAL_COMPONENT_ROLES.get(component)
    if role not in {"paper_decision", "paper_marker"}:
        raise ValueError("runtime component is not allowlisted")
    model_config = dict(DEFAULT_CONFIG)
    model_config.update(
        {
            "llm_provider": env.get(
                "TRADINGAGENTS_LLM_PROVIDER", model_config["llm_provider"]
            ),
            "quick_think_llm": env.get(
                "TRADINGAGENTS_QUICK_THINK_LLM", model_config["quick_think_llm"]
            ),
            "backend_url": env.get("TRADINGAGENTS_LLM_BACKEND_URL") or None,
            "openai_reasoning_effort": (
                env.get("TRADINGAGENTS_OPENAI_REASONING_EFFORT") or None
            ),
            "google_thinking_level": (
                env.get("TRADINGAGENTS_GOOGLE_THINKING_LEVEL") or None
            ),
            "anthropic_effort": env.get("TRADINGAGENTS_ANTHROPIC_EFFORT") or None,
            "temperature": (
                float(env["TRADINGAGENTS_TEMPERATURE"])
                if _configured(env, "TRADINGAGENTS_TEMPERATURE")
                else None
            ),
        }
    )
    configuration = paper_component_configuration(
        _paper_runtime_arguments(component, env),
        role=role,
        decision_semantics_id=GLOBAL_EVENT_V2_PROTOCOL["forecast"][
            "expected_decision_semantics_id"
        ],
        env=env,
        model_config=model_config,
    )
    return in_image_preflight_identity(
        configuration,
        env=env,
        resolved_outcome_semantics_id=outcome_semantics_id(),
    )


def _configuration_checks(component: str, env: Mapping[str, str]) -> list[CheckResult]:
    db_url = (env.get("MEDIA_DB_URL") or "").strip()
    checks = [
        _check(
            "config.media_db_url",
            bool(db_url),
            "configured (value redacted)",
            "MEDIA_DB_URL is required",
        ),
        _check(
            "config.postgres_url",
            db_url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")),
            "configured for PostgreSQL (value redacted)",
            "production preflight requires a PostgreSQL MEDIA_DB_URL",
        ),
        _check(
            "config.legacy_database_url_absent",
            not _configured(env, "DATABASE_URL"),
            "DATABASE_URL is absent",
            "remove legacy DATABASE_URL before production use",
        ),
        _check(
            "config.media_auto_migrate_disabled",
            _explicitly_disabled(env, "MEDIA_AUTO_MIGRATE"),
            "media runtime migrations are disabled",
            "MEDIA_AUTO_MIGRATE must be explicitly false",
        ),
        _check(
            "config.alert_webhook",
            _configured(env, "TRADINGAGENTS_ALERT_WEBHOOK_URL"),
            "alert route is configured (value redacted)",
            "TRADINGAGENTS_ALERT_WEBHOOK_URL is not configured",
        ),
        _check(
            "config.immutable_build_identity",
            any(
                _configured(env, key)
                for key in ("TRADINGAGENTS_BUILD_ID", "FLY_IMAGE_REF", "GIT_REVISION")
            ),
            "immutable build identity is configured (value redacted)",
            "set TRADINGAGENTS_BUILD_ID, FLY_IMAGE_REF, or GIT_REVISION",
        ),
    ]
    if component in _PAPER_RUNTIME_COMPONENTS:
        pause_name = (
            "PAPER_DECISIONS_ENABLED"
            if component == "paper-decision"
            else "PAPER_MARKS_ENABLED"
        )
        checks.extend(
            [
                _check(
                    "config.paper_auto_migrate_disabled",
                    _explicitly_disabled(env, "PAPER_AUTO_MIGRATE"),
                    "paper runtime migrations are disabled",
                    "PAPER_AUTO_MIGRATE must be explicitly false",
                ),
                _check(
                    f"config.{component}_paused",
                    _explicitly_disabled(env, pause_name),
                    f"{component} writes are paused",
                    f"{pause_name} must be explicitly false during preflight",
                ),
            ]
        )
        try:
            retry_envelope_matches = (
                int(env.get("PAPER_RETRY_ATTEMPTS", "")) == 3
                and float(env.get("PAPER_RETRY_SECONDS", "")) == 300.0
            )
        except (TypeError, ValueError):
            retry_envelope_matches = False
        checks.append(
            _check(
                "config.worker_retry_envelope",
                retry_envelope_matches,
                "worker retry envelope exactly matches the released configuration",
                "PAPER_RETRY_ATTEMPTS or PAPER_RETRY_SECONDS differs from release",
            )
        )
        if component == "paper-decision":
            checks.append(
                _check(
                    "config.llm_sdk_retries_disabled",
                    (env.get("TRADINGAGENTS_LLM_MAX_RETRIES") or "").strip() == "0",
                    "model SDK retries are disabled",
                    "TRADINGAGENTS_LLM_MAX_RETRIES must be exactly 0",
                )
            )
    else:
        checks.extend(
            [
                _check(
                    "config.collector_paused",
                    _explicitly_disabled(env, "MEDIA_COLLECTION_ENABLED"),
                    "formal evidence collection is paused",
                    "MEDIA_COLLECTION_ENABLED must be explicitly false during preflight",
                ),
                _check(
                    "config.x_credential",
                    _configured(env, "X_BEARER_TOKEN"),
                    "X credential is configured (value redacted)",
                    "X_BEARER_TOKEN is required for public-reaction collection",
                ),
            ]
        )

    try:
        material = _runtime_material(component, env)
        exact_component = (
            material["component_configuration"]["role"]
            == _INTERNAL_COMPONENT_ROLES[component]
        )
    except Exception:  # noqa: BLE001 - configuration errors may name secret variables
        exact_component = False
    checks.append(
        _check(
            "config.formal_component",
            exact_component,
            "exact content-addressed runtime configuration and credential scope match",
            "runtime configuration, build identity, or credential scope differs from protocol",
        )
    )
    return checks


def _expected_global_news_keys() -> set[str]:
    return {
        f"{theme}:{query}"
        for theme, queries in GLOBAL_EVENT_V2_PROTOCOL["evidence"]["broad_news_queries"].items()
        for query in queries
    }


def _decision_checks(now: datetime) -> tuple[list[CheckResult], str | None, float | None]:
    from tradingagents.paper_trading import (
        DecisionWindowClosedError,
        current_decision_date,
        decision_window,
    )

    try:
        decision_date = current_decision_date(now)
        cutoff, next_open, _ = decision_window(decision_date)
    except (DecisionWindowClosedError, ValueError):
        return (
            [
                CheckResult(
                    "time.decision_window",
                    False,
                    "not inside the after-cutoff, before-open decision window",
                )
            ],
            None,
            None,
        )
    return (
        [
            _check(
                "time.decision_window",
                cutoff <= now < next_open,
                f"decision date {decision_date} is inside its safe window",
                "current time is outside the safe decision window",
            )
        ],
        decision_date,
        cutoff.timestamp(),
    )


def _receipt_checks(
    store, cutoff_utc: float, now_utc: float, env: Mapping[str, str]
) -> list[CheckResult]:
    from tradingagents.formal_experiment import _formal_collector_cycle_window

    required_groups = GLOBAL_EVENT_V2_PROTOCOL["evidence"]["required_source_groups"]
    coverage = store.coverage_report(
        cutoff_utc,
        required_groups,
        max_age_seconds=_MAX_COVERAGE_AGE_SECONDS,
    )
    checks = [
        _check(
            "data.required_source_coverage",
            bool(coverage.get("complete")),
            "required source-group coverage is complete at cutoff",
            "required source-group coverage is missing or stale at cutoff",
        )
    ]

    try:
        interval = int(env.get("MEDIA_POLLER_INTERVAL", "3600"))
        _, cycle_lower_bound = _formal_collector_cycle_window(
            datetime.fromtimestamp(cutoff_utc, timezone.utc), interval
        )
        cycle_lower_utc = cycle_lower_bound.timestamp()
        cycle_max_age = cutoff_utc - cycle_lower_utc
    except (TypeError, ValueError):
        cycle_lower_utc = cutoff_utc
        cycle_max_age = 0.0
    expected = _expected_global_news_keys()
    latest: dict[str, tuple[tuple[float, str], dict]] = {}
    for row in store.fetch_runs(provider="globalnews", limit=_FETCH_AUDIT_LIMIT):
        key = row.get("query_key")
        started = row.get("started_utc")
        if isinstance(started, bool) or not isinstance(started, (int, float)):
            continue
        started_utc = float(started)
        if key not in expected or not cycle_lower_utc <= started_utc <= cutoff_utc:
            continue
        rank = (started_utc, str(row.get("fetch_run_id") or ""))
        if key not in latest or rank > latest[key][0]:
            latest[key] = (rank, row)
    healthy = set()
    strict_core_evidence_ids: set[str] = set()
    for key, (_rank, row) in latest.items():
        eligible_count = row.get("formal_eligible_item_count")
        eligible_ids = row.get("formal_eligible_evidence_ids")
        eligible_lineage = row.get("formal_eligible_lineage")
        completed = row.get("completed_utc")
        try:
            raw_metadata = row.get("metadata_json") or "{}"
            metadata = json.loads(raw_metadata) if isinstance(raw_metadata, str) else raw_metadata
        except (TypeError, json.JSONDecodeError):
            metadata = None
        exact_collector_identity = (
            isinstance(metadata, dict)
            and metadata.get("protocol_id") == GLOBAL_EVENT_V2_PROTOCOL_ID
            and metadata.get("collector_semantics_id")
            == GLOBAL_EVENT_V2_PROTOCOL["evidence"]["expected_collector_semantics_id"]
        )
        exact_lineage = (
            isinstance(eligible_count, int)
            and not isinstance(eligible_count, bool)
            and eligible_count >= 0
            and isinstance(eligible_ids, list)
            and eligible_ids == sorted(set(eligible_ids))
            and len(eligible_ids) == eligible_count
            and all(
                isinstance(value, str) and _FORMAL_EVIDENCE_ID.fullmatch(value) is not None
                for value in eligible_ids
            )
            and isinstance(eligible_lineage, list)
            and eligible_lineage
            == sorted(
                eligible_lineage,
                key=lambda item: (
                    str(item.get("evidence_id") or "") if isinstance(item, dict) else "",
                    str(item.get("raw_content_id") or "") if isinstance(item, dict) else "",
                ),
            )
            and len(eligible_lineage) == eligible_count
            and [item.get("evidence_id") for item in eligible_lineage] == eligible_ids
            and all(
                isinstance(item, dict)
                and set(item) == {"evidence_id", "raw_content_id"}
                and _FORMAL_EVIDENCE_ID.fullmatch(str(item.get("evidence_id") or "")) is not None
                and _FORMAL_RAW_CONTENT_ID.fullmatch(str(item.get("raw_content_id") or ""))
                is not None
                for item in eligible_lineage
            )
        )
        if (
            row.get("status") in {"success", "empty"}
            and exact_lineage
            and exact_collector_identity
            and not isinstance(completed, bool)
            and isinstance(completed, (int, float))
            and float(completed) <= cutoff_utc
            and cutoff_utc - float(completed) <= cycle_max_age
        ):
            healthy.add(key)
            strict_core_evidence_ids.update(eligible_ids)
    checks.append(
        _check(
            "data.expected_global_news_slots",
            healthy == expected and bool(expected),
            f"all {len(expected)} broad-news slots succeeded in the cutoff cycle",
            f"only {len(healthy)}/{len(expected)} broad-news slots are healthy in the cutoff cycle",
        )
    )
    minimum_news = int(GLOBAL_EVENT_V2_PROTOCOL["evidence"]["minimum_selected_globalnews_total"])
    checks.append(
        _check(
            "data.strict_core_news_available",
            len(strict_core_evidence_ids) >= minimum_news,
            "fresh receipts contain strict-core global-news evidence",
            "fresh receipts do not contain the minimum strict-core global-news evidence",
        )
    )

    day = datetime.fromtimestamp(now_utc, timezone.utc).strftime("%Y-%m-%d")
    day_start = (
        datetime.fromtimestamp(now_utc, timezone.utc)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .timestamp()
    )
    x_limits = {
        "trend": int(GLOBAL_EVENT_V2_PROTOCOL["evidence"]["max_x_trend_requests_per_utc_day"]),
        "search": int(GLOBAL_EVENT_V2_PROTOCOL["evidence"]["max_x_search_requests_per_utc_day"]),
    }
    x_rows = [
        row
        for row in store.fetch_runs(limit=_FETCH_AUDIT_LIMIT)
        if row.get("provider") in {"xtrend", "x"}
        and float(row.get("started_utc") or 0.0) >= day_start
    ]
    x_counts = {"trend": 0, "search": 0}
    malformed_x_receipts = 0
    allowed_statuses = {"running", "success", "empty", "failed"}
    for row in x_rows:
        category = "trend" if row.get("provider") == "xtrend" else "search"
        x_counts[category] += 1
        try:
            raw_metadata = row.get("metadata_json") or "{}"
            metadata = json.loads(raw_metadata) if isinstance(raw_metadata, str) else raw_metadata
            reservation = metadata["budget_reservation"]
            limits = reservation["limits"]
            reserved = reservation["reserved"]
            total_key = f"x-budget:{category}:{day}:total"
            request_keys = [
                key for key in limits if key.startswith(f"x-budget:{category}:{day}:request:")
            ]
            terminal = row.get("status") in {"success", "empty", "failed"}
            valid = (
                metadata.get("budget_category") == category
                and reservation.get("amount") == 1.0
                and set(limits) == set(reserved)
                and limits.get(total_key) == float(x_limits[category])
                and len(request_keys) == 1
                and limits.get(request_keys[0]) == 1.0
                and all(0.0 < float(reserved[key]) <= float(limits[key]) for key in limits)
                and row.get("status") in allowed_statuses
                and (not terminal or float(row.get("cost_units") or 0.0) == 1.0)
            )
            if category == "trend":
                expected_keys = {
                    f"woeid:{int(woeid)}"
                    for woeid in GLOBAL_EVENT_V2_PROTOCOL["evidence"]["x_trend_woeids"]
                }
                valid = valid and row.get("query_key") in expected_keys
            if not valid:
                malformed_x_receipts += 1
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            malformed_x_receipts += 1
    checks.append(
        _check(
            "data.x_request_accounting",
            not malformed_x_receipts
            and all(x_counts[category] <= limit for category, limit in x_limits.items()),
            "all paid X trend/search receipts have atomic frozen-budget reservations",
            "paid X request receipts are malformed, unreserved, or over budget",
        )
    )

    recent = store.fetch_runs(limit=_FETCH_AUDIT_LIMIT)
    cursor_offenders = [
        row
        for row in recent
        if row.get("status") in {"empty", "failed"} and row.get("cursor_after") is not None
    ]
    stale_running = [
        row
        for row in recent
        if row.get("status") == "running"
        and now_utc - float(row.get("started_utc") or now_utc) > 7_200
    ]
    checks.extend(
        [
            _check(
                "data.non_success_watermarks",
                not cursor_offenders,
                "failed and empty receipts did not advance cursors",
                f"{len(cursor_offenders)} failed/empty receipts advanced a cursor",
            ),
            _check(
                "data.stale_fetch_runs",
                not stale_running,
                "no fetch receipt has remained running for more than two hours",
                f"{len(stale_running)} fetch receipts are stale in running state",
            ),
        ]
    )
    return checks


def _collector_heartbeat_checks(
    store, env: Mapping[str, str], now_utc: float
) -> list[CheckResult]:
    """Check only the collector's legacy operational heartbeat.

    Formal paper liveness is stored in migration 013's append-only heartbeat
    ledger and is evaluated separately through its outcome-free projection.
    """

    try:
        collector_interval = max(1.0, float(env.get("MEDIA_POLLER_INTERVAL", "3600")))
    except ValueError:
        collector_interval = 0.0
    collector_success = store.get_meta("poller:last_cycle_utc")
    collector_failure = store.get_meta("poller:last_failure_utc")
    collector_healthy = bool(
        collector_interval
        and collector_success
        and now_utc - collector_success >= 0
        and now_utc - collector_success <= max(7_200.0, collector_interval * 2.5)
        and (not collector_failure or collector_success >= collector_failure)
    )
    return [
        _check(
            "health.collector_heartbeat",
            collector_healthy,
            "collector success heartbeat is fresh and newer than failures",
            "collector heartbeat is absent, stale, or older than a failure",
        ),
    ]


def _formal_runtime_health_checks(
    store, env: Mapping[str, str], now_utc: float
) -> list[CheckResult]:
    """Authenticate distinct paused decision/marker health without outcomes."""

    try:
        max_age = float(env.get("PAPER_HEARTBEAT_MAX_AGE", ""))
    except (TypeError, ValueError):
        max_age = 0.0
    try:
        from tradingagents.poller import (
            _formal_runtime_health_projection,
            _validated_formal_runtime_health_projection,
        )

        material = _runtime_material("collector", env)
        configuration = material["component_configuration"]
        preflight = material["preflight_payload"]
        release, rows = _formal_runtime_health_projection(
            store,
            protocol_id=GLOBAL_EVENT_V2_PROTOCOL_ID,
            collector_build_id=preflight["build_id"],
        )
        release, rows = _validated_formal_runtime_health_projection(release, rows)
        authorized = (
            release["authorized"] is True
            and release["collector_configuration_id"]
            == configuration["configuration_id"]
        )
    except Exception:  # noqa: BLE001 - database/build failures remain redacted
        authorized = False
        rows = []

    checks = [
        _check(
            "health.formal_runtime_authorized",
            authorized,
            "collector build and configuration are bound to the formal authorization",
            "formal authorization is absent, unavailable, or bound to another collector",
        )
    ]
    by_component = {
        row.get("runtime_component"): row
        for row in rows
        if isinstance(row, Mapping)
    }
    for runtime_component in ("decision", "marker"):
        row = by_component.get(runtime_component)
        observed = row.get("observed_utc") if row else None
        latest_success = row.get("latest_success_utc") if row else None
        latest_failure = row.get("latest_failure_utc") if row else None
        fresh = bool(
            max_age > 0
            and isinstance(observed, (int, float))
            and not isinstance(observed, bool)
            and 0 <= now_utc - float(observed) <= max_age
        )
        failure_resolved = bool(
            latest_failure is None
            or (
                isinstance(latest_success, (int, float))
                and not isinstance(latest_success, bool)
                and float(latest_success) > float(latest_failure)
            )
        )
        healthy_pause = bool(
            authorized
            and row is not None
            and row.get("event_type") == "paused"
            and fresh
            and failure_resolved
        )
        checks.append(
            _check(
                f"health.paper_{runtime_component}_paused",
                healthy_pause,
                f"paper-{runtime_component} has a fresh, failure-free paused heartbeat",
                f"paper-{runtime_component} heartbeat is missing, stale, active, or failed",
            )
        )
    return checks


def _table_privileges(conn, table: str) -> set[str]:
    from sqlalchemy import text

    privileges = set()
    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
        allowed = conn.execute(
            text("SELECT has_table_privilege(current_user, :table, :privilege)"),
            {"table": table, "privilege": privilege},
        ).scalar_one()
        if allowed:
            privileges.add(privilege)
    return privileges


def _installed_immutable_trigger_tables(conn) -> set[str]:
    """Return tables bound to the exact hardened append-only function body.

    PostgreSQL catalogs are intentionally used instead of the privilege-filtered
    ``information_schema.triggers`` view so a SELECT-only runtime can still
    authenticate function body, ownership, configuration, and trigger binding.
    """
    from tradingagents.paper_trading import PaperStore

    expected = set(PaperStore._IMMUTABLE_TABLES)
    rows = _fetch_trigger_contract_rows(
        conn, tuple(f"immutable_{table}" for table in sorted(expected))
    )
    return {
        str(row[1])
        for row in rows
        if str(row[1]) in expected
        and _exact_trigger_contract_row(
            row,
            table_name=str(row[1]),
            trigger_name=f"immutable_{row[1]}",
            function_name="reject_append_only_mutation",
            type_bits=27,  # ROW + BEFORE + DELETE + UPDATE.
            function_hash=_APPEND_ONLY_PROSRC_SHA256,
            function_contract=_APPEND_ONLY_CONTRACT,
        )
    }


def _normalized_pg_prosrc_sha256(source: object) -> str | None:
    """Hash stored PL/pgSQL source without version-specific DDL formatting."""
    if not isinstance(source, str):
        return None
    normalized = "\n".join(
        line.rstrip()
        for line in source.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _exact_trigger_contract_row(
    row,
    *,
    table_name: str,
    trigger_name: str,
    function_name: str,
    type_bits: int,
    function_hash: str,
    function_contract: str,
    function_default_acl: bool = True,
    security_definer: bool = False,
    constraint_trigger: bool = False,
    deferrable: bool = False,
    initially_deferred: bool = False,
) -> bool:
    """Authenticate one ordinary, owner-separated PL/pgSQL trigger binding."""
    return bool(
        str(row[0]) == "public"
        and str(row[1]) == table_name
        and str(row[2]) == "r"
        and str(row[3]) == trigger_name
        and str(row[4]) == "public"
        and str(row[5]) == function_name
        and str(row[6]) in {"O", "A"}
        and not bool(row[7])
        and int(row[8]) == type_bits
        and str(row[9]) == ""
        and bool(row[10])
        and int(row[11]) == 0
        and bool(row[12])
        and str(row[13]) == "plpgsql"
        and bool(row[14]) is security_definer
        and str(row[15]) == "f"
        and bool(row[16]) is (not constraint_trigger)
        and bool(row[17]) is (not deferrable)
        and bool(row[18]) is (not initially_deferred)
        and _normalized_pg_prosrc_sha256(row[19]) == function_hash
        and str(row[20]) == function_contract
        and tuple(row[21] or ()) == ("search_path=pg_catalog",)
        and not bool(row[22])
        and str(row[23]) == "v"
        and str(row[24]) == "u"
        and not bool(row[25])
        and not bool(row[26])
        and bool(row[27]) is function_default_acl
        and bool(row[28])
        and bool(row[29])
        and bool(row[30])
        and bool(row[31])
        and int(row[32]) == 0
        and int(row[33]) == 0
        and bool(row[34])
        and bool(row[35])
        and bool(row[36])
        and (function_default_acl or bool(row[37]))
    )


def _fetch_trigger_contract_rows(conn, trigger_names: tuple[str, ...]) -> list:
    """Read complete catalog contracts for an internal allowlist of triggers.

    Read the unfiltered PostgreSQL catalogs instead of
    ``information_schema.triggers`` because the latter hides trigger metadata
    from the paper role, which intentionally has no mutation grant on
    ``fetch_runs``.  Inspect raw attributes in Python so every part of the
    binding is independently testable and a similarly named trigger fails
    closed.
    """
    from sqlalchemy import text

    if not trigger_names or any(re.fullmatch(r"[a-z_]+", name) is None for name in trigger_names):
        raise ValueError("trigger contract names are invalid")
    encoded_names = ", ".join(f"'{name}'" for name in trigger_names)
    rows = conn.execute(
        text(
            f"""
            SELECT
                table_namespace.nspname,
                table_class.relname,
                table_class.relkind,
                trigger.tgname,
                function_namespace.nspname,
                trigger_function.proname,
                trigger.tgenabled,
                trigger.tgisinternal,
                CAST(trigger.tgtype AS integer),
                trigger.tgattr::text,
                trigger.tgqual IS NULL,
                trigger_function.pronargs,
                trigger_function.prorettype =
                    'pg_catalog.trigger'::pg_catalog.regtype,
                function_language.lanname,
                trigger_function.prosecdef,
                trigger_function.prokind,
                trigger.tgconstraint = 0,
                NOT trigger.tgdeferrable,
                NOT trigger.tginitdeferred,
                trigger_function.prosrc,
                pg_catalog.obj_description(trigger_function.oid, 'pg_proc'),
                trigger_function.proconfig,
                trigger_function.proleakproof,
                trigger_function.provolatile,
                trigger_function.proparallel,
                trigger_function.proisstrict,
                trigger_function.proretset,
                trigger_function.proacl IS NULL,
                trigger_function.probin IS NULL,
                trigger_function.proowner <>
                    (SELECT role.oid FROM pg_catalog.pg_roles AS role
                     WHERE role.rolname = current_user),
                NOT pg_catalog.pg_has_role(
                    current_user, trigger_function.proowner, 'MEMBER'
                ),
                function_language.lanpltrusted,
                trigger.tgnargs,
                pg_catalog.octet_length(trigger.tgargs),
                trigger.tgparentid = 0,
                trigger.tgoldtable IS NULL,
                trigger.tgnewtable IS NULL,
                NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.aclexplode(
                        COALESCE(
                            trigger_function.proacl,
                            pg_catalog.acldefault(
                                'f', trigger_function.proowner
                            )
                        )
                    ) AS function_acl
                    WHERE function_acl.grantee = 0
                      AND function_acl.privilege_type = 'EXECUTE'
                )
            FROM pg_catalog.pg_trigger AS trigger
            JOIN pg_catalog.pg_class AS table_class
              ON table_class.oid = trigger.tgrelid
            JOIN pg_catalog.pg_namespace AS table_namespace
              ON table_namespace.oid = table_class.relnamespace
            JOIN pg_catalog.pg_proc AS trigger_function
              ON trigger_function.oid = trigger.tgfoid
            JOIN pg_catalog.pg_namespace AS function_namespace
              ON function_namespace.oid = trigger_function.pronamespace
            JOIN pg_catalog.pg_language AS function_language
              ON function_language.oid = trigger_function.prolang
            WHERE trigger.tgname IN ({encoded_names})
            """
        )
    ).all()
    return list(rows)


def _fetch_receipt_lifecycle_trigger_is_installed(conn) -> bool:
    """Verify the exact enabled one-way receipt trigger from migration 006."""
    rows = _fetch_trigger_contract_rows(conn, ("immutable_fetch_runs",))
    for row in rows:
        if _exact_trigger_contract_row(
            row,
            table_name="fetch_runs",
            trigger_name="immutable_fetch_runs",
            function_name="enforce_fetch_run_lifecycle",
            type_bits=31,  # ROW + BEFORE + INSERT + DELETE + UPDATE.
            function_hash=_FETCH_RECEIPT_LIFECYCLE_PROSRC_SHA256,
            function_contract=_FETCH_RECEIPT_LIFECYCLE_CONTRACT,
        ):
            return True
    return False


def _fetch_content_lineage_triggers_are_installed(conn) -> bool:
    """Authenticate item immutability and terminal content projection triggers."""
    expected = {
        "immutable_fetch_run_items": {
            "table_name": "fetch_run_items",
            "trigger_name": "immutable_fetch_run_items",
            "function_name": "enforce_fetch_run_item_lifecycle",
            "type_bits": 31,
            "function_hash": _FETCH_ITEM_LIFECYCLE_PROSRC_SHA256,
            "function_contract": _FETCH_ITEM_LIFECYCLE_CONTRACT,
        },
        "validate_fetch_run_content_completion": {
            "table_name": "fetch_runs",
            "trigger_name": "validate_fetch_run_content_completion",
            "function_name": "enforce_fetch_run_content_completion",
            "type_bits": 19,  # ROW + BEFORE + UPDATE.
            "function_hash": _FETCH_CONTENT_COMPLETION_PROSRC_SHA256,
            "function_contract": _FETCH_CONTENT_COMPLETION_CONTRACT,
        },
    }
    rows = _fetch_trigger_contract_rows(conn, tuple(expected))
    installed = {
        str(row[3])
        for row in rows
        if str(row[3]) in expected and _exact_trigger_contract_row(row, **expected[str(row[3])])
    }
    return installed == set(expected)


def _formal_lineage_validator_is_installed(conn) -> bool:
    """Authenticate the exact immutable SQL function used by lineage checks."""
    from sqlalchemy import text

    rows = conn.execute(
        text(
            """
            SELECT
                function_namespace.nspname,
                function_row.proname,
                function_row.pronargs,
                function_row.prorettype = 'pg_catalog.bool'::pg_catalog.regtype,
                function_language.lanname,
                function_row.prosecdef,
                function_row.prokind,
                function_row.prosrc,
                pg_catalog.obj_description(function_row.oid, 'pg_proc'),
                function_row.proconfig,
                function_row.proleakproof,
                function_row.provolatile,
                function_row.proparallel,
                function_row.proisstrict,
                function_row.proretset,
                function_row.proacl IS NULL,
                function_row.probin IS NULL,
                function_row.proowner <>
                    (SELECT role.oid FROM pg_catalog.pg_roles AS role
                     WHERE role.rolname = current_user),
                NOT pg_catalog.pg_has_role(
                    current_user, function_row.proowner, 'MEMBER'
                ),
                function_language.lanpltrusted,
                pg_catalog.pg_get_function_identity_arguments(function_row.oid)
            FROM pg_catalog.pg_proc AS function_row
            JOIN pg_catalog.pg_namespace AS function_namespace
              ON function_namespace.oid = function_row.pronamespace
            JOIN pg_catalog.pg_language AS function_language
              ON function_language.oid = function_row.prolang
            WHERE function_namespace.nspname = 'public'
              AND function_row.proname = 'formal_evidence_lineage_is_valid'
            """
        )
    ).all()
    return len(rows) == 1 and bool(
        str(rows[0][0]) == "public"
        and str(rows[0][1]) == "formal_evidence_lineage_is_valid"
        and int(rows[0][2]) == 2
        and bool(rows[0][3])
        and str(rows[0][4]) == "sql"
        and not bool(rows[0][5])
        and str(rows[0][6]) == "f"
        and _normalized_pg_prosrc_sha256(rows[0][7]) == _FORMAL_LINEAGE_VALIDATOR_PROSRC_SHA256
        and str(rows[0][8]) == _FORMAL_LINEAGE_VALIDATOR_CONTRACT
        and tuple(rows[0][9] or ()) == ("search_path=pg_catalog",)
        and not bool(rows[0][10])
        and str(rows[0][11]) == "i"
        and str(rows[0][12]) == "u"
        and bool(rows[0][13])
        and not bool(rows[0][14])
        and bool(rows[0][15])
        and bool(rows[0][16])
        and bool(rows[0][17])
        and bool(rows[0][18])
        and bool(rows[0][19])
        and str(rows[0][20]) == "evidence_ids_text text, lineage_text text"
    )


def _fetch_receipt_lifecycle_check(conn) -> CheckResult:
    installed = (
        _fetch_receipt_lifecycle_trigger_is_installed(conn)
        and _fetch_content_lineage_triggers_are_installed(conn)
        and _formal_lineage_validator_is_installed(conn)
    )
    return _check(
        "database.terminal_fetch_receipts_immutable",
        installed,
        "fetch receipts and exact content lineage have authenticated one-way triggers",
        "fetch receipt/content lineage contract is missing, stale, or bound incorrectly",
    )


def _non_double_precision_columns(conn) -> set[tuple[str, str]]:
    """Return replay-critical columns that are absent or not PostgreSQL float8."""
    from sqlalchemy import text

    rows = conn.execute(
        text(
            "SELECT table_class.relname, attribute.attname, data_type.typname "
            "FROM pg_catalog.pg_attribute AS attribute "
            "JOIN pg_catalog.pg_class AS table_class "
            "ON table_class.oid=attribute.attrelid "
            "JOIN pg_catalog.pg_namespace AS table_namespace "
            "ON table_namespace.oid=table_class.relnamespace "
            "JOIN pg_catalog.pg_type AS data_type "
            "ON data_type.oid=attribute.atttypid "
            "WHERE table_namespace.nspname='public' "
            "AND table_class.relkind IN ('r','p') "
            "AND attribute.attnum>0 AND NOT attribute.attisdropped"
        )
    ).all()
    actual = {(str(row[0]), str(row[1])): str(row[2]) for row in rows}
    return {
        column for column in _POSTGRES_DOUBLE_PRECISION_COLUMNS if actual.get(column) != "float8"
    }


def _formal_registry_contract_is_installed(conn) -> bool:
    """Authenticate uniqueness plus every exact primary-run INSERT guard."""
    from sqlalchemy import text

    constraint_rows = conn.execute(
        text(
            """
            SELECT constraint_row.contype,
                   array_agg(attribute.attname ORDER BY key_column.ordinality)
            FROM pg_catalog.pg_constraint AS constraint_row
            CROSS JOIN LATERAL unnest(constraint_row.conkey)
                WITH ORDINALITY AS key_column(attribute_number, ordinality)
            JOIN pg_catalog.pg_attribute AS attribute
              ON attribute.attrelid = constraint_row.conrelid
             AND attribute.attnum = key_column.attribute_number
            WHERE constraint_row.conrelid =
                'public.formal_trial_registry'::pg_catalog.regclass
              AND constraint_row.contype IN ('p', 'u')
            GROUP BY constraint_row.oid, constraint_row.contype
            """
        )
    ).all()
    constraints = {
        (str(row[0]), tuple(str(column) for column in row[1])) for row in constraint_rows
    }
    expected_constraints = {
        ("p", ("protocol_id",)),
        ("u", ("run_id",)),
        ("u", ("registration_id",)),
    }

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
    expected_triggers = {
        ("formal_trial_registry", "validate_formal_trial_registry_insert"): {
            "table_name": "formal_trial_registry",
            "trigger_name": "validate_formal_trial_registry_insert",
            "function_name": "enforce_formal_trial_registry_insert",
            "type_bits": 7,  # ROW + BEFORE + INSERT.
            "function_hash": _FORMAL_REGISTRY_INSERT_PROSRC_SHA256,
            "function_contract": _FORMAL_REGISTRY_INSERT_CONTRACT,
            "function_default_acl": False,
        },
        ("paper_artifacts", "require_formal_primary_run"): {
            "table_name": "paper_artifacts",
            "trigger_name": "require_formal_primary_run",
            "function_name": "enforce_formal_artifact_primary_run",
            "type_bits": 7,
            "function_hash": _FORMAL_PRIMARY_ARTIFACT_PROSRC_SHA256,
            "function_contract": _FORMAL_PRIMARY_ARTIFACT_CONTRACT,
            "function_default_acl": False,
        },
        ("paper_run_labels", "guard_confirmatory_run_label"): {
            "table_name": "paper_run_labels",
            "trigger_name": "guard_confirmatory_run_label",
            "function_name": "enforce_formal_run_label",
            "type_bits": 7,
            "function_hash": _FORMAL_PRIMARY_LABEL_PROSRC_SHA256,
            "function_contract": _FORMAL_PRIMARY_LABEL_CONTRACT,
            "function_default_acl": False,
        },
        **{
            (table, "require_formal_primary_run"): {
                "table_name": table,
                "trigger_name": "require_formal_primary_run",
                "function_name": "enforce_formal_primary_run_activity",
                "type_bits": 7,
                "function_hash": _FORMAL_PRIMARY_ACTIVITY_PROSRC_SHA256,
                "function_contract": _FORMAL_PRIMARY_ACTIVITY_CONTRACT,
                "function_default_acl": False,
            }
            for table in activity_tables
        },
    }
    trigger_rows = _fetch_trigger_contract_rows(
        conn,
        (
            "validate_formal_trial_registry_insert",
            "require_formal_primary_run",
            "guard_confirmatory_run_label",
        ),
    )
    installed_triggers = {
        (str(row[1]), str(row[3]))
        for row in trigger_rows
        if (str(row[1]), str(row[3])) in expected_triggers
        and _exact_trigger_contract_row(row, **expected_triggers[(str(row[1]), str(row[3]))])
    }
    return (
        len(constraint_rows) == len(expected_constraints)
        and constraints == expected_constraints
        and len(trigger_rows) == len(expected_triggers)
        and installed_triggers == set(expected_triggers)
    )


def _formal_price_capture_contract_is_installed(conn) -> bool:
    """Authenticate every formal price identity, clock, halt, and atomicity guard."""
    terminal_activity_tables = {
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
        "paper_interval_assignments",
    }
    expected = {
        ("paper_price_capture_attempt_events", "validate_formal_price_attempt_event"): {
            "function_name": "enforce_formal_price_attempt_event",
            "type_bits": 7,
        },
        ("paper_price_capture_batches", "validate_formal_price_capture_batch"): {
            "function_name": "enforce_formal_price_capture_batch",
            "type_bits": 7,
        },
        ("paper_price_receipts", "validate_formal_price_receipt"): {
            "function_name": "enforce_formal_price_receipt",
            "type_bits": 7,
        },
        ("paper_price_integrity_failures", "validate_formal_price_terminal_failure"): {
            "function_name": "enforce_formal_price_terminal_failure",
            "type_bits": 7,
        },
        ("paper_marks", "validate_formal_mark_price_batch"): {
            "function_name": "enforce_formal_mark_price_batch",
            "type_bits": 7,
        },
        ("paper_price_capture_batches", "complete_formal_price_capture_batch"): {
            "function_name": "enforce_formal_price_batch_completion",
            "type_bits": 5,
            "constraint_trigger": True,
            "deferrable": True,
            "initially_deferred": True,
        },
        **{
            (table, "reject_after_terminal_price_failure"): {
                "function_name": "enforce_no_terminal_formal_price_failure",
                "type_bits": 7,
            }
            for table in terminal_activity_tables
        },
    }
    rows = _fetch_trigger_contract_rows(
        conn,
        (
            "validate_formal_price_attempt_event",
            "validate_formal_price_capture_batch",
            "validate_formal_price_receipt",
            "validate_formal_price_terminal_failure",
            "validate_formal_mark_price_batch",
            "complete_formal_price_capture_batch",
            "reject_after_terminal_price_failure",
        ),
    )
    installed = set()
    for row in rows:
        key = (str(row[1]), str(row[3]))
        contract = expected.get(key)
        if contract is None:
            continue
        function_hash, function_contract = _FORMAL_PRICE_CONTRACTS[contract["function_name"]]
        if _exact_trigger_contract_row(
            row,
            table_name=key[0],
            trigger_name=key[1],
            function_name=contract["function_name"],
            type_bits=contract["type_bits"],
            function_hash=function_hash,
            function_contract=function_contract,
            function_default_acl=False,
            constraint_trigger=contract.get("constraint_trigger", False),
            deferrable=contract.get("deferrable", False),
            initially_deferred=contract.get("initially_deferred", False),
        ):
            installed.add(key)
    return len(rows) == len(expected) and installed == set(expected)


def _formal_governance_contract_is_installed(conn) -> bool:
    """Authenticate migration 010's exact artifact/label boundary and helpers."""
    from sqlalchemy import text

    expected_triggers = {
        ("paper_artifacts", "govern_formal_artifact_insert"): (
            "enforce_formal_artifact_governance",
            *_FORMAL_GOVERNANCE_TRIGGER_CONTRACTS["enforce_formal_artifact_governance"],
        ),
        ("paper_run_labels", "govern_formal_label_insert"): (
            "enforce_formal_label_governance",
            *_FORMAL_GOVERNANCE_TRIGGER_CONTRACTS["enforce_formal_label_governance"],
        ),
    }
    trigger_rows = _fetch_trigger_contract_rows(
        conn, ("govern_formal_artifact_insert", "govern_formal_label_insert")
    )
    valid_triggers = set()
    for row in trigger_rows:
        key = (str(row[1]), str(row[3]))
        contract = expected_triggers.get(key)
        if contract is None:
            continue
        function_name, function_hash, function_contract = contract
        if _exact_trigger_contract_row(
            row,
            table_name=key[0],
            trigger_name=key[1],
            function_name=function_name,
            type_bits=7,
            function_hash=function_hash,
            function_contract=function_contract,
            function_default_acl=False,
            security_definer=(function_name == "enforce_formal_artifact_governance"),
        ):
            valid_triggers.add(key)

    helper_names = tuple(_FORMAL_GOVERNANCE_HELPER_CONTRACTS)
    encoded_names = ", ".join(f"'{name}'" for name in helper_names)
    helper_rows = conn.execute(
        text(
            f"""
            SELECT function_namespace.nspname, function_row.proname,
                   pg_catalog.pg_get_function_identity_arguments(function_row.oid),
                   pg_catalog.format_type(
                       function_row.prorettype, NULL
                   ) AS return_type,
                   function_language.lanname, function_row.prosecdef,
                   function_row.prokind, function_row.prosrc,
                   pg_catalog.obj_description(function_row.oid, 'pg_proc'),
                   function_row.proconfig, function_row.proleakproof,
                   function_row.provolatile, function_row.proparallel,
                   function_row.proisstrict, function_row.proretset,
                   function_row.probin IS NULL,
                   function_row.proowner <>
                       (SELECT role.oid FROM pg_catalog.pg_roles AS role
                        WHERE role.rolname = current_user),
                   NOT pg_catalog.pg_has_role(
                       current_user, function_row.proowner, 'MEMBER'
                   ),
                   function_language.lanpltrusted,
                   NOT EXISTS (
                       SELECT 1
                       FROM pg_catalog.aclexplode(
                           COALESCE(
                               function_row.proacl,
                               pg_catalog.acldefault('f', function_row.proowner)
                           )
                       ) AS function_acl
                       WHERE function_acl.grantee = 0
                         AND function_acl.privilege_type = 'EXECUTE'
                   ) AS public_execute_revoked
            FROM pg_catalog.pg_proc AS function_row
            JOIN pg_catalog.pg_namespace AS function_namespace
              ON function_namespace.oid = function_row.pronamespace
            JOIN pg_catalog.pg_language AS function_language
              ON function_language.oid = function_row.prolang
            WHERE function_namespace.nspname = 'public'
              AND function_row.proname IN ({encoded_names})
            """
        )
    ).all()
    valid_helpers = set()
    for row in helper_rows:
        name = str(row[1])
        contract = _FORMAL_GOVERNANCE_HELPER_CONTRACTS.get(name)
        if contract is None:
            continue
        source_hash, function_contract, arguments, return_type, strict = contract
        if (
            str(row[0]) == "public"
            and str(row[2]) == arguments
            and str(row[3]) == return_type
            and str(row[4]) == "sql"
            and not bool(row[5])
            and str(row[6]) == "f"
            and _normalized_pg_prosrc_sha256(row[7]) == source_hash
            and str(row[8]) == function_contract
            and tuple(row[9] or ()) == ("search_path=pg_catalog",)
            and not bool(row[10])
            and str(row[11]) == "i"
            and str(row[12]) == "u"
            and bool(row[13]) is strict
            and not bool(row[14])
            and bool(row[15])
            and bool(row[16])
            and bool(row[17])
            and bool(row[18])
            and bool(row[19])
        ):
            valid_helpers.add(name)
    return (
        len(trigger_rows) == len(expected_triggers)
        and valid_triggers == set(expected_triggers)
        and len(helper_rows) == len(_FORMAL_GOVERNANCE_HELPER_CONTRACTS)
        and valid_helpers == set(_FORMAL_GOVERNANCE_HELPER_CONTRACTS)
    )


def _formal_llm_budget_contract_is_installed(conn) -> bool:
    """Authenticate migration 011's atomic budget and attempt boundary."""
    from sqlalchemy import text

    expected_triggers = {
        (
            "paper_decision_bundles",
            "validate_formal_decision_bundle_attempt",
        ): (
            "enforce_formal_decision_bundle_attempt",
            _FORMAL_LLM_ATTEMPT_BINDING_PROSRC_SHA256,
            _FORMAL_LLM_ATTEMPT_BINDING_CONTRACT,
        ),
        (
            "paper_decision_attempt_events",
            "reject_attempt_retry_after_llm_reservation",
        ): (
            "enforce_no_attempt_retry_after_llm_reservation",
            _FORMAL_LLM_NO_RETRY_PROSRC_SHA256,
            _FORMAL_LLM_NO_RETRY_CONTRACT,
        ),
    }
    trigger_rows = _fetch_trigger_contract_rows(
        conn,
        (
            "validate_formal_decision_bundle_attempt",
            "reject_attempt_retry_after_llm_reservation",
        ),
    )
    valid_triggers = set()
    for row in trigger_rows:
        key = (str(row[1]), str(row[3]))
        contract = expected_triggers.get(key)
        if contract is None:
            continue
        function_name, function_hash, function_contract = contract
        if _exact_trigger_contract_row(
            row,
            table_name=key[0],
            trigger_name=key[1],
            function_name=function_name,
            type_bits=7,
            function_hash=function_hash,
            function_contract=function_contract,
            function_default_acl=False,
        ):
            valid_triggers.add(key)

    function_rows = conn.execute(
        text(
            """
            SELECT function_namespace.nspname, function_row.proname,
                   pg_catalog.pg_get_function_identity_arguments(function_row.oid),
                   pg_catalog.pg_get_function_result(function_row.oid),
                   function_language.lanname, function_row.prosecdef,
                   function_row.prokind, function_row.prosrc,
                   pg_catalog.obj_description(function_row.oid, 'pg_proc'),
                   function_row.proconfig, function_row.proleakproof,
                   function_row.provolatile, function_row.proparallel,
                   function_row.proisstrict, function_row.proretset,
                   function_row.probin IS NULL,
                   function_row.proowner <>
                       (SELECT role.oid FROM pg_catalog.pg_roles AS role
                        WHERE role.rolname = current_user),
                   NOT pg_catalog.pg_has_role(
                       current_user, function_row.proowner, 'MEMBER'
                   ),
                   function_language.lanpltrusted,
                   NOT EXISTS (
                       SELECT 1
                       FROM pg_catalog.aclexplode(
                           COALESCE(
                               function_row.proacl,
                               pg_catalog.acldefault('f', function_row.proowner)
                           )
                       ) AS function_acl
                       WHERE function_acl.grantee = 0
                         AND function_acl.privilege_type = 'EXECUTE'
                   ),
                   pg_catalog.has_function_privilege(
                       current_user, function_row.oid, 'EXECUTE'
                   )
            FROM pg_catalog.pg_proc AS function_row
            JOIN pg_catalog.pg_namespace AS function_namespace
              ON function_namespace.oid = function_row.pronamespace
            JOIN pg_catalog.pg_language AS function_language
              ON function_language.oid = function_row.prolang
            WHERE function_namespace.nspname = 'public'
              AND function_row.proname = 'reserve_formal_llm_invocation_budget'
            """
        )
    ).all()
    expected_arguments = (
        "p_run_id text, p_decision_date text, p_stage text, p_provider text, "
        "p_requested_model text, p_input_bundle_id text, p_prompt_id text, "
        "p_prompt_bytes integer, p_max_prompt_bytes integer, "
        "p_max_completion_tokens integer"
    )
    expected_result = (
        "TABLE(reservation_artifact_id text, reservation_receipt_json text, "
        "decision_count integer, daily_count integer, utc_day text, "
        "reserved_utc double precision, max_calls_per_decision integer, "
        "max_calls_per_utc_day integer, decision_counter_key text, "
        "daily_counter_key text)"
    )
    valid_function = len(function_rows) == 1
    if valid_function:
        row = function_rows[0]
        valid_function = (
            str(row[0]) == "public"
            and str(row[1]) == "reserve_formal_llm_invocation_budget"
            and str(row[2]) == expected_arguments
            and str(row[3]) == expected_result
            and str(row[4]) == "plpgsql"
            and bool(row[5])
            and str(row[6]) == "f"
            and _normalized_pg_prosrc_sha256(row[7]) == _FORMAL_LLM_RESERVATION_PROSRC_SHA256
            and str(row[8]) == _FORMAL_LLM_RESERVATION_CONTRACT
            and tuple(row[9] or ()) == ("search_path=pg_catalog",)
            and not bool(row[10])
            and str(row[11]) == "v"
            and str(row[12]) == "u"
            and not bool(row[13])
            and bool(row[14])
            and bool(row[15])
            and bool(row[16])
            and bool(row[17])
            and bool(row[18])
            and bool(row[19])
            and bool(row[20])
        )

    table_rows = conn.execute(
        text(
            """
            WITH counter_columns AS (
                SELECT pg_catalog.array_agg(
                           attribute.attname || ':' || pg_catalog.format_type(
                               attribute.atttypid, attribute.atttypmod
                           ) || ':' || attribute.attnotnull::TEXT
                           ORDER BY attribute.attname COLLATE pg_catalog."C"
                       ) AS columns
                FROM pg_catalog.pg_attribute AS attribute
                WHERE attribute.attrelid =
                        'public.formal_llm_budget_counters'::pg_catalog.regclass
                  AND attribute.attnum > 0
                  AND NOT attribute.attisdropped
            ), counter_keys AS (
                SELECT pg_catalog.array_agg(
                           installed.contype || ':'
                           || pg_catalog.array_to_string(installed.columns, ',')
                           ORDER BY installed.contype,
                                    pg_catalog.array_to_string(installed.columns, ',')
                       ) AS keys
                FROM (
                    SELECT constraint_row.contype,
                           pg_catalog.array_agg(
                               attribute.attname ORDER BY key_column.ordinality
                           ) AS columns
                    FROM pg_catalog.pg_constraint AS constraint_row
                    CROSS JOIN LATERAL pg_catalog.unnest(constraint_row.conkey)
                        WITH ORDINALITY AS key_column(attribute_number, ordinality)
                    JOIN pg_catalog.pg_attribute AS attribute
                      ON attribute.attrelid = constraint_row.conrelid
                     AND attribute.attnum = key_column.attribute_number
                    WHERE constraint_row.conrelid =
                            'public.formal_llm_budget_counters'::pg_catalog.regclass
                      AND constraint_row.contype IN ('p', 'u')
                    GROUP BY constraint_row.oid, constraint_row.contype
                ) AS installed
            )
            SELECT counter_columns.columns, counter_keys.keys,
                   NOT pg_catalog.has_table_privilege(
                       current_user, 'public.formal_llm_budget_counters', 'SELECT'
                   ),
                   NOT pg_catalog.has_table_privilege(
                       current_user, 'public.formal_llm_budget_counters', 'INSERT'
                   ),
                   NOT pg_catalog.has_table_privilege(
                       current_user, 'public.formal_llm_budget_counters', 'UPDATE'
                   ),
                   NOT pg_catalog.has_table_privilege(
                       current_user, 'public.formal_llm_budget_counters', 'DELETE'
                   ),
                   NOT pg_catalog.has_table_privilege(
                       current_user, 'public.formal_llm_budget_counters', 'TRUNCATE'
                   )
            FROM counter_columns CROSS JOIN counter_keys
            """
        )
    ).all()
    expected_columns = [
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
    expected_keys = [
        "p:counter_key",
        "u:scope,protocol_id,run_id,counter_kind,bucket_date",
    ]
    valid_table = (
        len(table_rows) == 1
        and list(table_rows[0][0] or ()) == expected_columns
        and list(table_rows[0][1] or ()) == expected_keys
        and all(bool(value) for value in table_rows[0][2:])
    )
    return (
        len(trigger_rows) == len(expected_triggers)
        and valid_triggers == set(expected_triggers)
        and valid_function
        and valid_table
    )


def _formal_primary_registry_check(conn, configured_run_id: str | None) -> CheckResult:
    """Bind PAPER_RUN_ID to the sole coherent primary row for this protocol."""
    from sqlalchemy import text

    run_id = (configured_run_id or "").strip()
    if not run_id:
        return CheckResult(
            "database.primary_confirmatory_run",
            False,
            "PAPER_RUN_ID is absent; primary-run binding cannot be verified",
        )
    registry_rows = conn.execute(
        text(
            "SELECT protocol_id,run_id,registration_id,created_utc,details_json "
            "FROM formal_trial_registry "
            "WHERE protocol_id=:protocol_id OR run_id=:run_id "
            "ORDER BY protocol_id,run_id"
        ),
        {"protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID, "run_id": run_id},
    ).all()
    coherent = len(registry_rows) == 1
    if coherent:
        registry = registry_rows[0]
        coherent = str(registry[0]) == GLOBAL_EVENT_V2_PROTOCOL_ID and str(registry[1]) == run_id
    if coherent:
        config_rows = conn.execute(
            text("SELECT config_json FROM paper_runs WHERE run_id=:run_id"),
            {"run_id": run_id},
        ).all()
        label_rows = conn.execute(
            text(
                "SELECT created_utc,details_json FROM paper_run_labels "
                "WHERE run_id=:run_id AND label='confirmatory-trial'"
            ),
            {"run_id": run_id},
        ).all()
        coherent = len(config_rows) == 1 and len(label_rows) == 1
    if coherent:
        try:
            config = json.loads(config_rows[0][0])
            details = json.loads(registry[4])
        except (TypeError, ValueError):
            coherent = False
        else:
            coherent = (
                isinstance(config, dict)
                and isinstance(details, dict)
                and config.get("engine") == "formal-global-v2"
                and config.get("protocol_id") == GLOBAL_EVENT_V2_PROTOCOL_ID
                and config.get("trial_registration_id") == registry[2]
                and details.get("protocol_id") == GLOBAL_EVENT_V2_PROTOCOL_ID
                and details.get("run_id") == run_id
                and details.get("registration_id") == registry[2]
                and details.get("registration_type") == "confirmatory"
                and details.get("outcomes_accessed_before_registration") is False
                and label_rows[0][0] == registry[3]
                and label_rows[0][1] == registry[4]
            )
    return _check(
        "database.primary_confirmatory_run",
        coherent,
        "PAPER_RUN_ID is the unique protocol-bound primary confirmatory run",
        "primary run registry is absent, multiple, mismatched, or incoherent",
    )


def _split_paper_postgres_checks(
    store,
    component: str,
    *,
    paper_run_id: str | None,
    env: Mapping[str, str],
) -> list[CheckResult]:
    """Authenticate one migration-013 paper principal on one connection."""

    from sqlalchemy import text

    from tradingagents.formal_activation import require_runtime_authorization
    from tradingagents.formal_roles import (
        DECISION_ROLE,
        MARKER_ROLE,
        ROLE_PREFLIGHT_SQL,
        validate_runtime_role_preflight,
    )
    from tradingagents.outcome_semantics import outcome_semantics_id
    from tradingagents.paper_trading import PaperStore

    internal_role = _INTERNAL_COMPONENT_ROLES[component]
    expected_role = DECISION_ROLE if component == "paper-decision" else MARKER_ROLE
    if getattr(store, "dialect", None) != "postgresql" or not hasattr(store, "engine"):
        return [
            CheckResult(
                "database.postgres_backend",
                False,
                "production preflight requires the PostgreSQL media store",
            ),
            CheckResult(
                "database.formal_role_split_contract",
                False,
                "migration-013 role and RLS checks require PostgreSQL",
            ),
            CheckResult(
                "database.runtime_authorization",
                False,
                "durable runtime authorization requires PostgreSQL",
            ),
        ]

    no_schema_admin = False
    role_contract = False
    primary_registry = CheckResult(
        "database.primary_confirmatory_run",
        False,
        "primary-run binding could not be authenticated",
    )
    authorization_row = None
    try:
        with store.engine.connect() as conn:
            no_schema_admin = not conn.execute(
                text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
            ).scalar_one() and not conn.execute(
                text(
                    "SELECT has_database_privilege(current_user, current_database(), 'CREATE')"
                )
            ).scalar_one()
            role_rows = conn.execute(text(ROLE_PREFLIGHT_SQL)).mappings().all()
            if len(role_rows) == 1:
                validate_runtime_role_preflight(
                    dict(role_rows[0]), expected_role=expected_role
                )
                role_contract = True
            if paper_run_id:
                primary_registry = _formal_primary_registry_check(conn, paper_run_id)
                authorization_rows = conn.execute(
                    text(
                        "SELECT protocol_id,run_id,registration_id,authorization_id,"
                        "authorized_utc,outcome_semantics_id,configuration_manifest_id,"
                        "collector_configuration_id,paper_decision_configuration_id,"
                        "paper_marker_configuration_id,collector_build_id,"
                        "paper_decision_build_id,paper_marker_build_id,authorization_json "
                        "FROM public.formal_trial_authorizations WHERE run_id=:run_id"
                    ),
                    {"run_id": paper_run_id},
                ).mappings().all()
                if len(authorization_rows) == 1:
                    authorization_row = dict(authorization_rows[0])
    except Exception:  # noqa: BLE001 - SQL/role details may expose deployment metadata
        role_contract = False
        authorization_row = None

    authorized = False
    try:
        if not paper_run_id or authorization_row is None:
            raise ValueError("formal authorization is absent")
        material = _runtime_material(component, env)
        configuration = material["component_configuration"]
        authorization = PaperStore._validated_authorization_row(  # noqa: SLF001
            authorization_row, run_id=paper_run_id
        )
        require_runtime_authorization(
            authorization,
            role=internal_role,
            outcome_semantics_id=outcome_semantics_id(),
            component_configuration_id=configuration["configuration_id"],
            env=env,
        )
        authorized = True
    except Exception:  # noqa: BLE001 - authorization failures must stay redacted
        authorized = False

    return [
        CheckResult("database.postgres_backend", True, "PostgreSQL connection succeeded"),
        _check(
            "database.no_schema_admin",
            no_schema_admin,
            "runtime identity cannot create schemas or databases",
            "runtime identity has schema or database creation privilege",
        ),
        _check(
            "database.formal_role_split_contract",
            role_contract,
            "exact login, legacy decommission, ACLs, and forced RLS contract match",
            "runtime login, role split, or forced RLS policy contract differs",
        ),
        primary_registry,
        _check(
            "database.runtime_authorization",
            authorized,
            "exact image, component configuration, and outcome semantics are authorized",
            "durable authorization is absent or bound to another runtime identity",
        ),
    ]


def _postgres_security_checks(
    store,
    component: str,
    paper_run_id: str | None = None,
    env: Mapping[str, str] | None = None,
) -> list[CheckResult]:
    from sqlalchemy import text

    from tradingagents.formal_roles import PROTECTED_TABLES
    from tradingagents.paper_trading import PaperStore

    if component in _PAPER_RUNTIME_COMPONENTS:
        return _split_paper_postgres_checks(
            store,
            component,
            paper_run_id=paper_run_id,
            env={} if env is None else env,
        )

    if getattr(store, "dialect", None) != "postgresql" or not hasattr(store, "engine"):
        checks = [
            CheckResult(
                "database.postgres_backend",
                False,
                "production preflight requires the PostgreSQL media store",
            ),
            CheckResult(
                "database.terminal_fetch_receipts_immutable",
                False,
                "fetch receipt lifecycle trigger requires PostgreSQL catalog verification",
            ),
        ]
        return checks
    media_tables = ("media_posts", "media_labels", "media_observations", "macro_odds")
    lineage_table = "fetch_run_items"
    paper_tables = tuple(sorted(PROTECTED_TABLES))
    with store.engine.connect() as conn:
        no_schema_create = not conn.execute(
            text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
        ).scalar_one()
        no_database_create = not conn.execute(
            text("SELECT has_database_privilege(current_user, current_database(), 'CREATE')")
        ).scalar_one()
        privileges = {
            table: _table_privileges(conn, table)
            for table in (*media_tables, lineage_table, "fetch_runs", "poll_state", *paper_tables)
        }
        role_row = conn.execute(
            text("SELECT current_user AS current_role, session_user AS session_role")
        ).mappings().one()
        exact_collector_role = (
            role_row["current_role"] == _COLLECTOR_DATABASE_ROLE
            and role_row["session_role"] == _COLLECTOR_DATABASE_ROLE
        )
        required = (
            all({"SELECT", "INSERT"}.issubset(privileges[table]) for table in media_tables)
            and {"SELECT", "INSERT"}.issubset(privileges[lineage_table])
            and {"SELECT", "INSERT", "UPDATE"}.issubset(privileges["fetch_runs"])
            and {"SELECT", "INSERT", "UPDATE"}.issubset(privileges["poll_state"])
        )
        forbidden = (
            any(
                privileges[table] & {"INSERT", "UPDATE", "DELETE", "TRUNCATE"}
                for table in paper_tables
            )
            or any(
                privileges[table] & {"UPDATE", "DELETE", "TRUNCATE"}
                for table in (*media_tables, lineage_table)
            )
            or bool(privileges["fetch_runs"] & {"DELETE", "TRUNCATE"})
            or bool(privileges["poll_state"] & {"DELETE", "TRUNCATE"})
        )
        expected_triggers = set(PaperStore._IMMUTABLE_TABLES)
        trigger_tables = _installed_immutable_trigger_tables(conn)
        fetch_receipt_lifecycle = _fetch_receipt_lifecycle_check(conn)
        registry_contract = _formal_registry_contract_is_installed(conn)
        imprecise_columns = _non_double_precision_columns(conn)
    checks = [
        CheckResult("database.postgres_backend", True, "PostgreSQL connection succeeded"),
        _check(
            "database.no_schema_admin",
            no_schema_create and no_database_create,
            "runtime identity cannot create schemas or databases",
            "runtime identity has schema or database creation privilege",
        ),
        _check(
            "database.runtime_role",
            exact_collector_role,
            "collector uses its exact login role without SET ROLE",
            "collector database login is wrong or changed with SET ROLE",
        ),
        _check(
            "database.required_runtime_grants",
            required,
            f"required {component} privileges are present",
            f"required {component} privileges are missing",
        ),
        _check(
            "database.forbidden_runtime_grants",
            not forbidden,
            f"forbidden {component} mutation privileges are absent",
            f"runtime identity has forbidden {component} mutation privileges",
        ),
        _check(
            "database.append_only_triggers",
            expected_triggers.issubset(trigger_tables),
            f"all {len(expected_triggers)} append-only table triggers are installed",
            "one or more append-only table triggers are missing",
        ),
        fetch_receipt_lifecycle,
        _check(
            "database.primary_run_registry_contract",
            registry_contract,
            "protocol/run uniqueness and every formal INSERT guard are installed",
            "primary-run constraints or formal INSERT guards are missing",
        ),
        _check(
            "database.double_precision_replay_columns",
            not imprecise_columns,
            "all replay-critical numeric columns use double precision",
            "one or more replay-critical numeric columns are absent or narrow",
        ),
    ]
    return checks


def run_preflight(
    component: str,
    *,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
    store_factory: Callable[[str], object] | None = None,
) -> PreflightReport:
    """Run read-only checks and convert every operational error to a redacted failure."""
    if component not in _RUNTIME_COMPONENTS:
        raise ValueError(
            "component must be collector, paper-decision, or paper-marker"
        )
    env = os.environ if env is None else env
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("preflight time must be timezone-aware")
    now = now.astimezone(timezone.utc)
    checks = _configuration_checks(component, env)
    cutoff_utc = None
    if component in {"collector", "paper-decision"}:
        decision_results, _decision_date, cutoff_utc = _decision_checks(now)
        checks.extend(decision_results)

    # Opening the current store can create tables unless this is checked first.
    # Refuse all database inspection when configuration is ambiguous or unsafe.
    safe_to_open = (
        bool((env.get("MEDIA_DB_URL") or "").strip())
        and _explicitly_disabled(env, "MEDIA_AUTO_MIGRATE")
        and (
            component not in _PAPER_RUNTIME_COMPONENTS
            or _explicitly_disabled(env, "PAPER_AUTO_MIGRATE")
        )
    )
    if not safe_to_open:
        checks.append(
            CheckResult(
                "database.connection",
                False,
                "database inspection skipped because runtime migration safety is not proven",
            )
        )
        return PreflightReport(component, tuple(checks))

    if store_factory is None:
        from tradingagents.dataflows.media_store import open_store

        def non_migrating_store(url: str):
            return open_store(url, auto_migrate=False)

        store_factory = non_migrating_store
    store = None
    try:
        store = store_factory(env["MEDIA_DB_URL"])
        checks.append(CheckResult("database.connection", True, "database connection succeeded"))
        checks.extend(
            _postgres_security_checks(
                store,
                component,
                env.get("PAPER_RUN_ID")
                if component in _PAPER_RUNTIME_COMPONENTS
                else None,
                env,
            )
        )
        if component == "collector":
            checks.extend(_collector_heartbeat_checks(store, env, now.timestamp()))
            checks.extend(_formal_runtime_health_checks(store, env, now.timestamp()))
        if component in {"collector", "paper-decision"}:
            if cutoff_utc is None:
                checks.append(
                    CheckResult(
                        "data.cutoff_checks",
                        False,
                        "coverage and receipt checks require an active decision window",
                    )
                )
            else:
                checks.extend(_receipt_checks(store, cutoff_utc, now.timestamp(), env))
    except Exception as exc:  # noqa: BLE001 - output must never contain exception text/DSNs
        checks.append(
            CheckResult(
                "database.inspection",
                False,
                f"database inspection failed ({type(exc).__name__}); details redacted",
            )
        )
    finally:
        if store is not None:
            try:
                store.close()
            except Exception:  # noqa: BLE001 - closing cannot make output disclose credentials
                checks.append(
                    CheckResult(
                        "database.close",
                        False,
                        "database close failed; details redacted",
                    )
                )
    return PreflightReport(component, tuple(checks))


def _print_report(report: PreflightReport, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(report.as_dict(), sort_keys=True))
        return
    for check in report.checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"{status} {check.name}: {check.detail}")
    print(f"runtime_ready={str(report.ready).lower()}")
    print("scope=restore drill and offline staging replay are separate required runbook gates")


def _alert_test(
    component: str,
    *,
    timeout: float,
    json_output: bool,
    observed_utc: float | None = None,
) -> int:
    if component not in _RUNTIME_COMPONENTS:
        raise ValueError("alert component is not allowlisted")
    endpoint = (os.getenv("TRADINGAGENTS_ALERT_WEBHOOK_URL") or "").strip()
    configured = bool(endpoint)
    material: Mapping[str, object] | None = None
    if configured and json_output:
        try:
            material = _runtime_material(component, os.environ)
        except Exception:  # noqa: BLE001 - configuration may name secret variables
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error_code": "runtime_material_invalid",
                    },
                    sort_keys=True,
                )
            )
            return 1
    delivered = configured and emit_alert(
        component,
        "operator_delivery_test",
        severity="warning",
        details={"test": True},
        timeout=timeout,
    )
    if json_output and delivered and material is not None:
        from tradingagents.formal_activation import build_alert_delivery_receipt

        component_configuration = material["component_configuration"]
        preflight_payload = material["preflight_payload"]
        if not isinstance(component_configuration, Mapping) or not isinstance(
            preflight_payload, Mapping
        ):
            print(
                json.dumps(
                    {"status": "failed", "error_code": "runtime_material_invalid"},
                    sort_keys=True,
                )
            )
            return 1
        try:
            receipt = build_alert_delivery_receipt(
                role=_INTERNAL_COMPONENT_ROLES[component],
                build_id=preflight_payload["build_id"],
                component_configuration_id=component_configuration["configuration_id"],
                route_fingerprint="sha256:"
                + hashlib.sha256(endpoint.encode("utf-8")).hexdigest(),
                client_observed_utc=(
                    datetime.now(timezone.utc).timestamp()
                    if observed_utc is None
                    else observed_utc
                ),
            )
        except Exception:  # noqa: BLE001 - output stays fail-closed and redacted
            print(
                json.dumps(
                    {"status": "failed", "error_code": "receipt_build_failed"},
                    sort_keys=True,
                )
            )
            return 1
        print(json.dumps(receipt, sort_keys=True))
    elif json_output:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_code": (
                        "alert_delivery_failed"
                        if configured
                        else "alert_webhook_not_configured"
                    ),
                },
                sort_keys=True,
            )
        )
    elif delivered:
        print("PASS alert.delivery: webhook returned a successful HTTP status")
    elif configured:
        print("FAIL alert.delivery: webhook delivery failed; endpoint details redacted")
    else:
        print("FAIL alert.delivery: TRADINGAGENTS_ALERT_WEBHOOK_URL is not configured")
    return 0 if delivered else 1


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError("release evidence contains a duplicate JSON key")
        document[key] = value
    return document


def _reject_nonstandard_json_constant(value: str) -> object:
    raise ValueError(f"release evidence contains invalid JSON constant {value!r}")


def _load_release_evidence(path: Path) -> object:
    """Read one bounded JSON document without accepting duplicate object keys."""

    if not isinstance(path, Path) or not path.is_file():
        raise ValueError("release evidence path is not a regular file")
    size = path.stat().st_size
    if size <= 0 or size > _MAX_RELEASE_EVIDENCE_BYTES:
        raise ValueError("release evidence file size is invalid")
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(
            handle,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonstandard_json_constant,
        )
    return value


def _build_restore_rehearsal_command(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    engine_factory: Callable[[str], object] | None = None,
) -> int:
    """Inspect a restored clone and emit the exact initial-release evidence.

    The database credential is environment-only and every failure is redacted.
    The command proves that the clone contains the collector cycle, has the
    migration-013 role contract, and has zero formal trial activity. It cannot
    manufacture the preauthorization decision/mark rows that the database is
    deliberately designed to forbid.
    """

    from sqlalchemy import create_engine, text

    from tradingagents.dataflows.media_store import _normalize_pg_url
    from tradingagents.formal_activation import (
        build_restore_rehearsal_payload,
        validate_collector_rehearsal_payload,
    )
    from tradingagents.formal_release import validate_in_image_runtime_material
    from tradingagents.formal_roles import (
        PREAUTHORIZATION_ACTIVITY_TABLES,
        is_formal_schema_admin_identity,
    )

    values = os.environ if env is None else env
    database_url = values.get("TRADINGAGENTS_RESTORE_DB_URL")
    engine = None
    try:
        if not isinstance(database_url, str) or not database_url.strip():
            raise ValueError("restore database is not configured")
        collector = validate_collector_rehearsal_payload(
            _load_release_evidence(args.collector_rehearsal)
        )
        decision_material = validate_in_image_runtime_material(
            _load_release_evidence(args.paper_decision_material),
            expected_role="paper_decision",
        )
        run_id = decision_material["component_configuration"]["settings"]["run_id"]
        activity_sources = [
            "SELECT pg_catalog.count(*) AS row_count "
            f"FROM public.{table_name} WHERE run_id=:run_id"
            for table_name in sorted(PREAUTHORIZATION_ACTIVITY_TABLES)
        ]
        activity_sources.extend(
            [
                "SELECT pg_catalog.count(*) FROM public.paper_artifacts "
                "WHERE content_json::jsonb->>'run_id'=:run_id",
                "SELECT pg_catalog.count(*) FROM public.paper_run_labels "
                "WHERE run_id=:run_id AND label<>'confirmatory-trial'",
            ]
        )
        activity_query = (
            "SELECT coalesce(pg_catalog.sum(activity.row_count),0) FROM ("
            + " UNION ALL ".join(activity_sources)
            + ") AS activity"
        )
        factory = create_engine if engine_factory is None else engine_factory
        engine = factory(_normalize_pg_url(database_url.strip()))
        with engine.connect() as conn:
            identity = dict(
                conn.execute(
                    text(
                        "SELECT current_user::text AS current_role,"
                        "session_user::text AS session_role,"
                        "pg_catalog.pg_has_role(current_user,'schema_admin','MEMBER') "
                        "AS schema_admin_member,"
                        "pg_catalog.pg_has_role(session_user,'schema_admin','MEMBER') "
                        "AS session_schema_admin_member,"
                        "(SELECT role.rolsuper FROM pg_catalog.pg_roles AS role "
                        "WHERE role.rolname=current_user) AS is_superuser,"
                        "public.formal_role_policy_contract_matches() AS role_contract_ready,"
                        "pg_catalog.date_part('epoch',pg_catalog.clock_timestamp()) "
                        "AS verification_completed_utc"
                    )
                ).mappings().one()
            )
            if (
                not is_formal_schema_admin_identity(
                    current_role=identity.get("current_role"),
                    session_role=identity.get("session_role"),
                    current_is_schema_admin=identity.get("schema_admin_member"),
                    session_is_schema_admin=identity.get(
                        "session_schema_admin_member"
                    ),
                )
                or identity.get("is_superuser") is not False
                or identity.get("role_contract_ready") is not True
            ):
                raise ValueError("restored clone identity or role contract is invalid")
            cycle_rows = [
                dict(row)
                for row in conn.execute(
                    text(
                        "SELECT collection_cycle_id,status,protocol_id,"
                        "collector_build_id,manifest_id,manifest_json "
                        "FROM public.collection_cycles "
                        "WHERE collection_cycle_id=:collection_cycle_id"
                    ),
                    {"collection_cycle_id": collector["collection_cycle_id"]},
                ).mappings().all()
            ]
            if len(cycle_rows) != 1:
                raise ValueError("restored clone lacks the exact collector cycle")
            cycle = cycle_rows[0]
            stored_manifest = cycle.get("manifest_json")
            if isinstance(stored_manifest, str):
                stored_manifest = json.loads(stored_manifest)
            if (
                cycle.get("status") != "complete"
                or cycle.get("protocol_id") != collector["protocol_id"]
                or cycle.get("collector_build_id") != collector["collector_build_id"]
                or cycle.get("manifest_id") != collector["manifest_id"]
                or stored_manifest != collector["manifest"]
            ):
                raise ValueError("restored clone collector cycle differs from its proof")
            activity_rows = int(
                conn.execute(
                    text(activity_query),
                    {"run_id": run_id},
                ).scalar_one()
            )
        payload = build_restore_rehearsal_payload(
            source_cluster_fingerprint=args.source_cluster_fingerprint,
            restored_cluster_fingerprint=args.restored_cluster_fingerprint,
            backup_fingerprint=args.backup_fingerprint,
            backup_completed_utc=args.backup_completed_utc,
            collector_rehearsal=collector,
            formal_trial_activity_rows=activity_rows,
            verification_completed_utc=float(
                identity["verification_completed_utc"]
            ),
        )
    except Exception:  # noqa: BLE001 - DB errors and paths may contain secrets
        print(
            json.dumps(
                {"status": "failed", "error_code": "restore_rehearsal_invalid"},
                sort_keys=True,
            )
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps(payload, sort_keys=True))
    return 0


def _formal_release_command(
    args: argparse.Namespace, *, env: Mapping[str, str] | None = None
) -> int:
    """Plan or execute a formal release while emitting only safe identities."""

    from tradingagents.formal_release import (
        build_formal_release_plan,
        execute_formal_release,
    )

    env = os.environ if env is None else env
    try:
        runtime_materials = {
            "collector": _load_release_evidence(args.collector_material),
            "paper_decision": _load_release_evidence(args.paper_decision_material),
            "paper_marker": _load_release_evidence(args.paper_marker_material),
        }
        machine_inventories = {
            "collector": _load_release_evidence(args.collector_machines),
            "paper_decision": _load_release_evidence(args.paper_decision_machines),
            "paper_marker": _load_release_evidence(args.paper_marker_machines),
        }
        restore_rehearsal = _load_release_evidence(args.restore_rehearsal)
        alert_deliveries = {
            "collector": _load_release_evidence(args.collector_alert),
            "paper_decision": _load_release_evidence(args.paper_decision_alert),
            "paper_marker": _load_release_evidence(args.paper_marker_alert),
        }
        from tradingagents.formal_activation import build_alert_delivery_payload

        alert_delivery = build_alert_delivery_payload(deliveries=alert_deliveries)
    except Exception:  # noqa: BLE001 - evidence and paths must never be echoed
        print(json.dumps({"status": "failed", "error_code": "evidence_invalid"}))
        return 1
    try:
        plan = build_formal_release_plan(
            runtime_materials=runtime_materials,
            machine_inventories=machine_inventories,
            restore_rehearsal=restore_rehearsal,
            alert_delivery=alert_delivery,
        )
    except Exception:  # noqa: BLE001 - payload material must never be echoed
        print(json.dumps({"status": "failed", "error_code": "release_plan_invalid"}))
        return 1
    if not args.execute:
        print(
            json.dumps(
                plan.safe_summary(status="planned", database_writes=False),
                sort_keys=True,
            )
        )
        return 0
    admin_db_url = env.get("TRADINGAGENTS_ADMIN_DB_URL")
    if not isinstance(admin_db_url, str) or not admin_db_url.strip():
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_code": "admin_database_not_configured",
                },
                sort_keys=True,
            )
        )
        return 1
    try:
        result = execute_formal_release(admin_db_url=admin_db_url, plan=plan)
    except Exception:  # noqa: BLE001 - database exceptions may contain the DSN
        print(
            json.dumps(
                {"status": "failed", "error_code": "release_transaction_failed"},
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Runtime preflight, explicit alert delivery test, and guarded "
            "administrator formal release."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight", help="Run fail-closed runtime checks")
    preflight.add_argument("--component", choices=_RUNTIME_COMPONENTS, required=True)
    preflight.add_argument("--json", action="store_true", help="Emit one JSON object")
    alert = commands.add_parser("alert-test", help="Send a synthetic operations alert")
    alert.add_argument("--component", choices=_RUNTIME_COMPONENTS, required=True)
    alert.add_argument("--timeout", type=float, default=5.0)
    alert.add_argument("--json", action="store_true", help="Emit one JSON object")
    release = commands.add_parser(
        "formal-release",
        help="Plan an offline-evidence-bound formal release; write only with --execute",
    )
    release.add_argument("--collector-material", type=Path, required=True)
    release.add_argument("--paper-decision-material", type=Path, required=True)
    release.add_argument("--paper-marker-material", type=Path, required=True)
    release.add_argument("--collector-machines", type=Path, required=True)
    release.add_argument("--paper-decision-machines", type=Path, required=True)
    release.add_argument("--paper-marker-machines", type=Path, required=True)
    release.add_argument("--restore-rehearsal", type=Path, required=True)
    release.add_argument("--collector-alert", type=Path, required=True)
    release.add_argument("--paper-decision-alert", type=Path, required=True)
    release.add_argument("--paper-marker-alert", type=Path, required=True)
    release.add_argument(
        "--execute",
        action="store_true",
        help="Commit bootstrap and release records using TRADINGAGENTS_ADMIN_DB_URL",
    )
    restore = commands.add_parser(
        "build-restore-rehearsal",
        help="Inspect an isolated restored clone and emit exact release evidence",
    )
    restore.add_argument("--collector-rehearsal", type=Path, required=True)
    restore.add_argument("--paper-decision-material", type=Path, required=True)
    restore.add_argument("--source-cluster-fingerprint", required=True)
    restore.add_argument("--restored-cluster-fingerprint", required=True)
    restore.add_argument("--backup-fingerprint", required=True)
    restore.add_argument("--backup-completed-utc", type=float, required=True)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "alert-test":
        if not 0 < args.timeout <= 30:
            parser.error("--timeout must be greater than zero and no more than 30 seconds")
        raise SystemExit(_alert_test(args.component, timeout=args.timeout, json_output=args.json))
    if args.command == "formal-release":
        raise SystemExit(_formal_release_command(args))
    if args.command == "build-restore-rehearsal":
        raise SystemExit(_build_restore_rehearsal_command(args))
    report = run_preflight(args.component)
    _print_report(report, json_output=args.json)
    raise SystemExit(0 if report.ready else 1)


if __name__ == "__main__":
    main()
