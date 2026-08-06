"""Exact runtime configuration and in-image preflight identities.

These builders consume the same parsed arguments and environment values used
by the long-running processes.  Release tooling must never independently
reconstruct what it believes a worker will use: the paused deployed image emits
its component manifest and a build-bound preflight payload, and the worker
recomputes that same manifest before every authorized formal operation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.formal_activation import build_runtime_preflight_payload
from tradingagents.formal_configuration import (
    build_component_configuration,
    validate_component_configuration,
)
from tradingagents.llm_clients.api_key_env import PROVIDER_API_KEY_ENV
from tradingagents.outcome_semantics import outcome_semantics_id
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    content_id,
    runtime_build_manifest,
)

_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
_LLM_SECRET_NAMES = frozenset(
    name for name in PROVIDER_API_KEY_ENV.values() if name is not None
) | frozenset({
    "AWS_ACCESS_KEY_ID",
    "AWS_BEARER_TOKEN_BEDROCK",
    "AWS_SECRET_ACCESS_KEY",
})
_SOCIAL_SECRET_NAMES = frozenset({"TRUTHSOCIAL_TOKEN", "X_BEARER_TOKEN"})
_DATA_VENDOR_SECRET_NAMES = frozenset({"ALPHA_VANTAGE_API_KEY", "FRED_API_KEY"})
_BROKER_SECRET_NAMES = frozenset({
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "FIDELITY_PASSWORD",
    "FIDELITY_USERNAME",
    "IBKR_PASSWORD",
    "IBKR_USERNAME",
    "ROBINHOOD_PASSWORD",
    "ROBINHOOD_USERNAME",
    "SCHWAB_CLIENT_ID",
    "SCHWAB_CLIENT_SECRET",
    "TRADIER_ACCESS_TOKEN",
})


class FormalRuntimeConfigurationError(ValueError):
    """The running process differs from the formal release configuration."""


def _explicitly_disabled(env: Mapping[str, str], name: str) -> bool:
    raw = env.get(name)
    if not isinstance(raw, str) or raw.strip().lower() not in _FALSE_VALUES:
        raise FormalRuntimeConfigurationError(
            f"{name} must be explicitly disabled for a formal runtime"
        )
    return False


def _secret_is_configured(env: Mapping[str, str], name: str) -> bool:
    value = env.get(name)
    return isinstance(value, str) and bool(value.strip())


def _reject_configured_secrets(
    env: Mapping[str, str], names: frozenset[str], *, role: str
) -> None:
    configured = sorted(name for name in names if _secret_is_configured(env, name))
    if configured:
        raise FormalRuntimeConfigurationError(
            f"{role} runtime contains prohibited credential {configured[0]}"
        )


def _validate_formal_database_environment(env: Mapping[str, str]) -> None:
    if "DATABASE_URL" in env:
        raise FormalRuntimeConfigurationError(
            "legacy DATABASE_URL must be absent from a formal runtime"
        )
    value = env.get("MEDIA_DB_URL")
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise FormalRuntimeConfigurationError(
            "MEDIA_DB_URL must configure formal PostgreSQL"
        )
    scheme = value.split(":", 1)[0].lower()
    if scheme not in {"postgres", "postgresql", "postgresql+psycopg"}:
        raise FormalRuntimeConfigurationError(
            "MEDIA_DB_URL must use a PostgreSQL scheme"
        )


def _validate_collector_release_environment(env: Mapping[str, str]) -> None:
    _validate_formal_database_environment(env)
    _reject_configured_secrets(
        env,
        _LLM_SECRET_NAMES
        | _DATA_VENDOR_SECRET_NAMES
        | _BROKER_SECRET_NAMES
        | frozenset({"TRUTHSOCIAL_TOKEN"}),
        role="collector",
    )


def _validate_paper_secret_scope(
    env: Mapping[str, str], *, role: str, provider: object = None
) -> None:
    if role == "paper_marker":
        _reject_configured_secrets(
            env,
            _LLM_SECRET_NAMES
            | _SOCIAL_SECRET_NAMES
            | _DATA_VENDOR_SECRET_NAMES
            | _BROKER_SECRET_NAMES,
            role="paper marker",
        )
        return

    _reject_configured_secrets(
        env,
        _SOCIAL_SECRET_NAMES | _DATA_VENDOR_SECRET_NAMES | _BROKER_SECRET_NAMES,
        role="paper decision",
    )
    provider_name = provider if isinstance(provider, str) else ""
    required_name = PROVIDER_API_KEY_ENV.get(provider_name.lower())
    if required_name is None or not _secret_is_configured(env, required_name):
        raise FormalRuntimeConfigurationError(
            "paper decision runtime lacks its configured provider credential"
        )
    _reject_configured_secrets(
        env,
        _LLM_SECRET_NAMES - frozenset({required_name}),
        role="paper decision",
    )


def _csv(value: Any, label: str, *, uppercase: bool = False) -> list[str]:
    if not isinstance(value, str):
        raise FormalRuntimeConfigurationError(f"{label} must be comma-separated text")
    items = [item.strip() for item in value.split(",") if item.strip()]
    if uppercase:
        items = [item.upper() for item in items]
    if not items or len(items) != len(set(items)):
        raise FormalRuntimeConfigurationError(f"{label} is empty or contains duplicates")
    return items


def _optional_csv(value: Any, label: str, *, uppercase: bool = False) -> list[str]:
    if value is None or value == "":
        return []
    return _csv(value, label, uppercase=uppercase)


def _environment_integer(
    env: Mapping[str, str], name: str, *, default: str
) -> int:
    raw = env.get(name, default)
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise FormalRuntimeConfigurationError(f"{name} must be an integer") from exc


def _configured_globalnews_slots(macro_themes: Any) -> list[dict[str, str]]:
    if not isinstance(macro_themes, Mapping):
        raise FormalRuntimeConfigurationError("macro themes must be an object")
    slots: list[dict[str, str]] = []
    for theme, specification in macro_themes.items():
        if not isinstance(theme, str) or not theme.strip() or theme != theme.strip():
            raise FormalRuntimeConfigurationError("macro theme names must be canonical")
        if not isinstance(specification, Mapping):
            raise FormalRuntimeConfigurationError("macro theme settings must be objects")
        queries = specification.get("queries")
        if not isinstance(queries, (list, tuple)):
            raise FormalRuntimeConfigurationError("macro theme queries must be a list")
        for query in queries:
            if not isinstance(query, str) or not query.strip() or query != query.strip():
                raise FormalRuntimeConfigurationError(
                    "macro theme queries must be canonical strings"
                )
            slots.append(
                {"provider": "globalnews", "query_key": f"{theme}:{query}"}
            )
    return slots


def collector_component_configuration(
    args: Any,
    *,
    enabled_sources: list[str],
    macro_themes: Mapping[str, Any],
    collector_semantics_id: str,
    env: Mapping[str, str],
    require_release_environment: bool = False,
) -> dict:
    """Build the collector component from its actual parsed runtime state."""
    if require_release_environment:
        _validate_collector_release_environment(env)
    evidence = GLOBAL_EVENT_V2_PROTOCOL["evidence"]
    globalnews_slots = _configured_globalnews_slots(macro_themes)
    globalnews_enabled = bool(getattr(args, "macro", None) is True and globalnews_slots)
    actual_sources = sorted(
        [*enabled_sources, *(["globalnews"] if globalnews_enabled else [])]
    )
    settings = {
        "collector_mode": (
            "formal-global-news-v2"
            if getattr(args, "formal_collector", None) is True
            else None
        ),
        "media_auto_migrate": _explicitly_disabled(env, "MEDIA_AUTO_MIGRATE"),
        "poller_interval_seconds": getattr(args, "interval", None),
        "trading_hours_only": getattr(args, "trading_hours", None),
        "ticker_watchlist": sorted(
            _optional_csv(
                getattr(args, "tickers", None), "collector ticker watchlist", uppercase=True
            )
        ),
        "enabled_sources": actual_sources,
        "globalnews_enabled": globalnews_enabled,
        "globalnews_query_slots": globalnews_slots,
        "globalnews_max_results_per_query": evidence[
            "max_global_news_results_per_query"
        ],
        "globalnews_retry_policy": evidence["query_cycle"][
            "globalnews_exception_retry_policy"
        ],
        "x_enabled": "x" in enabled_sources,
        "x_cycle_interval_seconds": getattr(args, "x_interval", None),
        "x_max_topics": getattr(args, "x_topics", None),
        "x_max_results_per_query": getattr(args, "x_limit", None),
        "paper_heartbeat_max_age_seconds": _environment_integer(
            env, "PAPER_HEARTBEAT_MAX_AGE", default="0"
        ),
        "collector_semantics_id": collector_semantics_id,
    }
    return build_component_configuration("collector", settings)


def _paper_common_settings(args: Any, env: Mapping[str, str]) -> dict[str, Any]:
    return {
        "media_auto_migrate": _explicitly_disabled(env, "MEDIA_AUTO_MIGRATE"),
        "paper_auto_migrate": _explicitly_disabled(env, "PAPER_AUTO_MIGRATE"),
        "run_id": getattr(args, "run_id", None),
        "engine": getattr(args, "engine", None),
        "universe": _csv(getattr(args, "tickers", None), "paper tickers", uppercase=True),
        "benchmark": getattr(args, "benchmark", None),
        "worker_retry_attempts": int(env.get("PAPER_RETRY_ATTEMPTS", "3")),
        "worker_retry_seconds": float(env.get("PAPER_RETRY_SECONDS", "300")),
        "portfolio_mode": getattr(args, "portfolio_mode", None),
        "trading_cost_bps": getattr(args, "cost_bps", None),
        "slippage_bps": getattr(args, "slippage_bps", None),
        "annual_borrow_bps": getattr(args, "annual_borrow_bps", None),
    }


def paper_component_configuration(
    args: Any,
    *,
    role: str,
    decision_semantics_id: str,
    env: Mapping[str, str],
    model_config: Mapping[str, Any] | None = None,
) -> dict:
    """Build a decision or marker component from actual parsed worker state."""
    if role not in {"paper_decision", "paper_marker"}:
        raise FormalRuntimeConfigurationError("paper component role is not allowed")
    _validate_formal_database_environment(env)
    protocol = GLOBAL_EVENT_V2_PROTOCOL
    forecast = protocol["forecast"]
    invocation = forecast["invocation_policy"]
    common = _paper_common_settings(args, env)
    if role == "paper_marker":
        _validate_paper_secret_scope(env, role=role)
        settings = {
            **common,
            "price_vendor": "yfinance",
            "price_capture_delay_minutes": protocol["portfolio"]["price_capture"][
                "scheduled_delay_after_xnys_session_open_minutes"
            ],
            "mark_authority": "durable-release-authorization-only",
        }
        return build_component_configuration(role, settings)

    config = DEFAULT_CONFIG if model_config is None else model_config
    provider = config.get("llm_provider")
    _validate_paper_secret_scope(env, role=role, provider=provider)
    reasoning_key = {
        "openai": "openai_reasoning_effort",
        "google": "google_thinking_level",
        "anthropic": "anthropic_effort",
    }.get(provider)
    settings = {
        **common,
        "analysts": sorted(_csv(getattr(args, "analysts", None), "paper analysts")),
        "global_topics_only": getattr(args, "global_topics_only", None),
        "media_poller_interval_seconds": int(
            env.get("MEDIA_POLLER_INTERVAL", "3600")
        ),
        "llm_provider": provider,
        "requested_model": config.get("quick_think_llm"),
        "allowed_models": sorted(
            _csv(getattr(args, "llm_model_allowlist", None), "LLM model allowlist")
        ),
        "llm_endpoint_class": forecast["endpoint_class"],
        "llm_backend_url": config.get("backend_url"),
        "llm_reasoning_effort": config.get(reasoning_key) if reasoning_key else None,
        "llm_temperature": config.get("temperature"),
        "llm_max_calls_per_decision": getattr(args, "llm_max_calls_per_decision", None),
        "llm_max_calls_per_utc_day": getattr(args, "llm_max_calls_per_utc_day", None),
        "llm_max_prompt_bytes": getattr(args, "llm_max_prompt_bytes", None),
        "llm_max_completion_tokens": getattr(
            args, "llm_max_completion_tokens", None
        ),
        "llm_timeout_seconds": getattr(args, "llm_timeout_seconds", None),
        "llm_sdk_max_retries": int(invocation["sdk_max_retries"]),
        "replicates": getattr(args, "replicates", None),
        "decision_semantics_id": decision_semantics_id,
        "decision_authority": "durable-release-authorization-only",
    }
    return build_component_configuration(role, settings)


def in_image_preflight_identity(
    component_configuration: Mapping[str, Any],
    *,
    env: Mapping[str, str],
    resolved_outcome_semantics_id: str | None = None,
) -> dict:
    """Build non-secret release material inside a paused Fly deployment."""
    component = validate_component_configuration(component_configuration)
    runtime = runtime_build_manifest(env)
    if runtime is None or runtime.get("platform") != "fly":
        raise FormalRuntimeConfigurationError(
            "formal release preflight must run in its Fly deployment"
        )
    role = component["role"]
    outcome_id = None
    if role != "collector":
        outcome_id = resolved_outcome_semantics_id or outcome_semantics_id()
    payload = build_runtime_preflight_payload(
        role=role,
        build_id=content_id(runtime, prefix="build_"),
        component_configuration_id=component["configuration_id"],
        outcome_semantics_id=outcome_id,
    )
    return {
        "component_configuration": component,
        "preflight_payload": payload,
    }


__all__ = [
    "FormalRuntimeConfigurationError",
    "collector_component_configuration",
    "in_image_preflight_identity",
    "paper_component_configuration",
]
