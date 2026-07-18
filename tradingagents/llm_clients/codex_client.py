"""ChatGPT subscription-backed OpenAI models via LangChain's Codex client."""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

logger = logging.getLogger(__name__)

# Rate-limit waits are budgeted separately from transport retries: a
# subscription quota window can take an hour to reset, and unattended runs
# should sleep through it rather than die.
RATE_LIMIT_MAX_WAITS = int(os.environ.get("TRADINGAGENTS_RATE_LIMIT_MAX_WAITS", "12"))
RATE_LIMIT_MAX_WAIT_SECONDS = float(
    os.environ.get("TRADINGAGENTS_RATE_LIMIT_MAX_WAIT_SECONDS", "3600")
)
_ESCALATING_WAITS = (60, 120, 300, 600, 900)

_DURATION_RE = re.compile(
    r"(?:try again|retry|resets?)[^0-9]*"
    r"(?:(\d+)\s*h(?:ours?)?)?\s*(?:(\d+)\s*m(?:in(?:utes?)?)?)?\s*(?:([\d.]+)\s*s(?:ec(?:onds?)?)?)?",
    re.IGNORECASE,
)


def _rate_limit_exceptions() -> tuple[type[BaseException], ...]:
    import openai

    return (openai.RateLimitError,)


def _retry_after_seconds(exc: BaseException) -> float | None:
    """Best-effort extraction of the reset delay from a rate-limit error."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or {}
    for key in ("retry-after", "x-ratelimit-reset-after", "x-ratelimit-reset-requests"):
        value = headers.get(key)
        if value:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    match = _DURATION_RE.search(str(exc))
    if match and any(match.groups()):
        hours, minutes, seconds = match.groups()
        return (
            float(hours or 0) * 3600 + float(minutes or 0) * 60 + float(seconds or 0)
        ) or None
    return None


def _stream_retryable_exceptions() -> tuple[type[BaseException], ...]:
    """Transport failures that can hit mid-stream, after the SDK's own
    ``max_retries`` no longer applies (the request succeeded; the SSE stream
    died halfway). Chat completions are stateless, so re-invoking is safe.
    """
    import httpx

    exceptions: list[type[BaseException]] = [httpx.TransportError]
    try:
        import openai

        exceptions += [openai.APIConnectionError, openai.APITimeoutError]
    except ImportError:
        pass
    return tuple(exceptions)

_PASSTHROUGH_KWARGS = (
    "timeout",
    "max_retries",
    "reasoning_effort",
    "temperature",
    "callbacks",
)


def _missing_chatgpt_token_error() -> FileNotFoundError:
    return FileNotFoundError(
        "No ChatGPT OAuth token found for provider 'openai_codex'. Run "
        "`python -c \"from langchain_openai.chatgpt_oauth import "
        "login_chatgpt; login_chatgpt()\"` once, or use "
        "`login_chatgpt_device()` on a headless machine. Tokens are "
        "stored by LangChain at ~/.langchain/chatgpt-auth.json."
    )


class OpenAICodexClient(BaseLLMClient):
    """Client for ChatGPT OAuth-backed Codex/OpenAI models.

    This provider intentionally uses LangChain's experimental
    ``_ChatOpenAICodex`` rather than reimplementing the ChatGPT OAuth and Codex
    backend wire protocol here. The class is private/upstream-experimental, so
    imports stay lazy and error messages are explicit.
    """

    provider = "openai_codex"

    def get_llm(self) -> Any:
        self.warn_if_unknown_model()
        if self.base_url:
            raise ValueError(
                "Provider 'openai_codex' uses the fixed ChatGPT Codex backend and "
                "does not accept backend_url / TRADINGAGENTS_LLM_BACKEND_URL."
            )

        try:
            from langchain_openai.chat_models.codex import _ChatOpenAICodex
        except (ImportError, ModuleNotFoundError) as exc:
            raise ImportError(
                "Provider 'openai_codex' requires LangChain's experimental "
                "ChatGPT OAuth Codex client. Upgrade with: "
                "pip install -U 'langchain-openai>=1.3.3' "
                "'langchain-core>=1.4.7' 'openai>=2.26.0'."
            ) from exc

        class NormalizedChatOpenAICodex(_ChatOpenAICodex):
            def _get_request_payload(self, input_, *, stop=None, **kwargs):
                try:
                    return super()._get_request_payload(input_, stop=stop, **kwargs)
                except FileNotFoundError as exc:
                    raise _missing_chatgpt_token_error() from exc

            def invoke(self, input, config=None, **kwargs):
                # Two failure modes are retried around the whole (stateless)
                # call, because the SDK's max_retries only covers request
                # setup:
                # - transport errors mid-stream (SSE dies half-way), with the
                #   SDK retry budget and short exponential backoff;
                # - rate limits / usage caps, with a separate budget and long
                #   waits (parsed reset delay when available), so unattended
                #   runs sleep through quota windows instead of dying.
                transport_retryable = _stream_retryable_exceptions()
                rate_limited = _rate_limit_exceptions()
                transport_attempts = max(1, int(getattr(self, "max_retries", None) or 2) + 1)
                transport_failures = 0
                rate_limit_waits = 0
                while True:
                    try:
                        return normalize_content(super().invoke(input, config, **kwargs))
                    except rate_limited as exc:
                        rate_limit_waits += 1
                        if rate_limit_waits > RATE_LIMIT_MAX_WAITS:
                            raise
                        wait = _retry_after_seconds(exc)
                        if wait is None:
                            wait = _ESCALATING_WAITS[
                                min(rate_limit_waits - 1, len(_ESCALATING_WAITS) - 1)
                            ]
                        wait = min(wait + 5, RATE_LIMIT_MAX_WAIT_SECONDS)  # +5s buffer
                        logger.warning(
                            "openai_codex rate limited (%s); sleeping %.0fs until reset "
                            "(wait %d/%d)",
                            exc,
                            wait,
                            rate_limit_waits,
                            RATE_LIMIT_MAX_WAITS,
                        )
                        time.sleep(wait)
                    except transport_retryable as exc:
                        transport_failures += 1
                        if transport_failures >= transport_attempts:
                            raise
                        delay = min(2 ** (transport_failures - 1), 30)
                        logger.warning(
                            "openai_codex stream failed mid-call (%s); retry %d/%d in %ds",
                            exc,
                            transport_failures,
                            transport_attempts - 1,
                            delay,
                        )
                        time.sleep(delay)

        llm_kwargs: dict[str, Any] = {
            "model": self.model,
            "originator": os.environ.get("TRADINGAGENTS_CODEX_ORIGINATOR")
            or "tradingagents",
        }

        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        try:
            return NormalizedChatOpenAICodex(**llm_kwargs)
        except FileNotFoundError as exc:
            raise _missing_chatgpt_token_error() from exc

    def validate_model(self) -> bool:
        return validate_model(self.provider, self.model)
