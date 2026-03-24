import json
import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model


class NormalizedChatOpenAI(ChatOpenAI):
    """ChatOpenAI with normalized content output.

    The Responses API returns content as a list of typed blocks
    (reasoning, text, etc.). This normalizes to string for consistent
    downstream handling.
    """

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))

# Kwargs forwarded from user config to ChatOpenAI
_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "reasoning_effort",
    "api_key", "callbacks", "http_client", "http_async_client",
)

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.json"


def _load_config() -> dict:
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
            config = json.load(config_file)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Config file not found: {CONFIG_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in config file: {CONFIG_PATH}") from exc
    except OSError as exc:
        raise RuntimeError(f"Unable to read config file: {CONFIG_PATH}") from exc

    if not isinstance(config, dict):
        raise RuntimeError(f"Invalid config format in file: {CONFIG_PATH}")
    return config


def _get_base_urls(config: dict) -> dict[str, str]:
    base_urls = config.get("BASE_URLS")
    if not isinstance(base_urls, list):
        raise RuntimeError(f"Invalid or missing 'BASE_URLS' in config file: {CONFIG_PATH}")

    mapped_urls: dict[str, str] = {}
    for item in base_urls:
        if (
            isinstance(item, list)
            and len(item) == 2
            and isinstance(item[0], str)
            and isinstance(item[1], str)
        ):
            mapped_urls[item[0].lower()] = item[1]
    return mapped_urls


CONFIG = _load_config()

load_dotenv()

_BASE_URLS = _get_base_urls(CONFIG)
_PROVIDER_BASE_URLS = {
    "xai": _BASE_URLS.get("xai", "https://api.x.ai/v1"),
    "openrouter": _BASE_URLS.get("openrouter", "https://openrouter.ai/api/v1"),
    "ollama": _BASE_URLS.get("ollama", "http://localhost:11434/v1"),
}
_PROVIDER_API_KEY_ENV = {
    "xai": "XAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


class OpenAIClient(BaseLLMClient):
    """Client for OpenAI, Ollama, OpenRouter, and xAI providers.

    For native OpenAI models, uses the Responses API (/v1/responses) which
    supports reasoning_effort with function tools across all model families
    (GPT-4.1, GPT-5). Third-party compatible providers (xAI, OpenRouter,
    Ollama) use standard Chat Completions.
    """

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        provider: str = "openai",
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = provider.lower()

    def get_llm(self) -> Any:
        """Return configured ChatOpenAI instance."""
        llm_kwargs: dict[str, Any] = {"model": self.model}

        # Provider-specific base URL and auth
        if self.provider in _PROVIDER_BASE_URLS:
            base_url = _PROVIDER_BASE_URLS[self.provider]
            llm_kwargs["base_url"] = base_url
            api_key_env = _PROVIDER_API_KEY_ENV.get(self.provider)
            if api_key_env:
                api_key = os.environ.get(api_key_env)
                if api_key:
                    llm_kwargs["api_key"] = api_key
            elif self.provider == "ollama":
                llm_kwargs["api_key"] = "ollama"
        elif self.base_url:
            llm_kwargs["base_url"] = self.base_url

        # Forward user-provided kwargs
        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        # Native OpenAI: use Responses API for consistent behavior across
        # all model families. Third-party providers use Chat Completions.
        if self.provider == "openai":
            llm_kwargs["use_responses_api"] = True

        return NormalizedChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for the provider."""
        return validate_model(self.provider, self.model)
