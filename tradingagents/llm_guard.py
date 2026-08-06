"""Fail-closed model and reservation-request policy for formal LLM decisions.

The worker may validate the requested model and bounded request shape, but it
never chooses a budget bucket or a call ceiling.  ``PaperStore`` obtains those
values from the immutable registered run and protocol, and PostgreSQL chooses
the UTC day from its own clock while reserving the durable counters.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


class LLMPolicyError(ValueError):
    """Raised when a model or policy is not explicitly authorized."""


class LLMCallBudgetExceeded(LLMPolicyError):
    """Raised before an LLM call that would exceed a persistent budget."""


def model_key(provider: str, model: str) -> str:
    """Canonical policy key; provider names are case-insensitive, model IDs are not."""
    normalized_provider = str(provider).strip().lower()
    normalized_model = str(model).strip()
    if not normalized_provider or not normalized_model:
        raise LLMPolicyError("LLM provider and model must both be non-empty")
    return f"{normalized_provider}:{normalized_model}"


@dataclass(frozen=True)
class LLMCallPolicy:
    """Exact model allowlist plus hard high-level invocation ceilings."""

    allowed_models: frozenset[str]
    max_calls_per_decision: int
    max_calls_per_utc_day: int

    @classmethod
    def from_values(
        cls,
        allowlist: str | Iterable[str] | None,
        max_calls_per_decision: int | None,
        max_calls_per_utc_day: int | None,
    ) -> LLMCallPolicy:
        entries = allowlist.split(",") if isinstance(allowlist, str) else allowlist
        if entries is None:
            raise LLMPolicyError("an explicit LLM model allowlist is required")
        allowed = set()
        for raw in entries:
            entry = str(raw).strip()
            if not entry:
                continue
            provider, separator, model = entry.partition(":")
            if not separator:
                raise LLMPolicyError(
                    f"invalid allowlist entry {entry!r}; expected provider:model"
                )
            allowed.add(model_key(provider, model))
        if not allowed:
            raise LLMPolicyError("the LLM model allowlist must not be empty")
        for name, value in (
            ("per-decision", max_calls_per_decision),
            ("per-UTC-day", max_calls_per_utc_day),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise LLMPolicyError(f"the {name} LLM call budget must be a non-negative integer")
        return cls(
            allowed_models=frozenset(allowed),
            max_calls_per_decision=max_calls_per_decision,
            max_calls_per_utc_day=max_calls_per_utc_day,
        )

    def require_model(self, provider: str, model: str) -> str:
        identity = model_key(provider, model)
        if identity not in self.allowed_models:
            raise LLMPolicyError(f"LLM model {identity!r} is not in the explicit allowlist")
        return identity

    def manifest(self) -> dict:
        """Stable, JSON-compatible policy recorded in the immutable run config."""
        return {
            "allowed_models": sorted(self.allowed_models),
            "max_calls_per_decision": self.max_calls_per_decision,
            "max_calls_per_utc_day": self.max_calls_per_utc_day,
        }


class PersistentLLMCallGuard:
    """Build a bounded request for an atomic, database-owned reservation."""

    def __init__(
        self,
        policy: LLMCallPolicy,
        *,
        scope: str,
        run_id: str,
        decision_date: str,
    ):
        for name, value in (
            ("scope", scope), ("run_id", run_id), ("decision_date", decision_date)
        ):
            if not str(value).strip():
                raise LLMPolicyError(f"LLM budget {name} must be non-empty")
        self.policy = policy
        self.scope = str(scope)
        self.run_id = str(run_id)
        self.decision_date = str(decision_date)

    def reservation_spec(
        self,
        provider: str,
        requested_model: str,
        *,
        decision_date: str,
        stage: str,
        input_bundle_id: str,
        prompt_id: str,
        prompt_bytes: int,
        max_prompt_bytes: int,
        max_completion_tokens: int,
    ) -> dict:
        """Build the exact request for an atomic counter/receipt reservation."""
        self.policy.require_model(provider, requested_model)
        if decision_date != self.decision_date:
            raise LLMPolicyError("LLM reservation decision date differs from its guard")
        for name, value in (
            ("stage", stage),
            ("input bundle ID", input_bundle_id),
            ("prompt ID", prompt_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise LLMPolicyError(f"LLM reservation {name} must be non-empty")
        for name, value in (
            ("prompt bytes", prompt_bytes),
            ("prompt byte ceiling", max_prompt_bytes),
            ("completion-token ceiling", max_completion_tokens),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise LLMPolicyError(f"LLM reservation {name} must be a positive integer")
        if prompt_bytes > max_prompt_bytes:
            raise LLMPolicyError("LLM reservation prompt exceeds its byte ceiling")
        return {
            "scope": self.scope,
            "run_id": self.run_id,
            "decision_date": self.decision_date,
            "stage": stage,
            "provider": provider,
            "requested_model": requested_model,
            "input_bundle_id": input_bundle_id,
            "prompt_id": prompt_id,
            "prompt_bytes": prompt_bytes,
            "max_prompt_bytes": max_prompt_bytes,
            "max_completion_tokens": max_completion_tokens,
        }

    def require_returned_model(
        self,
        provider: str,
        requested_model: str,
        response_metadata: dict | None,
    ) -> str:
        """Reject silent provider-side model substitution after a charged call."""
        metadata = response_metadata or {}
        returned_values = {
            value.strip()
            for key in ("model_name", "model", "model_id")
            if isinstance((value := metadata.get(key)), str) and value.strip()
        }
        if not returned_values:
            raise LLMPolicyError(
                "LLM response omitted an explicit returned-model identity"
            )
        if len(returned_values) != 1:
            raise LLMPolicyError(
                "LLM response contained conflicting returned-model identities"
            )
        returned = returned_values.pop()
        try:
            return self.policy.require_model(provider, returned)
        except LLMPolicyError as exc:
            requested = model_key(provider, requested_model)
            actual = model_key(provider, returned)
            raise LLMPolicyError(
                f"LLM returned unallowlisted model {actual!r} for request {requested!r}"
            ) from exc
