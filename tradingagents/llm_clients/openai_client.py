import os
from typing import Any, Optional

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from .api_key_env import get_api_key_env
from .base_client import BaseLLMClient, normalize_content
from .capabilities import get_capabilities
from .validators import validate_model


class NormalizedChatOpenAI(ChatOpenAI):
    """ChatOpenAI with normalized content output and capability-aware binding.

    The Responses API returns content as a list of typed blocks
    (reasoning, text, etc.). ``invoke`` normalizes to string for
    consistent downstream handling.

    ``with_structured_output`` consults the per-model capability table
    (``capabilities.get_capabilities``) to pick the method and to decide
    whether ``tool_choice`` may be sent. Models that reject ``tool_choice``
    (e.g. DeepSeek V4 and reasoner — per their official tool-calling
    guide) still bind the schema as a tool, but no ``tool_choice``
    parameter is sent.

    Provider-specific quirks beyond structured-output (e.g. DeepSeek's
    reasoning_content roundtrip) live in subclasses so this base class
    stays small.
    """

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))

    def with_structured_output(self, schema, *, method=None, **kwargs):
        caps = get_capabilities(self.model_name)
        if caps.preferred_structured_method == "none":
            raise NotImplementedError(
                f"{self.model_name} has no structured-output method available; "
                f"agent factories will fall back to free-text generation."
            )
        method = method or caps.preferred_structured_method
        # When the model rejects tool_choice, suppress langchain's hardcoded
        # value. The schema is still bound as a tool — exactly what
        # DeepSeek's official tool-calling examples do.
        if method == "function_calling" and not caps.supports_tool_choice:
            kwargs.setdefault("tool_choice", None)
        return super().with_structured_output(schema, method=method, **kwargs)


def _input_to_messages(input_: Any) -> list:
    """Normalise a langchain LLM input to a list of message objects.

    Accepts a list of messages, a ``ChatPromptValue`` (from a
    ChatPromptTemplate), or anything else (treated as no messages).
    Used by providers that need to walk the outgoing message history;
    in particular DeepSeek thinking-mode propagation must work for
    both bare-list invocations and ChatPromptTemplate-driven ones, so
    treating only ``list`` here would silently skip half the call sites.
    """
    if isinstance(input_, list):
        return input_
    if hasattr(input_, "to_messages"):
        return input_.to_messages()
    return []


class DeepSeekChatOpenAI(NormalizedChatOpenAI):
    """DeepSeek-specific overrides on top of the OpenAI-compatible client.

    Thinking-mode round-trip is the only DeepSeek-specific behavior that
    stays here. When DeepSeek's thinking models return a response with
    ``reasoning_content``, that field must be echoed back as part of the
    assistant message on the next turn or the API fails with HTTP 400.
    ``_create_chat_result`` captures it on receive and
    ``_get_request_payload`` re-attaches it on send.

    Tool-choice handling for V4 and reasoner — those models reject the
    ``tool_choice`` parameter — is handled by the capability dispatch in
    ``NormalizedChatOpenAI.with_structured_output``, not here.
    """

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        outgoing = payload.get("messages", [])
        for message_dict, message in zip(outgoing, _input_to_messages(input_)):
            if not isinstance(message, AIMessage):
                continue
            reasoning = message.additional_kwargs.get("reasoning_content")
            if reasoning is not None:
                message_dict["reasoning_content"] = reasoning
        return payload

    def _create_chat_result(self, response, generation_info=None):
        chat_result = super()._create_chat_result(response, generation_info)
        response_dict = (
            response
            if isinstance(response, dict)
            else response.model_dump(
                exclude={"choices": {"__all__": {"message": {"parsed"}}}}
            )
        )
        for generation, choice in zip(
            chat_result.generations, response_dict.get("choices", [])
        ):
            reasoning = choice.get("message", {}).get("reasoning_content")
            if reasoning is not None:
                generation.message.additional_kwargs["reasoning_content"] = reasoning
        return chat_result


