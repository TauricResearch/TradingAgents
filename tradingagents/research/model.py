"""Forecast-model port and the existing structured global-forecast adapter."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from httpx import TransportError
from openai import APIConnectionError, InternalServerError, RateLimitError

from tradingagents.research.contracts import ModelCheckpointSpec
from tradingagents.research.errors import ForecastUnavailableError


@runtime_checkable
class ForecastModel(Protocol):
    def forecast(
        self,
        *,
        checkpoint: ModelCheckpointSpec,
        decision_date: str,
        raw_evidence: Sequence[Mapping[str, Any]],
        universe: Sequence[str],
    ) -> dict[str, Any]: ...


class GlobalForecastModel:
    """Use `global_research` directly, with no tools or live retrieval."""

    def __init__(self, llm: Any):
        self.llm = llm

    def forecast(
        self,
        *,
        checkpoint: ModelCheckpointSpec,
        decision_date: str,
        raw_evidence: Sequence[Mapping[str, Any]],
        universe: Sequence[str],
    ) -> dict[str, Any]:
        from tradingagents.global_research import invoke_global_forecast

        try:
            bundle = invoke_global_forecast(
                llm=self.llm,
                provider=checkpoint.provider,
                requested_model=checkpoint.requested_model,
                decision_date=decision_date,
                rows=[dict(row) for row in raw_evidence],
                universe=list(universe),
            )
        except (
            APIConnectionError,
            InternalServerError,
            RateLimitError,
            TransportError,
        ):
            raise ForecastUnavailableError("forecast provider unavailable") from None
        returned = {
            value.strip()
            for key in ("model_name", "model", "model_id")
            if isinstance((value := bundle.response_metadata.get(key)), str) and value.strip()
        }
        if len(returned) != 1:
            raise ValueError("forecast response requires one exact returned-model identity")
        if returned.pop() not in checkpoint.returned_model_allowlist:
            raise ValueError("forecast provider returned a different model checkpoint")
        return {
            **bundle.as_dict(),
            "checkpoint_id": checkpoint.checkpoint_id,
            "checkpoint_weights_sha256": checkpoint.weights_sha256,
        }


def create_global_forecast_model(checkpoint: ModelCheckpointSpec) -> GlobalForecastModel:
    """Construct the real provider adapter only inside the decision command."""
    from tradingagents.llm_clients.factory import create_llm_client
    from tradingagents.research_protocol import GLOBAL_EVENT_V2_PROTOCOL

    policy = GLOBAL_EVENT_V2_PROTOCOL["forecast"]
    provider = str(policy["provider"])
    if checkpoint.provider != provider \
            or checkpoint.requested_model != policy["requested_model"]:
        raise ValueError("checkpoint differs from the frozen forecast protocol")
    if not set(checkpoint.returned_model_allowlist).issubset(
        set(policy["allowed_returned_models"])
    ):
        raise ValueError("checkpoint returned-model allowlist exceeds the protocol")
    invocation = policy["invocation_policy"]
    kwargs: dict[str, Any] = {
        "max_retries": int(invocation["sdk_max_retries"]),
        "max_completion_tokens": int(invocation["max_completion_tokens"]),
    }
    if policy.get("temperature") is not None:
        kwargs["temperature"] = policy["temperature"]
    if provider == "openai" and policy.get("reasoning_effort"):
        kwargs["reasoning_effort"] = policy["reasoning_effort"]
    elif provider == "google" and policy.get("reasoning_effort"):
        kwargs["thinking_level"] = policy["reasoning_effort"]
    elif provider == "anthropic" and policy.get("reasoning_effort"):
        kwargs["effort"] = policy["reasoning_effort"]
    client = create_llm_client(
        provider=provider,
        model=checkpoint.requested_model,
        base_url=policy.get("backend_url"),
        **kwargs,
    )
    return GlobalForecastModel(client.get_llm())
