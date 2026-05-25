from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import logging
import warnings

logger = logging.getLogger(__name__)


# --- Determinism: T0.1 / T0.2 ---
# Reasoning models reject temperature != 1 (OpenAI o-series, GPT-5 with
# reasoning_effort; Anthropic claude-opus-4+ with effort=high enabled).
# When the caller has activated a reasoning/thinking mode for one of these
# models, we silently skip the temperature pin and let provider defaults
# apply, since pinning would 400 the request. The audit trail still records
# the effective parameters via the trace callback (T0.5 / T1.2).
_REASONING_KWARGS = ("reasoning_effort", "effort", "thinking_level", "thinking_budget")


def supports_temperature_pin(model: str, llm_kwargs: Dict[str, Any]) -> bool:
    """Return False when the model+kwargs combination would reject temperature."""
    model_lc = (model or "").lower()
    # GPT-5 family with the Responses API + reasoning_effort rejects
    # temperature overrides — and reasoning_effort is the only path the
    # framework currently exposes for it (#openai_reasoning_effort in
    # default_config).
    if any(k in llm_kwargs and llm_kwargs[k] for k in _REASONING_KWARGS):
        return False
    # Claude opus/sonnet with explicit effort: extended-thinking mode does
    # not accept non-default temperature.
    if "effort" in llm_kwargs and llm_kwargs["effort"]:
        return False
    return True


def apply_determinism_kwargs(
    llm_kwargs: Dict[str, Any],
    model: str,
    temperature: Optional[float],
    seed: Optional[int],
    provider: str,
) -> Dict[str, Any]:
    """Inject deterministic generation kwargs unless they'd be rejected.

    Mutates and returns ``llm_kwargs``. Skips temperature when a reasoning
    mode is active for the model (would cause a 400). Logs at INFO so the
    audit trail records the decision. ``provider`` controls which extra
    knobs are added (e.g. ``top_p`` for Anthropic, ``top_k`` for Google).
    """
    if temperature is not None and "temperature" not in llm_kwargs:
        if supports_temperature_pin(model, llm_kwargs):
            llm_kwargs["temperature"] = temperature
        else:
            logger.info(
                "Skipping temperature pin for %s: reasoning/thinking mode active. "
                "Reproducibility relies on seed (if supported) and prompt/data snapshots.",
                model,
            )
    # Seed: OpenAI Chat Completions + Responses API accept seed; xAI, DeepSeek,
    # OpenRouter inherit via the OpenAI-compatible interface. Anthropic and
    # Google currently do not expose a public seed param, so we no-op for them.
    if seed is not None and "seed" not in llm_kwargs and provider in (
        "openai", "xai", "deepseek", "openrouter", "ollama", "qwen", "qwen-cn",
        "glm", "glm-cn", "minimax", "minimax-cn",
    ):
        llm_kwargs["seed"] = seed
    # Provider-specific sampling-narrowing knobs.  Setting top_p=1 / top_k=1
    # is a no-op when temperature=0 but defends against providers that
    # silently ignore temperature.
    if provider == "google":
        llm_kwargs.setdefault("top_p", 1.0)
        llm_kwargs.setdefault("top_k", 1)
    return llm_kwargs


def normalize_content(response):
    """Normalize LLM response content to a plain string.

    Multiple providers (OpenAI Responses API, Google Gemini 3) return content
    as a list of typed blocks, e.g. [{'type': 'reasoning', ...}, {'type': 'text', 'text': '...'}].
    Downstream agents expect response.content to be a string. This extracts
    and joins the text blocks, discarding reasoning/metadata blocks.
    """
    content = response.content
    if isinstance(content, list):
        texts = [
            item.get("text", "") if isinstance(item, dict) and item.get("type") == "text"
            else item if isinstance(item, str) else ""
            for item in content
        ]
        response.content = "\n".join(t for t in texts if t)
    return response


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        self.model = model
        self.base_url = base_url
        self.kwargs = kwargs

    def get_provider_name(self) -> str:
        """Return the provider name used in warning messages."""
        provider = getattr(self, "provider", None)
        if provider:
            return str(provider)
        return self.__class__.__name__.removesuffix("Client").lower()

    def warn_if_unknown_model(self) -> None:
        """Warn when the model is outside the known list for the provider."""
        if self.validate_model():
            return

        warnings.warn(
            (
                f"Model '{self.model}' is not in the known model list for "
                f"provider '{self.get_provider_name()}'. Continuing anyway."
            ),
            RuntimeWarning,
            stacklevel=2,
        )

    @abstractmethod
    def get_llm(self) -> Any:
        """Return the configured LLM instance."""
        pass

    @abstractmethod
    def validate_model(self) -> bool:
        """Validate that the model is supported by this client."""
        pass
