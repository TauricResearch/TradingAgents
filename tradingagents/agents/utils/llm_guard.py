from __future__ import annotations

import contextvars
import logging
import queue
import threading
import time
from typing import Any

from tradingagents.default_config import DEFAULT_CONFIG

logger = logging.getLogger(__name__)

_TIER_DEFAULTS: dict[str, float] = {"quick": 300.0, "mid": 240.0, "deep": 360.0}


def resolve_timeout(tier: str) -> float:
    """Return the effective LLM timeout (seconds) for a given reasoning tier.

    Reads ``<tier>_think_llm_timeout_cap`` and ``<tier>_think_llm_timeout`` from
    ``DEFAULT_CONFIG``, falling back to ``llm_timeout`` and built-in defaults.
    The returned value is always capped at the tier cap.
    """
    raw_cap = DEFAULT_CONFIG.get(f"{tier}_think_llm_timeout_cap")
    cap = float(raw_cap if raw_cap is not None else _TIER_DEFAULTS.get(tier, 300.0))

    raw_timeout = DEFAULT_CONFIG.get(f"{tier}_think_llm_timeout")
    raw_global = DEFAULT_CONFIG.get("llm_timeout")
    if raw_timeout is not None:
        timeout = float(raw_timeout)
    elif raw_global is not None:
        timeout = float(raw_global)
    else:
        timeout = cap
    return min(timeout, cap)


def bind_max_tokens_if_supported(llm: Any, max_tokens: int | None = None) -> Any:
    bind_fn = getattr(llm, "bind", None)
    if max_tokens is None or not callable(bind_fn):
        return llm
    try:
        return bind_fn(max_tokens=max_tokens)
    except Exception:
        return llm


def _is_retryable_error(exc: Exception) -> bool:
    """Return True for transient LLM API errors worth retrying.

    Provider-agnostic: checks exception class names and message content
    so it works for OpenAI, xAI, OpenRouter, Ollama, and any other
    provider that routes through an OpenAI-compatible client.
    """
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    cls_name = type(exc).__name__
    if any(k in cls_name for k in ("Connection", "Timeout", "Network")):
        return True
    msg = str(exc).lower()
    return any(
        k in msg
        for k in (
            "json error",
            "injected into sse",
            "connection",
            "timeout",
            "timed out",
            "network",
            "stream",
        )
    )


def invoke_with_timeout(
    llm: Any,
    prompt_or_messages: Any,
    *,
    timeout_seconds: float,
    max_tokens: int | None = None,
    max_retries: int = 2,
) -> tuple[Any | None, Exception | None]:
    guarded_llm = bind_max_tokens_if_supported(llm, max_tokens=max_tokens)

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        if attempt > 0:
            delay = 2**attempt  # 2s, 4s
            logger.warning(
                "invoke_with_timeout: retrying after transient error (attempt %d/%d, delay=%ds): %s",
                attempt,
                max_retries,
                delay,
                last_error,
            )
            time.sleep(delay)

        result_queue: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)
        parent_context = contextvars.copy_context()

        def _runner(
            ctx: contextvars.Context = parent_context,
            llm_inst: Any = guarded_llm,
            msgs: Any = prompt_or_messages,
            q: queue.Queue[tuple[str, object]] = result_queue,
        ) -> None:
            try:
                result = ctx.run(llm_inst.invoke, msgs)
                q.put(("ok", result))
            except Exception as err:  # pragma: no cover - exercised through callers
                q.put(("err", err))

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join(timeout=max(1.0, float(timeout_seconds)))
        if thread.is_alive():
            return None, TimeoutError(f"llm invoke exceeded {timeout_seconds:.1f}s")

        try:
            status, payload = result_queue.get(timeout=1.0)
        except queue.Empty:
            return None, TimeoutError(
                f"llm invoke exceeded {timeout_seconds:.1f}s (queue empty after join)"
            )

        if status == "ok":
            return payload, None  # type: ignore[return-value]

        exc = payload  # type: ignore[assignment]
        if attempt < max_retries and _is_retryable_error(exc):  # type: ignore[arg-type]
            last_error = exc  # type: ignore[assignment]
            continue

        return None, exc  # type: ignore[return-value]

    return None, last_error


def truncate_text(value: Any, *, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 24].rstrip() + "\n...[truncated]"
