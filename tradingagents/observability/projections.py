"""Truthful, versioned role-input projections for the 13 graph actors."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from tradingagents.observability.canonical import canonical_sha256
from tradingagents.observability.redaction import redact_recursive
from tradingagents.observability.roles import ROLES_BY_ACTOR_ID


ROLE_INPUT_PROJECTION_VERSION = 1
EVIDENCE_CONFIG_WHITELIST_VERSION = 1


@dataclass(frozen=True)
class RoleProjectionRunContext:
    """Immutable run information shared by every role projection."""

    effective_config: Mapping[str, Any]
    effective_config_artifact_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "effective_config",
            MappingProxyType(deepcopy(dict(self.effective_config))),
        )


@dataclass(frozen=True)
class RoleInputProjectionV1:
    actor_id: str
    node_id: str
    state_fields: dict[str, Any]
    effective_config_artifact_id: str | None
    projection_version: int = ROLE_INPUT_PROJECTION_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "projection_version": self.projection_version,
            "actor_id": self.actor_id,
            "node_id": self.node_id,
            "state_fields": self.state_fields,
            "effective_config_artifact_id": self.effective_config_artifact_id,
        }


@dataclass(frozen=True)
class EvidenceConfigSnapshotV1:
    values: dict[str, Any]
    sha256: str
    redaction_manifest: tuple[str, ...] = ()
    whitelist_version: int = EVIDENCE_CONFIG_WHITELIST_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "whitelist_version": self.whitelist_version,
            "values": self.values,
            "sha256": self.sha256,
            "redaction_manifest": list(self.redaction_manifest),
        }


class EvidenceConfigDrift(RuntimeError):
    def __init__(
        self,
        *,
        expected_sha256: str,
        actual_sha256: str,
        differing_keys: tuple[str, ...],
    ):
        self.expected_sha256 = expected_sha256
        self.actual_sha256 = actual_sha256
        self.differing_keys = differing_keys
        joined = ", ".join(differing_keys) or "unknown"
        super().__init__(f"evidence configuration drift: {joined}")


_INSTRUMENT_FIELDS = (
    "company_of_interest",
    "instrument_context",
    "asset_type",
)
_FOUR_REPORTS = (
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
)


ROLE_STATE_FIELDS: dict[str, tuple[str, ...]] = {
    "analyst.market": (*_INSTRUMENT_FIELDS, "trade_date", "messages"),
    "analyst.sentiment": (*_INSTRUMENT_FIELDS, "trade_date", "messages"),
    "analyst.news": (*_INSTRUMENT_FIELDS, "trade_date", "messages"),
    "analyst.fundamentals": (*_INSTRUMENT_FIELDS, "trade_date", "messages"),
    "evidence.steward": (
        "company_of_interest",
        "canonical_company_profile",
        "trade_date",
        *_FOUR_REPORTS,
    ),
    "researcher.bull": (
        *_INSTRUMENT_FIELDS,
        *_FOUR_REPORTS,
        "investment_debate_state",
    ),
    "researcher.bear": (
        *_INSTRUMENT_FIELDS,
        *_FOUR_REPORTS,
        "investment_debate_state",
    ),
    "manager.research": (*_INSTRUMENT_FIELDS, "investment_debate_state"),
    "trader": (*_INSTRUMENT_FIELDS, "investment_plan"),
    "risk.aggressive": (
        *_INSTRUMENT_FIELDS,
        *_FOUR_REPORTS,
        "trader_investment_plan",
        "risk_debate_state",
    ),
    "risk.neutral": (
        *_INSTRUMENT_FIELDS,
        *_FOUR_REPORTS,
        "trader_investment_plan",
        "risk_debate_state",
    ),
    "risk.conservative": (
        *_INSTRUMENT_FIELDS,
        *_FOUR_REPORTS,
        "trader_investment_plan",
        "risk_debate_state",
    ),
    "manager.portfolio": (
        *_INSTRUMENT_FIELDS,
        "risk_debate_state",
        "investment_plan",
        "trader_investment_plan",
        "past_context",
    ),
}

_INVEST_DEBATE_FIELDS = {
    "researcher.bull": ("history", "bull_history", "bear_history", "current_response", "count"),
    "researcher.bear": ("history", "bear_history", "bull_history", "current_response", "count"),
    "manager.research": ("history", "bear_history", "bull_history", "count"),
}
_RISK_DEBATE_FIELDS = {
    "risk.aggressive": (
        "history",
        "aggressive_history",
        "conservative_history",
        "neutral_history",
        "current_conservative_response",
        "current_neutral_response",
        "count",
    ),
    "risk.neutral": (
        "history",
        "neutral_history",
        "aggressive_history",
        "conservative_history",
        "current_aggressive_response",
        "current_conservative_response",
        "count",
    ),
    "risk.conservative": (
        "history",
        "conservative_history",
        "aggressive_history",
        "neutral_history",
        "current_aggressive_response",
        "current_neutral_response",
        "count",
    ),
    "manager.portfolio": (
        "history",
        "aggressive_history",
        "conservative_history",
        "neutral_history",
        "current_aggressive_response",
        "current_conservative_response",
        "current_neutral_response",
        "count",
    ),
}


EVIDENCE_CONFIG_FIELDS: tuple[str, ...] = (
    "evidence_gate_enabled",
    "evidence_max_enrichment_rounds",
    "evidence_max_enrichment_seconds",
    "news_min_company_items",
    "news_min_mixed_items",
    "evidence_stop_on_fail",
    "credibility_enabled",
    "credibility_domain_overrides",
    "consistency_enabled",
    "news_advisor_enabled",
    "wrong_identity_hints",
    "news_article_limit",
    "global_news_article_limit",
    "global_news_lookback_days",
    "global_news_queries",
    "news_curator_max_items",
    "data_vendors",
    "tool_vendors",
    "halt_on_missing_data",
    "llm_provider",
    "quick_think_llm",
    "deep_think_llm",
    "backend_url",
    "google_thinking_level",
    "openai_reasoning_effort",
    "anthropic_effort",
    "temperature",
    "llm_max_retries",
    "output_language",
)


def project_role_input(
    actor_id: str,
    state: Mapping[str, Any],
    run_context: RoleProjectionRunContext,
) -> RoleInputProjectionV1:
    role = ROLES_BY_ACTOR_ID[actor_id]
    if actor_id not in ROLE_STATE_FIELDS:
        raise KeyError(f"unknown role projection: {actor_id}")
    return RoleInputProjectionV1(
        actor_id=actor_id,
        node_id=role.node_id,
        state_fields=_project_state_fields(actor_id, state),
        effective_config_artifact_id=run_context.effective_config_artifact_id,
    )


def _project_state_fields(actor_id: str, state: Mapping[str, Any]) -> dict[str, Any]:
    instrument = _project_instrument_context(
        state,
        company_required=actor_id in {"analyst.sentiment", "trader"},
        asset_required=actor_id in {
            "analyst.news",
            "researcher.bull",
            "researcher.bear",
        },
    )
    if actor_id.startswith("analyst."):
        projected = dict(instrument)
        if actor_id in {"analyst.sentiment", "trader"}:
            projected["company_of_interest"] = state.get("company_of_interest")
        if actor_id == "analyst.news":
            projected["asset_type"] = state.get("asset_type", "stock")
        projected["trade_date"] = state.get("trade_date")
        projected["messages"] = state.get("messages")
        return projected
    if actor_id == "evidence.steward":
        return {
            "company_of_interest": state.get("company_of_interest"),
            "canonical_company_profile": state.get("canonical_company_profile"),
            "trade_date": state.get("trade_date"),
            **{name: state.get(name) for name in _FOUR_REPORTS},
        }
    if actor_id in _INVEST_DEBATE_FIELDS:
        projected = dict(instrument)
        if actor_id in {"researcher.bull", "researcher.bear"}:
            projected["asset_type"] = state.get("asset_type", "stock")
            projected.update({name: state.get(name) for name in _FOUR_REPORTS})
        projected["investment_debate_state"] = _project_nested(
            state.get("investment_debate_state"),
            _INVEST_DEBATE_FIELDS[actor_id],
        )
        return projected
    if actor_id == "trader":
        return {
            **instrument,
            "company_of_interest": state.get("company_of_interest"),
            "investment_plan": state.get("investment_plan"),
        }
    if actor_id in _RISK_DEBATE_FIELDS:
        projected = dict(instrument)
        if actor_id.startswith("risk."):
            projected.update({name: state.get(name) for name in _FOUR_REPORTS})
            projected["trader_investment_plan"] = state.get("trader_investment_plan")
        else:
            projected["investment_plan"] = state.get("investment_plan")
            projected["trader_investment_plan"] = state.get("trader_investment_plan")
            projected["past_context"] = state.get("past_context", "")
        projected["risk_debate_state"] = _project_nested(
            state.get("risk_debate_state"),
            _RISK_DEBATE_FIELDS[actor_id],
        )
        return projected
    raise KeyError(f"unknown role projection: {actor_id}")


def _project_instrument_context(
    state: Mapping[str, Any],
    *,
    company_required: bool,
    asset_required: bool,
) -> dict[str, Any]:
    instrument_context = state.get("instrument_context")
    projected = {"instrument_context": instrument_context}
    if not instrument_context:
        if not company_required:
            projected["company_of_interest"] = state.get("company_of_interest")
        if not asset_required:
            projected["asset_type"] = state.get("asset_type", "stock")
    return projected


def _project_nested(value: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    return {name: source.get(name) for name in fields}


def evidence_config_snapshot(config: Mapping[str, Any]) -> EvidenceConfigSnapshotV1:
    normalized = {_normalize_key(str(key)): value for key, value in config.items()}
    values = {name: normalized.get(name) for name in EVIDENCE_CONFIG_FIELDS}
    values["backend_url"] = _normalize_backend_url(values["backend_url"])
    for name in sorted(normalized):
        if name.startswith("tavily_"):
            values[name] = normalized[name]
    redacted = redact_recursive(values)
    safe_values = dict(redacted.value)
    document = {
        "whitelist_version": EVIDENCE_CONFIG_WHITELIST_VERSION,
        "values": safe_values,
    }
    return EvidenceConfigSnapshotV1(
        values=safe_values,
        sha256=canonical_sha256(document),
        redaction_manifest=tuple(record.path for record in redacted.manifest),
    )


def assert_evidence_config_matches(
    expected_config: Mapping[str, Any],
    actual_config: Mapping[str, Any],
) -> tuple[EvidenceConfigSnapshotV1, EvidenceConfigSnapshotV1]:
    expected = evidence_config_snapshot(expected_config)
    actual = evidence_config_snapshot(actual_config)
    if expected.sha256 != actual.sha256:
        keys = set(expected.values) | set(actual.values)
        differing = tuple(
            sorted(key for key in keys if expected.values.get(key) != actual.values.get(key))
        )
        raise EvidenceConfigDrift(
            expected_sha256=expected.sha256,
            actual_sha256=actual.sha256,
            differing_keys=differing,
        )
    return expected, actual


def _normalize_key(key: str) -> str:
    return key.strip().lower().replace("-", "_").replace(" ", "_")


def _normalize_backend_url(value: Any) -> str | None:
    if value is None or value == "":
        return None
    parsed = urlsplit(str(value).strip())
    if not parsed.scheme and not parsed.netloc:
        return str(value).strip().rstrip("/")
    hostname = (parsed.hostname or "").lower()
    port = f":{parsed.port}" if parsed.port is not None else ""
    netloc = f"{hostname}{port}"
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))
