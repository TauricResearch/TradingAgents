from __future__ import annotations

import contextvars
import queue
import threading
from typing import Any


def bind_max_tokens_if_supported(llm: Any, max_tokens: int | None = None) -> Any:
    bind_fn = getattr(llm, "bind", None)
    if max_tokens is None or not callable(bind_fn):
        return llm
    try:
        return bind_fn(max_tokens=max_tokens)
    except Exception:
        return llm


def invoke_with_timeout(
    llm: Any,
    prompt_or_messages: Any,
    *,
    timeout_seconds: float,
    max_tokens: int | None = None,
) -> tuple[Any | None, Exception | None]:
    guarded_llm = bind_max_tokens_if_supported(llm, max_tokens=max_tokens)
    result_queue: "queue.Queue[tuple[str, object]]" = queue.Queue(maxsize=1)
    parent_context = contextvars.copy_context()

    def _runner() -> None:
        try:
            result = parent_context.run(guarded_llm.invoke, prompt_or_messages)
            result_queue.put(("ok", result))
        except Exception as exc:  # pragma: no cover - exercised through callers
            result_queue.put(("err", exc))

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join(timeout=max(1.0, float(timeout_seconds)))
    if thread.is_alive():
        return None, TimeoutError(f"llm invoke exceeded {timeout_seconds:.1f}s")

    try:
        status, payload = result_queue.get(timeout=1.0)
    except queue.Empty:
        return None, TimeoutError(f"llm invoke exceeded {timeout_seconds:.1f}s (queue empty after join)")
    if status == "err":
        return None, payload  # type: ignore[return-value]
    return payload, None


def truncate_text(value: Any, *, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 24].rstrip() + "\n...[truncated]"
