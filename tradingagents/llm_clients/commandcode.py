"""Command Code Provider API metadata and model-aware adapter.

Sources (verified 2026-10-04):
https://commandcode.ai/docs/provider
https://api.commandcode.ai/provider/v1/models
https://github.com/CommandCodeAI/pi-commandcode-provider

The catalog is a verified offline snapshot, not a guess from a model's name.
New/custom IDs require an explicit protocol until this snapshot is refreshed.
SDK imports stay lazy so the CLI can configure a provider without its key.
"""

import os
from urllib.parse import urlsplit

from .api_key_env import get_api_key_env
from .base_client import BaseLLMClient
from .headers import parse_llm_headers

COMMANDCODE_BASE_URL = "https://api.commandcode.ai/provider/v1"
COMMANDCODE_APIS = frozenset({"chat_completions", "responses", "messages"})

# Exact Provider API IDs and supported routes, including case and date suffixes.
COMMANDCODE_MODEL_ENDPOINTS = {
    **dict.fromkeys((
        "claude-sonnet-5-5",
        "claude-sonnet-5",
        "claude-sonnet-4-6",
        "claude-fable-5-1",
        "claude-fable-5",
        "claude-opus-5-5",
        "claude-opus-5",
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-haiku-4-5-20251001",
    ), ('messages',)),
    **dict.fromkeys((
        "gpt-6-astra",
        "gpt-6.1-sol",
        "gpt-6-sol",
        "gpt-6-luna",
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-5.5",
        "gpt-5.4",
        "gpt-5.3-codex",
        "gpt-5.4-mini",
        "deepseek/deepseek-v4-pro",
        "deepseek/deepseek-v4-flash",
        "deepseek/deepseek-v4-flash-vision-exp",
        "deepseek/deepseek-v4.1-flash",
        "deepseek/deepseek-v4.1-flash-fast",
        "moonshotai/Kimi-K3",
        "moonshotai/Kimi-K2.7-Code",
        "moonshotai/Kimi-K2.7-Code-Highspeed",
        "moonshotai/Kimi-K2.6",
        "moonshotai/Kimi-K2.5",
        "z-ai/glm-5.3-flash",
        "z-ai/glm-5.3-flashx",
        "zai-org/GLM-5.3",
        "zai-org/GLM-5.2",
        "zai-org/GLM-5.2-Fast",
        "zai-org/GLM-5.1",
        "zai-org/GLM-5",
        "MiniMaxAI/MiniMax-M3",
        "MiniMaxAI/MiniMax-M2.7",
        "MiniMaxAI/MiniMax-M2.5",
        "xiaomi/mimo-v2.6-pro",
        "xiaomi/mimo-v2.6-pro-ultraspeed",
        "xiaomi/mimo-v2.6-flash",
        "xiaomi/mimo-v2.5-pro",
        "xiaomi/mimo-v2.5",
        "Qwen/Qwen3.8-Omni-Flash",
        "Qwen/Qwen3.8-Max",
        "Qwen/Qwen3.8-27B",
        "Qwen/Qwen3.7-Max",
        "Qwen/Qwen3.7-Plus",
        "Qwen/Qwen3.7-Flash",
        "Qwen/Qwen3.6-Max-Preview",
        "Qwen/Qwen3.6-Plus",
        "stepfun/Step-5-Preview",
        "stepfun/Step-3.7-Flash",
        "stepfun/Step-3.5-Flash",
        "tencent/hy3-paid",
        "google/gemini-3.8-flash",
        "google/gemini-3.6-flash",
        "google/gemini-3.5-flash",
        "google/gemini-3.5-flash-lite",
        "google/gemini-3.1-flash-lite",
        "sakana/fugu-ultra",
        "nvidia/nemotron-3-ultra-550b-a55b",
        "thinkingmachines/inkling",
        "thinkingmachines/inkling-small",
        "poolside/laguna-s-2.1-free",
        "meta/muse-spark-1.1",
        "meta/muse-spark-1.2",
        "meta/muse-spark-1.2-contributor",
        "meta/muse-spark-1.3",
        "meta/muse-spark-1.3-contributor",
        "xai/grok-4.5",
        "xai/grok-4.6",
        "xai/grok-4.7",
    ), ('chat_completions', 'responses')),
    **dict.fromkeys((
        "deepseek/deepseek-v4-flash-fast",
        "Qwen/Qwen3.8-Max-0902",
        "Qwen/Qwen3.8-Flash",
        "meituan/LongCat-2.0",
        "tencent/hy4-preview",
        "google/gemini-3.7-flash",
        "stealth/space-bunny-alpha",
        "inclusionai/ling-3.0-flash-sante:free",
        "inclusionai/ling-3.1-flash:free",
    ), ('chat_completions',)),
}