class MinimaxChatOpenAI(NormalizedChatOpenAI):
    """MiniMax-specific overrides on top of the OpenAI-compatible client.

    M2.x reasoning models embed ``<think>...</think>`` blocks directly in
    ``message.content`` by default, which would pollute saved reports.
    Per platform.minimax.io/docs/api-reference/text-openai-api, setting
    ``reasoning_split=True`` in the request body redirects the thinking
    block into ``reasoning_details`` so ``content`` stays clean.

    The flag is gated by ``ModelCapabilities.requires_reasoning_split``
    because non-reasoning MiniMax endpoints (Coding Plan, MiniMax-Text-01)
    reject the parameter via the openai SDK's strict kwarg validation
    (#826).

    Tool-choice handling for M2.x — those models accept only the string
    enum ``{"none", "auto"}`` and reject langchain's function-spec dict —
    is handled by the capability dispatch in
    ``NormalizedChatOpenAI.with_structured_output``, not here.
    """

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        if get_capabilities(self.model_name).requires_reasoning_split:
            payload.setdefault("reasoning_split", True)
        return payload


def _install_codex_responses_output_shim() -> None:
    """Tolerate Codex ``response.completed`` events that omit ``output``.

    The ChatGPT-Codex backend streams text via ``response.output_text.delta``
    events and ends with a ``response.completed`` event that — unlike
    api.openai.com — carries NO ``output`` array. langchain's
    ``_construct_lc_result_from_responses_api`` does ``for output in
    response.output`` and raises ``TypeError: 'NoneType' object is not
    iterable``. We coerce a missing ``output`` to ``[]`` (the text has already
    been delivered by the deltas). This is a strict no-op for standard OpenAI
    responses — whose completed events always include ``output`` — so it is safe
    process-wide. Installed lazily (only when the OAuth path is built) and
    idempotently, so non-OAuth users are unaffected.
    """
    import langchain_openai.chat_models.base as _lc_base

    current = _lc_base._construct_lc_result_from_responses_api
    if getattr(current, "_codex_output_shim", False):
        return

    def shimmed(response, *args, **kwargs):
        if getattr(response, "output", None) is None:
            try:
                response.output = []
            except Exception:  # pragma: no cover - defensive
                pass
        return current(response, *args, **kwargs)

    shimmed._codex_output_shim = True
    _lc_base._construct_lc_result_from_responses_api = shimmed


class CodexChatOpenAI(NormalizedChatOpenAI):
    """ChatOpenAI for the ChatGPT-Codex backend (provider ``openai-oauth``).

    Rewrites the outgoing Responses payload to satisfy the Codex backend
    (store=false, stream=true, non-empty ``instructions``, system/developer
    messages hoisted out of ``input``, ``max_output_tokens`` stripped). Doing
    this in ``_get_request_payload`` — the single method langchain calls on
    both the sync and async paths before serialization — guarantees the
    constraints reach the wire, unlike an httpx event-hook.
    """

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        from .oauth import apply_codex_payload_constraints

        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        return apply_codex_payload_constraints(payload)


# Kwargs forwarded from user config to ChatOpenAI
_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "reasoning_effort",
    "api_key", "callbacks", "http_client", "http_async_client",
)

# Provider base URLs. API-key env vars live in api_key_env.PROVIDER_API_KEY_ENV
# (one canonical mapping consulted by both this client and the CLI's
# interactive key-prompt). Dual-region providers (qwen/glm/minimax) keep
# separate endpoints because international and China accounts cannot share
# credentials (#758).
_PROVIDER_BASE_URL = {
    "xai":        "https://api.x.ai/v1",
    "deepseek":   "https://api.deepseek.com",
    "qwen":       "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "qwen-cn":    "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "glm":        "https://api.z.ai/api/paas/v4/",
    "glm-cn":     "https://open.bigmodel.cn/api/paas/v4/",
    "minimax":    "https://api.minimax.io/v1",
    "minimax-cn": "https://api.minimaxi.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama":     "http://localhost:11434/v1",
}


