"""OpenCode Go metadata and model-aware client (SDK imports stay lazy).

Endpoint source: https://opencode.ai/docs/go/#endpoints (2026-09-27).
Go is not a single OpenAI-compatible API: different models use Chat
Completions, Responses, or Anthropic Messages.
"""

import os
from importlib.metadata import PackageNotFoundError, version
from urllib.parse import urlsplit
from uuid import uuid4

from .api_key_env import get_api_key_env
from .base_client import BaseLLMClient
from .headers import parse_llm_headers

GO_BASE_URL = "https://opencode.ai/zen/go/v1"
GO_APIS = frozenset({"chat_completions", "responses", "messages"})
GO_MODEL_APIS = {
    **dict.fromkeys((
        "glm-5.3-flash", "glm-5.3", "glm-5.2", "glm-5.1",
        "kimi-k3", "kimi-k2.7-code", "kimi-k2.6", "longcat-2.0",
        "deepseek-v4.1-flash", "deepseek-v4-pro", "deepseek-v4-flash",
        "deepseek-v4-flash-vision-exp", "mimo-v2.6-flash", "mimo-v2.6-pro",
        "mimo-v2.5", "mimo-v2.5-pro", "hy4-preview", "hy3",
        "space-bunny-free", "longcat-2.5-preview-free",
    ), "chat_completions"),
    **dict.fromkeys((
        "grok-4.7", "grok-4.6", "gpt-6-luna", "gpt-5.6-luna",
        "muse-spark-1.3-contributor", "muse-spark-1.2-contributor",
    ), "responses"),
    **dict.fromkeys((
        "minimax-m3", "minimax-m2.7", "minimax-m2.5", "qwen3.8-max",
        "qwen3.8-flash", "qwen3.7-max", "qwen3.7-plus", "qwen3.6-plus",
    ), "messages"),
}

GO_MODEL_OPTIONS = {
    "quick": [
        ("GLM-5.3-Flash (Chat Completions)", "glm-5.3-flash"),
        ("MiMo-V2.6-Flash (Chat Completions)", "mimo-v2.6-flash"),
        ("GPT-6 Luna (Responses)", "gpt-6-luna"),
        ("Qwen3.8 Flash (Messages)", "qwen3.8-flash"),
        ("MiniMax M3 (Messages)", "minimax-m3"),
        ("Custom model ID", "custom"),
    ],
    "deep": [
        ("Kimi K3 (Chat Completions)", "kimi-k3"),
        ("GLM-5.3 (Chat Completions)", "glm-5.3"),
        ("DeepSeek V4 Pro (Chat Completions)", "deepseek-v4-pro"),
        ("Qwen3.8 Max (Messages)", "qwen3.8-max"),
        ("Grok 4.7 (Responses)", "grok-4.7"),
        ("Custom model ID", "custom"),
    ],
}


def normalize_go_model(model: str) -> str:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("OpenCode Go requires a nonempty model ID")
    model = model.strip().removeprefix("opencode-go/")
    if not model:
        raise ValueError("OpenCode Go requires a nonempty model ID")
    # Official Go IDs are lowercase, unlike some direct-provider IDs.
    return model.lower() if model.lower() in GO_MODEL_APIS else model


def resolve_go_api(model: str, api: str = "auto") -> str:
    if not isinstance(api, str) or api not in GO_APIS | {"auto"}:
        raise ValueError("opencode_go_api must be auto, chat_completions, responses or messages")
    if api != "auto":
        return api
    model = normalize_go_model(model)
    if model not in GO_MODEL_APIS:
        raise ValueError(
            "Unknown OpenCode Go model protocol. Set opencode_go_api / "
            "TRADINGAGENTS_OPENCODE_GO_API explicitly for a new or custom model."
        )
    return GO_MODEL_APIS[model]


def resolve_go_base_url(base_url: str | None, api: str) -> str:
    """Accept the shared /v1 base; Anthropic's SDK appends /v1/messages itself."""
    if api not in GO_APIS:
        raise ValueError("Invalid OpenCode Go API protocol")
    base = (base_url or GO_BASE_URL).rstrip("/")
    parsed = urlsplit(base)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise ValueError("OpenCode Go backend_url must be an HTTP(S) base URL without credentials, query or fragment")
    if parsed.path.endswith(("/messages", "/responses", "/chat/completions")):
        raise ValueError("OpenCode Go backend_url must be the API base, not a complete request endpoint")
    return base.removesuffix("/v1") if api == "messages" else base


def _user_agent() -> str:
    try:
        release = version("tradingagents")
    except PackageNotFoundError:
        release = "source"
    return f"TradingAgents/{release}"


class OpenCodeGoClient(BaseLLMClient):
    """Native Go adapter. Each instance owns a stable default session ID.

    Deep and quick clients get independent IDs by default. For checkpoint
    resume across processes, supply a persisted x-opencode-session header.
    No OpenAI/Anthropic account key is used as a fallback for a missing Go key.
    """

    provider = "opencode-go"

    def __init__(self, model: str, base_url: str | None = None, *, api="auto", **kwargs):
        super().__init__(normalize_go_model(model), base_url, **kwargs)
        self.api = resolve_go_api(self.model, api)
        self.base_url = resolve_go_base_url(base_url, self.api)
        self.default_headers = {
            "User-Agent": _user_agent(),
            "x-opencode-session": str(uuid4()),
        }
        # Canonicalize Go's two headers while merging so differently-cased
        # overrides don't accidentally leave duplicate User-Agent/session values.
        canonical = {"user-agent": "User-Agent", "x-opencode-session": "x-opencode-session"}
        for name, value in parse_llm_headers(kwargs.get("default_headers")).items():
            self.default_headers[canonical.get(name.lower(), name)] = value
        for name in ("User-Agent", "x-opencode-session"):
            if not self.default_headers[name].strip():
                raise ValueError(f"OpenCode Go requires a nonempty {name} header")

    def validate_model(self) -> bool:
        # Explicit protocol selection is the supported escape hatch for new IDs.
        return self.api in GO_APIS

    def get_llm(self):
        env_var = get_api_key_env(self.provider)
        api_key = self.kwargs.get("api_key") or os.environ.get(env_var or "")
        if not api_key:
            raise ValueError("Set OPENCODE_GO_API_KEY or pass api_key for OpenCode Go")
        common = {
            key: self.kwargs[key]
            for key in ("timeout", "max_retries", "temperature", "max_tokens",
                        "callbacks", "http_client", "http_async_client")
            if key in self.kwargs
        }
        common.update(model=self.model, base_url=self.base_url, api_key=api_key,
                      default_headers=dict(self.default_headers))
        if self.api == "messages":
            from .anthropic_client import NormalizedChatAnthropic
            return NormalizedChatAnthropic(**common)

        from .openai_client import (
            DeepSeekChatOpenAI,
            NormalizedChatOpenAI,
            _supports_reasoning_effort,
        )
        if self.api == "responses":
            common["use_responses_api"] = True
            if _supports_reasoning_effort(self.model) and self.kwargs.get("reasoning_effort"):
                common["reasoning_effort"] = self.kwargs["reasoning_effort"]
            return NormalizedChatOpenAI(**common)
        # Explicit False also prevents model-name inference from selecting
        # Responses when a user chooses a custom Chat Completions deployment.
        common["use_responses_api"] = False
        chat_class = DeepSeekChatOpenAI if self.model.startswith("deepseek-") else NormalizedChatOpenAI
        return chat_class(**common)