# Match Command Code's official integration: GPT -> Responses, Claude ->
# Messages, other models -> Chat Completions. Every choice is catalog-checked.
COMMANDCODE_MODEL_APIS = {
    model: "messages" if "messages" in apis
    else "responses" if model.startswith("gpt-") and "responses" in apis
    else "chat_completions"
    for model, apis in COMMANDCODE_MODEL_ENDPOINTS.items()
}

COMMANDCODE_MODEL_OPTIONS = {
    "quick": [
        ("DeepSeek V4 Flash (Chat Completions)", "deepseek/deepseek-v4-flash"),
        ("GPT-6 Luna (Responses)", "gpt-6-luna"),
        ("Claude Haiku 4.5 (Messages)", "claude-haiku-4-5-20251001"),
        ("Gemini 3.8 Flash (Chat Completions)", "google/gemini-3.8-flash"),
        ("Custom model ID", "custom"),
    ],
    "deep": [
        ("Kimi K3 (Chat Completions)", "moonshotai/Kimi-K3"),
        ("DeepSeek V4 Pro (Chat Completions)", "deepseek/deepseek-v4-pro"),
        ("GPT-6.1 Sol (Responses)", "gpt-6.1-sol"),
        ("Claude Sonnet 5.5 (Messages)", "claude-sonnet-5-5"),
        ("Claude Opus 5.5 (Messages)", "claude-opus-5-5"),
        ("Custom model ID", "custom"),
    ],
}


def normalize_commandcode_model(model: str) -> str:
    """Preserve API ID spelling, including publisher namespace and case."""
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Command Code requires a nonempty model ID")
    return model.strip()


def resolve_commandcode_api(model: str, api: str = "auto") -> str:
    if not isinstance(api, str) or api not in COMMANDCODE_APIS | {"auto"}:
        raise ValueError("commandcode_api must be auto, chat_completions, responses or messages")
    model = normalize_commandcode_model(model)
    if api != "auto":
        supported = COMMANDCODE_MODEL_ENDPOINTS.get(model)
        if supported is not None and api not in supported:
            raise ValueError(f"Command Code model {model!r} supports {', '.join(supported)}, not {api}")
        return api
    if model not in COMMANDCODE_MODEL_APIS:
        raise ValueError(
            "Unknown Command Code model protocol. Check "
            "https://api.commandcode.ai/provider/v1/models and set commandcode_api / "
            "TRADINGAGENTS_COMMANDCODE_API explicitly for a new or custom model."
        )
    return COMMANDCODE_MODEL_APIS[model]


def resolve_commandcode_base_url(base_url: str | None, api: str) -> str:
    """Normalize the shared /v1 base for the SDK's native request paths."""
    if api not in COMMANDCODE_APIS:
        raise ValueError("Invalid Command Code API protocol")
    base = (base_url or COMMANDCODE_BASE_URL).rstrip("/")
    parsed = urlsplit(base)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise ValueError("Command Code backend_url must be an HTTP(S) base URL without credentials, query or fragment")
    if parsed.path.endswith(("/messages", "/responses", "/chat/completions", "/models", "/systemone")):
        raise ValueError("Command Code backend_url must be the API base, not a complete request endpoint")
    # Anthropic appends /v1/messages, whereas OpenAI appends /responses or
    # /chat/completions. Never produce /provider/v1/v1/messages.
    return base.removesuffix("/v1") if api == "messages" else base


