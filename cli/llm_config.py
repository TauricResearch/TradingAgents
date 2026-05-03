"""Resolve LLM configuration from CLI overrides and environment variables."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class LLMConfigOverrides:
    provider: str | None = None
    quick_model: str | None = None
    deep_model: str | None = None
    backend_url: str | None = None
    openai_reasoning_effort: str | None = None
    google_thinking_level: str | None = None
    anthropic_effort: str | None = None


@dataclass(frozen=True)
class ResolvedLLMConfig:
    provider: str | None = None
    quick_model: str | None = None
    deep_model: str | None = None
    backend_url: str | None = None
    openai_reasoning_effort: str | None = None
    google_thinking_level: str | None = None
    anthropic_effort: str | None = None

    @property
    def is_complete(self) -> bool:
        return bool(self.provider and self.quick_model and self.deep_model)


_ENV_VARS = {
    "provider": "TRADINGAGENTS_LLM_PROVIDER",
    "quick_model": "TRADINGAGENTS_QUICK_MODEL",
    "deep_model": "TRADINGAGENTS_DEEP_MODEL",
    "backend_url": "TRADINGAGENTS_BACKEND_URL",
    "openai_reasoning_effort": "TRADINGAGENTS_OPENAI_REASONING_EFFORT",
    "google_thinking_level": "TRADINGAGENTS_GOOGLE_THINKING_LEVEL",
    "anthropic_effort": "TRADINGAGENTS_ANTHROPIC_EFFORT",
}


def resolve_llm_config(overrides: LLMConfigOverrides | None = None) -> ResolvedLLMConfig:
    overrides = overrides or LLMConfigOverrides()

    values = {
        field: _first_present(getattr(overrides, field), os.environ.get(env_var))
        for field, env_var in _ENV_VARS.items()
    }
    if values["provider"] is not None:
        values["provider"] = values["provider"].lower()

    return ResolvedLLMConfig(**values)


def _first_present(*values: str | None) -> str | None:
    for value in values:
        normalized = _blank_to_none(value)
        if normalized is not None:
            return normalized
    return None


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None

    stripped = value.strip()
    if not stripped:
        return None

    return stripped
