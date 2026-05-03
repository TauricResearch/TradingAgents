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

    cli_provider = _normalize_provider(overrides.provider)
    env_provider = _normalize_provider(os.environ.get(_ENV_VARS["provider"]))
    provider = cli_provider or env_provider
    use_env_provider_config = bool(env_provider and provider == env_provider)

    values = {"provider": provider}
    for field, env_var in _ENV_VARS.items():
        if field == "provider":
            continue
        env_value = os.environ.get(env_var) if use_env_provider_config else None
        values[field] = _first_present(getattr(overrides, field), env_value)

    return ResolvedLLMConfig(**values)


def _normalize_provider(value: str | None) -> str | None:
    normalized = _blank_to_none(value)
    return normalized.lower() if normalized is not None else None


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