class _CommandCodeChatMixin:
    """The gateway's Chat wire uses system roles and max_tokens.

    Mirrors the official Command Code integration's supportsDeveloperRole and
    maxTokensField compatibility flags; do not apply this to Responses.
    """

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        if "max_completion_tokens" in payload:
            payload["max_tokens"] = payload.pop("max_completion_tokens")
        for message in payload.get("messages", []):
            if message.get("role") == "developer":
                message["role"] = "system"
        return payload


class CommandCodeClient(BaseLLMClient):
    """Use Command Code credentials and the selected model's native protocol."""

    provider = "commandcode"

    def __init__(self, model: str, base_url: str | None = None, *, api="auto", **kwargs):
        super().__init__(normalize_commandcode_model(model), base_url, **kwargs)
        self.api = resolve_commandcode_api(self.model, api)
        self.base_url = resolve_commandcode_base_url(base_url, self.api)
        self.default_headers = parse_llm_headers(kwargs.get("default_headers"))

    def validate_model(self) -> bool:
        # An explicit protocol is the intentional escape hatch for future IDs.
        return self.api in COMMANDCODE_APIS

    def _isolate_sdk_credentials(self, llm):
        """Do not send another provider's ambient headers to this gateway.

        Both SDKs merge *_CUSTOM_HEADERS after construction even when a key
        is explicit. Replace that per-instance header store, preserving only
        the caller's requested headers. Never mutate the process environment.
        Older Anthropic SDKs also read AUTH_TOKEN alongside an explicit key.
        """
        clients = ((llm._client, llm._async_client) if self.api == "messages"
                   else (llm.root_client, llm.root_async_client))
        for client in clients:
            client._custom_headers = dict(self.default_headers)
            if self.api == "messages":
                client.auth_token = None
            else:
                client.organization = None
                client.project = None
                if hasattr(client, "admin_api_key"):
                    client.admin_api_key = None
        return llm

    def get_llm(self):
        env_var = get_api_key_env(self.provider)
        api_key = self.kwargs.get("api_key") or os.environ.get(env_var or "")
        if not api_key:
            raise ValueError("Set CMD_API_KEY or pass api_key for Command Code")
        common = {
            key: self.kwargs[key]
            for key in ("timeout", "max_retries", "temperature", "max_tokens",
                        "callbacks")
            if key in self.kwargs
        }
        common.update(model=self.model, base_url=self.base_url, api_key=api_key,
                      default_headers=dict(self.default_headers))
        if self.api == "messages":
            from .anthropic_client import NormalizedChatAnthropic, _supports_effort
            if self.kwargs.get("effort") and _supports_effort(self.model):
                common["effort"] = self.kwargs["effort"]
            llm = NormalizedChatAnthropic(anthropic_proxy="", **common)
            # ChatAnthropic has no http_client fields; forwarding them would
            # put Python client objects into the Messages request body. Apply
            # transports through the native SDK's supported copy interface.
            if "http_client" in self.kwargs:
                llm._client = llm._client.with_options(http_client=self.kwargs["http_client"])
            if "http_async_client" in self.kwargs:
                llm._async_client = llm._async_client.with_options(http_client=self.kwargs["http_async_client"])
            return self._isolate_sdk_credentials(llm)

        from .openai_client import (
            DeepSeekChatOpenAI,
            NormalizedChatOpenAI,
            _supports_reasoning_effort,
        )
        for key in ("http_client", "http_async_client"):
            if key in self.kwargs:
                common[key] = self.kwargs[key]
        # A direct provider's private proxy is unrelated to Command Code.
        # Generic HTTP(S)_PROXY still works through the underlying transport.
        common["openai_proxy"] = ""
        common["use_responses_api"] = self.api == "responses"
        if self.kwargs.get("reasoning_effort") and _supports_reasoning_effort(self.model):
            common["reasoning_effort"] = self.kwargs["reasoning_effort"]
        if self.api == "chat_completions":
            base = DeepSeekChatOpenAI if self.model.startswith("deepseek/") else NormalizedChatOpenAI

            # Keep imports lazy while combining gateway wire compatibility with
            # DeepSeek's reasoning_content round-trip when the model needs it.
            class CommandCodeChat(_CommandCodeChatMixin, base):
                pass

            return self._isolate_sdk_credentials(CommandCodeChat(**common))
        return self._isolate_sdk_credentials(NormalizedChatOpenAI(**common))