def _resolve_provider_base_url(provider: str) -> Optional[str]:
    """Default base URL for ``provider``, with env-var overrides where defined.

    Currently only Ollama supports an env-var override (``OLLAMA_BASE_URL``),
    matching the convention in the broader Ollama tooling ecosystem so users
    can point at a remote ollama-serve without editing code. The check is
    call-time, not import-time, so tests that monkeypatch the env after
    import behave correctly.
    """
    if provider == "ollama":
        env_url = os.environ.get("OLLAMA_BASE_URL")
        if env_url:
            return env_url
    return _PROVIDER_BASE_URL.get(provider)


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
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        # ChatGPT OAuth (Codex backend): bearer OAuth + Responses API streaming.
        if self.provider == "openai-oauth":
            return self._build_oauth_llm(llm_kwargs)

        # Provider-specific base URL and auth. An explicit base_url on the
        # client (e.g. a corporate proxy) takes precedence over the
        # provider default so users can route through their own gateway.
        if self.provider in _PROVIDER_BASE_URL:
            llm_kwargs["base_url"] = self.base_url or _resolve_provider_base_url(self.provider)
            api_key_env = get_api_key_env(self.provider)
            if api_key_env:
                api_key = os.environ.get(api_key_env)
                if api_key:
                    llm_kwargs["api_key"] = api_key
                else:
                    raise ValueError(
                        f"API key for provider '{self.provider}' is not set. "
                        f"Please set the {api_key_env} environment variable "
                        f"(e.g. add {api_key_env}=your_key to your .env file)."
                    )
            else:
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

        # Provider-specific quirks live in their own subclasses so the
        # base NormalizedChatOpenAI stays free of provider branches.
        if self.provider == "deepseek":
            chat_cls = DeepSeekChatOpenAI
        elif self.provider in ("minimax", "minimax-cn"):
            chat_cls = MinimaxChatOpenAI
        else:
            chat_cls = NormalizedChatOpenAI
        return chat_cls(**llm_kwargs)

    def _build_oauth_llm(self, llm_kwargs: dict) -> Any:
        """Build a ChatOpenAI bound to the Codex ChatGPT backend via OAuth.

        Differences from the API-key path (all required by the backend, see
        docs/superpowers/specs):
        - base_url = chatgpt.com/backend-api/codex, path /responses;
        - auth via a custom httpx client (CodexOAuth) so the bearer is always
          fresh and a 401 triggers one refresh+retry;
        - the Responses payload is rewritten in CodexChatOpenAI to satisfy the
          backend: store=false, stream=true, non-empty ``instructions`` (the
          system prompt), system/developer messages hoisted out of ``input``
          (the backend 400s on "System messages are not allowed"), and
          ``max_output_tokens`` stripped. This happens in
          ``_get_request_payload`` so it works identically sync and async —
          unlike an httpx event-hook, which would not modify the sent
          ``request.stream`` and would crash the async path;
        - ``store=False`` / ``streaming=True`` are also set as native langchain
          params (langchain emits them into the payload); the payload rewrite
          is the guaranteeing layer and the only source of ``instructions``;
        - ChatGPT-Account-ID / originator (+ conditional fedramp/residency)
          default headers.
        """
        import httpx

        from .oauth import (
            CODEX_BASE_URL,
            CODEX_DEFAULT_HEADERS,
            CodexOAuth,
            OAuthTokenStore,
            ensure_token,
        )

        _install_codex_responses_output_shim()

        store = OAuthTokenStore()
        tokens = ensure_token(store)  # raises OAuthNotLoggedIn if absent

        auth = CodexOAuth(store)

        headers = dict(CODEX_DEFAULT_HEADERS)
        if tokens.account_id:
            headers["ChatGPT-Account-ID"] = tokens.account_id
        if tokens.is_fedramp:
            headers["X-OpenAI-Fedramp"] = "true"
        if tokens.residency:
            headers["x-openai-internal-codex-residency"] = tokens.residency

        llm_kwargs["base_url"] = self.base_url or CODEX_BASE_URL
        llm_kwargs["api_key"] = "oauth"  # placeholder; real auth via httpx
        llm_kwargs["use_responses_api"] = True
        llm_kwargs["streaming"] = True
        llm_kwargs["store"] = False
        llm_kwargs["default_headers"] = headers
        # No event_hooks: the body rewrite lives in CodexChatOpenAI so it works
        # on both sync and async paths and modifies the actually-sent payload.
        llm_kwargs["http_client"] = httpx.Client(auth=auth)
        llm_kwargs["http_async_client"] = httpx.AsyncClient(auth=auth)

        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs and key not in llm_kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return CodexChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for the provider."""
        return validate_model(self.provider, self.model)
